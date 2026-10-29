"""v2.0.8: correct data first. Each test reproduces a live finding (70 to 95) or a fault found when the plan was
checked against the code (docs/plan_v2.0.8_and_visualisation.md, section 10), and fails on v2.0.7."""
import json
from pathlib import Path

import httpx
import pytest

from ashare.http import set_default_transport


# --- A. the universe and panels (findings 92, 93, 71) ------------------------------------------------------------

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


def test_listing_date_used_when_the_history_was_built_before_it(company):
    """Finding 92: a derived history without a start must not hide the company's listing date."""
    from ashare.security_master import rebuild_security_history, universe_at
    rebuild_security_history()                       # built while the company has no listing date
    rep = {}
    assert universe_at("2025-12-31", report=rep) == []
    assert rep["excluded_no_listing_date"] == 1
    _set("600519", listing_date="2001-08-27", status="LISTED")
    rep = {}
    got = universe_at("2025-12-31", report=rep)
    assert [r["current_code"] for r in got] == ["600519"]
    assert rep["excluded_no_listing_date"] == 0
    assert universe_at("2000-12-31") == []           # not yet listed


def test_update_rebuilds_history_and_marks_companies_in_neither_list(company, monkeypatch):
    from ashare.storage import upsert_ashares
    from ashare.models import SessionLocal, Company
    from ashare.security_master import rebuild_security_history, universe_at
    from ashare import exchange_lists, pipeline
    upsert_ashares([{"code": "000999", "exchange": "SZSE", "legal_name_cn": "某某股份有限公司", "short_name_cn": "某某股份",
                     "org_id": "x"},
                    {"code": "000998", "exchange": "SZSE", "legal_name_cn": "退市甲", "short_name_cn": "甲退",
                     "org_id": "y"}])
    rebuild_security_history()
    info = exchange_lists.ExchangeListing({"600519": {"name": "贵州茅台", "listing_date": "2001-08-27",
                                                      "source": "sse_main"}})
    info.lists = {k: {"name": n, "rows": m, "dated": m, "error": None, "whole": True} for k, n, m in exchange_lists.LISTS}
    info.complete = True
    monkeypatch.setattr(exchange_lists, "exchange_listing_info", lambda *a, **k: info)
    counts = pipeline.enrich_listing_status()
    assert counts["listing_dates_added"] == 1
    assert counts["history_rebuilt"] >= 1
    assert counts["NOT_IN_EXCHANGE_LIST"] == 1
    s = SessionLocal()
    try:
        st = {c.security_code: c.status for c in s.query(Company)}
    finally:
        s.close()
    assert st == {"600519": "LISTED", "000999": "NOT_IN_EXCHANGE_LIST", "000998": "DELISTED"}
    assert [r["current_code"] for r in universe_at("2025-12-31")] == ["600519"]


def test_fiscal_year_not_ended_is_reported(company):
    """Finding 93: a fiscal-year row for a year that has not ended is named, with the rows lacking figures."""
    from ashare.panel import build_panel
    _set("600519", listing_date="2001-08-27", status="LISTED")
    r = build_panel(["revenue"], "year", "2026-01-01", "2026-10-24", "fiscal")
    assert r["fiscal_years_not_ended"] == [2026]
    assert r["rows_without_financials"] == len(r["rows"]) == 1
    r = build_panel(["revenue"], "year", "2025-01-01", "2025-12-31", "fiscal")
    assert r["fiscal_years_not_ended"] == []


def test_desktop_panel_form_ends_with_the_last_complete_year():
    pytest.importorskip("tkinter")
    from datetime import date
    from ashare.gui import SECTIONS
    form = next(a for p in SECTIONS for a in p["actions"] if a["command"] == "build-panel")
    end = next(f for f in form["fields"] if f["key"] == "end")
    assert end["default"] == f"{date.today().year - 1}-12-31"


# --- B. financial figures (findings 84 to 87) ---------------------------------------------------------------------

@pytest.mark.parametrize("title,kind", [
    ("关于2025年年度报告的更正公告", "report_notice"),
    ("2025年年度报告披露提示性公告", "report_notice"),
    ("关于2025年半年度报告的补充公告", "report_notice"),
    ("关于2025年年度报告摘要的更正公告", "report_notice"),
    ("2025年年度报告（更正后）", "annual_report"),
    ("2025年年度报告（修订版）", "annual_report"),
    ("2025年年度报告", "annual_report"),
    ("2025年年度报告摘要", "annual_report_summary"),
    ("2026年第一季度报告", "quarterly_report"),
    ("关于2025年年度报告的问询函", "regulatory_enquiry"),
])
def test_notices_about_reports_are_not_reports(title, kind):
    from ashare.disclosures import classify_title
    assert classify_title(title) == kind


