"""v1.9: resumable jobs, high-water marks, daily update, storage, scheduling, transactions, back ends."""
import json
from datetime import date, timedelta

import httpx
import pytest

from ashare.http import set_default_transport
from ashare.selftest import _fixture_pdf


def _universe(codes):
    from ashare.storage import upsert_ashares
    upsert_ashares([{"code": c, "exchange": "SSE" if c.startswith("6") else "SZSE", "legal_name_cn": f"公司{c}",
                     "short_name_cn": f"简{c}", "org_id": f"org{c}"} for c in codes])


CODES = ["600001", "600002", "000003", "300004"]


def _handler(calls):
    def handle(request: httpx.Request):
        url = str(request.url)
        calls.append(url)
        if "hisAnnouncement/query" in url:
            body = dict(httpx.QueryParams(request.content.decode()))
            day = body["seDate"].split("~")[0]
            col = body["column"]
            codes = [c for c in CODES if (c.startswith("6")) == (col == "sse")]
            if body.get("stock"):
                codes = [body["stock"].split(",")[0]]
            ann = []
            for c in codes:
                ann.append({"announcementId": f"{c}-{day}-a", "announcementTitle": f"{day[:4]}年年度报告",
                            "adjunctUrl": f"finalpage/{day}/{c}a.PDF", "secCode": c,
                            "announcementTime": int((date.fromisoformat(day) - date(1970, 1, 1)).total_seconds() * 1000)})
                ann.append({"announcementId": f"{c}-{day}-b", "announcementTitle": "关于召开股东大会的通知",
                            "adjunctUrl": f"finalpage/{day}/{c}b.PDF", "secCode": c,
                            "announcementTime": int((date.fromisoformat(day) - date(1970, 1, 1)).total_seconds() * 1000)})
            ann.append({"announcementId": f"999999-{day}", "announcementTitle": "其他", "secCode": "999999",
                        "adjunctUrl": "x.PDF", "announcementTime": 0})
            return httpx.Response(200, json={"announcements": ann, "hasMore": False, "totalAnnouncement": len(ann)})
        if "static.cninfo.com.cn" in url:
            return httpx.Response(200, content=_fixture_pdf() + url.encode(), headers={"content-type": "application/pdf"})
        if "clist/get" in url:
            diff = [{"f2": 10.0, "f3": 1.0, "f4": 0.1, "f5": 100, "f6": 1e5, "f12": c, "f15": 10.5, "f16": 9.5, "f17": 9.9,
                     "f18": 9.9} for c in CODES]
            return httpx.Response(200, json={"data": {"total": len(diff), "diff": diff}})
        if "kline/get" in url:
            q = dict(request.url.params)
            beg = date(int(q["beg"][:4]), int(q["beg"][4:6]), int(q["beg"][6:]))
            end = date(int(q["end"][:4]), int(q["end"][4:6]), int(q["end"][6:]))
            kl, d = [], beg
            while d <= end:
                if d.weekday() < 5:
                    kl.append(f"{d.isoformat()},10,10,10,10,100,1000,0,0,0,0.1")
                d += timedelta(days=1)
            return httpx.Response(200, json={"data": {"klines": kl}})
        return httpx.Response(404)
    return handle


@pytest.fixture
def mocked():
    calls = []
    set_default_transport(httpx.MockTransport(_handler(calls)))
    yield calls
    set_default_transport(None)


