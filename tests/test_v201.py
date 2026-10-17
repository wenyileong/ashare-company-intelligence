"""v2.0.1: fixes from the first live run (CNINFO's Shanghai list returned 404)."""
import httpx

from ashare.http import set_default_transport


def _list_handler(seen):
    def handle(request):
        url = str(request.url)
        seen.append(url)
        if url.endswith("sse_stock.json") and "szse" not in url:
            return httpx.Response(404)
        if url.endswith("szse_stock.json"):
            return httpx.Response(200, json={"stockList": [
                {"code": "600519", "orgId": "gssh0600519", "zwjc": "贵州茅台", "category": "A股"},
                {"code": "688981", "orgId": "9900040732", "zwjc": "中芯国际", "category": "A股"},
                {"code": "000001", "orgId": "gssz0000001", "zwjc": "平安银行", "category": "A股"},
                {"code": "300750", "orgId": "9900033007", "zwjc": "宁德时代", "category": "A股"},
                {"code": "920001", "orgId": "x", "zwjc": "北交所示例", "category": "A股"},
                {"code": "900901", "orgId": "y", "zwjc": "B股示例", "category": "B股"}]})
        return httpx.Response(404)
    return handle


def test_universe_comes_from_the_single_cninfo_list(db):
    from ashare.pipeline import update_universe
    from ashare.models import SessionLocal, Company
    seen = []
    set_default_transport(httpx.MockTransport(_list_handler(seen)))
    try:
        r = update_universe()
    finally:
        set_default_transport(None)
    assert not any(u.endswith("/sse_stock.json") for u in seen)
    assert r["inserted"] == 4 and r["rejected"] == 2          # BSE and B shares are off by default
    s = SessionLocal()
    got = {c.security_code: (c.exchange, c.board, c.org_id) for c in s.query(Company)}
    s.close()
    assert got["600519"] == ("SSE", "SSE_MAIN", "gssh0600519") and got["688981"][:2] == ("SSE", "STAR")
    assert got["300750"][:2] == ("SZSE", "CHINEXT")


def test_stock_list_address_can_be_overridden(monkeypatch):
    from ashare.sources.cninfo import CNInfoAdapter
    monkeypatch.setenv("ASHARE_CNINFO_STOCK_LIST_URL", "https://example.org/list.json")
    assert CNInfoAdapter.stock_list_url() == "https://example.org/list.json"


def test_selftest_reports_each_exchange_in_the_list():
    from ashare.selftest import check_stock_lists
    from ashare.http import RateLimitedClient
    seen = []
    c = RateLimitedClient("t", transport=httpx.MockTransport(_list_handler(seen)))
    rows = {r["check"]: r for r in check_stock_lists(c)}
    c.close()
    assert rows["cninfo_stock_list"]["status"] == "WARN"           # only 6 records in the mock
    assert rows["cninfo_stock_list_sse"]["status"] == "FAIL"       # 2 < 1000: coverage lost
    from ashare.selftest import run_selftest
    r = run_selftest(None, offline=True)
    assert {x["check"]: x["status"] for x in r["results"]}["cninfo_stock_list_sse"] == "PASS"


def test_friendly_errors():
    from ashare.errors import friendly_error
    req = httpx.Request("GET", "https://www.cninfo.com.cn/new/data/sse_stock.json")
    e = httpx.HTTPStatusError("x", request=req, response=httpx.Response(404, request=req))
    msg = friendly_error(e)
    assert "HTTP 404" in msg and "Self-test" in msg
    assert "network" in friendly_error(httpx.ConnectError("no route", request=req))


def test_empty_universe_warning(db):
    from typer.testing import CliRunner
    from ashare.cli import app
    r = CliRunner().invoke(app, ["extract-financials"])
    assert r.exit_code == 0 and "company list is empty" in r.output
    assert "No companies to check" in CliRunner().invoke(app, ["validate-universe"]).output
