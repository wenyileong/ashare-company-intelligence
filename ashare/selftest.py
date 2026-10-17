"""Live-source self-test (v1.4).

Checks that each public endpoint the collector relies on still answers in
the shape the adapters expect. It sends a handful of requests at the normal
polite rate (about 15 requests in total) and never retries aggressively.

Statuses:
  PASS                 endpoint answered in the expected shape
  WARN                 answered, but something looks off (e.g. a category
                       code returned no announcements for a large issuer)
  FAIL                 answered, but not in the expected shape: the adapter
                       probably needs updating
  NETWORK_UNREACHABLE  no answer (offline, proxy, firewall, DNS); this says
                       nothing about the adapter

``--offline`` runs the same checks against built-in canned responses so the
checks themselves can be exercised without a network (used in CI).
"""
from __future__ import annotations

import html
import json
import platform
from datetime import date, timedelta
from pathlib import Path

import httpx

from . import __version__
from .config import USER_AGENT, CNINFO_QUERY_URL, CNINFO_STATIC_BASE
from .disclosures import REPORT_CATEGORIES, PLATE_MAP, document_url
from .http import RateLimitedClient
from .sources.cninfo import CNInfoAdapter
from .timeutil import utcnow

SSE_LIST_URL = "https://www.sse.com.cn/assortment/stock/list/share/"
SZSE_LIST_URL = "https://www.szse.cn/market/product/stock/list/index.html"
EASTMONEY_KLINE_URL = "https://push2his.eastmoney.com/api/qt/stock/kline/get"

PROBE = {"code": "600519", "org_id": "gssh0600519", "board": "SSE_MAIN", "exchange": "SSE"}

# Categories every large issuer should have within two years. A zero count
# for these is a WARN; for the others (e.g. regulatory) zero is plausible.
EXPECTED_NONEMPTY = {"annual", "interim", "quarterly", "q1", "reports", "distributions", "all"}


def _result(check, status, detail, **extra):
    row = {"check": check, "status": status, "detail": detail}
    row.update(extra)
    return row


def _unreachable(exc) -> bool:
    return isinstance(exc, (httpx.ConnectError, httpx.ConnectTimeout, httpx.ReadTimeout,
                            httpx.ProxyError, httpx.NetworkError, httpx.TimeoutException, OSError))


def _call(check, fn):
    """Run ``fn``; convert transport failures into result rows."""
    try:
        return fn()
    except httpx.HTTPStatusError as exc:
        return _result(check, "FAIL", f"HTTP {exc.response.status_code} from {exc.request.url}")
    except Exception as exc:  # noqa: BLE001 - every failure must become a row
        if _unreachable(exc):
            return _result(check, "NETWORK_UNREACHABLE", f"{type(exc).__name__}: {exc}")
        return _result(check, "FAIL", f"{type(exc).__name__}: {exc}")


def check_stock_lists(client) -> list[dict]:
    """v2.0.1: CNINFO's single code-to-orgId list for all mainland shares.
    One row per exchange, so a list that silently loses one exchange shows."""
    from .universe import enabled_optional_boards, infer_exchange
    check_all = "cninfo_stock_list"
    exchanges = ["SSE", "SZSE"] + (["BSE"] if "BSE" in enabled_optional_boards() else [])
    state: dict = {}

    def run_all():
        url = CNInfoAdapter.stock_list_url()
        data = client.get(url).json()
        rows = (data.get("stockList") or data.get("data") or []) if isinstance(data, dict) else []
        if not rows:
            return _result(check_all, "FAIL", "no stockList/data array in response")
        sample = rows[0]
        missing = [k for k in ("code", "orgId", "zwjc") if k not in sample]
        if missing:
            return _result(check_all, "FAIL", f"records lack keys {missing}; keys seen: {sorted(sample)[:8]}")
        counts: dict[str, int] = {}
        for r in rows:
            ex = infer_exchange(str(r.get("code", "")).zfill(6)) or "OTHER"
            counts[ex] = counts.get(ex, 0) + 1
        state["counts"] = counts
        status = "PASS" if len(rows) > 3000 else "WARN"
        return _result(check_all, status, f"{len(rows)} records ({url})", records=len(rows), by_exchange=counts)

    out = [_call(check_all, run_all)]
    for ex in exchanges:
        check = f"cninfo_stock_list_{ex.lower()}"
        if out[0]["status"] in ("FAIL", "NETWORK_UNREACHABLE"):
            out.append(_result(check, out[0]["status"], "the stock list could not be read (see cninfo_stock_list)"))
            continue
        n = state.get("counts", {}).get(ex, 0)
        floor = 100 if ex == "BSE" else 1000
        out.append(_result(check, "PASS" if n >= floor else "FAIL",
                           f"{n} {ex} securities in the list" + ("" if n >= floor else
                           "; the list no longer covers this exchange"), records=n))
    return out