def test_stored_kinds_are_reclassified(company):
    from helpers import add_disclosure
    from ashare.models import SessionLocal, Disclosure
    from ashare.disclosures import reclassify_report_kinds
    add_disclosure(company, "2025年年度报告披露提示性公告", "2026-03-31", ann_id="N1")
    s = SessionLocal()
    try:
        s.query(Disclosure).filter_by(announcement_id="N1").one().kind = "annual_report"    # as v2.0.7 stored it
        s.commit()
    finally:
        s.close()
    assert reclassify_report_kinds() == 1
    s = SessionLocal()
    try:
        assert s.query(Disclosure).filter_by(announcement_id="N1").one().kind == "report_notice"
    finally:
        s.close()


def test_unit_not_taken_from_an_unrelated_earlier_table():
    """Finding 84: a key-figures table without its own unit must not borrow 万元 from pages earlier."""
    from ashare.financials import pdf_facts_from_pages
    pages = ["募集资金使用情况\n单位：万元\n募集资金总额 120,000.00",
             "第二节 公司简介",
             "主要会计数据和财务指标\n营业收入 1,234,567,890.12 1,100,000,000.00"]
    f = {x["metric"]: x for x in pdf_facts_from_pages(pages, "2025年年度报告", "2025-12-31")}
    assert f["revenue"]["value"] == pytest.approx(1234567890.12)
    assert f["revenue"]["unit"] == "CNY_ASSUMED"


def test_unit_declared_on_the_same_page_still_applies():
    from ashare.financials import pdf_facts_from_pages
    pages = ["主要会计数据和财务指标\n单位：万元\n营业收入 123,456.78 110,000.00"]
    f = {x["metric"]: x for x in pdf_facts_from_pages(pages, "2025年年度报告", "2025-12-31")}
    assert f["revenue"]["value"] == pytest.approx(1234567800.0)
    assert f["revenue"]["unit"] == "CNY_10K"


def test_unit_carried_from_the_end_of_the_previous_page():
    from ashare.financials import pdf_facts_from_pages
    pages = ["其他内容\n单位：千元 币种：人民币", "营业收入 1,234.56 1,000.00"]
    f = {x["metric"]: x for x in pdf_facts_from_pages(pages, "2025年年度报告", "2025-12-31")}
    assert f["revenue"]["value"] == pytest.approx(1234560.0)


@pytest.mark.parametrize("raw", ["22,103", "1,355.2"])
def test_amounts_in_yuan_need_two_decimals(raw):
    """Finding 85: figures cut at a separator or a line break are not read."""
    from ashare.cas import parse_statement_items
    pages = [f"合并资产负债表\n单位：元\n项目 附注 期末余额 期初余额\n货币资金 {raw} 1,000.00\n"
             "短期借款 7,102,914.31 6,000,000.00"]
    got = {i["metric"]: i["value"] for i in parse_statement_items(pages)}
    assert "cash" not in got
    assert got.get("short_term_borrowings") == pytest.approx(7102914.31)


def test_amounts_in_ten_thousands_may_have_fewer_decimals():
    from ashare.cas import parse_statement_items
    pages = ["合并资产负债表\n单位：万元\n货币资金 22,103 1,000"]
    got = {i["metric"]: i["value"] for i in parse_statement_items(pages)}
    assert got["cash"] == pytest.approx(221030000.0)


def test_glued_note_number_resolved_by_the_other_reading():
    """Finding 85: '1' + '1,791,960,892.40' is a well-formed number; only another reading can tell."""
    from ashare.numbers import glue_split
    assert glue_split("11,791,960,892.40", "1,791,960,892.40") == "1,791,960,892.40"
    assert glue_split("452,156,535.48", "2,156,535.48") == "2,156,535.48"
    assert glue_split("227,102,914.31", "7,102,914.31") == "7,102,914.31"
    assert glue_split("1,791,960,892.40", "1,791,960,892.40") is None          # the same
    assert glue_split("1,234.00", "5,678.00") is None                          # unrelated
    assert glue_split("123,456,789.00", "56,789.00") is None                   # more than two digits


def test_dual_run_prefers_the_reading_without_a_glued_note(tmp_path, monkeypatch):
    from ashare import parsers
    spec_t, spec_l = parsers.PARSERS["statements"], parsers.PARSERS["statements@layout"]
    runs = {"statements": [{"metric": "equity", "value": 11791960892.40, "raw_value": "11,791,960,892.40"}],
            "statements@layout": [{"metric": "equity", "value": 1791960892.40, "raw_value": "1,791,960,892.40"}]}
    monkeypatch.setattr(parsers, "pages_for", lambda path, inp, cache=None: ["x"])
    for spec in (spec_t, spec_l):
        monkeypatch.setattr(spec, "run", lambda pages, meta, n=spec.name: [dict(r) for r in runs[n]])
    # make the text variant primary, to show the rule is not just "layout wins"
    monkeypatch.setattr("ashare.evaluation.calibrated_confidence",
                        lambda name, prior: 0.9 if name == "statements" else 0.5)
    (tmp_path / "a.pdf").write_bytes(b"%PDF-1.4")
    rows, info = parsers.dual_run("statements", tmp_path / "a.pdf", {})
    assert rows[0]["value"] == pytest.approx(1791960892.40)
    assert rows[0]["_glue"] == "11,791,960,892.40"
    assert info["glue_resolved"] == 1


