"""Command-line commands added in v2.4.0, registered on the main application (``ashare.cli.app``), as for v2.3."""
from __future__ import annotations

import json

import typer


def register(app, _table) -> None:
    def _fail(exc: Exception) -> None:
        print(f"Stopped: {exc}")
        raise typer.Exit(1)

    PACK_HELP = "The rule pack: insider, deadlines or nominees"

    def _pack(name: str) -> str:
        from .rulepacks import PACKS
        n = (name or "").strip().lower()
        if n not in PACKS:
            _fail(ValueError(f"unknown rule pack '{name}'; the packs are {', '.join(PACKS)}"))
        return n

    # --- Part A: swappable rule packs ----------------------------------------------------------------------------

    @app.command("rules-list")
    def rules_list_cmd():
        """The rule packs: which version is in use, where it comes from and how many rules are provisional
        (v2.4.0; swappable packs)."""
        from .rulepacks import listing
        rows = listing()
        _table(rows, ["pack", "version", "status", "in_use", "rules", "provisional", "confirmed"],
               title="Rule packs (swappable)")
        for r in rows:
            if r["problem"]:
                print(f"{r['pack']}: the updated pack in the data folder was not used: {r['problem']}")
        print("Each pack can be updated without a new version: rules-export, edit, rules-check, rules-import --apply.")

    @app.command("rules-show")
    def rules_show_cmd(pack: str = typer.Argument(..., help=PACK_HELP),
                       as_json: bool = typer.Option(False, "--json", help="The whole pack as JSON")):
        """The rules of a pack, with each rule's status and source (v2.4.0)."""
        from .rulepacks import load, rule_status
        pk = load(_pack(pack))
        if as_json:
            print(json.dumps(pk.data, ensure_ascii=False, indent=2))
            return
        print(pk.describe())
        if pk.rules:
            rows = []
            for r in pk.rules:
                n = r.get("trading_days") or r.get("months_after_period_end") or ", ".join(
                    f"{w['before']} {w['calendar_days']}d" for w in r.get("windows", []))
                rows.append({"id": r.get("id"), "status": rule_status(r), "value": n,
                             "effective_from": r.get("effective_from") or "", "source": r.get("source", "")})
            _table(rows, ["id", "status", "value", "effective_from", "source"], title=f"Rules: {pk.name}")
        else:
            print(f"{len(pk.data.get('names', [])):,} names")

    @app.command("rules-export")
    def rules_export_cmd(pack: str = typer.Argument(..., help=PACK_HELP),
                         out: str = typer.Option(None, "--out", help="A file or folder; blank: the data folder's rules "
                                                                     "folder, where the copy becomes the pack in use"),
                         force: bool = typer.Option(False, "--force", help="Overwrite (the old pack is kept)")):
        """Copy a rule pack for editing (v2.4.0)."""
        from .rulepacks import export, PackError
        try:
            r = export(_pack(pack), out or None, force)
        except PackError as exc:
            _fail(exc)
        print(f"Written: {r['written']} ({r['pack']} {r['version']}, from the {r['from']} pack)")
        print("Edit it, then check it with rules-check" + ("" if out else "; it is already the pack in use") + ".")

    @app.command("rules-check")
    def rules_check_cmd(pack: str = typer.Argument(..., help=PACK_HELP),
                        file: str = typer.Option(None, "--file", help="A file to check; blank: the pack in use")):
        """Check a rule pack: its fields, numbers, dates and statuses (v2.4.0)."""
        from .rulepacks import check
        r = check(_pack(pack), file or None)
        print(f"{r['file']}: {'valid' if r['ok'] else 'NOT VALID'}"
              + (f" ({r.get('version')}; {r.get('status')})" if r["ok"] else ""))
        for e in r["errors"]:
            print(f"  error: {e}")
        for w in r["warnings"]:
            print(f"  warning: {w}")
        if r.get("fallback"):
            print(f"  the updated pack in the data folder was not used: {r['fallback']}")
        if not r["ok"]:
            raise typer.Exit(1)

    @app.command("rules-import")
    def rules_import_cmd(pack: str = typer.Argument(..., help=PACK_HELP),
                         file: str = typer.Argument(..., help="The edited pack"),
                         apply: bool = typer.Option(False, "--apply", help="Install it; without it, only checks it")):
        """Install an updated rule pack after checking it; the pack it replaces is kept (v2.4.0)."""
        from .rulepacks import import_pack
        r = import_pack(_pack(pack), file, apply)
        print(f"{file}: {'valid' if r['ok'] else 'NOT VALID'}")
        for e in r["errors"]:
            print(f"  error: {e}")
        for w in r["warnings"]:
            print(f"  warning: {w}")
        if not r["ok"]:
            raise typer.Exit(1)
        print(f"In use now: {r['replaces']}")
        if r["applied"]:
            print(f"Installed. In use from the next action: {r['now']}")
            if r.get("kept"):
                print(f"The pack it replaced is kept: {r['kept']}")
        else:
            print("Not installed: add --apply to install it.")

    @app.command("rules-reset")
    def rules_reset_cmd(pack: str = typer.Argument(..., help=PACK_HELP),
                        apply: bool = typer.Option(False, "--apply", help="Return to the bundled pack")):
        """Return to the rule pack shipped with the program; the updated one is kept (v2.4.0)."""
        from .rulepacks import reset
        r = reset(_pack(pack), apply)
        if not r["override"]:
            print("The pack shipped with the program is already in use.")
        elif r["applied"]:
            print(f"Returned to the bundled pack: {r['now']}. The updated pack is kept: {r['kept']}")
        else:
            print(f"An updated pack is in use ({r['override']}); add --apply to return to the bundled pack.")
