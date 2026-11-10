"""Command-line commands added in v2.3.0, registered on the main application (``ashare.cli.app``).

Kept apart from ``cli.py`` so that the v2.3 commands can be read, switched off and fixed together. Each command whose
feature has a switch checks it first (``features.require``).
"""
from __future__ import annotations

import json
from pathlib import Path

import typer



def register(app, _table) -> None:
    """Add the v2.3 commands to ``app`` (called by ``ashare.cli`` with its own application, so the commands are also
    there when the module runs as ``python -m ashare.cli``)."""
    def _fail(exc: Exception) -> None:
        print(f"Stopped: {exc}")
        raise typer.Exit(1)


    @app.command("features")
    def features_cmd(on: str = typer.Option(None, "--on", help="Switch a feature on, by name"),
                     off: str = typer.Option(None, "--off", help="Switch a feature off, by name")):
        """The v2.3 feature switches: list them, or switch one on or off (v2.3.0)."""
        from . import features
        try:
            if on:
                features.set_feature(on, True)
            if off:
                features.set_feature(off, False)
        except KeyError as exc:
            _fail(exc)
        rows = [{**r, "on": "on" if r["on"] else "off", "default": "on" if r["default"] else "off"}
                for r in features.status()]
        _table(rows, ["name", "on", "default", "source", "part", "title"], title="Feature switches")
        print("Switching a feature off never deletes its data.")


    @app.command("diagnostics")
    def diagnostics_cmd(as_json: bool = typer.Option(False, "--json")):
        """The data folder, the schema revision and the feature switches (v2.3.0)."""
        from . import features
        d = features.diagnostics()
        if as_json:
            print(json.dumps(d, ensure_ascii=False, indent=2))
            return
        print(f"Version {d['version']}; data folder {d['data_root']}")
        sch = d.get("schema") or {}
        if "error" in sch:
            print(f"Schema: could not be read ({sch['error']})")
        else:
            print(f"Schema: {sch.get('current')} (head {sch.get('head')})")
        _table([{**r, "on": "on" if r["on"] else "off"} for r in d["features"]], ["name", "on", "source", "part"],
               title="Feature switches")
        if d.get("rule_packs"):
            _table(d["rule_packs"], ["pack", "version", "status", "in_use", "problem"], title="Rule packs (swappable)")


    @app.command("paths-report")
    def paths_report_cmd(no_files: bool = typer.Option(False, "--no-files", help="Skip checking each file"),
                         as_json: bool = typer.Option(False, "--json")):
        """Stored paths by form, files present, missing or recoverable after a move, caches and free space (v2.3.0;
        read-only)."""
        from .datafolder import paths_report
        r = paths_report(check_files=not no_files)
        if as_json:
            print(json.dumps(r, ensure_ascii=False, indent=2))
            return
        print(f"Data folder: {r['data_root']}")
        rows = []
        for label, t in r["tables"].items():
            f = t["forms"]
            rows.append({"stored": label, "relative": f.get("relative", 0), "inside (absolute)": f.get("inside", 0),
                         "outside (absolute)": f.get("outside", 0), "present": t["files"].get("present", ""),
                         "recoverable": t["files"].get("recoverable", ""), "missing": t["files"].get("missing", "")})
        _table(rows, ["stored", "relative", "inside (absolute)", "outside (absolute)", "present", "recoverable",
                      "missing"], title="Stored paths")
        c = r["caches"]
        print(f"Section indexes: {c['section_indexes']:,} ({c['mb']:,.1f} MB)")
        if r.get("disk"):
            print(f"Free space: {r['disk']['free_gb']:,.1f} GB of {r['disk']['total_gb']:,.1f} GB")
        if r.get("outputs"):
            o = r["outputs"]
            print(f"Outputs: {o['inside']:,} inside the data folder (move with it), {o['outside']:,} elsewhere "
                  "(do not move)")
        print("'recoverable': the stored path is gone but the file was found under the current folder with a matching "
              "hash. Nothing has been changed.")

    @app.command("not-read")
    def not_read_cmd(job: str = typer.Option(None, "--job", help="An extractor (financials, control, top_holders ...) or "
                                                                  "market_prices; blank for all"),
                     limit: int = typer.Option(200, help="Rows to list")):
        """Documents (and companies) whose latest attempt did not succeed, and why (v2.3.0, Files > Documents not
        read)."""
        from .ledger import not_read
        r = not_read(job or None, limit=max(limit, 1))
        if not r["summary"]:
            print("Nothing is recorded as not read. (The record starts with v2.3; runs before it are not listed.)")
            return
        _table(r["summary"], ["job", "reason", "meaning", "documents"], title="Not read, by reason")
        _table(r["rows"][:limit], ["job", "reason", "item", "code", "date", "title", "detail"], title="Examples")

    # --- B1 phases 4 and 5: the data folder -------------------------------------------------------------------

    def _guard(fn, *a, **k):
        from .features import FeatureOff
        try:
            return fn(*a, **k)
        except (FeatureOff, RuntimeError) as exc:
            _fail(exc)

    @app.command("paths-normalise")
    def paths_normalise_cmd(apply: bool = typer.Option(False, "--apply", help="Rewrite (after a backup); without it, "
                                                                               "a preview"),
                            confirm_other_database: bool = typer.Option(False, "--confirm-dumped",
                                                                         help="For PostgreSQL: you have made a dump")):
        """Rewrite stored paths relative to the data folder; every change is recorded and can be undone (v2.3.0)."""
        from .datafolder import normalise_paths
        r = _guard(normalise_paths, apply=apply, confirm_other_database=confirm_other_database)
        print({k: v for k, v in r.items() if k not in ("examples", "note")})
        if r.get("examples"):
            _table(r["examples"], ["table", "old", "new"], title="Examples")
        print(r.get("note", ""))

    @app.command("paths-undo")
    def paths_undo_cmd(run_id: str = typer.Argument(None, help="The run to undo (see 'paths-runs')")):
        """Restore the stored paths a normalising run or a move changed (v2.3.0)."""
        from .datafolder import undo_paths, rewrite_runs
        if not run_id:
            _table(rewrite_runs(), ["run_id", "changes", "when", "undone"], title="Path rewrites")
            return
        print(undo_paths(run_id))

    @app.command("paths-runs")
    def paths_runs_cmd():
        """The normalising runs and moves recorded, with their changes (v2.3.0)."""
        from .datafolder import rewrite_runs
        _table(rewrite_runs(), ["run_id", "changes", "when", "undone"], title="Path rewrites")

    @app.command("move-data-folder")
    def move_data_folder_cmd(target: str = typer.Argument(..., help="The new data folder (empty or not yet made)"),
                             apply: bool = typer.Option(False, "--apply", help="Move; without it, a dry run")):
        """Move the data folder: a dry run first; then rename (same drive) or copy and verify, rewrite the stored
        paths, switch the setting and re-create the scheduled update (v2.3.0). After a copy the old folder is left
        untouched."""
        from .datafolder import move_data_folder
        r = _guard(move_data_folder, target, apply=apply, progress=lambda m: print(m, flush=True))
        print(f"From {r['from']}\nTo   {r['to']}\n{r['files']:,} files, {r['gb']:,.2f} GB; method: {r['method']}"
              + (f"; free on the target: {r['free_gb']:,.1f} GB" if r.get("free_gb") is not None else ""))
        for p in r.get("problems", []):
            print(f"[red]Problem: {p}[/red]")
        for w in r.get("warnings", []):
            print(f"[yellow]Warning: {w}[/yellow]")
        if r.get("applied"):
            print(f"Paths rewritten: {r.get('paths_rewritten', 0):,} (undo: paths-undo {r.get('undo_run')})")
            if r.get("schedule"):
                print(f"Scheduled update: {r['schedule']}")
            print(f"Data folder now: {r['to']}")
        print(r.get("note", ""))

    @app.command("adopt-data-folder")
    def adopt_data_folder_cmd(folder: str = typer.Argument(..., help="A data folder already moved or restored"),
                              apply: bool = typer.Option(False, "--apply", help="Switch to it; without it, a check")):
        """Use a data folder already moved or restored (for example after reinstalling Windows): checks it, then
        switches to it (v2.3.0)."""
        from .datafolder import adopt_data_folder
        r = _guard(adopt_data_folder, folder, apply=apply)
        if "report" in r:
            for label, t in r["report"]["tables"].items():
                print(f"{label}: {t['forms']} {t['files']}")
            sm = r["sample"]
            print(f"Sample of documents: {sm['checked']} checked, {sm['ok']} match, {sm['mismatched']} differ, "
                  f"{sm['missing']} missing")
        if r.get("applied"):
            print(f"Data folder now: {r['folder']}")
        print(r.get("note", ""))

    def _number(text: str) -> int:
        try:
            return int(str(text).strip())
        except ValueError:
            _fail(ValueError(f"not a whole number: {text!r}"))

    # --- B11: the outputs register -------------------------------------------------------------------------------

    @app.command("outputs")
    def outputs_cmd(kind: str = typer.Option(None, "--kind", help="view, topology, panel, event_study, release, "
                                                                   "export, files_export, chart, query"),
                    removed: bool = typer.Option(False, "--removed", help="Include removed outputs")):
        """Every output the program wrote, by kind and date, with its place and size (v2.3.0)."""
        from .outputs import list_outputs, disk_use
        from .features import enabled
        if not enabled("outputs.register"):
            _fail(RuntimeError("the outputs register is switched off (features --on outputs.register)"))
        rows = list_outputs(kind or None, removed)
        _table(rows[:500], ["id", "kind", "created", "status", "files", "mb", "inside_data_folder", "path"],
               title="Outputs")
        _table(disk_use(), ["category", "files", "mb", "path"], title="Disk use")
        print("Outputs made before v2.3 can be added with 'outputs-scan'.")

    @app.command("outputs-check")
    def outputs_check_cmd(output_id: str = typer.Argument(..., help="The output's number (see 'outputs')")):
        """An output against its manifest: each listed file present, with the hash recorded (v2.3.0)."""
        from .outputs import check_output
        print(check_output(_number(output_id)))

    @app.command("outputs-remove")
    def outputs_remove_cmd(output_id: str = typer.Argument(..., help="The output's number (see 'outputs')"),
                           apply: bool = typer.Option(False, "--apply", help="Remove; without it, a preview")):
        """Remove an output's files (preview first); its record is kept, marked removed (v2.3.0)."""
        from .outputs import remove_output
        print(remove_output(_number(output_id), apply))

    @app.command("outputs-scan")
    def outputs_scan_cmd(folder: str = typer.Option(None, "--folder", help="Blank: the usual output folders"),
                         apply: bool = typer.Option(False, "--apply", help="Record them; without it, a preview")):
        """Find outputs made before v2.3 by their manifests and add them to the register (v2.3.0)."""
        from .outputs import scan_outputs
        r = scan_outputs(folder or None, apply)
        print({k: v for k, v in r.items() if k != "rows"})
        _table(r["rows"][:200], ["kind", "path", "manifest"], title="Found")

    # --- B5: disclosure timeliness ---------------------------------------------------------------------------------

    @app.command("timeliness")
    def timeliness_cmd(code: str = typer.Option(None, "--code", "--security-code", help="Blank for every company"),
                       year: str = typer.Option(None, "--year", help="Reporting year, e.g. 2024"),
                       as_of: str = typer.Option(None, "--as-of", help="Only reports published by this date"),
                       out: str = typer.Option("exports/timeliness.csv", "--out")):
        """Periodic reports against their legal deadlines: days from the period end, the deadline, late or not
        (v2.3.0; the rules and their sources are in rules/disclosure_deadlines.json)."""
        from .timeliness import timeliness
        r = _guard(timeliness, code or None, _number(year) if year else None, as_of or None, out)
        sm = r["summary"]
        print(f"{sm['reports']:,} reports; {sm['with_a_deadline']:,} with a deadline; {sm['late']:,} late "
              f"(rules {sm['rules']})")
        print(sm["note"])
        late = [x for x in r["rows"] if x["late"]]
        if late:
            _table(late[:200], ["code", "kind", "period", "published", "deadline", "days_late", "title"],
                   title="Late reports")
        if sm.get("file"):
            print(f"Written: {sm['file']}")
            from .outputs import record_output
            record_output("export", sm["file"], "timeliness", {"code": code, "year": year, "as_of": as_of})

    # --- B6: directors' and officers' share dealings (experimental) -------------------------------------------

    @app.command("extract-insider-dealings")
    def extract_insider_cmd(code: str = typer.Option(None, "--code", "--security-code", help="Blank for every company")):
        """Read directors', supervisors' and senior managers' share dealings from their announcements (v2.3.0;
        experimental: switch 'insider' on first)."""
        from .insider import extract_dealings
        print(_guard(extract_dealings, code or None, progress=lambda m: print(m, flush=True)))

    @app.command("insider-flags")
    def insider_flags_cmd(code: str = typer.Option(None, "--code", "--security-code"),
                          confirmed_only: bool = typer.Option(False, "--confirmed-only",
                                                              help="Apply only the rules confirmed by the author")):
        """Each dealing with the flags of the rules applied: provisional rules (flags marked so) and confirmed ones
        (v2.3.0; v2.4.0 applies the swappable rule pack; experimental)."""
        from .insider import flags
        r = _guard(flags, code or None, confirmed_only)
        _table(r["rows"][:500], ["code", "deal_date", "direction", "shares", "published", "flags"],
               title="Share dealings")
        print(r["note"])

    # --- B7: entity identifiers from GLEIF ---------------------------------------------------------------------

    @app.command("gleif-match")
    def gleif_match_cmd(names: bool = typer.Option(False, "--names", help="Also look up by name (candidates for "
                                                                          "review)"),
                        limit: str = typer.Option(None, "--limit", help="At most this many entities")):
        """Look up Legal Entity Identifiers at GLEIF: accepted when the credit code matches exactly, candidates by
        name; then GLEIF's direct and ultimate parents (v2.3.0; switch 'gleif' on first)."""
        from .gleif import match_entities
        print(_guard(match_entities, names, _number(limit) if limit else None,
                     progress=lambda m: print(m, flush=True)))

    @app.command("gleif-candidates")
    def gleif_candidates_cmd():
        """LEIs matched by name, waiting for a decision (v2.3.0)."""
        from .gleif import candidates
        _table(candidates(), ["id", "entity", "credit_code", "lei", "gleif_name", "registered_as", "jurisdiction"],
               title="Candidates")

    @app.command("gleif-decide")
    def gleif_decide_cmd(identifier_id: str = typer.Argument(..., help="The candidate's number"),
                         decision: str = typer.Argument(..., help="accept or reject")):
        """Accept or reject an LEI candidate (v2.3.0)."""
        from .gleif import decide
        if decision.lower() not in ("accept", "reject"):
            _fail(ValueError("the decision is 'accept' or 'reject'"))
        print(decide(_number(identifier_id), decision.lower() == "accept"))

    # --- B9: watchlists and alerts -------------------------------------------------------------------------------

    @app.command("watch-add")
    def watch_add_cmd(name: str = typer.Argument(..., help="A name for the watchlist"),
                      codes: str = typer.Option(..., "--codes", help="Comma-separated codes"),
                      kinds: str = typer.Option("regulatory,guidance,controller_change,late_report", "--kinds",
                                                help="announcement, regulatory, guidance, controller_change, "
                                                     "late_report, insider")):
        """Create or change a watchlist (v2.3.0). Its first run records what is already there."""
        from .watch import add_watchlist
        try:
            print(_guard(add_watchlist, name, codes, kinds))
        except ValueError as exc:
            _fail(exc)

    @app.command("watch-run")
    def watch_run_cmd(name: str = typer.Argument(None, help="Blank for every watchlist"),
                      out: str = typer.Option("exports/alerts.csv", "--out")):
        """Run the watchlists: the new items since the last run (v2.3.0). The daily update runs them too."""
        from .watch import run_watchlists
        r = _guard(run_watchlists, name or None)
        print(f"{r['watchlists']} watchlist(s); {len(r['new'])} new item(s)")
        if r["new"]:
            _table(r["new"][:300], ["watchlist", "kind", "code", "date", "title"], title="New")
            import csv
            p = Path(out)
            p.parent.mkdir(parents=True, exist_ok=True)
            with p.open("w", encoding="utf-8-sig", newline="") as fh:
                w = csv.DictWriter(fh, fieldnames=["watchlist", "kind", "code", "date", "title"])
                w.writeheader()
                w.writerows(r["new"])
            print(f"Written: {p}")

    @app.command("alerts")
    def alerts_cmd(all_: bool = typer.Option(False, "--all", help="Include alerts already seen"),
                   mark_seen: bool = typer.Option(False, "--mark-seen", help="Mark the listed alerts as seen")):
        """The alerts from the watchlists (v2.3.0)."""
        from .watch import alerts
        rows = alerts(not all_, mark_seen)
        _table(rows[:500], ["id", "watchlist", "kind", "code", "date", "title"], title="Alerts")
