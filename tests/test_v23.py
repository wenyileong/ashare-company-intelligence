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


# --- B2: network patience ----------------------------------------------------------------------------------------

def _client(handler, patience=True, retries=3):
    import httpx
    from ashare.http import RateLimitedClient
    return RateLimitedClient("t", transport=httpx.MockTransport(handler), retries=retries, server_patience=patience)


def test_server_errors_are_waited_out_for_patient_clients(capsys):
    import httpx
    calls = []

    def handler(req):
        calls.append(1)
        return httpx.Response(504) if len(calls) <= 3 else httpx.Response(200, text="ok")
    assert _client(handler).get("http://www.cninfo.com.cn/x").text == "ok"
    assert len(calls) == 4
    assert "CNINFO is not answering (504)" in capsys.readouterr().out


def test_patience_has_an_end_and_other_clients_keep_quick_retries():
    import httpx
    from ashare.http import SERVER_PAUSES
    calls = []

    def handler(req):
        calls.append(1)
        return httpx.Response(503)
    with pytest.raises(httpx.HTTPStatusError):
        _client(handler).get("http://www.cninfo.com.cn/x")
    assert len(calls) == len(SERVER_PAUSES) + 3                  # the pauses, then the usual retries
    calls.clear()
    with pytest.raises(httpx.HTTPStatusError):
        _client(handler, patience=False, retries=2).get("http://push2.eastmoney.com/x")
    assert len(calls) == 2                                        # unchanged for Eastmoney's refusals
    calls.clear()

    def notfound(req):
        calls.append(1)
        return httpx.Response(404)
    with pytest.raises(httpx.HTTPStatusError):
        _client(notfound).get("http://www.cninfo.com.cn/x")
    assert len(calls) == 1                                        # a 404 is not retried by a patient client


def test_a_429_honours_retry_after(monkeypatch):
    import httpx
    from ashare import http
    waits = []
    monkeypatch.setattr(http, "_sleep_checking", lambda s: waits.append(s))
    calls = []

    def handler(req):
        calls.append(1)
        return httpx.Response(429, headers={"Retry-After": "7"}) if len(calls) == 1 else httpx.Response(200)
    c = _client(handler)
    c.offline = False                         # take the real pause path, with the sleep recorded instead
    c.delay = 0
    assert c.get("http://www.cninfo.com.cn/x").status_code == 200
    assert waits == [7.0]


# --- B3: the work ledger -------------------------------------------------------------------------------------------

def test_the_ledger_records_and_lists_documents_not_read(db, company, monkeypatch):
    from ashare.models import SessionLocal, Disclosure
    from ashare.ledger import Ledger, not_read, DONE, NOT_READ, FAILED
    s = SessionLocal()
    s.add_all([Disclosure(company_id=company.id, announcement_id=f"N{i}", title_cn=f"报告{i}", kind="annual_report",
                          announcement_date="2025-04-01") for i in range(3)])
    s.commit()
    ids = [d.id for d in s.query(Disclosure).order_by(Disclosure.id)]
    s.close()
    with Ledger("control") as led:
        led.record(ids[0], NOT_READ, "MISSING_FILE")
        led.record(ids[1], FAILED, "PARSE_ERROR", "boom")
        led.record(ids[2], DONE)
    with Ledger("control") as led:
        led.record(ids[1], DONE)                                  # read on a later run: no longer listed
    r = not_read()
    assert [x["item"] for x in r["rows"]] == [str(ids[0])]
    assert r["rows"][0]["code"] == "600519" and r["summary"][0]["reason"] == "MISSING_FILE"
    monkeypatch.setenv("ASHARE_FEATURES", "jobs.ledger=off")
    with Ledger("control") as led:
        led.record(ids[2], FAILED, "PARSE_ERROR")
    assert len(not_read()["rows"]) == 1                           # switched off: nothing recorded


def test_extraction_records_missing_files_in_the_ledger(db, company):
    from ashare.models import SessionLocal, Disclosure
    from ashare.ledger import not_read
    from ashare.control import extract_control
    s = SessionLocal()
    s.add(Disclosure(company_id=company.id, announcement_id="R1", title_cn="2024年年度报告", kind="annual_report",
                     announcement_date="2025-04-01", local_path="disclosures/600519/" + "a" * 64 + ".pdf",
                     sha256="a" * 64))
    s.commit()
    s.close()
    extract_control(security_code="600519")
    rows = not_read("control")["rows"]
    assert len(rows) == 1 and rows[0]["reason"] == "MISSING_FILE"