def test_power_of_ten_between_readers_of_one_document():
    from ashare.financials import reconcile_readings
    facts = [{"metric": "revenue", "value": 123456.78, "unit": "CNY_ASSUMED", "method": "PDF_TEXT_HEURISTIC"},
             {"metric": "revenue", "value": 1234567800.0, "unit": "CNY", "method": "PDF_STATEMENT_TABLE"},
             {"metric": "net_profit", "value": 5.0, "unit": "CNY", "method": "PDF_TEXT_HEURISTIC"}]
    out = reconcile_readings(facts)
    assert out[0]["value"] == pytest.approx(1234567800.0) and out[0]["unit"] == "CNY"
    assert "rescaled" in out[0]["extraction_note"]
    assert out[2]["value"] == 5.0


def _fact(s, company_id, did, value, metric="revenue", method="PDF_TEXT_HEURISTIC"):
    from ashare.models import FinancialFact
    s.add(FinancialFact(company_id=company_id, disclosure_id=did, reporting_period="2025-12-31", period_type="FY",
                        metric=metric, value=value, extraction_method=method, source_document="x"))


def test_same_day_difference_is_not_explained_by_a_restatement(company):
    """Finding 86."""
    from helpers import add_disclosure
    from ashare.models import SessionLocal, Disclosure, RegulatoryEvent, ValidationFlag
    from ashare.crossvalidation import cross_validate
    add_disclosure(company, "2025年年度报告", "2026-04-29", ann_id="A")
    add_disclosure(company, "2025年年度报告（更正后）", "2026-04-29", ann_id="B")
    s = SessionLocal()
    try:
        a = s.query(Disclosure).filter_by(announcement_id="A").one().id
        b = s.query(Disclosure).filter_by(announcement_id="B").one().id
        _fact(s, company.id, a, 9835474916.5)
        _fact(s, company.id, b, 2544411519.38)
        s.add(RegulatoryEvent(company_id=company.id, event_id="R1", event_type="ACCOUNTING_RESTATEMENT", legal_classification="ACCOUNTING", status="ANNOUNCED", event_date="2026-04-29",
                              announcement_date="2026-04-29", source="CNINFO", extraction_method="TITLE"))
        s.commit()
    finally:
        s.close()
    counts = cross_validate("600519")
    assert counts["flags"].get("RESTATEMENT_EXPLAINED", 0) == 0
    assert counts["flags"]["CORRECTED_REPORT"] == 1
    s = SessionLocal()
    try:
        f = s.query(ValidationFlag).filter_by(rule="CORRECTED_REPORT").one()
        assert f.severity == "INFO"
    finally:
        s.close()


def test_digit_glue_named_in_a_discrepancy(company):
    from helpers import add_disclosure
    from ashare.models import SessionLocal, Disclosure, ValidationFlag
    from ashare.crossvalidation import cross_validate
    add_disclosure(company, "2025年年度报告", "2026-03-31", ann_id="A")
    add_disclosure(company, "2025年年度报告（更正后）", "2026-06-13", ann_id="B")
    s = SessionLocal()
    try:
        a = s.query(Disclosure).filter_by(announcement_id="A").one().id
        b = s.query(Disclosure).filter_by(announcement_id="B").one().id
        _fact(s, company.id, a, 11791960892.40, "equity", "PDF_STATEMENT_TABLE")
        _fact(s, company.id, b, 1791960892.40, "equity", "PDF_STATEMENT_TABLE")
        s.commit()
    finally:
        s.close()
    cross_validate("600519")
    s = SessionLocal()
    try:
        f = s.query(ValidationFlag).filter(ValidationFlag.rule.in_(("EXTRACTION_DISCREPANCY", "CORRECTED_REPORT"))).one()
        assert json.loads(f.details)["pattern"] == "DIGITS_GLUED"
    finally:
        s.close()


def test_reextraction_removes_facts_no_longer_read(company, tmp_path):
    """A value the new reader rejects must not linger from the old one."""
    from helpers import make_pdf, add_disclosure
    from ashare.models import SessionLocal, Disclosure, FinancialFact
    from ashare.financials import extract_financials
    pdf = make_pdf(tmp_path / "r.pdf", ["2025年年度报告", "主要会计数据和财务指标", "单位：元",
                                        "营业收入 1,234,567,890.12 1,100,000,000.00"])
    add_disclosure(company, "2025年年度报告", "2026-03-31", pdf, ann_id="R")
    s = SessionLocal()
    try:
        did = s.query(Disclosure).filter_by(announcement_id="R").one().id
        _fact(s, company.id, did, 1.0, "inventory")              # an old misreading
        s.commit()
    finally:
        s.close()
    extract_financials("600519")
    s = SessionLocal()
    try:
        metrics = {f.metric for f in s.query(FinancialFact).filter_by(disclosure_id=did)}
    finally:
        s.close()
    assert "inventory" not in metrics and "revenue" in metrics


