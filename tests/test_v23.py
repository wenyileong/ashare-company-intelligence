"""v2.3.0: tests named after the plan's parts (docs/plan_v2.3.md)."""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest


# --- Scaffolding: feature switches --------------------------------------------------------------------------------

def test_feature_switches_have_defaults_settings_and_overrides(tmp_path, monkeypatch):
    from ashare import features
    monkeypatch.delenv("ASHARE_FEATURES", raising=False)
    assert features.enabled("outputs.register") is True and features.enabled("gleif") is False
    features.set_feature("outputs.register", False)
    assert features.enabled("outputs.register") is False
    assert json.loads((tmp_path / "features.json").read_text())["outputs.register"] is False
    monkeypatch.setenv("ASHARE_FEATURES", "outputs.register=on,gleif=on")
    assert features.enabled("outputs.register") and features.enabled("gleif")
    monkeypatch.setenv("ASHARE_FEATURES", "all=off")
    assert not any(r["on"] for r in features.status())
    with pytest.raises(features.FeatureOff):
        features.require("timeliness")
    with pytest.raises(KeyError):
        features.enabled("no.such.feature")


def test_a_damaged_switch_file_falls_back_to_the_defaults(tmp_path, monkeypatch):
    from ashare import features
    monkeypatch.delenv("ASHARE_FEATURES", raising=False)
    (tmp_path / "features.json").write_text("{not json", encoding="utf-8")
    assert features.enabled("timeliness") is True


def test_the_features_and_diagnostics_commands(tmp_path, monkeypatch):
    from typer.testing import CliRunner
    from ashare.cli import app
    monkeypatch.delenv("ASHARE_FEATURES", raising=False)
    r = CliRunner().invoke(app, ["features", "--off", "watchlists"])
    assert r.exit_code == 0, r.output
    assert "watchlists" in r.output and "never deletes" in r.output
    r = CliRunner().invoke(app, ["diagnostics", "--json"])
    assert r.exit_code == 0, r.output
    d = json.loads(r.output)
    assert d["data_root"] == str(tmp_path.resolve())
    assert {"name": "watchlists", "on": False} .items() <= next(x for x in d["features"] if x["name"] == "watchlists").items()
    r = CliRunner().invoke(app, ["features", "--on", "nonsense"])
    assert r.exit_code == 1


# --- B1 phases 0 to 3: the path accessor, tolerant reads, relative writes ------------------------------------------

def test_no_module_builds_a_path_from_a_stored_column_directly():
    import re
    root = Path(__file__).resolve().parents[1] / "ashare"
    bad = []
    for p in root.rglob("*.py"):
        if p.name in ("storepaths.py", "datafolder.py", "models.py"):
            continue
        text = p.read_text(encoding="utf-8")
        for m in re.finditer(r"Path\([^)]*\.(local_path|payload_path)\b|Path\(\w+\[\"payload_path\"\]\)", text):
            bad.append(f"{p.name}: {m.group(0)}")
    assert bad == []


def _doc(folder: Path, code="600519", content=b"%PDF-1.4 test"):
    import hashlib
    sha = hashlib.sha256(content).hexdigest()
    p = folder / code / f"{sha}.pdf"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(content)
    return p, sha


def test_stored_paths_resolve_after_the_folder_moves(tmp_path):
    from ashare import storepaths as sp
    sp.clear_cache()
    p, sha = _doc(tmp_path / "disclosures")
    assert sp.resolve_stored(str(p), sha) == p                                  # absolute, present
    rel = p.relative_to(tmp_path).as_posix()
    assert sp.resolve_stored(rel, sha) == tmp_path / rel                         # relative to the data root
    old = f"/old/machine/AShareScraper/disclosures/600519/{p.name}"
    assert sp.resolve_stored(old, sha) == p.resolve()                           # moved: found by its tail
    win = "C:\\Users\\User\\Documents\\AShareScraper\\disclosures\\600519\\" + p.name
    assert sp.resolve_stored(win, sha) == p.resolve()                           # written on Windows
    assert sp.recovery_stats()["recovered"] == 2
    gone = "/old/machine/AShareScraper/disclosures/600519/" + "0" * 64 + ".pdf"
    assert sp.resolve_stored(gone, "0" * 64) == Path(gone)                       # unresolved: unchanged
    assert sp.resolve_stored(None) is None and sp.resolve_stored("") is None