# --- Part A ----------------------------------------------------------------------------------------------------------

from test_v22 import rel, _ego  # noqa: E402,F401  (the seeded ego-map database of v2.2)


def test_events_without_an_authority_are_drawn_and_counted(rel):
    from ashare.models import SessionLocal, RegulatoryEvent, Company
    s = SessionLocal()
    a = s.query(Company).filter_by(security_code="600519").one()
    s.add(RegulatoryEvent(company_id=a.id, event_id="E2", event_type="REGULATORY_LETTER",
                          legal_classification="EXCHANGE_SUPERVISORY_MEASURE", announcement_date="2024-02-01", event_date="2024-01-30", title_cn="关于收到问询函的公告",
                          extraction_method="TITLE", source="CNINFO"))
    s.add(RegulatoryEvent(company_id=a.id, event_id="E3", event_type="REGULATORY_LETTER",
                          legal_classification="EXCHANGE_SUPERVISORY_MEASURE", announcement_date="2025-02-01", event_date="2025-01-30", title_cn="later",
                          extraction_method="TITLE", source="CNINFO"))
    s.commit()
    s.close()
    snap = _ego().snapshot
    unnamed = [n for n in snap["nodes"] if "UNNAMED" in n["flags"]]
    assert len(unnamed) == 1 and unnamed[0]["kind"] == "authority"
    note = next(c for c in snap["coverage"] if c["item"] == "regulators")["note"]
    assert "2 event(s) from 1 named authority; 1 naming no authority; 1 published after the date" in note


def test_codes_given_twice_count_once():
    from ashare.util import parse_codes, plural, span
    assert parse_codes("688012, 600519,688012，1") == (["688012", "600519", "000001"], ["688012"])
    assert parse_codes(["1", "000001"]) == (["000001"], ["000001"])
    assert plural(1, "announcement") == "1 announcement" and plural(2, "company", "companies") == "2 companies"
    assert span("2020-12-30", "2020-12-30") == "2020-12-30" and span("a", "b") == "a to b"


def test_the_price_download_resumes_and_reports_progress(db, company, monkeypatch):
    from ashare import market
    from ashare.storage import upsert_ashares
    from ashare.ledger import not_read
    upsert_ashares([{"code": "000001", "exchange": "SZSE", "legal_name_cn": "平安银行股份有限公司",
                     "short_name_cn": "平安银行", "org_id": "z"}])
    fetched = []

    def fake(c, start, end, adjust):
        fetched.append(c.security_code)
        if c.security_code == "000001" and fetched.count("000001") == 1:
            raise RuntimeError("source down")
        return [{"trade_date": d, "close": 1.0, "adjustment": adjust, "source": "EASTMONEY_PUBLIC"}
                for d in ("2025-01-02", "2025-06-30", "2025-12-31")]
    monkeypatch.setattr(market, "_fetcher", lambda p: fake)
    said = []
    r = market.acquire_market_data(None, "2025-01-01", "2025-12-31", "eastmoney", progress=said.append)
    assert r["companies"] == 2 and r["errors"] and "2 of 2 companies" in said[-1]
    assert [x["item"] for x in not_read("market_prices")["rows"]] == ["000001"]
    fetched.clear()
    r = market.acquire_market_data(None, "2025-01-01", "2025-12-31", "eastmoney", progress=said.append)
    assert fetched == ["000001"] and r["skipped_up_to_date"] == 1   # 600519 is covered; 000001 failed before
    fetched.clear()
    r = market.acquire_market_data(None, "2025-01-01", "2025-12-31", "eastmoney", refetch=True)
    assert sorted(fetched) == ["000001", "600519"]


# --- B11: the outputs register -------------------------------------------------------------------------------------

