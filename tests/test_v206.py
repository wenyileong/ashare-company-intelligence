"""v2.0.6: listing dates in full, extraction with progress and resume, the last catalogue gaps
(findings 35 to 57)."""
from pathlib import Path

import httpx
import pytest

from ashare.http import set_default_transport

# --- the quote list (findings 50 and 57) ------------------------------------------------------

BOARD_SIZES = {"m:0+t:6": 1500, "m:0+t:80": 1300, "m:1+t:2": 1700, "m:1+t:23": 600}
BOARD_BASE = {"m:0+t:6": 1, "m:0+t:80": 300001, "m:1+t:2": 600000, "m:1+t:23": 688001}


def _board_rows(fs):
    n, base = BOARD_SIZES[fs], BOARD_BASE[fs]
    return [{"f12": f"{base + i:06d}", "f14": f"名{base + i}", "f26": 20100104, "f2": 10.0} for i in range(n)]


def _cap_server(cap=1000, sizes=None, flaky=()):
    """Eastmoney as it probably behaves live: at most ``cap`` rows of one query (later pages answer without
    data); ``fs`` selects boards and ``po`` the code order. ``flaky``: (fs, pn) pages that fail once."""
    sizes = sizes or BOARD_SIZES
    calls, failed = [], set()

    def handler(request):
        url = request.url
        if "clist/get" not in str(url):
            return httpx.Response(404)
        p = url.params
        pn, pz, po, fs = int(p["pn"]), int(p["pz"]), int(p["po"]), p["fs"]
        calls.append((fs, po, pn))
        rows = []
        for part in fs.split(","):
            base = BOARD_BASE[part]
            rows += [{"f12": f"{base + i:06d}", "f14": f"名{base + i}", "f26": 20100104, "f2": 10.0}
                     for i in range(sizes[part])]
        rows.sort(key=lambda r: r["f12"], reverse=bool(po))
        if (fs, pn) in flaky and (fs, pn) not in failed:
            failed.add((fs, pn))
            return httpx.Response(502)
        if (pn - 1) * pz >= cap:
            return httpx.Response(200, json={"rc": 0, "data": None})
        return httpx.Response(200, json={"rc": 0, "data": {"total": len(rows), "diff": rows[(pn - 1) * pz: pn * pz]}})
    return handler, calls


def _with(handler, fn):
    set_default_transport(httpx.MockTransport(handler))
    try:
        return fn()
    finally:
        set_default_transport(None)


def test_quote_list_over_the_row_limit_is_read_board_by_board(db):
    from ashare.quotelist import listing_info
    handler, calls = _cap_server()
    info = _with(handler, listing_info)
    assert info.complete and len(info) == 5100 and info.row_cap == 1000
    assert "board by board" in info.note and "1,000" in info.note
    assert all(b["complete"] for b in info.parts.values()) and info.parts["shmb"]["rows"] == 1700
    # The limit, once confirmed, is not waited for again: each board stops at its limit page once at most.
    board_fails = [c for c in calls if c[0] != "m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23" and c[2] == 11]
    assert len(board_fails) <= 3 * 6 * 2                      # three large boards, six variants, two tries each
    # A second run the same day uses what was fetched: one attempt beyond the limit, then the cache.
    calls.clear()
    info2 = _with(handler, listing_info)
    assert info2.complete and len(info2) == 5100
    assert {c[2] for c in calls} == {11}


def test_quote_list_board_over_twice_the_limit_is_reported(db):
    from ashare.quotelist import listing_info
    sizes = dict(BOARD_SIZES, **{"m:1+t:2": 2500})
    handler, _ = _cap_server(sizes=sizes)
    info = _with(handler, listing_info)
    assert not info.complete and info.parts["shmb"]["rows"] == 2000 and info.parts["shmb"]["total"] == 2500
    assert "Shanghai main board 2,000 of 2,500" in info.note and "page 11" in info.note


def test_quote_list_retries_a_failed_page(db):
    from ashare.quotelist import listing_info
    handler, calls = _cap_server(cap=10 ** 6, flaky={("m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23", 3)})
    info = _with(handler, listing_info)
    assert info.complete and len(info) == 5100 and not info.parts      # no board-by-board reading needed
    assert info.row_cap is None