def test_notice_documents_lose_their_facts(company, tmp_path):
    from helpers import add_disclosure
    from ashare.models import SessionLocal, Disclosure, FinancialFact
    from ashare.financials import extract_financials
    p = tmp_path / "n.pdf"
    p.write_bytes(b"%PDF-1.4")
    add_disclosure(company, "2025年年度报告披露提示性公告", "2026-03-31", p, ann_id="N")
    s = SessionLocal()
    try:
        d = s.query(Disclosure).filter_by(announcement_id="N").one()
        d.kind = "annual_report"
        _fact(s, company.id, d.id, 1.0)
        s.commit()
        did = d.id
    finally:
        s.close()
    r = extract_financials("600519")
    assert r["notice_facts_removed"] == 1
    s = SessionLocal()
    try:
        assert s.query(FinancialFact).filter_by(disclosure_id=did).count() == 0
    finally:
        s.close()


# --- C. targeted reading, progress and resume (findings 76, 77, 79, 82) -------------------------------------------

LAYOUT_B = ["（二）前10名股东持股情况", "单位：股",
            "股东名称 股东性质 持股比例 报告期末持股数量 报告期内增减变动情况 持有有限售条件的股份数量 "
            "持有无限售条件的股份数量 质押、标记或冻结情况",
            "西安投资控股有限公司 国有法人 26.80% 1,370,083,991 0 0 1,370,083,991 不适用 0",
            "陕西煤业化工集团有限责任公司 国有法人 16.76% 856,800,000 46 0 856,800,000 质押 100,000",
            "上述股东关联关系或一致行动的说明 无"]


def _long_report(path, filler_pages=30):
    from helpers import make_pdf
    lines = ["2025年年度报告", "<PAGE>"]
    for i in range(filler_pages):
        lines += [f"第{i + 1}页 公司治理与经营情况讨论 正文内容", "<PAGE>"]
    lines += LAYOUT_B
    return make_pdf(path, lines)


def test_targeted_reading_lays_out_only_the_section_pages(tmp_path):
    pytest.importorskip("pypdfium2")
    from ashare.reportreader import ReportReader
    from ashare.control import parse_top10_pages
    pdf = _long_report(tmp_path / "r.pdf")
    rr = ReportReader(pdf)
    pages = rr.pages("layout", ["top10"])
    assert len(pages) == 32                              # full length; page numbers unchanged
    assert rr.layout_pages_read <= 3
    targeted = parse_top10_pages(pages)
    from ashare.layout import layout_text_pages
    full = parse_top10_pages(layout_text_pages(pdf))
    assert [(r["shareholder_name"], r["ownership_pct"], r["page"]) for r in targeted] == \
        [(r["shareholder_name"], r["ownership_pct"], r["page"]) for r in full]
    rr.close()


def test_targeted_reading_falls_back_to_the_whole_document(tmp_path):
    pytest.importorskip("pypdfium2")
    from helpers import make_pdf
    from ashare.reportreader import ReportReader
    pdf = make_pdf(tmp_path / "x.pdf", ["没有任何表格", "<PAGE>", "第二页"])
    rr = ReportReader(pdf)
    pages = rr.pages("text", ["top10"])
    assert rr.fallback_full and len(pages) == 2 and "第二页" in pages[1]
    rr.close()


def test_top_holders_resume_and_report_progress(company, tmp_path):
    from helpers import make_pdf, add_disclosure
    from ashare.control import extract_top_holders
    from ashare.models import SessionLocal, OwnershipObservation
    pdf = make_pdf(tmp_path / "q.pdf", ["2026年第一季度报告"] + LAYOUT_B)
    add_disclosure(company, "2026年第一季度报告", "2026-04-29", pdf, ann_id="Q1")
    lines = []
    r = extract_top_holders("600519", progress=lines.append)
    assert r["to_read"] == 1 and r["reports"] == 1
    assert any("1 document(s) to read" in x for x in lines) and any("1 of 1 documents" in x for x in lines)
    r = extract_top_holders("600519")
    assert r["to_read"] == 0 and r["already_read"] == 1
    r = extract_top_holders("600519", again=True)
    assert r["to_read"] == 1
    s = SessionLocal()
    try:
        pct = sorted(o.ownership_pct for o in s.query(OwnershipObservation))
    finally:
        s.close()
    assert pct == [16.76, 26.8]