def _query(client, kind, since, until, page_size=30):
    column, plate = PLATE_MAP[PROBE["board"]]
    payload = {
        "pageNum": "1", "pageSize": str(page_size), "tabName": "fulltext", "column": column,
        "stock": f"{PROBE['code']},{PROBE['org_id']}", "searchkey": "", "secid": "", "plate": plate,
        "category": REPORT_CATEGORIES[kind], "trade": "", "seDate": f"{since}~{until}",
        "sortName": "", "sortType": "", "isHLtitle": "true",
    }
    response = client.post(CNINFO_QUERY_URL, data=payload, headers={
        "Referer": "https://www.cninfo.com.cn/new/commonUrl?url=disclosure/list/notice",
        "Origin": "https://www.cninfo.com.cn", "X-Requested-With": "XMLHttpRequest",
    })
    return response.json()


def check_announcements(client, today: date) -> tuple[list[dict], str | None]:
    """One query per category code; returns rows and an annual-report adjunct URL."""
    since, until = (today - timedelta(days=730)).isoformat(), today.isoformat()
    out, adjunct = [], None
    kinds = [k for k in REPORT_CATEGORIES if k != "quarterly_preview"]
    for kind in kinds:
        check = f"cninfo_category_{kind}"

        def run(kind=kind, check=check):
            nonlocal adjunct
            data = _query(client, kind, since, until)
            if not isinstance(data, dict) or "announcements" not in data:
                return _result(check, "FAIL", "response lacks an 'announcements' key", code=REPORT_CATEGORIES[kind])
            rows = data.get("announcements") or []
            if rows:
                missing = [k for k in ("announcementTitle", "adjunctUrl", "announcementTime") if k not in rows[0]]
                if missing:
                    return _result(check, "FAIL", f"announcement records lack {missing}", code=REPORT_CATEGORIES[kind])
            total = data.get("totalAnnouncement") or data.get("totalRecordNum") or len(rows)
            if kind == "annual" and rows and adjunct is None:
                for r in rows:
                    t = r.get("announcementTitle") or ""
                    if "摘要" not in t and "英文" not in t and (r.get("adjunctUrl") or "").lower().endswith(".pdf"):
                        adjunct = r["adjunctUrl"]
                        break
            if not rows and kind in EXPECTED_NONEMPTY:
                return _result(check, "WARN",
                               f"no announcements in two years for {PROBE['code']}; the category code may have changed",
                               code=REPORT_CATEGORIES[kind], count=0)
            return _result(check, "PASS", f"{total} announcement(s)", code=REPORT_CATEGORIES[kind], count=total)
        out.append(_call(check, run))
    return out, adjunct


def check_market_day(client, today: date) -> dict:
    """v1.9: the market-wide query used by the daily update (stock field empty)."""
    check = "cninfo_market_day_query"
    day = today - timedelta(days=1)
    while day.weekday() >= 5:
        day -= timedelta(days=1)

    def run():
        payload = {"pageNum": "1", "pageSize": "30", "tabName": "fulltext", "column": "szse", "stock": "",
                   "searchkey": "", "secid": "", "plate": "", "category": "", "trade": "",
                   "seDate": f"{day.isoformat()}~{day.isoformat()}", "sortName": "", "sortType": "", "isHLtitle": "true"}
        data = client.post(CNINFO_QUERY_URL, data=payload, headers={
            "Referer": "https://www.cninfo.com.cn/new/commonUrl?url=disclosure/list/notice",
            "Origin": "https://www.cninfo.com.cn", "X-Requested-With": "XMLHttpRequest"}).json()
        rows = (data or {}).get("announcements") or []
        codes = {r.get("secCode") for r in rows}
        if not rows:
            return _result(check, "WARN", f"no announcements for {day}; the market-wide query may need other parameters")
        if len(codes) < 5:
            return _result(check, "FAIL", f"only {len(codes)} companies in the market-wide result: the empty stock "
                                          "field may not mean 'all companies'")
        total = data.get("totalAnnouncement") or len(rows)
        return _result(check, "PASS", f"{total} announcement(s) on {day} from {len(codes)}+ companies")
    return _call(check, run)


