"""v2.0.2: fixes from the second live run (whole-market catalogue looked stuck;
listing dates unknown; new code ranges)."""
from datetime import date

import httpx
import pytest

from ashare.http import set_default_transport


def _companies(rows):
    from ashare.storage import upsert_ashares
    upsert_ashares([{"code": c, "exchange": "SSE" if c.startswith("6") else "SZSE", "short_name_cn": n,
                     "org_id": f"o{c}"} for c, n in rows])


def _ms(day):
    return int((date.fromisoformat(day) - date(1970, 1, 1)).total_seconds() * 1000)


def _market_handler(calls, big_month="2026-04"):
    """Exchange-wide report queries; April holds more than one query returns."""
    def handle(request):
        url = str(request.url)
        if "hisAnnouncement/query" in url:
            body = dict(httpx.QueryParams(request.content.decode()))
            calls.append(body)
            a, b = body["seDate"].split("~")
            col = body["column"]
            n_days = (date.fromisoformat(b) - date.fromisoformat(a)).days + 1
            total = 4000 if (a.startswith(big_month) and n_days > 16) else 3
            codes = ["600519", "688981"] if col == "sse" else ["000001"]
            ann = [{"announcementId": f"{c}-{a}", "announcementTitle": f"{a[:4]}年第一季度报告", "secCode": c,
                    "adjunctUrl": f"finalpage/{a}/{c}.PDF", "announcementTime": _ms(a)} for c in codes]
            ann.append({"announcementId": f"x-{a}", "announcementTitle": "其他", "secCode": "999999",
                        "adjunctUrl": "x.PDF", "announcementTime": _ms(a)})
            return httpx.Response(200, json={"announcements": ann, "totalAnnouncement": total, "hasMore": False})
        if "static.cninfo.com.cn" in url:
            return httpx.Response(200, content=b"%PDF-1.4 " + url.encode(), headers={"content-type": "application/pdf"})
        return httpx.Response(404)
    return handle


def test_market_wide_catalogue_uses_exchange_queries_and_splits_full_windows(db):
    from ashare.disclosure_pipeline import catalogue_disclosures
    from ashare.models import SessionLocal, Disclosure
    _companies([("600519", "贵州茅台"), ("688981", "中芯国际"), ("000001", "平安银行")])
    calls, lines = [], []
    set_default_transport(httpx.MockTransport(_market_handler(calls)))
    try:
        r = catalogue_disclosures("2026-03-01", "2026-05-31", kind="reports", download_documents=True,
                                  progress=lines.append)
    finally:
        set_default_transport(None)
    assert r["mode"] == "market" and not r["errors"]
    assert all(c["stock"] == "" for c in calls)                    # no per-company queries
    april = [c["seDate"] for c in calls if c["seDate"].startswith("2026-04")]
    assert "2026-04-01~2026-04-30" in april and any(s.endswith("2026-04-15") for s in april)   # split
    assert r["unmatched"] > 0 and r["downloaded"] == r["inserted"] > 0
    s = SessionLocal()
    assert s.query(Disclosure).filter(Disclosure.local_path.isnot(None)).count() == r["inserted"]
    s.close()
    assert any("Downloading" in x and "GB" in x for x in lines) and any("Catalogue done" in x for x in lines)


def test_stop_is_safe_and_resumable(db):
    from ashare.disclosure_pipeline import catalogue_disclosures
    from ashare.http import Cancelled, request_cancel, reset_cancel
    from ashare.models import SessionLocal, Disclosure
    _companies([("600519", "贵州茅台"), ("000001", "平安银行")])
    calls = []
    base = _market_handler(calls)

    def handler(request):
        if len(calls) == 3:
            request_cancel()                       # the Stop button, mid-run
        return base(request)
    set_default_transport(httpx.MockTransport(handler))
    try:
        with pytest.raises(Cancelled):
            catalogue_disclosures("2026-01-01", "2026-06-30", kind="reports")
        s = SessionLocal()
        partial = s.query(Disclosure).count()
        s.close()
        assert partial > 0                          # what was fetched before Stop is kept
        reset_cancel()
        r = catalogue_disclosures("2026-01-01", "2026-06-30", kind="reports")
    finally:
        reset_cancel()
        set_default_transport(None)
    s = SessionLocal()
    ids = [d.announcement_id for d in s.query(Disclosure)]
    s.close()
    assert len(ids) == len(set(ids)) and len(ids) > partial and not r["errors"]


