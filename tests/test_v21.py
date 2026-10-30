"""v2.1: data corrections from the live runs (findings 96 to 109), extraction speed, the visualisation layer's first
phases, polish and the Chinese interface. Each test reproduces a fault planned in docs/plan_v2.1.md (with the review
round that found it, where it came from the review) and fails on v2.0.9."""
import json
from pathlib import Path

import httpx
import pytest

from ashare.http import set_default_transport


def _set(code, **kw):
    from ashare.models import SessionLocal, Company
    s = SessionLocal()
    try:
        c = s.query(Company).filter_by(security_code=code).one()
        for k, v in kw.items():
            setattr(c, k, v)
        s.commit()
    finally:
        s.close()


def _status():
    from ashare.models import SessionLocal, Company
    s = SessionLocal()
    try:
        return {c.security_code: (c.status, c.listing_date) for c in s.query(Company)}
    finally:
        s.close()


def _lists(covered_ok=True, b=None):
    """An ExchangeListing as read: the A-share lists whole, optionally the B-share lists (b: None, 'ok', 'fail')."""
    from ashare import exchange_lists
    info = exchange_lists.ExchangeListing({"600519": {"name": "贵州茅台", "listing_date": "2001-08-27",
                                                      "source": "sse_main"}})
    info.lists = {k: {"name": n, "rows": m, "dated": m, "error": None, "whole": covered_ok}
                  for k, n, m in exchange_lists.LISTS}
    if b:
        for k, n, m in exchange_lists.B_LISTS:
            info.lists[k] = {"name": n, "rows": 0 if b == "fail" else m, "dated": 0, "error": "HTTP 404" if b == "fail"
                             else None, "whole": b == "ok"}
        if b == "ok":
            info["900901"] = {"name": "云赛B股", "listing_date": "1992-07-28", "source": "sse_b"}
    info.complete = all(v["whole"] for v in info.lists.values())
    return info


@pytest.fixture
def boards(db, monkeypatch):
    """600519 (Shanghai main), 830799 (Beijing), 900901 and 900902 (Shanghai B), 600001 (absent from the lists)."""
    monkeypatch.setenv("ASHARE_OPTIONAL_BOARDS", "BSE,B_SHARE")
    from ashare.storage import upsert_ashares
    upsert_ashares([
        {"code": "600519", "exchange": "SSE", "legal_name_cn": "贵州茅台酒股份有限公司", "short_name_cn": "贵州茅台", "org_id": "a"},
        {"code": "830799", "exchange": "BSE", "legal_name_cn": "艾融软件", "short_name_cn": "艾融软件", "org_id": "b"},
        {"code": "900901", "exchange": "SSE", "legal_name_cn": "云赛智联", "short_name_cn": "云赛B股", "org_id": "c"},
        {"code": "900902", "exchange": "SSE", "legal_name_cn": "市北高新", "short_name_cn": "市北B股", "org_id": "d"},
        {"code": "600001", "exchange": "SSE", "legal_name_cn": "某某", "short_name_cn": "某某股份", "org_id": "e"}])
    from ashare.models import SessionLocal, Company
    s = SessionLocal()
    try:
        assert {c.security_code: c.board for c in s.query(Company)}["830799"] == "BSE"
        for c in s.query(Company).filter(Company.security_code.in_(["830799", "900901", "900902"])):
            c.status = "NOT_IN_EXCHANGE_LIST"            # as v2.0.8 and v2.0.9 left them
        s.commit()
    finally:
        s.close()
    return db


# --- A1. The optional boards (finding 104) ------------------------------------------------------------------------

def test_beijing_companies_are_restored_and_dated_from_the_quote_list(boards, monkeypatch):
    from ashare import exchange_lists, pipeline, quotelist
    monkeypatch.setattr(exchange_lists, "exchange_listing_info", lambda *a, **k: _lists(b="ok"))
    asked = []

    def bse_list(progress=None, board=None):
        asked.append(board)
        out = quotelist.ListingInfo({"830799": {"name": "艾融软件", "listing_date": "2016-01-20"}} if board == "BSE"
                                    else {"900902": {"name": "市北B股", "listing_date": "1992-03-27"}})
        out.complete = True
        return out
    monkeypatch.setattr(quotelist, "listing_info", bse_list)
    counts = pipeline.enrich_listing_status()
    st = _status()
    assert st["830799"] == ("LISTED", "2016-01-20")
    assert st["900901"] == ("LISTED", "1992-07-28")              # from the Shanghai B-share list
    assert st["600001"][0] == "NOT_IN_EXCHANGE_LIST"             # its own board's list was read whole
    assert st["900902"][0] == "LISTED"                           # B list read whole and absent, but quote list has it
    assert "BSE" in asked
    assert counts["NOT_IN_EXCHANGE_LIST"] == 1


def test_a_board_whose_list_failed_keeps_its_status(boards, monkeypatch):
    """Review round 3: a failed request must not make statuses flap."""
    from ashare import exchange_lists, pipeline, quotelist
    monkeypatch.setattr(exchange_lists, "exchange_listing_info", lambda *a, **k: _lists(b="fail"))
    monkeypatch.setattr(quotelist, "listing_info", lambda progress=None, board=None: quotelist.ListingInfo())
    pipeline.enrich_listing_status()
    st = _status()
    assert st["900901"][0] == "NOT_IN_EXCHANGE_LIST" and st["900902"][0] == "NOT_IN_EXCHANGE_LIST"
    assert st["830799"][0] == "LISTED"                             # no list exists for the board: undone
    assert st["600001"][0] == "NOT_IN_EXCHANGE_LIST"


