"""v2.1: data corrections from the live runs (findings 96 to 109), extraction speed, the visualisation layer's first
phases, polish and the Chinese interface. Each test reproduces a fault planned in docs/plan_v2.1.md (with the review
round that found it, where it came from the review) and fails on v2.0.9."""
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


# --- A2. Top-10 rows only one reading found (finding 98) ----------------------------------------------------------

def _holder(name, shares, pct, rank=0):
    return {"shareholder_name": name, "shares": shares, "ownership_pct": pct, "rank": rank}


def test_top10_rows_matched_by_share_count_and_missing_rows_added():
    """Review round 2: the readings are matched by share count, since rank is the parser's own counter."""
    from ashare.control import merge_top10
    kept = [_holder("甲集团有限公司", 5_000_000, 50.0, 1), _holder("丙投资", 1_000_000, 10.0, 2)]
    other = [_holder("甲集团有限 公司", 5_000_000, 50.0, 1),            # the same holder, read with a break
             _holder("乙基金", 2_000_000, 20.0, 2),                        # missed by the kept reading
             _holder("丙投资", 1_000_000, 10.0, 3)]
    rows, n = merge_top10(kept, other)
    assert n == 1
    assert [(r["shareholder_name"], r["rank"]) for r in rows] == [("甲集团有限公司", 1), ("乙基金", 2), ("丙投资", 3)]
    assert rows[1].get("_added") and not rows[0].get("_added")


@pytest.mark.parametrize("extra", [
    [_holder("乙", 4_000_000, 60.0)],                                 # the percentages would add up to 110
    [_holder("乙", 4_000_000, 160.0)],                                # a percentage out of range
    [_holder(f"乙{i}", 10 + i, 0.1) for i in range(9)],                # eleven rows
])
def test_a_merged_table_that_fails_the_checks_keeps_the_kept_reading(extra):
    from ashare.control import merge_top10
    kept = [_holder("甲", 5_000_000, 50.0, 1), _holder("丙", 1_000_000, 10.0, 2)]
    rows, n = merge_top10([dict(r) for r in kept], extra)
    assert n == 0 and [r["shareholder_name"] for r in rows] == ["甲", "丙"]


def test_tradable_row_found_by_unrestricted_shares_when_names_differ():
    from ashare.control import _tradable_for
    tradable = [{"shareholder_name": "乙基金（有限合伙）", "tradable_shares": 1_500_000}]
    r = {"shareholder_name": "乙基金", "shares": 2_000_000, "restricted_shares": 500_000}
    assert _tradable_for(r, {t["shareholder_name"]: t for t in tradable}, tradable) is tradable[0]
    assert _tradable_for(dict(r, restricted_shares=0), {}, tradable) is None


# --- B1. Financial extraction reads only its pages (findings 101 and 107) -----------------------------------------

_FILLER = [["公司治理与经营情况讨论 正文内容，第%d段" % k, "本段为叙述性文字，无表格。"] for k in range(4)]


def _long_corpus_report(path, seed, filler=_FILLER):
    import random
    from ashare.corpus import _annual_report, _write_pdf
    title, pages, _ = _annual_report(random.Random(seed), 1)
    long = []
    for p in pages:
        long.append(p)
        long += filler
    _write_pdf(path, long)
    return title


def _fact_keys(facts):
    return sorted((f["metric"], f["period"], str(f["value"]), f["unit"], f.get("page")) for f in facts)


@pytest.mark.parametrize("seed", [3, 11, 23])
def test_targeted_financial_reading_gives_the_same_facts_as_whole_reading(tmp_path, seed):
    pytest.importorskip("pypdfium2")
    from ashare.financials import extract_path, parse_financials_job
    from ashare.reportreader import ReportReader
    pdf = tmp_path / f"l{seed}.pdf"
    title = _long_corpus_report(pdf, seed)
    whole = extract_path(pdf, title, None, None)
    with ReportReader(pdf) as rr:
        assert rr.n > 30
        res = parse_financials_job({"path": str(pdf), "title": title}, rr)
        assert res["by_section"] and not rr.fallback_full
        assert rr.layout_pages_read < rr.n / 3
    assert whole and _fact_keys(res["facts"]) == _fact_keys(whole)