def test_progress_line_counts_documents_not_readings():
    from ashare.extractstate import Progress
    lines = []
    p = Progress(4, lines.append, every=2)
    for _ in range(4):
        p.step()
    assert lines[-1].startswith("  4 of 4 documents") and "per second" not in "".join(lines)


def test_extractor_versions_force_a_reread():
    from ashare.extractstate import VERSIONS
    assert VERSIONS["top_holders"].endswith("-2") and VERSIONS["segments"].endswith("-2")
    assert VERSIONS["control"].endswith("-2")


# --- D. segments and control (findings 83, 78, 89) ----------------------------------------------------------------

def test_segment_table_continues_over_a_page_break():
    """Finding 83: the dimension and unit carry over; the next page has no heading."""
    from ashare.segments import parse_segment_pages, _merge
    pages = ["营业收入构成\n单位：元\n项目 2025年 金额 占营业收入比重\n营业收入合计 300.00 100%\n分产品\n"
             "甲产品 100.00 33.33%\n乙产品 100.00 33.33%",
             "丙产品 100.00 33.34%\n分地区\n境内 200.00 66.67%\n境外 100.00 33.33%",
             "第四节 公司治理\n董事会 9.00 1.00"]
    rows = _merge(parse_segment_pages(pages))
    prod = {r["segment_name"]: r["revenue"] for r in rows if r["dimension"] == "PRODUCT"}
    assert prod == {"甲产品": 100.0, "乙产品": 100.0, "丙产品": 100.0}
    assert {r["segment_name"] for r in rows if r["dimension"] == "REGION"} == {"境内", "境外"}
    assert not any(r["segment_name"] == "董事会" for r in rows)


def test_subtotals_and_breakdowns_are_not_segments():
    from ashare.segments import parse_segment_pages, _merge
    pages = ["营业收入构成\n单位：元\n分行业\n白酒 200.00 80%\n其中：茅台酒 150.00 60%\n其他 50.00 20%\n小计 250.00 100%"]
    rows = _merge(parse_segment_pages(pages))
    names = {r["segment_name"]: r for r in rows if r["dimension"] == "INDUSTRY"}
    assert set(names) == {"白酒", "其他", "小计"}
    assert names["小计"]["is_total"] is True


def test_margin_table_kind_recorded_and_not_compared_with_revenue(company):
    from ashare.segments import parse_segment_pages, _merge
    pages = ["主营业务分行业、分产品、分地区情况\n单位：元\n分行业 营业收入 营业成本 毛利率(%)\n"
             "白酒 100.00 10.00 90.00% 5% 5% 1\n"]
    rows = _merge(parse_segment_pages(pages))
    assert rows[0]["table_kind"] == "margin"
    from ashare.models import SessionLocal, SegmentObservation, FinancialFact
    from ashare.crossvalidation import cross_validate
    s = SessionLocal()
    try:
        s.add(SegmentObservation(company_id=company.id, reporting_period="2025-12-31", dimension="INDUSTRY",
                                 segment_name="白酒", revenue=1e8, source="CNINFO", extraction_method="X",
                                 table_kind="margin", is_total=False))
        s.add(FinancialFact(company_id=company.id, reporting_period="2025-12-31", period_type="FY", metric="revenue",
                            value=2e8, extraction_method="PDF_TEXT_HEURISTIC", source_document="x"))
        s.commit()
    finally:
        s.close()
    counts = cross_validate("600519")
    assert counts["flags"].get("SEGMENT_SUM_MISMATCH", 0) == 0
    # the same row from the composition table, which lists every segment, is compared and flagged
    s = SessionLocal()
    try:
        s.query(SegmentObservation).update({"table_kind": "composition"})
        s.commit()
    finally:
        s.close()
    assert cross_validate("600519")["flags"]["SEGMENT_SUM_MISMATCH"] == 1


SZSE_CONTROL = """2、控股股东情况
控股股东性质：地方国有控股
控股股东类型：法人
控股股东名称 法定代表人/单位负责人 成立日期 组织机构代码 主要经营业务
深圳市投资控股有限公司 何建锋 2004年10月13日 91440300767569153C 投资
3、公司实际控制人及其一致行动人
实际控制人性质：地方国资管理机构
实际控制人类型：法人
实际控制人名称 法定代表人/单位负责人 成立日期 组织机构代码 主要经营业务
深圳市人民政府国有资产监督管理委员会 王勇健 2004年06月01日 11440300K317280672 国资监管
实际控制人报告期内变更"""

SZSE_PERSON = """2、控股股东情况
控股股东性质：自然人控股
控股股东类型：自然人
控股股东姓名 国籍 是否取得其他国家或地区居留权
王传福 中国 否
3、公司实际控制人及其一致行动人
实际控制人性质：境内自然人
实际控制人类型：自然人
实际控制人姓名 与实际控制人关系 国籍 是否取得其他国家或地区居留权
王传福 本人 中国 否
吕向阳 一致行动（含协议、亲属、同一控制） 中国 否
主要职业及职务 董事长"""