def test_a_view_command_records_its_output_and_it_can_be_checked_and_removed(rel, tmp_path):
    from typer.testing import CliRunner
    from ashare.cli import app
    from ashare.outputs import list_outputs, check_output, remove_output, inside_outside
    out = tmp_path / "visualise" / "ego"
    r = CliRunner().invoke(app, ["viz-ego-map", "--code", "600519", "--as-of", "2024-06-30", "--out", str(out)])
    assert r.exit_code == 0, r.output
    rows = list_outputs()
    assert len(rows) == 1 and rows[0]["kind"] == "view" and rows[0]["inside_data_folder"]
    assert check_output(rows[0]["id"])["status"] == "OK"
    (out / "nodes.csv").write_text("changed", encoding="utf-8")
    assert "nodes.csv" in check_output(rows[0]["id"])["changed"]
    assert inside_outside()["inside"] == 1
    prev = remove_output(rows[0]["id"])
    assert not prev["applied"] and out.exists()
    remove_output(rows[0]["id"], apply=True)
    assert not out.exists() and list_outputs() == [] and list_outputs(include_removed=True)[0]["status"] == "REMOVED"


def test_recording_never_fails_the_output_and_respects_its_switch(db, tmp_path, monkeypatch):
    from ashare import outputs
    f = tmp_path / "exports" / "x.csv"
    f.parent.mkdir()
    f.write_text("a", encoding="utf-8")
    monkeypatch.setenv("ASHARE_FEATURES", "outputs.register=off")
    assert outputs.record_output("export", f) is None
    monkeypatch.delenv("ASHARE_FEATURES")
    monkeypatch.setattr(outputs, "_size", lambda p: 1 / 0)
    assert outputs.record_output("export", f) is None                        # logged, not raised


def test_earlier_outputs_are_found_by_their_manifests_once(db, tmp_path):
    from ashare.outputs import scan_outputs, list_outputs
    v = tmp_path / "visualise" / "old_view"
    v.mkdir(parents=True)
    (v / "manifest.json").write_text(json.dumps({"view": "coverage", "files": {}}), encoding="utf-8")
    p = tmp_path / "panels"
    p.mkdir()
    (p / "panel.csv").write_text("a", encoding="utf-8")
    (p / "panel_manifest.json").write_text(json.dumps({"columns": ["a"], "files": {"panel.csv": None}}),
                                           encoding="utf-8")
    r = scan_outputs()
    assert r["found"] == 2 and r["by_kind"] == {"view": 1, "panel": 1} and list_outputs() == []
    scan_outputs(apply=True)
    assert len(list_outputs()) == 2
    assert scan_outputs()["found"] == 0                                      # not added twice


# --- B1 phases 4 and 5: normalise, undo, move, adopt ---------------------------------------------------------------

def _seed_paths(company, root: Path, old_root: str):
    from ashare.models import SessionLocal, Disclosure, FinancialFact
    p, sha = _doc(root / "disclosures")
    s = SessionLocal()
    d = Disclosure(company_id=company.id, announcement_id="P1", title_cn="2024年年度报告", kind="annual_report",
                   announcement_date="2025-04-01", local_path=f"{old_root}/disclosures/600519/{p.name}", sha256=sha)
    s.add(d)
    s.flush()
    s.add(FinancialFact(company_id=company.id, disclosure_id=d.id, reporting_period="2024-12-31", period_type="FY",
                        metric="revenue", value=1.0, source_document=d.local_path, extraction_method="PDF_TEXT"))
    s.commit()
    did = d.id
    s.close()
    return did, p


def test_normalising_rewrites_with_a_backup_and_can_be_undone(db, company, tmp_path):
    from ashare.datafolder import normalise_paths, undo_paths
    from ashare.models import SessionLocal, Disclosure, FinancialFact
    did, p = _seed_paths(company, tmp_path, "/old/machine/AShareScraper")
    pre = normalise_paths()
    assert pre["changes"] == 2 and not pre["applied"]
    s = SessionLocal()
    assert s.get(Disclosure, did).local_path.startswith("/old/")                 # the preview changed nothing
    s.close()
    r = normalise_paths(apply=True)
    assert r["applied"] and r["verified"] == 1 and Path(r["backup"]).exists()
    s = SessionLocal()
    rel = p.relative_to(tmp_path).as_posix()
    assert s.get(Disclosure, did).local_path == rel
    assert s.query(FinancialFact).one().source_document == rel
    s.close()
    assert undo_paths(r["run_id"])["restored"] == 2
    s = SessionLocal()
    assert s.get(Disclosure, did).local_path.startswith("/old/")
    s.close()