def test_unit_declared_at_the_foot_of_the_page_before_a_statement_is_found(tmp_path):
    """Review round 1: the unit rule looks at the figure's page and the page before."""
    pytest.importorskip("pypdfium2")
    from helpers import make_pdf
    from ashare.financials import extract_path
    from ashare.reportreader import ReportReader
    lines = ["示例股份有限公司2025年年度报告", "<PAGE>"]
    for i in range(40):
        lines += [f"第{i + 1}页 经营情况讨论 正文内容", "<PAGE>"]
    lines += ["第十节 财务报告", "单位：万元", "<PAGE>",
              "合并资产负债表", "项目 期末余额 期初余额", "资产总计 1,000.00 900.00", "负债合计 400.00 300.00",
              "所有者权益合计 600.00 600.00", "<PAGE>", "其他内容"]
    pdf = make_pdf(tmp_path / "u.pdf", lines)
    whole = {f["metric"]: (f["value"], f["unit"]) for f in extract_path(pdf, "示例2025年年度报告", None, None)}
    with ReportReader(pdf) as rr:
        part = {f["metric"]: (f["value"], f["unit"]) for f in extract_path(pdf, "示例2025年年度报告", None, rr)}
        assert rr.layout_pages_read < 10
    assert part == whole
    assert part["total_assets"] == (pytest.approx(10_000_000.0), "CNY")      # 万元 applied


def test_a_statement_continued_on_the_next_page_keeps_its_unit():
    """Banks declare 百万元 once, under the statement heading; the continuation page has no declaration."""
    from ashare.cas import parse_statement_items
    pages = ["合并资产负债表\n单位：人民币百万元\n项目 附注 期末余额 期初余额\n货币资金 1,234 1,000",
             "负债合计 4,000 3,900\n所有者权益合计 2,000 1,900"]
    got = {i["metric"]: i["value"] for i in parse_statement_items(pages)}
    assert got["total_liabilities"] == pytest.approx(4_000_000_000.0)


def test_short_documents_and_long_documents_without_headings_are_read_whole(tmp_path):
    """Review round 1: flash reports and announcements carry figures under other headings."""
    pytest.importorskip("pypdfium2")
    from helpers import make_pdf
    from ashare.financials import parse_financials_job
    from ashare.reportreader import ReportReader
    flash = ["示例股份有限公司2025年度业绩快报", "单位：元", "主要财务数据和指标", "营业总收入 1,000.00 900.00",
             "资产总计 5,000.00 4,000.00"]
    short = make_pdf(tmp_path / "flash.pdf", flash + ["<PAGE>", "其他"] * 24)
    with ReportReader(short) as rr:
        assert rr.n == 25
        res = parse_financials_job({"path": str(short), "title": "示例2025年度业绩快报"}, rr)
        assert not res["by_section"] and any(f["metric"] == "total_assets" for f in res["facts"])
    lines = []
    for i in range(250):
        lines += [f"第{i + 1}页 叙述", "<PAGE>"]
    big = make_pdf(tmp_path / "big.pdf", lines[:-1] + ["单位：元", "资产总计 5,000.00 4,000.00"])
    with ReportReader(big) as rr:
        res = parse_financials_job({"path": str(big), "title": "示例2025年年度报告"}, rr)
        assert rr.n == 250 and rr.fallback_full and not res["by_section"]
        assert any(f["metric"] == "total_assets" for f in res["facts"])