def test_partial_list_note_names_the_error(db):
    from ashare.quotelist import listing_info

    def refuse_after_two(request):
        pn = int(request.url.params["pn"])
        if pn > 2:
            return httpx.Response(503)
        rows = [{"f12": f"{600000 + i}", "f14": "x", "f26": 20100104} for i in range((pn - 1) * 100, pn * 100)]
        return httpx.Response(200, json={"rc": 0, "data": {"total": 5000, "diff": rows}})
    info = _with(refuse_after_two, listing_info)
    assert not info.complete and "HTTP 503" in info.note and "page 3" in info.note


def test_snapshot_reads_board_by_board_over_the_limit(db):
    from ashare.market import fetch_eastmoney_snapshot
    handler, _ = _cap_server()
    rows = _with(handler, lambda: fetch_eastmoney_snapshot("2026-10-23"))
    assert len(rows) == 5100 and len({r["code"] for r in rows}) == 5100


def test_snapshot_incomplete_raises_with_the_reason(db):
    from ashare.market import fetch_eastmoney_snapshot
    sizes = dict(BOARD_SIZES, **{"m:1+t:2": 2500})
    handler, _ = _cap_server(sizes=sizes)
    with pytest.raises(RuntimeError) as e:
        _with(handler, lambda: fetch_eastmoney_snapshot("2026-10-23"))
    assert "incomplete" in str(e.value)


def test_diagnose_reports_the_row_limit(db):
    from ashare.quotelist import diagnose
    handler, _ = _cap_server()
    r = _with(handler, diagnose)
    deep = [e for e in r["results"] if e.get("deep")]
    assert len(deep) == 2 and not deep[0]["ok"] and "1,000 rows" in r["verdict"]
    handler2, _ = _cap_server(cap=10 ** 6)
    r2 = _with(handler2, diagnose)
    assert all(e["ok"] for e in r2["results"] if e.get("deep")) and "1,000" not in r2["verdict"]


def test_update_universe_fills_listing_dates_for_every_board(db):
    from ashare.storage import upsert_ashares
    from ashare.pipeline import enrich_listing_status
    from ashare.quotelist import listing_info
    items = [{"code": r["f12"], "exchange": "SSE" if r["f12"].startswith("6") else "SZSE",
              "short_name_cn": r["f14"], "org_id": f"g{r['f12']}"} for fs in BOARD_SIZES for r in _board_rows(fs)]
    upsert_ashares(items)
    handler, _ = _cap_server()
    st = _with(handler, lambda: enrich_listing_status(listing_info()))
    assert st["listing_dates_added"] == 5100 and st["quote_list_complete"]


# --- extraction: progress, resume, stop wording (findings 42 and 51) --------------------------

def _three_reports(company, tmp_path):
    from helpers import make_pdf, add_disclosure
    for i, (title, day) in enumerate([("2023年年度报告", "2024-03-30"), ("2024年年度报告", "2025-03-30"),
                                      ("2025年年度报告", "2026-03-30")]):
        pdf = make_pdf(tmp_path / f"r{i}.pdf", [title, "单位：元", f"资产总计 {1000 + i}.00", "负债合计 400.00",
                                                f"所有者权益合计 {600 + i}.00"])
        add_disclosure(company, title, day, pdf, ann_id=f"R{i}")


def test_extraction_reports_progress_and_continues_after_stop(company, tmp_path, monkeypatch):
    from ashare import financials
    from ashare.http import Cancelled
    _three_reports(company, tmp_path)
    real, calls = financials.extract_path, []      # v2.1: the reading half, called once a document

    def rid(path):
        return "R" + Path(path).stem[1:]

    def stop_on_second(path, title, ann, reader=None):
        calls.append(rid(path))
        if len(calls) == 2:
            raise Cancelled("stopped by the user; everything saved so far is kept")
        return real(path, title, ann, reader)
    monkeypatch.setattr(financials, "extract_path", stop_on_second)
    lines = []
    with pytest.raises(Cancelled):
        financials.extract_financials("600519", progress=lines.append)
    assert lines[0].startswith("3 document(s) to read")
    monkeypatch.setattr(financials, "extract_path",
                        lambda path, title, ann, reader=None: (calls.append(rid(path)), real(path, title, ann, reader))[1])
    calls.clear()
    lines.clear()
    r = financials.extract_financials("600519", progress=lines.append)
    assert calls == ["R1", "R2"] and r["already_read"] == 1 and r["documents"] == 2
    assert "1 already read" in lines[0] and lines[-1].strip().startswith("2 of 2 documents;")
    calls.clear()
    r = financials.extract_financials("600519")
    assert calls == [] and r["to_read"] == 0
    r = financials.extract_financials("600519", again=True)
    assert calls == ["R0", "R1", "R2"] and r["facts_updated"] > 0 and r["facts_inserted"] == 0