def test_daily_update_is_incremental_and_complete(db, mocked):
    from ashare.ops import daily_update, get_mark, marks
    from ashare.models import SessionLocal, Disclosure, MarketBar
    _universe(CODES)
    r = daily_update(until="2026-03-31", extract=False)
    assert r["since"] == "2026-03-30" and r["catalogue"]["status"] == "DONE"
    s = SessionLocal()
    docs = s.query(Disclosure).all()
    s.close()
    assert len(docs) == 2 * 2 * len(CODES)                     # two days, two announcements each, unknown code ignored
    downloaded = [d for d in docs if d.local_path]
    assert {d.kind for d in downloaded} == {"annual_report"}  # only the kinds the extractors read
    assert get_mark("CNINFO", "*", "announcements") == "2026-03-31"
    n_queries = sum(1 for c in mocked if "hisAnnouncement" in c)
    mocked.clear()
    r2 = daily_update(until="2026-03-31", extract=False)       # nothing new: no announcement query at all
    assert "catalogue" not in r2 and not any("hisAnnouncement" in c for c in mocked)
    s = SessionLocal()
    assert s.query(Disclosure).count() == len(docs)
    bars = s.query(MarketBar).filter_by(trade_date="2026-03-31").count()
    s.close()
    assert bars == len(CODES) and n_queries == 4                # 2 days × 2 exchanges
    assert any(m["kind"] == "daily_snapshot" for m in marks())


def test_jobs_resume_after_cancel_and_failure_without_duplicates(db, mocked, monkeypatch):
    from ashare import ops
    from ashare.models import SessionLocal, Disclosure
    _universe(CODES)
    job = ops.create_job("catalogue_day", {"since": "2026-03-02", "until": "2026-03-06", "kind": "all", "download": False})
    seen = []

    def progress(done, total, key, status):
        seen.append(key)
        if done == 2:
            ops.request_cancel(job)
    r = ops.run_job(job, progress)
    assert r["status"] == "CANCELLED" and r["done"] == 2
    # a transient failure on one day: retried on the next run
    real = ops.HANDLERS["catalogue_day"]
    fail_once = {"2026-03-05": 1}

    def flaky(key, params):
        if fail_once.get(key):
            fail_once[key] -= 1
            raise httpx.ConnectError("reset")
        return real(key, params)
    monkeypatch.setitem(ops.HANDLERS, "catalogue_day", flaky)
    r = ops.run_job(job, sleep=lambda s: None)
    assert r["failed"] == 1 and r["status"] == "QUEUED"
    r = ops.run_job(job, sleep=lambda s: None)
    assert r["status"] == "DONE" and r["done"] == 5 and r["failed"] == 0
    s = SessionLocal()
    n = s.query(Disclosure).count()
    ids = [d.announcement_id for d in s.query(Disclosure)]
    s.close()
    assert n == 5 * 2 * len(CODES) and len(ids) == len(set(ids))
    assert ops.run_job(job)["status"] == "DONE"                 # running a finished job is a no-op
    assert ops.list_jobs()[0]["id"] == job


def test_estimate_within_one_hour():
    from ashare.ops import estimate_daily_requests
    e = estimate_daily_requests(announcements=6000, download_share=0.25, companies=5400)
    assert e["minutes_at_rate"] < 60 and e["price_requests"] == 54


def test_storage_prune_and_refetch(db, mocked):
    from ashare.ops import daily_update, storage_stats, prune_documents, refetch_document
    from ashare.models import SessionLocal, Disclosure
    _universe(CODES)
    daily_update(until="2026-03-31", prices=False, extract=False)
    st = storage_stats()
    assert st["by_kind"]["annual_report"]["documents"] == 8
    dry = prune_documents(("annual_report",), dry_run=True)
    assert dry["documents"] == 8 and storage_stats()["by_kind"]["annual_report"]["documents"] == 8
    done = prune_documents(("annual_report",), dry_run=False)
    assert done["documents"] == 8 and storage_stats()["pruned_documents"] == 8
    s = SessionLocal()
    d = s.query(Disclosure).filter_by(kind="annual_report").first()
    s.close()
    r = refetch_document(d.id)
    assert r["hash_matches"] and r["path"]


def test_schedule_command_is_opt_in_and_dry():
    from ashare.ops import schedule
    r = schedule(True, "18:45", dry_run=True)
    assert ("cron" in r and "daily-update" in r["cron"]) or "schtasks" in r["command"][0]