def test_a_long_report_is_read_in_a_fraction_of_the_whole_reading_time(tmp_path):
    pytest.importorskip("pypdfium2")
    import time
    from ashare.financials import extract_path
    from ashare.reportreader import ReportReader
    filler = [["公司治理与经营情况讨论 正文内容，第%d段" % k, "本段为叙述性文字，无表格。" * 3,
               "项目 2025年 2024年", "其他非财务数据 12 13"] for k in range(22)]
    pdf = tmp_path / "long.pdf"
    title = _long_corpus_report(pdf, 5, filler)
    t = time.perf_counter()
    extract_path(pdf, title, None, None)
    whole = time.perf_counter() - t
    with ReportReader(pdf) as rr:
        assert rr.n >= 251
        t = time.perf_counter()
        extract_path(pdf, title, None, rr)
        part = time.perf_counter() - t
        assert rr.layout_pages_read <= 20 and rr.text_pages_read <= 20    # of 253 pages; the rest only indexed
    # On these generated pages the layout pass is cheap, so the index pass (every page's plain text, once) weighs
    # more than on real reports, where laying out a page is the slow step (finding 101); the plan's tenth is
    # measured on the author's reports (B4).
    assert part < whole / 2


# --- B3. Parallel extraction ---------------------------------------------------------------------------------------

def _reports(company, tmp_path, n=5):
    from helpers import add_disclosure
    for i in range(n):
        pdf = tmp_path / f"p{i}.pdf"
        title = _long_corpus_report(pdf, 30 + i) if i % 2 == 0 else None
        if title is None:
            from helpers import make_pdf
            make_pdf(pdf, [f"{2020 + i}年年度报告", "单位：元", f"资产总计 {1000 + i}.00 900.00",
                           "负债合计 400.00 300.00", f"所有者权益合计 {600 + i}.00 600.00"])
            title = f"{2020 + i}年年度报告"
        add_disclosure(company, title, f"{2021 + i}-03-30", pdf, ann_id=f"P{i}")


def _facts():
    from ashare.models import SessionLocal, FinancialFact, Disclosure
    s = SessionLocal()
    try:
        facts = sorted((f.disclosure_id, f.metric, f.reporting_period, str(f.value), f.unit, f.extraction_method)
                       for f in s.query(FinancialFact))
        marks = sorted((d.id, d.extracted_version) for d in s.query(Disclosure))
        return facts, marks
    finally:
        s.close()


def test_parallel_and_serial_extraction_write_the_same_facts(company, tmp_path, monkeypatch):
    from ashare import financials, parallel
    _reports(company, tmp_path)
    monkeypatch.setenv("ASHARE_WORKERS", "1")
    serial = financials.extract_financials("600519")
    s_facts = _facts()
    used = []
    real = parallel.ProcessPoolExecutor

    def spy(*a, **k):
        used.append(k.get("max_workers"))
        return real(*a, **k)
    monkeypatch.setattr(parallel, "ProcessPoolExecutor", spy)
    monkeypatch.setenv("ASHARE_WORKERS", "2")
    par = financials.extract_financials("600519", again=True)
    assert used == [2]                                       # the workers were really used
    assert _facts() == s_facts and s_facts[0]
    assert par["documents"] == serial["documents"] == 5 and not par["errors"]
    assert par["read_by_section"] == serial["read_by_section"] == 3


def test_results_come_back_in_job_order_whatever_finishes_first(tmp_path):
    from ashare.parallel import imap
    jobs = [{"id": i, "path": str(tmp_path / "none.pdf"), "delay": 0.4 if i == 0 else 0.0} for i in range(6)]
    got = [r["id"] for r in imap("parallel_helpers:slow_job", jobs, n_workers=3)]
    assert got == list(range(6))


def test_stop_during_a_parallel_run_marks_only_what_was_written(company, tmp_path, monkeypatch):
    from ashare import financials, http
    from ashare.http import Cancelled
    _reports(company, tmp_path)
    monkeypatch.setenv("ASHARE_WORKERS", "2")
    calls = {"n": 0}

    def check():
        calls["n"] += 1
        if calls["n"] > 3:
            raise Cancelled("stopped by the user; everything saved so far is kept")
    monkeypatch.setattr(http, "check_cancel", check)
    with pytest.raises(Cancelled):
        financials.extract_financials("600519")
    facts, marks = _facts()
    marked = {i for i, v in marks if v == financials.EXTRACTOR_VERSION}
    with_facts = {f[0] for f in facts}
    assert marked == with_facts and len(marked) < 5          # nothing marked that was not written, and vice versa
    monkeypatch.setattr(http, "check_cancel", lambda: None)
    r = financials.extract_financials("600519")
    assert r["already_read"] == len(marked) and r["documents"] == 5 - len(marked)