def test_progress_line_gives_time_per_document_and_estimate(company, tmp_path, monkeypatch):
    import re
    import time as _time
    from ashare import financials
    _three_reports(company, tmp_path)
    t = {"now": 0.0}

    def clock():                       # every reading of the clock moves it on by 40 seconds
        t["now"] += 40.0
        return t["now"]
    monkeypatch.setattr(_time, "monotonic", clock)
    lines = []
    financials.extract_financials("600519", progress=lines.append)
    steps = [ln.strip() for ln in lines[1:]]
    assert re.fullmatch(r"[12] of 3 documents; \d+\.\d s each; about \d+ (s|min) left", steps[0])  # over a minute
    assert re.fullmatch(r"3 of 3 documents; \d+\.\d s each", steps[-1])                           # no estimate


def test_duration_wording():
    from ashare.financials import _duration
    assert _duration(45) == "45 s" and _duration(600) == "10 min" and _duration(3 * 3600 + 5 * 60) == "3 h 05 min"


def test_a_changed_download_is_read_again(company, tmp_path):
    from types import SimpleNamespace
    from ashare.models import SessionLocal, Disclosure
    from ashare.disclosures import store_downloaded
    from ashare.financials import extract_financials, EXTRACTOR_VERSION
    _three_reports(company, tmp_path)
    extract_financials("600519")
    s = SessionLocal()
    d = s.query(Disclosure).filter_by(announcement_id="R0").one()
    assert d.extracted_version == EXTRACTOR_VERSION
    resp = SimpleNamespace(content=b"%PDF-1.4 new", headers={"content-type": "application/pdf"})
    store_downloaded(SimpleNamespace(http=SimpleNamespace(get=lambda url: resp)), company, d)
    assert d.extracted_version is None
    s.close()


def test_stop_message_says_what_a_rerun_does():
    pytest.importorskip("tkinter")
    from ashare.gui import stop_message
    from ashare.http import Cancelled
    exc = Cancelled("stopped by the user; everything saved so far is kept")
    assert "continues with the rest" in stop_message(["extract-financials"], exc)
    assert "first unfinished day" in stop_message(["catalogue-disclosures", "--kind", "all"], exc)
    assert stop_message(["build-panel"], exc) == "Stopped: stopped by the user; everything saved so far is kept"


def test_migration_adds_extraction_columns(db):
    from sqlalchemy import inspect
    from ashare.models import engine
    cols = {c["name"] for c in inspect(engine()).get_columns("disclosures")}
    assert {"extracted_version", "extracted_at"} <= cols


# --- the catalogue engine (findings 37 to 56) -------------------------------------------------

from test_v204 import (LiveCNInfo, items_for, SZ_MAIN, CODES, CSRC_SECTIONS, _run, _stored,  # noqa: E402
                       universe)  # noqa: F401  (fixture)
from ashare.market_catalogue import CSRC_MANUFACTURING  # noqa: E402

LEAF_DAY = "2026-04-29"


def _leaf_items():
    """A day like 29 April: 日常经营 on the Shenzhen main board, in manufacturing, is over 3,000 rows."""
    items = items_for(LEAF_DAY, 9000, rcjy_share=0.75, codes=SZ_MAIN) + items_for(LEAF_DAY, 600, codes=CODES)
    for i, it in enumerate(items):
        it["announcementId"] = f"{LEAF_DAY}-x{i}"
        it["_division"] = CSRC_MANUFACTURING[int(it["secCode"][-2:]) % 7]
    return items