def test_normalising_is_refused_when_switched_off(db, monkeypatch):
    from ashare.datafolder import normalise_paths
    from ashare.features import FeatureOff
    monkeypatch.setenv("ASHARE_FEATURES", "storage.normalise=off")
    with pytest.raises(FeatureOff):
        normalise_paths()


def _home_folder(tmp_path, monkeypatch, name="home"):
    """A data folder laid out as the desktop program lays it out."""
    import os
    from ashare.models import reset_init_cache
    home = tmp_path / name
    home.mkdir()
    for k, v in {"ASHARE_HOME": home, "ASHARE_DB": home / "ashares.db", "ASHARE_RAW_DIR": home / "raw",
                 "ASHARE_DISCLOSURE_DIR": home / "disclosures", "ASHARE_MARKET_RAW_DIR": home / "market_raw"}.items():
        monkeypatch.setenv(k, str(v))
    monkeypatch.chdir(home)
    reset_init_cache()
    return home


@pytest.mark.skipif(bool(os.environ.get("ASHARE_TEST_DB_URL")), reason="moves a SQLite database")
@pytest.mark.parametrize("method", ["copy", "rename"])
def test_moving_the_data_folder_keeps_every_link(tmp_path, monkeypatch, method):
    from ashare.storage import upsert_ashares
    from ashare.models import SessionLocal, Disclosure, Company, init_db, ExtractionState
    from ashare import datafolder
    from ashare.datafolder import move_data_folder
    from ashare.storepaths import has_document
    home = _home_folder(tmp_path, monkeypatch)
    init_db()
    upsert_ashares([{"code": "600519", "exchange": "SSE", "legal_name_cn": "x", "short_name_cn": "x", "org_id": "o"}])
    s = SessionLocal()
    c = s.query(Company).one()
    s.close()
    did, p = _seed_paths(c, home, str(home))                                  # absolute, as the desktop wrote them
    s = SessionLocal()
    s.add(ExtractionState(disclosure_id=did, extractor="control", version="control-4", outcome="READ"))
    s.commit()
    s.close()
    if method == "copy":
        monkeypatch.setattr(datafolder, "_same_device", lambda a, b: False)
    target = tmp_path / "elsewhere" / "AShareScraper"
    dry = move_data_folder(str(target))
    assert not dry["applied"] and not target.exists() and dry["can_move"]
    r = move_data_folder(str(target), apply=True)
    assert r["applied"] and r["paths_rewritten"] == 2, r
    assert (home.exists() and (home / "ashares.db").exists()) == (method == "copy")   # a copy leaves the old one
    s = SessionLocal()
    d = s.get(Disclosure, did)
    assert d.local_path == p.relative_to(home).as_posix() and has_document(d)
    assert s.query(ExtractionState).one().version == "control-4"                     # nothing to read again
    s.close()
    assert (target / "logs").exists() and "data folder moved" in (target / "run_log.txt").read_text(encoding="utf-8")


@pytest.mark.skipif(bool(os.environ.get("ASHARE_TEST_DB_URL")), reason="moves a SQLite database")
def test_a_move_is_refused_into_a_non_empty_or_nested_folder(tmp_path, monkeypatch):
    from ashare.models import init_db
    from ashare.datafolder import move_data_folder
    home = _home_folder(tmp_path, monkeypatch)
    init_db()
    full = tmp_path / "full"
    full.mkdir()
    (full / "x").write_text("x")
    assert "not empty" in move_data_folder(str(full), apply=True)["note"]
    assert "inside the current" in move_data_folder(str(home / "sub"), apply=True)["note"]


@pytest.mark.skipif(bool(os.environ.get("ASHARE_TEST_DB_URL")), reason="adopts a SQLite database")
def test_adopting_a_restored_folder(tmp_path, monkeypatch):
    import shutil
    from ashare.storage import upsert_ashares
    from ashare.models import SessionLocal, Company, init_db
    from ashare.datafolder import adopt_data_folder
    from ashare.features import data_root
    home = _home_folder(tmp_path, monkeypatch)
    init_db()
    upsert_ashares([{"code": "600519", "exchange": "SSE", "legal_name_cn": "x", "short_name_cn": "x", "org_id": "o"}])
    s = SessionLocal()
    c = s.query(Company).one()
    s.close()
    _seed_paths(c, home, "C:\\Users\\User\\Documents\\AShareScraper")
    from ashare.models import engine
    engine().dispose()
    restored = tmp_path / "restored"
    shutil.copytree(home, restored)
    _home_folder(tmp_path, monkeypatch, "blank")                              # the program, pointing elsewhere
    init_db()
    chk = adopt_data_folder(str(restored))
    assert not chk["applied"] and chk["sample"] == {"checked": 1, "ok": 1, "mismatched": 0, "missing": 0}
    assert data_root() == (tmp_path / "blank").resolve()                    # a check changes nothing
    r = adopt_data_folder(str(restored), apply=True)
    assert r["applied"] and data_root() == restored.resolve()