def test_worker_notices_are_added_to_the_main_summary():
    from ashare import pdfwarnings
    from ashare.parallel import merge_notices
    c = pdfwarnings.install()
    c.reset()
    merge_notices({"kinds": {"FontWarning": 3}, "docs": {"a.pdf": {"FontWarning": 3}}, "samples": {"FontWarning": "x"}})
    assert c.kinds["FontWarning"] == 3 and c.docs["a.pdf"]["FontWarning"] == 3
    c.reset()


def test_worker_count_from_the_setting(monkeypatch):
    from ashare.parallel import workers
    monkeypatch.setenv("ASHARE_WORKERS", "1")
    assert workers() == 1
    monkeypatch.setenv("ASHARE_WORKERS", "99")
    assert workers() == 8
    monkeypatch.setenv("ASHARE_WORKERS", "x")
    assert 1 <= workers() <= 8


def test_table_extractors_give_the_same_rows_in_parallel_and_serial(company, tmp_path, monkeypatch):
    from helpers import add_disclosure
    from ashare.control import extract_top_holders
    from ashare.segments import extract_segments
    from ashare.models import SessionLocal, OwnershipObservation, SegmentObservation
    for i in range(5):
        pdf = tmp_path / f"t{i}.pdf"
        title = _long_corpus_report(pdf, 40 + i)
        add_disclosure(company, title, f"{2021 + i}-03-30", pdf, ann_id=f"T{i}")

    def rows():
        s = SessionLocal()
        try:
            return (sorted((r.disclosure_id, r.rank, r.shareholder_name, str(r.shares), str(r.tradable_shares))
                           for r in s.query(OwnershipObservation)),
                    sorted((r.disclosure_id, r.dimension, r.segment_name, str(r.revenue))
                           for r in s.query(SegmentObservation)))
        finally:
            s.close()
    monkeypatch.setenv("ASHARE_WORKERS", "1")
    extract_top_holders("600519")
    extract_segments("600519")
    serial = rows()
    monkeypatch.setenv("ASHARE_WORKERS", "2")
    extract_top_holders("600519", again=True)
    extract_segments("600519", again=True)
    assert rows() == serial and serial[0] and serial[1]


# --- B2. The text layer (decision recorded in docs/text_layer_comparison_v2.1.md) ---------------------------------

def test_pdfium_text_layer_is_an_option_and_pypdf_the_default(tmp_path, monkeypatch):
    pytest.importorskip("pypdfium2")
    from helpers import make_pdf
    from ashare.financials import text_layer, _pdf_text_pages
    from ashare.reportreader import ReportReader
    pdf = make_pdf(tmp_path / "x.pdf", ["前十名股东持股情况", "<PAGE>", "第二页"])
    monkeypatch.delenv("ASHARE_TEXT_LAYER", raising=False)
    assert text_layer() == "pypdf"
    monkeypatch.setenv("ASHARE_TEXT_LAYER", "pdfium")
    assert text_layer() == "pdfium"
    assert "第二页" in _pdf_text_pages(pdf)[1]
    with ReportReader(pdf) as rr:
        assert "前十名股东" in rr.pages("text", ["top10"])[0] and rr._pypdf is None