def test_a_recovered_file_must_match_its_hash(tmp_path):
    from ashare import storepaths as sp
    sp.clear_cache()
    named = tmp_path / "disclosures" / "600519" / "report.pdf"
    named.parent.mkdir(parents=True)
    named.write_bytes(b"other content")
    old = "/old/disclosures/600519/report.pdf"
    assert sp.resolve_stored(old, "f" * 64) == Path(old)                         # hash differs: refused
    assert sp.recovery_stats()["refused"] == 1


def test_new_paths_are_stored_relative_unless_switched_off(tmp_path, monkeypatch):
    from ashare import storepaths as sp
    p, _ = _doc(tmp_path / "disclosures")
    monkeypatch.delenv("ASHARE_FEATURES", raising=False)
    assert sp.to_stored(p) == p.relative_to(tmp_path).as_posix()
    monkeypatch.setenv("ASHARE_FEATURES", "storage.relative_paths=off")
    assert sp.to_stored(p) == str(p)
    outside = Path("/elsewhere/file.pdf")
    monkeypatch.delenv("ASHARE_FEATURES")
    assert sp.to_stored(outside) == str(outside)


def test_archived_responses_are_stored_relative_and_read_back(db, tmp_path, monkeypatch):
    from ashare.storage import store_raw
    from ashare.models import SessionLocal, RawRecord
    from ashare.storepaths import raw_path
    monkeypatch.delenv("ASHARE_FEATURES", raising=False)
    r = store_raw("TEST", "http://example/x", {"a": 1}, {"content_type": "application/json"})
    assert not Path(r["payload_path"]).is_absolute() and r["payload_path"].startswith("raw/")
    s = SessionLocal()
    row = s.query(RawRecord).one()
    assert raw_path(row.payload_path, row.sha256).read_text(encoding="utf-8") == '{"a": 1}'
    s.close()


def test_a_document_stored_on_another_machine_is_read_and_counted(db, company, tmp_path):
    from ashare.models import SessionLocal, Disclosure
    from ashare.storepaths import document_path, has_document
    from ashare.datafolder import paths_report
    p, sha = _doc(tmp_path / "disclosures")
    s = SessionLocal()
    s.add_all([Disclosure(company_id=company.id, announcement_id="A1", title_cn="t", kind="annual_report",
                          local_path="C:\\Users\\User\\AShareScraper\\disclosures\\600519\\" + p.name, sha256=sha),
               Disclosure(company_id=company.id, announcement_id="A2", title_cn="t", kind="annual_report",
                          local_path=p.relative_to(tmp_path).as_posix(), sha256=sha),
               Disclosure(company_id=company.id, announcement_id="A3", title_cn="t", kind="annual_report",
                          local_path="/gone/disclosures/600519/" + "1" * 64 + ".pdf", sha256="1" * 64)])
    s.commit()
    d1, d2, d3 = s.query(Disclosure).order_by(Disclosure.id).all()
    assert has_document(d1) and has_document(d2) and not has_document(d3)
    assert document_path(d1).read_bytes() == p.read_bytes()
    s.close()
    r = paths_report()
    t = r["tables"]["documents"]
    assert t["forms"] == {"outside": 2, "relative": 1}
    assert t["files"] == {"recoverable": 1, "present": 1, "missing": 1}


def test_the_section_index_survives_a_move(tmp_path):
    from helpers import make_pdf
    import hashlib
    from ashare.reportreader import ReportReader
    from ashare.config import disclosure_dir
    a = tmp_path / "a.pdf"
    make_pdf(a, ["合并资产负债表", "资产总计 100"])
    sha = hashlib.sha256(a.read_bytes()).hexdigest()
    first = tmp_path / "one" / f"{sha}.pdf"
    first.parent.mkdir()
    a.rename(first)
    ReportReader(first).index()
    cached = list((disclosure_dir() / ".section_index").glob("*.json"))
    assert len(cached) == 1
    moved = tmp_path / "two" / f"{sha}.pdf"
    moved.parent.mkdir()
    first.rename(moved)
    r = ReportReader(moved)
    r.index()
    assert len(list((disclosure_dir() / ".section_index").glob("*.json"))) == 1     # read, not rebuilt


def test_the_paths_report_command(db, tmp_path):
    from typer.testing import CliRunner
    from ashare.cli import app
    r = CliRunner().invoke(app, ["paths-report"])
    assert r.exit_code == 0, r.output
    assert "Nothing has been changed" in r.output