def _leaf_total(items):
    return sum(1 for it in items if it["_cat"] == "category_rcjy_szsh" and it["secCode"] in SZ_MAIN
               and it["_trade"] == CSRC_SECTIONS[2])


def _status():
    from ashare.market_catalogue import day_status
    return day_status("all")[0]


def test_leaf_over_the_limit_is_split_by_company_batches(universe):
    items = _leaf_items()
    assert _leaf_total(items) > 3000
    server = LiveCNInfo(items, column_strict=True)
    r = _run(server, LEAF_DAY, LEAF_DAY, "all")
    st = _status()
    assert st["status"] == "DONE" and st["stored"] == len(items) and "STOCK" in st["method"], st
    assert r["filters"].get("stock_style") == "A"
    batches = [c for c in server.calls if c.get("stock")]
    assert batches and all(c["column"] == ("sse" if c["stock"][0] == "6" else "szse") for c in batches)
    assert all(len({p[0] for p in c["stock"].split(";")}) == 1 or not c["stock"] for c in batches)


def test_leaf_is_split_by_single_companies_when_batches_fail(universe):
    items = _leaf_items()
    server = LiveCNInfo(items, stock="no", sort="ignore")       # the time order adds nothing (finding 37)
    r = _run(server, LEAF_DAY, LEAF_DAY, "all")
    st = _status()
    assert st["status"] == "DONE" and "SINGLE_COMPANIES" in st["method"], st
    singles = [c for c in server.calls if c.get("stock") and ";" not in c["stock"] and c["pageNum"] == "1"]
    assert 0 < len(singles) <= len(SZ_MAIN) + 6
    assert r["filters"].get("stock") is False


def test_leaf_is_split_by_manufacturing_division(universe):
    items = _leaf_items()
    server = LiveCNInfo(items, stock="never", division="yes")
    _run(server, LEAF_DAY, LEAF_DAY, "all")
    st = _status()
    assert st["status"] == "DONE" and "TRADE_DIVISION" in st["method"], st


def test_leaf_with_no_finer_split_is_recorded(universe):
    items = _leaf_items()
    server = LiveCNInfo(items, stock="never", sort="ignore")
    r = _run(server, LEAF_DAY, LEAF_DAY, "all")
    st = _status()
    assert st["status"] == "SHORTFALL" and st["gap_in_scope"] == _leaf_total(items) - 3000
    assert "unreachable" in st["partition"] and r["filters"].get("single") is False


def test_a_leaf_is_read_once(universe):
    items = _leaf_items()
    server = LiveCNInfo(items, stock="never", sort="ignore")
    _run(server, LEAF_DAY, LEAF_DAY, "all")
    leaf = [c for c in server.calls if c.get("category") == "category_rcjy_szsh;" and c.get("plate") == "szmb"
            and c.get("trade") == CSRC_SECTIONS[2] and not c.get("stock") and not c.get("sortType")]
    assert len(leaf) == 100                     # its 100 pages, once (and its count asked once, on page 1)
    firsts = [c for c in server.calls if c["pageNum"] == "1" and not c.get("sortType")]
    keys = [(c["seDate"], c.get("category"), c.get("plate"), c.get("trade"), c.get("stock")) for c in firsts]
    assert len(keys) == len(set(keys))          # no count asked twice


def test_short_window_under_the_limit_is_split_by_day(universe):
    from ashare.market_catalogue import day_status
    items = []
    for d in ("2026-01-09", "2026-01-10", "2026-01-11", "2026-01-12"):
        items += items_for(d, 700)
    _run(LiveCNInfo(items, unstable=True, sort="ignore"), "2026-01-09", "2026-01-12", "all")
    sts = day_status("all")
    assert {x["status"] for x in sts} == {"DONE"} and sum(x["stored"] for x in sts) == 2800
    assert all("DAYS" in x["method"] for x in sts)