def test_inspect_tables_writes_both_readings_with_a_decision_on_each_line(company, tmp_path, monkeypatch):
    pytest.importorskip("pypdfium2")
    from helpers import add_disclosure
    from ashare.cli import app
    from typer.testing import CliRunner
    monkeypatch.chdir(tmp_path)
    pdf = tmp_path / "i.pdf"
    title = _long_corpus_report(pdf, 3)
    add_disclosure(company, title, "2023-03-30", pdf, ann_id="I1")
    r = CliRunner().invoke(app, ["inspect-tables", "--code", "600519", "--table", "top10"])
    assert r.exit_code == 0, r.output
    text = Path(r.output.split("Written:")[1].strip()).read_text(encoding="utf-8")
    assert "=== text reading:" in text and "=== layout reading:" in text and "=== Decision ===" in text
    assert "-> table heading: reading starts" in text and "-> row 1 read:" in text
    assert "section pages found:" in text and "none" not in text.split("section pages found:")[1].splitlines()[0]
    for table in ("segments", "control"):
        r = CliRunner().invoke(app, ["inspect-tables", "--code", "600519", "--table", table])
        assert r.exit_code == 0, r.output
        body = Path(r.output.split("Written:")[1].strip()).read_text(encoding="utf-8")
        assert "-> read:" in body
    r = CliRunner().invoke(app, ["inspect-tables", "--code", "000001"])
    assert r.exit_code == 1 and "no downloaded periodic report" in r.output


def test_top10_trace_names_the_check_that_failed():
    from ashare.control import parse_top10_pages
    trace = []
    pages = ["前十名股东持股情况\n股东名称 报告期内增减 期末持股数量 比例(%) 股东性质\n"
             "甲集团有限公司 0 5,000,000 150.00 国有法人\n乙基金 0 2,000,000 20.00 境内非国有法人\n"
             "丙投资 0 1,0002,000,000 10.00 境内非国有法人"]
    rows = parse_top10_pages(pages, trace)
    assert [r["shareholder_name"] for r in rows] == ["乙基金"]
    decisions = [d for _, _, d in trace]
    assert any(d.startswith("rejected: percentage 150.0") for d in decisions)
    assert any(d.startswith("rejected: two cells run together") for d in decisions)
    assert any(d.startswith("header") for d in decisions)


def test_top10_row_with_its_name_above_the_figures_is_read():
    """Found with inspect-tables on the synthetic corpus: the plain-text reading puts a wrapped name on lines of its
    own, above the figures; v2.0.9 rejected the figures as a line without a name."""
    from ashare.control import parse_top10_pages
    pages = ["前十名股东持股情况\n股东名称 股东性质 持股比例(%) 报告期末持股数量 报告期内增减变动情况 持有有限售条件的股份数量\n"
             "四川省示例投资集团有\n限公司国有法人\n44.49 756,330,000 400,000 0\n"
             "黄军磊境内自然人 1.24 21,080,000 100,000 0\n"
             "单位：股\n1.00 1,000 0 0"]
    rows = parse_top10_pages(pages)
    assert [(r["shareholder_name"], r["shares"]) for r in rows] == [("四川省示例投资集团有限公司", 756_330_000),
                                                                    ("黄军磊", 21_080_000)]
    assert rows[0]["shareholder_nature"] == "国有法人"


# --- A4. Findings as rates (finding 108) ---------------------------------------------------------------------------

def _two_reports_disagreeing(company):
    from helpers import add_disclosure
    from ashare.models import SessionLocal, Disclosure, FinancialFact, SegmentObservation
    add_disclosure(company, "2025年年度报告", "2026-03-30", ann_id="A")
    add_disclosure(company, "2026年第一季度报告", "2026-04-29", ann_id="B")
    s = SessionLocal()
    try:
        a = s.query(Disclosure).filter_by(announcement_id="A").one().id
        b = s.query(Disclosure).filter_by(announcement_id="B").one().id
        for did, rev, assets in ((a, 1_000_000.0, 5_000.0), (b, 10_000_000_000.0, 5_000.0)):
            for metric, v in (("revenue", rev), ("total_assets", assets)):
                s.add(FinancialFact(company_id=company.id, disclosure_id=did, reporting_period="2025-12-31",
                                    period_type="FY", metric=metric, value=v, extraction_method="PDF_TEXT_HEURISTIC",
                                    source_document="x"))
        for name, rev in (("甲", 600_000.0), ("乙", 300_000.0), ("合计", 1_000_000.0)):
            s.add(SegmentObservation(company_id=company.id, disclosure_id=a, reporting_period="2025-12-31",
                                     dimension="PRODUCT", segment_name=name, revenue=rev, is_total=name == "合计",
                                     source="CNINFO", extraction_method="PDF_TEXT_HEURISTIC"))
        s.commit()
    finally:
        s.close()


