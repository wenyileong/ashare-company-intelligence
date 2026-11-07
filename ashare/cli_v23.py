"""Command-line commands added in v2.3.0, registered on the main application (``ashare.cli.app``).

Kept apart from ``cli.py`` so that the v2.3 commands can be read, switched off and fixed together. Each command whose
feature has a switch checks it first (``features.require``).
"""
from __future__ import annotations

import json

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