def test_transaction_titles_and_texts(db, company, tmp_path):
    from ashare.transactions import classify_transaction_title, parse_transaction_text, extract_transactions, \
        show_transactions
    from helpers import add_disclosure, make_pdf
    assert classify_transaction_title("发行股份购买资产暨关联交易预案") == [("MAJOR_RESTRUCTURING", "PLAN")]
    assert classify_transaction_title("关于终止筹划重大资产重组的公告") == [("MAJOR_RESTRUCTURING", "TERMINATED")]
    assert classify_transaction_title("关于2026年度日常关联交易预计的公告") == [("RELATED_PARTY", "ESTIMATE")]
    assert classify_transaction_title("关于为全资子公司提供担保的公告") == [("GUARANTEE", None)]
    assert classify_transaction_title("2025年年度股东大会决议公告") == [("SHAREHOLDER_MEETING", None)]
    [g] = parse_transaction_text("公司为全资子公司甲科技有限公司提供连带责任保证担保，担保金额为人民币5,000万元。"
                                 "截至公告日，公司对外担保余额为3亿元，无逾期担保。本事项已经董事会审议通过。", "GUARANTEE")
    assert (g["counterparty"], g["amount"], g["cumulative_amount"], g["overdue"], g["approval_body"]) == \
        ("甲科技有限公司", 5e7, 3e8, False, "BOARD")
    [rp] = parse_transaction_text("关联方名称：乙集团有限公司。预计2026年向关联方采购原材料，金额不超过1.2亿元，"
                                  "尚需提交股东大会审议。", "RELATED_PARTY")
    assert (rp["counterparty"], rp["amount"], rp["nature"], rp["approval_body"]) == \
        ("乙集团有限公司", 1.2e8, "PURCHASE", "SHAREHOLDER_MEETING")
    votes = parse_transaction_text("会议召开时间：2026年5月20日。1、审议通过《关于2025年度利润分配方案的议案》"
                                   "表决情况：同意 1,000,000 股，占出席会议有表决权股份总数的 99.50%；反对 4,000 股，占 0.40%；"
                                   "弃权 1,000 股，占 0.10%。2、审议通过《关于修订公司章程的议案》表决情况：同意 900,000 股，"
                                   "占出席会议有表决权股份总数的 90.00%；反对 100,000 股，占 10.00%；弃权 0 股，占 0.00%。",
                                   "SHAREHOLDER_MEETING")
    assert [v["proposal"] for v in votes] == ["关于2025年度利润分配方案的议案", "关于修订公司章程的议案"]
    assert votes[0]["votes_for_pct"] == pytest.approx(0.995) and votes[1]["votes_against_pct"] == pytest.approx(0.1)
    assert votes[0]["event_date"] == "2026-05-20" and all(v["resolution_passed"] for v in votes)
    # stages of one deal share a case; a new deal after termination gets a new case
    for i, (title, d) in enumerate((("关于筹划重大资产重组的停牌公告", "2025-01-02"), ("发行股份购买资产预案", "2025-02-01"),
                                    ("关于终止重大资产重组的公告", "2025-06-01"), ("重大资产购买报告书（草案）", "2025-09-01"))):
        add_disclosure(company, title, d, None, ann_id=f"MR{i}")
    extract_transactions("600519")
    mr = show_transactions("600519", "MAJOR_RESTRUCTURING")
    assert [x["stage"] for x in mr] == ["PLANNING", "PLAN", "TERMINATED", "DRAFT"]
    assert mr[0]["case"] == mr[1]["case"] == mr[2]["case"] != mr[3]["case"]


def test_init_db_runs_once_and_indexes_exist(db):
    from ashare.models import init_db, engine, is_sqlite
    from sqlalchemy import inspect
    init_db()
    names = {ix["name"] for ix in inspect(engine()).get_indexes("market_bars")}
    assert "ix_market_bars_company_date" in names
    if is_sqlite():
        with engine().connect() as c:
            assert c.exec_driver_sql("PRAGMA journal_mode").scalar().lower() == "wal"


def test_duckdb_export_optional(db, tmp_path):
    pytest.importorskip("duckdb")
    from ashare.ops import export_duckdb
    _universe(CODES)
    r = export_duckdb(str(tmp_path / "x.duckdb"), ["companies"])
    import duckdb
    assert duckdb.connect(r["file"]).execute("select count(*) from companies").fetchone()[0] == len(CODES)