def test_beijing_is_not_marked_when_its_board_has_no_list(boards, monkeypatch):
    from ashare import exchange_lists, pipeline, quotelist
    _set("830799", status="LISTED")
    monkeypatch.setattr(exchange_lists, "exchange_listing_info", lambda *a, **k: _lists())
    monkeypatch.setattr(quotelist, "listing_info", lambda progress=None, board=None: quotelist.ListingInfo())
    counts = pipeline.enrich_listing_status()
    assert _status()["830799"][0] == "LISTED"
    assert counts["undated_listed_by_board"]["BSE"] == 1


def test_b_share_lists_are_read_with_their_own_parameters(db, monkeypatch):
    from ashare import exchange_lists
    from test_v207 import _xlsx
    seen = []

    def handler(request):
        url = str(request.url)
        p = request.url.params
        seen.append((request.url.host, dict(p)))
        if "query.sse.com.cn" in url:
            if p["STOCK_TYPE"] == "2":
                return httpx.Response(200, json={"result": [{"B_STOCK_CODE": "900901", "COMPANY_ABBR": "云赛B股",
                                                             "LIST_DATE": "19920728"}] * 1 + [
                    {"B_STOCK_CODE": f"9009{i:02d}", "COMPANY_ABBR": "x", "LIST_DATE": "19920101"} for i in range(2, 30)]})
            return httpx.Response(200, json={"result": [{"A_STOCK_CODE": "600519", "COMPANY_ABBR": "贵州茅台",
                                                         "LIST_DATE": "20010827"}]})
        if "ShowReport" in url:
            if p["TABKEY"] == "tab2":
                rows = [["B股代码", "B股简称", "B股上市日期"]] + [[200000 + i, f"深B{i}", "1993-01-01"] for i in range(25)]
            else:
                rows = [["A股代码", "A股简称", "A股上市日期"], [1, "平安银行", "1991-04-03"]]
            return httpx.Response(200, content=_xlsx(rows))
        return httpx.Response(404)
    set_default_transport(httpx.MockTransport(handler))
    try:
        info = exchange_lists.exchange_listing_info(store=False, b_shares=True)
    finally:
        set_default_transport(None)
    assert info["900901"]["listing_date"] == "1992-07-28" and info["200000"]["listing_date"] == "1993-01-01"
    assert info.lists["sse_b"]["whole"] and info.lists["szse_b"]["whole"]
    assert {"SSE_B", "SZSE_B"} <= info.covered
    assert "SSE_MAIN" not in info.covered                    # the A list here is far too short to count as whole
    assert any(p.get("STOCK_TYPE") == "2" for _, p in seen) and any(p.get("TABKEY") == "tab2" for _, p in seen)


def test_quote_list_can_read_one_optional_board(db):
    from ashare.quotelist import listing_info
    asked = []

    def handler(request):
        p = request.url.params
        asked.append(p["fs"])
        if p["fs"] != "m:0+t:81+s:2048":
            return httpx.Response(404)
        rows = [{"f12": f"8307{i:02d}", "f14": "x", "f26": 20200101} for i in range(5)]
        return httpx.Response(200, json={"rc": 0, "data": {"total": 5, "diff": rows if int(p["pn"]) == 1 else []}})
    set_default_transport(httpx.MockTransport(handler))
    try:
        got = listing_info(board="BSE")
    finally:
        set_default_transport(None)
    assert got.complete and got["830700"]["listing_date"] == "2020-01-01"
    assert set(asked) == {"m:0+t:81+s:2048"}


# --- A3. Errors in full (finding 96) ------------------------------------------------------------------------------

def test_a_failed_action_leaves_its_traceback_in_a_file(db, monkeypatch, tmp_path):
    from ashare import crossvalidation
    from ashare.gui import run_command

    def boom(*a, **k):
        raise TypeError("'<' not supported between instances of 'NoneType' and 'str'")
    monkeypatch.setattr(crossvalidation, "flag_summary", boom)
    code, out = run_command(["show-flags"])
    assert code == 1 and "Full error:" in out
    path = Path(out.split("Full error:")[1].strip().splitlines()[0])
    text = path.read_text(encoding="utf-8")
    assert "Traceback" in text and "flag_summary" not in "" and "boom" in text and "command: show-flags" in text


def test_the_launcher_calls_freeze_support_first():
    """Review round 5: a frozen worker would otherwise run ashare.app.main with the worker's arguments."""
    src = (Path(__file__).resolve().parents[1] / "packaging" / "launcher.py").read_text(encoding="utf-8")
    assert src.index("freeze_support()") < src.index("main()")
    assert "from ashare.app import main" in src.split("freeze_support()")[1]


# --- A6. The self-test (finding 106) ------------------------------------------------------------------------------

def test_self_test_reports_every_quote_list_variant():
    from ashare.selftest import check_eastmoney_list
    from ashare.quotelist import VARIANTS

    class Client:
        offline = False

        def get(self, url, params=None, headers=None):
            if url.startswith("https://push2.eastmoney.com") and not (headers or {}).get("Referer"):
                raise httpx.RemoteProtocolError("Server disconnected without sending a response.")
            req = httpx.Request("GET", url)
            raise httpx.HTTPStatusError("502", request=req, response=httpx.Response(502, request=req))
    r = check_eastmoney_list(Client())
    assert r["status"] == "FAIL"
    for name, *_ in VARIANTS:
        assert name in r["detail"]
    assert "Diagnose the quote list" in r["detail"]