def test_per_company_mode_still_available(db):
    from ashare.disclosure_pipeline import catalogue_disclosures
    _companies([("600519", "贵州茅台")])
    calls = []
    set_default_transport(httpx.MockTransport(_market_handler(calls)))
    try:
        r = catalogue_disclosures("2026-03-01", "2026-03-31", kind="reports", security_code="600519")
    finally:
        set_default_transport(None)
    assert r["mode"] == "company" and calls[0]["stock"].startswith("600519,")


def test_listing_dates_status_and_point_in_time_list(db):
    from ashare.pipeline import enrich_listing_status
    from ashare.security_master import rebuild_security_history, universe_at
    from ashare.models import SessionLocal, Company
    _companies([("600519", "贵州茅台"), ("688981", "中芯国际"), ("000004", "国华退"), ("000003", "PT金田A"),
                ("000010", "*ST美丽")])
    info = {f"{i:06d}": {"name": "x", "listing_date": None} for i in range(100000, 103500)}   # looks complete
    info.update({"600519": {"name": "贵州茅台", "listing_date": "2001-08-27"},
                 "688981": {"name": "中芯国际", "listing_date": "2020-07-16"}})
    st = enrich_listing_status(info)
    assert st["LISTED"] == 2 and st["DELISTED"] == 2 and st["NOT_IN_QUOTE_LIST"] == 1
    rebuild_security_history()
    rep = {}
    rows = universe_at("2015-12-31", report=rep)
    assert [r["code"] for r in rows] == ["600519"]                  # STAR company not yet listed
    assert rep["excluded_no_listing_date"] == 3                    # delisted and missing ones are counted
    assert {r["code"] for r in universe_at("2026-06-30")} == {"600519", "688981"}
    s = SessionLocal()
    assert s.query(Company).filter_by(security_code="000004").one().status == "DELISTED"
    s.close()


def test_listing_info_parses_quote_list():
    from ashare.market import fetch_listing_info

    def handler(request):
        return httpx.Response(200, json={"data": {"total": 2, "diff": [
            {"f12": "600519", "f14": "贵州茅台", "f26": 20010827}, {"f12": "302132", "f14": "中航成飞", "f26": "-"}]}})
    set_default_transport(httpx.MockTransport(handler))
    try:
        info = fetch_listing_info()
    finally:
        set_default_transport(None)
    assert info["600519"]["listing_date"] == "2001-08-27" and info["302132"]["listing_date"] is None


def test_new_code_ranges_and_reasons():
    from ashare.universe import infer_exchange, infer_board, rejection_reason, looks_delisted
    assert (infer_exchange("302132"), infer_board("SZSE", "302132")) == ("SZSE", "CHINEXT")
    assert (infer_exchange("689009"), infer_board("SSE", "689009")) == ("SSE", "STAR")
    assert rejection_reason("920001").startswith("Beijing") and rejection_reason("900901").startswith("B shares")
    assert looks_delisted("大明退市") and looks_delisted("神城A退") and not looks_delisted("退之科技")
    assert not looks_delisted("*ST美丽")


def test_validation_no_longer_counts_short_names_as_problems(db):
    from ashare.validation import validate_database
    _companies([("600519", "贵州茅台")])
    assert validate_database() == []


def test_gui_output_streams_lines():
    pytest.importorskip("tkinter")
    from ashare.gui import run_command
    got = []
    code, out = run_command(["version"], stream=got.append)
    assert code == 0 and got and got[0].strip() == out.strip()


def test_repeated_network_failures_stop_early(db):
    from ashare.disclosure_pipeline import catalogue_disclosures
    _companies([("600519", "贵州茅台")])
    calls = []

    def handler(request):
        calls.append(1)
        raise httpx.ConnectError("blocked", request=request)
    set_default_transport(httpx.MockTransport(handler))
    try:
        r = catalogue_disclosures("2026-01-01", "2026-12-31", kind="reports")
    finally:
        set_default_transport(None)
    assert r["stopped_early"] and len(r["errors"]) == 3