def test_paging_does_not_stop_at_one_page_of_repeats(universe):
    """Rows moving between pages can make a whole page repeat; reading goes on (finding 38)."""
    from ashare.market_catalogue import MarketQuery, Spec
    from types import SimpleNamespace

    class Http:
        def __init__(self):
            self.n = 0

        def post(self, url, data=None, headers=None):
            p = int(data["pageNum"])
            self.n += 1
            src = 2 if p == 3 else p                        # page 3 repeats page 2
            items = [{"announcementId": f"a{(src - 1) * 30 + i}", "secCode": "000001"} for i in range(30)]
            return SimpleNamespace(json=lambda: {"announcements": items, "totalAnnouncement": 150,
                                                 "hasMore": p < 5}, content=b"")
    q = MarketQuery(SimpleNamespace(http=Http()), store_raw=False)
    total, data = q.first(Spec("2026-01-09", "2026-01-09"))
    rows = q.rest(Spec("2026-01-09", "2026-01-09"), data, total)
    assert len(rows) == 120                            # pages 4 and 5 were still read


def test_paging_never_goes_past_page_100(universe):
    from ashare.market_catalogue import MarketQuery, Spec
    from types import SimpleNamespace

    class Http:
        pages = []

        def post(self, url, data=None, headers=None):
            p = int(data["pageNum"])
            self.pages.append(p)
            items = [{"announcementId": f"a{p}-{i}", "secCode": "000001"} for i in range(30)]
            return SimpleNamespace(json=lambda: {"announcements": items, "totalAnnouncement": 5000,
                                                 "hasMore": True}, content=b"")
    http = Http()
    q = MarketQuery(SimpleNamespace(http=http), store_raw=False)
    total, data = q.first(Spec("2026-04-29", "2026-04-29"))
    q.rest(Spec("2026-04-29", "2026-04-29"), data, total)
    assert max(http.pages) == 100


def test_a_failed_sorted_request_does_not_turn_sorting_off(universe):
    from ashare.market_catalogue import day_status
    day = "2026-01-27"
    items = items_for(day, 1614)
    server = LiveCNInfo(items, unstable=True, disjoint="zero")
    failed = {"n": 0}

    def handler(request):
        body = dict(httpx.QueryParams(request.content.decode()))
        if body.get("sortType") == "desc" and failed["n"] < 3:   # every retry of the first sorted request
            failed["n"] += 1
            return httpx.Response(500)
        return server(request)
    r = _run(handler, day, day, "all")
    assert not any(v is False for k, v in r["filters"].items() if k.startswith("sort["))
    assert day_status("all")[0]["status"] in ("DONE", "SHORTFALL")
    assert not r["days_failed"]


def test_strategy_2_shortfalls_are_fetched_again(universe):
    from ashare.models import SessionLocal
    from ashare.market_catalogue import _record, busy_days, current_strategy_shortfalls, STRATEGY
    assert STRATEGY == 3
    s = SessionLocal()
    _record(s, "all", "2026-04-29", "SHORTFALL", 26066, 26046, "2026-04-29~2026-04-29", "SPLIT", 10)
    s.commit()
    from ashare.models import CatalogueDay
    s.query(CatalogueDay).filter_by(day="2026-04-29").one().strategy = 2
    s.commit()
    s.close()
    assert busy_days("all") == ["2026-04-29"] and current_strategy_shortfalls("all") == []


def test_probe_reports_where_company_queries_fail(universe):
    from ashare.market_catalogue import probe_filters
    items = _leaf_items()
    for case, expected in (({}, "WORKS"), ({"stock": "no"}, "SINGLES_ONLY"), ({"stock": "never"}, "FAILS")):
        set_default_transport(httpx.MockTransport(LiveCNInfo(items, **case)))
        try:
            r = {t["test"]: t for t in probe_filters(LEAF_DAY)["tests"]}
        finally:
            set_default_transport(None)
        assert r["company_batches"]["verdict"] == expected, (case, r["company_batches"])
    set_default_transport(httpx.MockTransport(LiveCNInfo(items, division="yes")))
    try:
        r = {t["test"]: t for t in probe_filters(LEAF_DAY)["tests"]}
    finally:
        set_default_transport(None)
    assert r["manufacturing_divisions"]["verdict"] == "PARTITION"


# --- reporting (findings 40 and 43) -----------------------------------------------------------

