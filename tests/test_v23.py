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