def check_eastmoney_list(client) -> dict:
    """v1.9: the whole-market quote list used for daily prices."""
    from .market import EASTMONEY_LIST_URL, EASTMONEY_LIST_FS
    check = "eastmoney_market_list"

    def run():
        params = {"pn": 1, "pz": 100, "po": 1, "np": 1, "fltt": 2, "invt": 2, "fid": "f12", "fs": EASTMONEY_LIST_FS,
                  "fields": "f2,f5,f12,f15,f16,f17", "ut": "bd1d9ddb04089700cf9c27f6f7426281"}
        data = (client.get(EASTMONEY_LIST_URL, params=params).json() or {}).get("data") or {}
        rows = data.get("diff") or []
        if isinstance(rows, dict):
            rows = list(rows.values())
        if not rows:
            return _result(check, "FAIL", "response lacks data.diff")
        if "f12" not in rows[0] or "f2" not in rows[0]:
            return _result(check, "FAIL", f"records lack f12/f2; keys: {sorted(rows[0])[:8]}")
        total = data.get("total") or len(rows)
        return _result(check, "PASS" if total > 3000 else "WARN", f"{total} securities listed")
    return _call(check, run)


def check_document(client, adjunct: str | None, queries_reached: bool = True) -> dict:
    check = "cninfo_document_download"
    if not adjunct and not queries_reached:
        return _result(check, "NETWORK_UNREACHABLE", "skipped: the announcement query could not be reached")
    if not adjunct:
        return _result(check, "WARN", "skipped: no annual-report link was returned by the query check")

    def run():
        url = document_url(adjunct)
        r = client.get(url)
        if not r.content.startswith(b"%PDF"):
            return _result(check, "FAIL", f"{url} did not return a PDF (content-type {r.headers.get('content-type')})")
        return _result(check, "PASS", f"PDF, {len(r.content) // 1024} KiB", url=url)
    return _call(check, run)


def check_exchange_pages(client) -> list[dict]:
    out = []

    def sse():
        r = client.get(SSE_LIST_URL)
        has_rows = "600519" in r.text or "<table" in r.text.lower()
        if has_rows:
            return _result("sse_list_page", "PASS", f"HTTP {r.status_code}, table present")
        return _result("sse_list_page", "WARN",
                       f"HTTP {r.status_code}, but the list is rendered by script; SSE cross-checks will be empty")
    out.append(_call("sse_list_page", sse))

    def szse():
        r = client.get(SZSE_LIST_URL)
        return _result("szse_list_page", "PASS", f"HTTP {r.status_code} (used as a reachability hook only)")
    out.append(_call("szse_list_page", szse))
    return out


def check_eastmoney(client, today: date) -> dict:
    check = "eastmoney_daily_bars"

    def run():
        params = {
            "secid": f"1.{PROBE['code']}", "klt": "101", "fqt": "0",
            "beg": (today - timedelta(days=40)).strftime("%Y%m%d"), "end": today.strftime("%Y%m%d"),
            "fields1": "f1,f2,f3,f4,f5,f6",
            "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61",
            "ut": "7eea3edcaed734bea9cbfc24409ed989",
        }
        payload = client.get(EASTMONEY_KLINE_URL, params=params).json()
        klines = ((payload or {}).get("data") or {}).get("klines")
        if klines is None:
            return _result(check, "FAIL", "response lacks data.klines")
        if not klines:
            return _result(check, "WARN", "no bars returned for the last 40 days")
        fields = klines[0].split(",")
        if len(fields) < 11:
            return _result(check, "FAIL", f"bar has {len(fields)} fields, expected 11")
        return _result(check, "PASS", f"{len(klines)} bars; latest {klines[-1].split(',')[0]}")
    return _call(check, run)