# --- B4: interactive charts (the author's requirement R1) ------------------------------------------------------------

def _page(path, ready, steps):
    """Open ``path`` in a headless browser, wait for ``ready``, run ``steps(page)``; returns (errors, requests, out)."""
    pw = pytest.importorskip("playwright.sync_api")
    with pw.sync_playwright() as p:
        try:
            browser = p.chromium.launch()
        except Exception as exc:                       # noqa: BLE001
            pytest.skip(f"no browser: {exc}")
        try:
            page = browser.new_page(viewport={"width": 1300, "height": 900})
            errors, requests = [], []
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
            page.on("request", lambda r: requests.append(r.url) if not r.url.startswith(("file:", "data:")) else None)
            page.goto(Path(path).as_uri())
            page.wait_for_function(ready, timeout=60000)
            out = steps(page)
            return errors, requests, out
        finally:
            browser.close()


def _guidance_view(company, tmp_path, folder="g"):
    from test_v22 import _guidance
    from ashare.viz.registry import get
    from ashare.viz.publish import write_view
    _guidance(company, tmp_path)
    built = get("guidance_outcome").build({"start": "2023", "end": "2023", "as_of": "2024-06-30", "key": b"k" * 32})
    write_view(get("guidance_outcome"), built, tmp_path / folder, formats=("html", "svg", "csv"), width="page")
    return tmp_path / folder


def test_every_series_chart_zooms_resets_and_reads_exactly(db, company, tmp_path):
    import hashlib
    folder = _guidance_view(company, tmp_path)
    before = {f.name: hashlib.sha256(f.read_bytes()).hexdigest() for f in folder.glob("figure_*")}

    def steps(page):
        n = page.evaluate("window.AshareInteractive.charts.length")
        r0 = page.evaluate("(() => { const c = window.AshareInteractive.charts[0]; return [c.scales.x.min, c.scales.x.max]; })()")
        page.evaluate("window.AshareInteractive.charts[0].zoom(2)")
        r1 = page.evaluate("(() => { const c = window.AshareInteractive.charts[0]; return [c.scales.x.min, c.scales.x.max]; })()")
        box = page.locator("canvas").first.bounding_box()
        page.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
        page.mouse.wheel(0, 400)
        page.wait_for_timeout(200)
        r2 = page.evaluate("(() => { const c = window.AshareInteractive.charts[0]; return [c.scales.x.min, c.scales.x.max]; })()")
        page.get_by_text("Reset zoom").first.click()
        r3 = page.evaluate("(() => { const c = window.AshareInteractive.charts[0]; return [c.scales.x.min, c.scales.x.max]; })()")
        # the readout gives the stored value exactly: point at the scatter's one point
        i = page.evaluate("window.AshareInteractive.charts.findIndex(c => c.config.type === 'scatter')")
        page.evaluate(f"window.AshareInteractive.charts[{i}].canvas.scrollIntoView()")
        pt = page.evaluate(f"""(() => {{ const c = window.AshareInteractive.charts[{i}];
            const m = c.getDatasetMeta(0).data[0]; const r = c.canvas.getBoundingClientRect();
            return [r.left + m.x, r.top + m.y]; }})()""")
        page.mouse.move(pt[0], pt[1])
        page.wait_for_timeout(200)
        text = page.locator(".ai-readout").nth(i).inner_text()
        return n, r0, r1, r2, r3, text
    errors, requests, (n, r0, r1, r2, r3, text) = _page(folder / "view.html", "window.__chartview !== undefined",
                                                        steps)
    assert errors == [] and requests == []
    assert n >= 2
    assert (r1[1] - r1[0]) < (r0[1] - r0[0])                    # zoomed in
    assert r2 != r1                                              # the wheel changed the range
    assert r3 == r0                                              # reset
    assert "620,000,000" in text                                 # the exact stored value (6.2e8)
    after = {f.name: hashlib.sha256(f.read_bytes()).hexdigest() for f in folder.glob("figure_*")}
    assert before == after and before                            # publication figures untouched