SSE_CONTROL = """（二）控股股东情况
1 法人
√适用 □不适用
名称 中国贵州茅台酒厂（集团）有限责任公司
单位负责人或法定代表人 丁雄军
成立日期 1997-01-20
（三）实际控制人情况
1 法人
√适用 □不适用
名称 贵州省人民政府国有资产监督管理委员会
单位负责人或法定代表人 张三"""

SSE_PERSON = """（二）控股股东情况
2 自然人
√适用 □不适用
姓名 李四
国籍 中国
是否取得其他国家或地区居留权 否
（三）实际控制人情况
2 自然人
√适用 □不适用
姓名 李四
国籍 中国"""


@pytest.mark.parametrize("text,holder,controller,typ", [
    (SZSE_CONTROL, "深圳市投资控股有限公司", "深圳市人民政府国有资产监督管理委员会", "LOCAL_SOE"),
    (SZSE_PERSON, "王传福", "王传福、吕向阳", "PRIVATE"),
    (SSE_CONTROL, "中国贵州茅台酒厂（集团）有限责任公司", "贵州省人民政府国有资产监督管理委员会", "LOCAL_SOE"),
    (SSE_PERSON, "李四", "李四", "PRIVATE"),
])
def test_controller_in_both_exchanges_layouts(text, holder, controller, typ):
    """Findings 78 and 89."""
    from ashare.control import parse_control_text, classify_ownership
    r = parse_control_text([text])
    assert r["controlling_shareholder"] == holder
    assert r["actual_controller"] == controller
    assert classify_ownership(r["actual_controller"], r["controller_nature"])[0] == typ


def test_a_heading_is_never_a_controller():
    from ashare.control import parse_control_text
    text = "3、公司实际控制人及其一致行动人\n实际控制人姓名 与本公司的关系 国籍\n"
    assert parse_control_text([text])["actual_controller"] is None


def test_no_controller_statement():
    from ashare.control import parse_control_text
    r = parse_control_text(["3、公司实际控制人及其一致行动人\n实际控制人性质：无实际控制人\n实际控制人类型：不存在"])
    assert r["no_actual_controller"] and r["actual_controller"] is None


# --- E. installer and findings display (findings 74, 91) ----------------------------------------------------------

def test_installer_checks_for_a_running_copy():
    nsi = (Path(__file__).resolve().parents[1] / "packaging" / "installer.nsi").read_text(encoding="utf-8")
    assert "Function CheckRunning" in nsi and "FileOpen" in nsi and "AShareScraper.exe" in nsi
    assert "ashare-cli.exe" in nsi and "Call CheckRunning" in nsi


def test_findings_summary_and_export(company, tmp_path):
    from ashare.models import SessionLocal, ValidationFlag
    from ashare.crossvalidation import flag_summary, export_flags
    s = SessionLocal()
    try:
        for i in range(3):
            s.add(ValidationFlag(rule="SEGMENT_SUM_MISMATCH", severity="WARN", layer="segments",
                                 company_id=company.id, table_name="segment_observations", row_ids=f"[{i}]",
                                 details=json.dumps({"x": i})))
        s.add(ValidationFlag(rule="OWNERSHIP_TYPE_UNKNOWN", severity="INFO", layer="control", company_id=company.id,
                             table_name="control_observations", row_ids="[9]", details="{}"))
        s.commit()
    finally:
        s.close()
    summ = flag_summary()
    assert summ["total"] == 4
    assert summ["by_rule"][0] == {"rule": "SEGMENT_SUM_MISMATCH", "severity": "WARN", "count": 3}
    assert summ["by_company"][0]["code"] == "600519"
    out = export_flags(str(tmp_path / "f.csv"))
    text = Path(out).read_text(encoding="utf-8-sig")
    assert text.splitlines()[0].startswith("id,code,severity,rule") and text.count("600519") == 4


def test_show_flags_defaults_to_the_summary(company):
    from typer.testing import CliRunner
    from ashare.cli import app
    from ashare.models import SessionLocal, ValidationFlag
    r = CliRunner().invoke(app, ["show-flags"])
    assert r.exit_code == 0 and "No findings recorded" in r.output
    s = SessionLocal()
    try:
        s.add(ValidationFlag(rule="X_RULE", severity="WARN", layer="l", company_id=company.id, table_name="t",
                             row_ids="[1]", details="{}"))
        s.commit()
    finally:
        s.close()
    r = CliRunner().invoke(app, ["show-flags"])
    assert r.exit_code == 0 and "Findings by rule" in r.output and "600519" in r.output
    r = CliRunner().invoke(app, ["show-flags", "--details"])
    assert "X_RULE" in r.output and "600519" in r.output