def run_selftest(output_dir: str | Path | None = None, offline: bool = False,
                 transport=None, today: date | None = None) -> dict:
    today = today or date.today()
    if offline and transport is None:
        transport = fixture_transport()
    client = RateLimitedClient(USER_AGENT, 1.0, transport=transport, retries=2)
    results = []
    try:
        results += check_stock_lists(client)
        ann, adjunct = check_announcements(client, today)
        results += ann
        reached = any(r["status"] != "NETWORK_UNREACHABLE" for r in ann)
        results.append(check_document(client, adjunct, reached))
        results.append(check_market_day(client, today))
        results += check_exchange_pages(client)
        results.append(check_eastmoney(client, today))
        results.append(check_eastmoney_list(client))
    finally:
        client.close()
    summary = {s: sum(1 for r in results if r["status"] == s)
               for s in ("PASS", "WARN", "FAIL", "NETWORK_UNREACHABLE")}
    if summary["NETWORK_UNREACHABLE"] and not summary["PASS"] and not summary["FAIL"]:
        verdict = "NO_NETWORK"
    elif summary["FAIL"]:
        verdict = "ADAPTERS_NEED_ATTENTION"
    elif summary["WARN"] or summary["NETWORK_UNREACHABLE"]:
        verdict = "OK_WITH_WARNINGS"
    else:
        verdict = "OK"
    report = {
        "version": __version__, "run_at": utcnow().isoformat(timespec="seconds") + "Z",
        "mode": "offline-fixtures" if offline else "live", "platform": platform.platform(),
        "probe": PROBE, "verdict": verdict, "summary": summary, "results": results,
    }
    if output_dir is not None:
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)
        (out / "selftest_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        (out / "selftest_report.html").write_text(render_html(report), encoding="utf-8")
        report["files"] = [str(out / "selftest_report.json"), str(out / "selftest_report.html")]
    return report


_COLOURS = {"PASS": "#1a7f37", "WARN": "#9a6700", "FAIL": "#cf222e", "NETWORK_UNREACHABLE": "#57606a"}


def render_html(report: dict) -> str:
    rows = "".join(
        f"<tr><td>{html.escape(r['check'])}</td><td style='color:{_COLOURS[r['status']]};font-weight:600'>"
        f"{r['status']}</td><td>{html.escape(str(r['detail']))}</td></tr>" for r in report["results"])
    s = report["summary"]
    return (
        "<!doctype html><meta charset='utf-8'><title>Self-test</title>"
        "<style>body{font:14px system-ui,sans-serif;margin:2em;max-width:60em}"
        "td,th{padding:4px 10px;border-bottom:1px solid #ddd;text-align:left}</style>"
        f"<h1>Live-source self-test</h1><p>Version {report['version']} · {report['run_at']} · "
        f"mode {report['mode']}</p><p><b>Verdict: {report['verdict']}</b> · "
        f"{s['PASS']} pass, {s['WARN']} warn, {s['FAIL']} fail, {s['NETWORK_UNREACHABLE']} unreachable</p>"
        f"<table><tr><th>Check</th><th>Status</th><th>Detail</th></tr>{rows}</table>"
        "<p>Send <code>selftest_report.json</code> with any bug report. FAIL means an adapter needs "
        "updating; NETWORK_UNREACHABLE means the site could not be reached from this computer.</p>"
    )


# --- offline fixtures ----------------------------------------------------------

def _fixture_pdf() -> bytes:
    return b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n"


def fixture_handler(request: httpx.Request) -> httpx.Response:
    url = str(request.url)
    if url.endswith("szse_stock.json"):            # one list for all mainland shares
        rows = ([{"code": f"{600000 + i}", "orgId": f"gssh0{600000 + i}", "zwjc": f"沪{i}"} for i in range(1, 1700)]
                + [{"code": f"{i:06d}", "orgId": f"gssz0{i:06d}", "zwjc": f"深{i}"} for i in range(1, 1700)]
                + [{"code": f"{920000 + i}", "orgId": f"gfbj0{920000 + i}", "zwjc": f"京{i}"} for i in range(1, 200)])
        return httpx.Response(200, json={"stockList": rows})
    if url.startswith(CNINFO_QUERY_URL):
        body = dict(httpx.QueryParams(request.content.decode()))
        cat = body.get("category", "")
        if not body.get("stock"):      # market-wide query
            ann = [{"announcementTitle": f"示例公告{i}", "adjunctUrl": f"finalpage/x/{i}.PDF", "secCode": f"{600000 + i}",
                    "announcementTime": 1774800000000, "announcementId": f"m{i}"} for i in range(30)]
            return httpx.Response(200, json={"announcements": ann, "totalAnnouncement": 30, "hasMore": False})
        if "category_tbclts" in cat or "category_fxts" in cat:
            return httpx.Response(200, json={"announcements": None, "totalAnnouncement": 0, "hasMore": False})
        ann = [{"announcementTitle": "2025年年度报告", "adjunctUrl": "finalpage/2026-03-30/1.PDF",
                "announcementTime": 1774800000000, "announcementId": "1"}]
        return httpx.Response(200, json={"announcements": ann, "totalAnnouncement": 1, "hasMore": False})
    if url.startswith(CNINFO_STATIC_BASE.rstrip("/")):
        return httpx.Response(200, content=_fixture_pdf(), headers={"content-type": "application/pdf"})
    if url.startswith(SSE_LIST_URL):
        return httpx.Response(200, text="<html><table><tr><td>600519</td></tr></table></html>")
    if url.startswith(SZSE_LIST_URL):
        return httpx.Response(200, text="<html></html>")
    if url.startswith("https://push2.eastmoney.com/api/qt/clist/get"):
        diff = [{"f2": 10.0 + i, "f5": 1000, "f12": f"{600000 + i:06d}", "f15": 11.0, "f16": 9.0, "f17": 10.0}
                for i in range(100)]
        return httpx.Response(200, json={"data": {"total": 5300, "diff": diff}})
    if url.startswith(EASTMONEY_KLINE_URL):
        k = ["2026-09-30,1500,1510,1520,1490,30000,4.5e9,2.0,0.6,9.0,0.24"]
        return httpx.Response(200, json={"data": {"klines": k}})
    return httpx.Response(404)


def fixture_transport() -> httpx.MockTransport:
    return httpx.MockTransport(fixture_handler)