def test_with_the_switch_off_the_pages_are_as_in_v22(db, company, tmp_path, monkeypatch):
    monkeypatch.setenv("ASHARE_FEATURES", "viz.interactive=off")
    folder = _guidance_view(company, tmp_path, "off")
    html_text = (folder / "view.html").read_text(encoding="utf-8")
    assert "chartjs-plugin-zoom" not in html_text and "AshareInteractive" in html_text   # (the hook in chart.js)
    errors, _, inter = _page(folder / "view.html", "window.__chartview !== undefined",
                             lambda page: page.evaluate("window.__chartview.interactive"))
    assert errors == [] and inter is False


def test_the_coverage_heatmap_is_a_zoomable_matrix(rel, tmp_path):
    from ashare.viz.registry import get
    from ashare.viz.publish import write_view
    built = get("coverage").build({"start": "2023", "end": "2024", "as_of": "2024-06-30", "key": b"k" * 32})
    write_view(get("coverage"), built, tmp_path / "cov", formats=("html",), width="page")
    errors, requests, types = _page(tmp_path / "cov" / "view.html", "window.__chartview !== undefined",
                                    lambda page: page.evaluate("window.AshareInteractive.charts.map(c => c.config.type)"))
    assert errors == [] and requests == [] and "matrix" in types


def test_relational_maps_and_the_topology_charts_zoom(rel, tmp_path):
    from ashare.viz.registry import get
    from ashare.viz.publish import write_view
    from test_v22 import _ego as ego
    write_view(get("ego_map"), ego(), tmp_path / "e", formats=("html",), width="page")

    def steps(page):
        page.wait_for_timeout(300)
        z0 = page.evaluate("window.__relmap.graph.zoom()")
        page.get_by_text("+", exact=True).click()
        page.wait_for_timeout(400)
        return z0, page.evaluate("window.__relmap.graph.zoom()"), page.get_by_role("button", name="Zoom to selected").count()
    errors, requests, (z0, z1, buttons) = _page(tmp_path / "e" / "view.html", "window.__relmap !== undefined", steps)
    assert errors == [] and requests == [] and z1 > z0 and buttons == 1


def test_a_desktop_chart_opens_as_an_interactive_page(tmp_path):
    from ashare.charts.spec import ChartSpec, Series, Point
    from ashare.charts.interactive import write_page, config
    spec = ChartSpec("line", "Revenue", [Series("600519", [Point("2023", 1.5e11), Point("2024", None),
                                                          Point("2025", 1.7e11)])], unit="CNY", y_label="yuan")
    assert config(spec)["data"]["datasets"][0]["data"] == [1.5e11, None, 1.7e11]       # gaps stay gaps
    p = write_page(spec, tmp_path)
    errors, requests, n = _page(p, "window.__interactive !== undefined",
                                lambda page: page.evaluate("window.__interactive.charts"))
    assert errors == [] and requests == [] and n == 1
    with pytest.raises(ValueError):
        config(ChartSpec("network", "x", []))


def test_the_new_libraries_are_bundled_with_their_licences():
    from ashare.viz.pages import INTERACTIVE_LIBS
    from ashare.viz.viewer import HERE
    text = (HERE / "vendor" / "LICENSES.txt").read_text(encoding="utf-8")
    for lib in INTERACTIVE_LIBS:
        assert (HERE / "vendor" / lib).exists() and lib in text
    for name in ("chartjs-plugin-zoom 2.2.0", "Hammer.js 2.0.8", "chartjs-chart-matrix 2.1.1"):
        assert name in text


def test_the_topology_page_carries_the_zoom_runtime(monkeypatch):
    from ashare.viz.viewer import render_viewer
    snap = {"schema_version": 1}
    monkeypatch.setattr("ashare.viz.snapshot.dumps", lambda s: "{}")
    page = render_viewer(snap)
    assert "chartjs-plugin-zoom" in page and "AshareInteractive" in page and "/*INTERACTIVE*/" not in page
    monkeypatch.setenv("ASHARE_FEATURES", "viz.interactive=off")
    assert "chartjs-plugin-zoom" not in render_viewer(snap)
