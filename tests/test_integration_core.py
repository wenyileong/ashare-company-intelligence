"""Database-level tests. v0.7 had none, which hid a session-factory defect
that broke every write path."""
import json
from helpers import make_pdf, add_disclosure


def test_session_is_a_session(db):
    from ashare.models import SessionLocal
    s = SessionLocal()
    assert hasattr(s, "query") and hasattr(s, "close")
    s.close()


def test_universe_upsert_idempotent(db):
    from ashare.storage import upsert_ashares
    items = [{"code": "600519", "exchange": "SSE", "legal_name_cn": "贵州茅台"},
             {"code": "300750", "exchange": "SZSE", "legal_name_cn": "宁德时代"},
             {"code": "900901", "exchange": "SSE", "legal_name_cn": "B股"}]
    r1 = upsert_ashares(items)
    r2 = upsert_ashares(items)
    assert (r1["inserted"], r1["rejected"]) == (2, 1)
    assert (r2["inserted"], r2["updated"]) == (0, 2)


def test_store_raw_is_content_addressed(db):
    from ashare.storage import store_raw
    from ashare.models import SessionLocal, RawRecord
    a = store_raw("CNINFO", "https://x", b'{"a":1}', {"content_type": "application/json"})
    b = store_raw("CNINFO", "https://x", b'{"a":1}', {"content_type": "application/json"})
    assert a["sha256"] == b["sha256"] and a["payload_path"].endswith(".json")
    s = SessionLocal()
    assert s.query(RawRecord).count() == 2  # each retrieval is logged
    s.close()


def test_disclosure_adapter_constructs():
    from ashare.disclosures import CNInfoDisclosureAdapter
    CNInfoDisclosureAdapter().close()


def test_persist_disclosures_offline(company):
    from ashare.disclosures import persist_disclosures
    from ashare.models import SessionLocal, Disclosure
    page = {"announcements": [
        {"announcementId": "1", "announcementTitle": "<em>2025年年度报告</em>", "announcementTime": 1775000000000,
         "adjunctUrl": "finalpage/2026-04-01/1.PDF"},
        {"announcementId": "2", "announcementTitle": "2025年年度报告摘要", "announcementTime": 1775000000000,
         "adjunctUrl": "finalpage/2026-04-01/2.PDF"},
    ], "hasMore": False}
    raw = json.dumps(page).encode()
    r1 = persist_disclosures(company, [(1, page, raw)], "reports")
    r2 = persist_disclosures(company, [(1, page, raw)], "reports")
    assert r1["inserted"] == 2 and r2["updated"] == 2
    s = SessionLocal()
    kinds = {d.announcement_id: d.kind for d in s.query(Disclosure).all()}
    s.close()
    assert kinds == {"1": "annual_report", "2": "annual_report_summary"}


def test_migration_adds_columns(tmp_path, monkeypatch):
    import sqlite3
    path = tmp_path / "old.db"
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE market_bars (id INTEGER PRIMARY KEY, company_id INTEGER, trade_date VARCHAR(20), "
                "adjustment VARCHAR(20), source VARCHAR(100))")
    con.commit(); con.close()
    monkeypatch.setenv("ASHARE_DB", str(path))
    from ashare.models import init_db
    init_db()
    cols = [r[1] for r in sqlite3.connect(path).execute("PRAGMA table_info(market_bars)")]
    assert "volume_unit" in cols