def test_a_window_is_one_row_with_its_gap_once():
    from ashare.market_catalogue import units
    rows = [{"day": d, "status": "SHORTFALL", "expected": None, "stored": n, "window": "2026-01-09~2026-01-12",
             "window_expected": 2954, "gap_in_scope": 13, "gap_out_scope": 0, "method": "WINDOW+DAYS"}
            for d, n in (("2026-01-09", 1168), ("2026-01-10", 1230), ("2026-01-11", 0), ("2026-01-12", 543))]
    rows.append({"day": "2026-01-13", "status": "DONE", "expected": 800, "stored": 800,
                 "window": "2026-01-13~2026-01-13", "window_expected": 800, "gap_in_scope": 0})
    u = units(rows)
    assert len(u) == 2 and u[0]["day"] == "2026-01-09~2026-01-12 (window)"
    assert (u[0]["expected"], u[0]["stored"], u[0]["gap_in_scope"], u[0]["days"]) == (2954, 2941, 13, 4)
    assert u[1]["day"] == "2026-01-13"


def test_catalogue_days_counts_a_window_once(universe, monkeypatch):
    monkeypatch.setenv("COLUMNS", "160")       # the table's width must not depend on what ran before (v2.0.8)
    from typer.testing import CliRunner
    from ashare.cli import app
    from ashare.models import SessionLocal
    from ashare.market_catalogue import _record
    s = SessionLocal()
    for d in ("2026-01-09", "2026-01-10", "2026-01-11", "2026-01-12"):
        _record(s, "all", d, "SHORTFALL", None, 700, "2026-01-09~2026-01-12", "WINDOW", 5, gap_in_scope=13,
                gap_out_scope=0, window_expected=2813)
    _record(s, "all", "2026-01-13", "DONE", 800, 800, "2026-01-13~2026-01-13", "DAY", 6, window_expected=800)
    s.commit()
    s.close()
    out = CliRunner().invoke(app, ["catalogue-days", "--kind", "all"]).output
    assert "DONE 1, SHORTFALL 1 (5 days; a window of quiet days counts once)" in out
    assert "2026-01-09~2026-01-12 (window)" in out
    out2 = CliRunner().invoke(app, ["catalogue-days", "--kind", "all", "--by-day"]).output
    assert "SHORTFALL 4" in out2


def test_summary_keeps_today_open(universe):
    from ashare.market_catalogue import _china_today
    today = _china_today()
    lines = []
    r = _run(LiveCNInfo(items_for(today, 50)), today, today, "all", progress=lines.append)
    assert r["days_open"] == 1 and r["days_done"] == 0
    assert any("0 day(s) finished; today kept open" in x for x in lines)


# --- found by the PostgreSQL run of the build ---------------------------------------------------

def test_method_fits_its_column():
    from ashare.market_catalogue import _short_method
    long = "+".join(["BOARD_DISJOINT", "BOARD_EXCHANGE", "CATEGORY", "TRADE", "TRADE_DIVISION", "STOCK",
                     "SINGLE_COMPANIES"])
    short = _short_method(long)
    assert len(short) <= 60 and short.endswith("+...") and short.startswith("BOARD_DISJOINT+")
    assert _short_method("DAY+BOARDS") == "DAY+BOARDS" and _short_method(None) is None


def test_a_failed_write_leaves_the_day_failed(universe, monkeypatch):
    from ashare import market_catalogue as mc
    real, state = mc._record, {"n": 0}

    def flaky(session, kind, day, status, *a, **kw):
        if status != "FAILED" and state["n"] == 0:
            state["n"] += 1
            raise RuntimeError("value too long")
        return real(session, kind, day, status, *a, **kw)
    monkeypatch.setattr(mc, "_record", flaky)
    day = "2026-03-02"
    r = _run(LiveCNInfo(items_for(day, 40)), day, day, "all")
    assert r["days_failed"] == [day] and r["days_done"] == 0
    assert mc.day_status("all")[0]["status"] == "FAILED"


def test_single_companies_only_for_a_leaf(universe):
    """At the level of a whole day the single-company fallback is not used (it cannot place a gap)."""
    from test_v204 import _april29
    server = LiveCNInfo(_april29(), disjoint="zero", bj="no", trade="ignore", sort="ignore")
    _run(server, DAY_APRIL29, DAY_APRIL29, "all")
    singles = [c for c in server.calls if c.get("stock") and ";" not in c["stock"]]
    assert len(singles) < 50


DAY_APRIL29 = "2026-04-29"