def test_findings_are_given_as_rates_after_the_checks_are_run(company, tmp_path, monkeypatch):
    from typer.testing import CliRunner
    from ashare.cli import app
    from ashare.crossvalidation import flag_summary, load_validation_summary
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("COLUMNS", "200")
    _two_reports_disagreeing(company)
    from ashare.crossvalidation import cross_validate
    cross_validate()                                   # findings recorded the v2.0.9 way: no saved summary
    summ = flag_summary()
    assert not summ["summary_saved"] and all(r["rate"] is None for r in summ["by_rule"])
    r = CliRunner().invoke(app, ["show-flags"])
    assert "Counts only: rates appear after" in r.output
    r = CliRunner().invoke(app, ["validate-all"])
    assert r.exit_code == 0, r.output
    assert "document pairs compared" in r.output and "segment tables compared" in r.output
    saved = load_validation_summary()
    assert saved["checked"]["document_pairs"] == 2 and saved["checked"]["segment_tables"] == 1
    summ = flag_summary()
    rate = {x["rule"]: x for x in summ["by_rule"]}
    assert rate["EXTRACTION_DISCREPANCY"]["rate"] == "50.0%" and "2 document pairs" in rate["EXTRACTION_DISCREPANCY"]["of"]
    assert rate["SEGMENT_SUM_MISMATCH"]["rate"] == "100.0%"
    assert summ["segment_bands"] == [{"size": "within 10%", "count": 1}]
    assert summ["discrepancy_patterns"] == [{"pattern": "POWER_OF_TEN", "count": 1}]
    r = CliRunner().invoke(app, ["show-flags"])
    assert "rate" in r.output and "Segment mismatches by size" in r.output and "POWER_OF_TEN" in r.output


def test_a_company_run_keeps_its_own_counts(company, tmp_path, monkeypatch):
    """Review round 3: rates for the whole database are not taken from a one-company run."""
    from ashare.crossvalidation import validate_all, load_validation_summary
    monkeypatch.chdir(tmp_path)
    _two_reports_disagreeing(company)
    validate_all("600519")
    assert load_validation_summary() is None and load_validation_summary("600519")["checked"]["document_pairs"] == 2
    validate_all()
    assert load_validation_summary()["companies"] == 1 and load_validation_summary("600519")


# --- A5. Panel coverage (finding 109) ------------------------------------------------------------------------------

def test_panel_names_how_many_companies_have_figures_and_reports(boards, tmp_path, monkeypatch):
    from helpers import add_disclosure
    from ashare.models import SessionLocal, Company
    from ashare.panel import build_panel, coverage_line
    s = SessionLocal()
    try:
        for c in s.query(Company):
            c.status, c.listing_date = "LISTED", "2001-01-01"
        s.commit()
        c = s.query(Company).filter_by(security_code="600519").one()
    finally:
        s.close()
    pdf = tmp_path / "r.pdf"
    pdf.write_bytes(b"%PDF-1.4")
    add_disclosure(c, "2025年年度报告", "2026-03-30", pdf, ann_id="R")
    r = build_panel(["revenue"], "year", "2025-01-01", "2025-12-31", "fiscal")
    cov = r["coverage"]
    assert cov == {"companies": len({x["code"] for x in r["rows"]}), "with_figures": 0, "with_reports": 1}
    line = coverage_line(cov)
    assert line.startswith(f"Financial figures exist for 0 of {cov['companies']:,} companies; periodic reports are "
                           "downloaded for 1.") and "Download periodic reports" in line
    assert "Run 'Extract figures" in coverage_line({"companies": 1, "with_figures": 0, "with_reports": 1})