# --- F. price sources (finding 73) --------------------------------------------------------------------------------

TENCENT = {"code": 0, "msg": "", "data": {"sh600519": {"day": [
    ["2026-10-08", "1450.00", "1460.50", "1465.00", "1440.10", "32155.000"],
    ["2026-10-09", "1460.50", "1455.00", "1470.00", "1450.00", "28100.000"]]}}}


def test_tencent_bars(company):
    from ashare.market import fetch_tencent_bars
    from ashare.models import SessionLocal, Company
    seen = []

    def handler(request):
        seen.append(str(request.url))
        return httpx.Response(200, json=TENCENT)
    set_default_transport(httpx.MockTransport(handler))
    try:
        s = SessionLocal()
        c = s.query(Company).filter_by(security_code="600519").one()
        s.close()
        bars = fetch_tencent_bars(c, "2026-10-01", "2026-10-10")
    finally:
        set_default_transport(None)
    assert "param=sh600519%2Cday%2C2026-10-01%2C2026-10-10" in seen[0]
    assert [(b["trade_date"], b["close"], b["volume"]) for b in bars] == [("2026-10-08", 1460.5, 32155.0),
                                                                          ("2026-10-09", 1455.0, 28100.0)]
    assert bars[0]["source"] == "TENCENT_PUBLIC" and bars[0]["volume_unit"] == "LOTS_100_SHARES"
    assert bars[1]["prev_close"] == 1460.5


def test_acquire_with_a_chosen_provider(company):
    from ashare.market import acquire_market_data
    set_default_transport(httpx.MockTransport(lambda r: httpx.Response(200, json=TENCENT)))
    try:
        r = acquire_market_data("600519", "2026-10-01", "2026-10-10", provider="tencent")
    finally:
        set_default_transport(None)
    assert r["bars_inserted"] == 2 and r["provider"] == "tencent"
    with pytest.raises(ValueError):
        acquire_market_data("600519", "2026-10-01", "2026-10-10", provider="nowhere")


def test_price_source_test_reports_each_provider(company):
    from ashare.market import diagnose_prices

    def handler(request):
        if "eastmoney" in request.url.host:
            return httpx.Response(502)
        return httpx.Response(200, json=TENCENT)
    set_default_transport(httpx.MockTransport(handler))
    try:
        r = diagnose_prices("600519", days=30)
    finally:
        set_default_transport(None)
    by = {x["provider"]: x for x in r["providers"]}
    assert by["eastmoney"]["ok"] is False and "502" in by["eastmoney"]["error"]
    assert by["tencent"]["ok"] is True and by["tencent"]["bars"] == 2
    assert r["suggestion"] == "tencent"


def test_daily_update_backfill_follows_the_setting(company, monkeypatch):
    from ashare import ops
    monkeypatch.setenv("ASHARE_PRICE_SOURCE", "none")
    calls = []
    monkeypatch.setattr("ashare.market.fetch_eastmoney_snapshot", lambda *a, **k: calls.append("snap") or [])
    r = ops.update_prices("2026-10-28")
    assert calls == [] and r["skipped"].startswith("price source is 'none'")


def test_backfill_stops_after_three_refused_companies(db, monkeypatch):
    from ashare.storage import upsert_ashares
    from ashare import ops
    upsert_ashares([{"code": f"60000{i}", "exchange": "SSE", "legal_name_cn": f"公司{i}", "short_name_cn": f"公司{i}",
                     "org_id": str(i)} for i in range(6)])
    monkeypatch.setenv("ASHARE_PRICE_SOURCE", "eastmoney")
    monkeypatch.setattr("ashare.market.fetch_eastmoney_snapshot", lambda *a, **k: (_ for _ in ()).throw(
        RuntimeError("HTTP 502")))
    asked = []

    def refuse(company, start, end, adjust="none"):
        asked.append(company.security_code)
        raise httpx.HTTPStatusError("502", request=httpx.Request("GET", "https://x"), response=httpx.Response(502))
    monkeypatch.setattr("ashare.market.fetch_eastmoney_bars", refuse)
    r = ops.update_prices("2026-10-28")
    assert len(asked) == 3
    assert "refused" in r["backfill_stopped"]


def test_imported_prices_preferred_over_any_public_feed(company):
    from ashare.models import SessionLocal, MarketBar
    from ashare.valuation import _closes
    s = SessionLocal()
    try:
        for src, close in (("CSV_IMPORT", 11.0), ("TENCENT_PUBLIC", 10.0), ("EASTMONEY_PUBLIC", 12.0)):
            s.add(MarketBar(company_id=company.id, trade_date="2026-10-08", close=close, adjustment="none",
                            source=src))
        s.commit()
        assert _closes(s, company.id) == [("2026-10-08", 11.0)]
    finally:
        s.close()


