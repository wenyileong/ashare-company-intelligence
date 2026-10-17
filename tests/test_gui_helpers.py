"""GUI logic that needs no display: argument building, form checks, and
consistency of every form with the CLI."""
import pytest

tk = pytest.importorskip("tkinter")


def test_build_argv_and_checks():
    from ashare.gui import build_argv, check_values, F
    fields = [F("since", "From", "date", "", "--since", required=True), F("code", "Code", "code", "", "--security-code"),
              F("dl", "Download", "bool", True, ("--download-documents", "--no-download-documents")),
              F("path", "File", "file", "", None)]
    assert build_argv("catalogue-disclosures", fields, {"since": "2026-01-01", "code": " ", "dl": False, "path": "a.csv"}) == \
        ["catalogue-disclosures", "--since", "2026-01-01", "--no-download-documents", "a.csv"]
    assert check_values(fields, {"since": "", "code": "60051X", "dl": True}) == [
        "From is required.", "Code must be a six-digit code."]
    assert check_values(fields, {"since": "2026/01/01"}) == ["From must be a date like 2026-01-31."]


def test_every_form_is_a_valid_cli_invocation(db):
    """Each GUI form, filled with defaults or placeholders, must parse as a CLI command."""
    from ashare.gui import SECTIONS, build_argv
    from ashare.cli import app
    import typer.main
    cmd = typer.main.get_command(app)
    n = 0
    for sec in SECTIONS:
        for action in sec["actions"]:
            values = {}
            for f in action["fields"]:
                if f["kind"] == "bool":
                    values[f["key"]] = f["default"]
                elif f["kind"].startswith("choice:"):
                    opts = f["kind"][7:].split(";") if ";" in f["kind"] else f["kind"][7:].split(",")
                    values[f["key"]] = f["default"] or opts[-1]
                else:
                    values[f["key"]] = f["default"] or {"year": "2025", "date": "2026-01-01", "code": "600519", "number": "1", "integer": "1"}.get(
                        f["kind"], "1" if f["key"] == "row_id" else "x")
            argv = build_argv(action["command"], action["fields"], values)
            sub = cmd.get_command(None, action["command"])
            assert sub is not None, action["command"]
            sub.make_context(action["command"], argv[1:])
            n += 1
    assert n >= 35


def test_run_command_captures_output(db):
    from ashare.gui import run_command, database_summary
    from ashare import __version__
    code, out = run_command(["version"])
    assert code == 0 and __version__ in out
    code, out = run_command(["show-company", "999999"])
    assert code == 0 and "No company found" in out
    assert run_command(["no-such-command"])[0] != 0
    assert database_summary()["Companies"] == 0