@pytest.mark.parametrize("seed", [3, 7, 11, 19])
def test_targeted_reading_matches_full_reading_on_the_synthetic_corpus(tmp_path, seed):
    """Every table family gives the same records from the section pages as from the whole document."""
    pytest.importorskip("pypdfium2")
    import random
    from ashare.corpus import _annual_report, _write_pdf
    from ashare.parsers import dual_run
    from ashare.reportreader import ReportReader
    title, pages, _ = _annual_report(random.Random(seed), 1)
    pdf = tmp_path / f"ar{seed}.pdf"
    _write_pdf(pdf, pages)
    families = {"top10": ["top10", "top10_tradable"], "top10_tradable": ["top10", "top10_tradable"],
                "segments": ["segments"], "human_capital": ["human_capital"], "subsidiaries": ["subsidiaries"],
                "roster": ["roster"]}
    strip = lambda rows: sorted(json.dumps({k: v for k, v in r.items() if not k.startswith("_")}, sort_keys=True,  # noqa
                                           ensure_ascii=False, default=str) for r in rows)
    with ReportReader(pdf) as rr:
        for fam, sections in families.items():
            full, _ = dual_run(fam, pdf, {"title": title})
            part, _ = dual_run(fam, pdf, {"title": title}, reader=rr, sections=sections)
            assert strip(part) == strip(full), fam
        assert not rr.fallback_full and rr.layout_pages_read < rr.n
    from ashare.control import parse_control_text
    from ashare.layout import layout_text_pages
    with ReportReader(pdf) as rr:
        assert parse_control_text(rr.pages("layout", ["control"])) == parse_control_text(layout_text_pages(pdf))


def test_update_rebuilds_a_history_left_stale_by_an_earlier_update(company, monkeypatch):
    """The author's case: v2.0.7 added the dates, the history had been built before; nothing changes now."""
    from ashare.security_master import rebuild_security_history
    from ashare.models import SessionLocal, SecurityHistory
    from ashare import exchange_lists, pipeline
    rebuild_security_history()
    _set("600519", listing_date="2001-08-27", status="LISTED")
    info = exchange_lists.ExchangeListing({"600519": {"name": "贵州茅台", "listing_date": "2001-08-27",
                                                      "source": "sse_main"}})
    info.lists = {k: {"name": n, "rows": m, "dated": m, "error": None, "whole": True} for k, n, m in exchange_lists.LISTS}
    info.complete = True
    monkeypatch.setattr(exchange_lists, "exchange_listing_info", lambda *a, **k: info)
    counts = pipeline.enrich_listing_status()
    assert counts["listing_dates_added"] == 0 and counts["history_rebuilt"] == 1
    s = SessionLocal()
    try:
        assert {h.valid_from for h in s.query(SecurityHistory)} == {"2001-08-27"}
    finally:
        s.close()


def test_history_rebuild_with_a_warning_imposed_and_lifted_the_same_day(company):
    """v2.0.8 live fault: two risk-warning events on one date (one imposed, one lifted) made the sort compare None
    with 'ST', and "Update the company list" failed with a TypeError."""
    from ashare.models import SessionLocal, RegulatoryEvent
    from ashare.security_master import rebuild_security_history, universe_at
    _set("600519", listing_date="2001-08-27", status="LISTED")
    s = SessionLocal()
    try:
        for i, st in enumerate(("IMPOSED", "LIFTED")):
            s.add(RegulatoryEvent(company_id=company.id, event_id=f"W{i}", event_type="DELISTING_RISK",
                                  event_subtype="OTHER_RISK_WARNING", legal_classification="ADMINISTRATIVE",
                                  status=st, event_date="2024-05-06", announcement_date="2024-05-06",
                                  source="CNINFO", extraction_method="TITLE"))
        s.commit()
    finally:
        s.close()
    assert rebuild_security_history()["companies"] == 1
    assert [r["current_code"] for r in universe_at("2025-12-31")] == ["600519"]


def test_update_survives_a_failed_history_rebuild(company, monkeypatch):
    from ashare import exchange_lists, pipeline, security_master
    info = exchange_lists.ExchangeListing({"600519": {"name": "贵州茅台", "listing_date": "2001-08-27",
                                                      "source": "sse_main"}})
    info.lists = {k: {"name": n, "rows": m, "dated": m, "error": None, "whole": True} for k, n, m in exchange_lists.LISTS}
    info.complete = True
    monkeypatch.setattr(exchange_lists, "exchange_listing_info", lambda *a, **k: info)
    monkeypatch.setattr(security_master, "rebuild_security_history",
                        lambda **k: (_ for _ in ()).throw(TypeError("boom")))
    counts = pipeline.enrich_listing_status()
    assert counts["listing_dates_added"] == 1 and counts["history_rebuilt"] == 0
    assert "Build listing history" in counts["history_note"] and "boom" in counts["history_note"]
