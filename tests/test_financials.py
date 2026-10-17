from helpers import make_pdf, add_disclosure
from ashare.financials import (
    _normalise_number, infer_reporting_period, infer_period_type, infer_period,
    _unit_multiplier, _pdf_facts, _xbrl_facts, select_xbrl_facts,
)


def test_normalise_numbers():
    assert _normalise_number("1,234.50") == 1234.5
    assert _normalise_number("(12.5)") == -12.5
    assert _normalise_number("−8") == -8


def test_period_and_unit_inference():
    assert infer_reporting_period("2025年年度报告") == "2025-12-31"
    assert infer_reporting_period("2025年第三季度报告") == "2025-09-30"
    assert infer_reporting_period("2025年半年度报告") == "2025-06-30"
    assert infer_period_type("2025年半年度报告") == "H1"
    assert _unit_multiplier("单位：百万元") == ("CNY_1M", 1_000_000.0)


def test_title_decides_period_over_body():
    # v0.7 read 第一季度 in an annual report's quarterly table as Q1.
    body = "主要会计数据\n分季度主要财务指标 第一季度 第二季度 第三季度 第四季度"
    assert infer_period("2025年年度报告", body) == ("2025-12-31", "FY")


def test_period_fallback_uses_prior_year_for_annual():
    assert infer_period("年度报告", "", "2026-03-28") == ("2025-12-31", "FY")
    assert infer_period("第一季度报告", "", "2026-04-28") == ("2026-03-31", "Q1")


def test_pdf_heuristic(tmp_path):
    path = make_pdf(tmp_path / "r.pdf", [
        "2025年年度报告", "单位：百万元",
        "营业收入 五、61 37,124.00",
        "归属于上市公司股东的净利润 18,000.50",
        "净利润 19,000.25",
        "营业利润率 52.3%",
        "营业利润 25,000.00",
        "在职员工的数量合计 1,000",
        "员工人数 34,000",
    ])
    facts = {f["metric"]: f for f in _pdf_facts(path, "2025年年度报告", None)}
    assert facts["revenue"]["value"] == 37124 * 1_000_000  # note ref 61 skipped
    assert facts["net_profit"]["value"] == 19000.25 * 1_000_000
    assert facts["net_profit_parent"]["value"] == 18000.5 * 1_000_000
    assert facts["operating_profit"]["value"] == 25000 * 1_000_000
    assert facts["employees"]["value"] == 34000  # not scaled by the currency unit
    assert facts["revenue"]["period"] == "2025-12-31"
    assert facts["revenue"]["label"] == "营业收入"


XBRL = b"""<?xml version='1.0'?>
<xbrl xmlns:xbrli='http://www.xbrl.org/2003/instance' xmlns:ix='http://www.xbrl.org/2013/inlineXBRL'
      xmlns:xbrldi='http://xbrl.org/2006/xbrldi'>
 <xbrli:context id='cur'><xbrli:period><xbrli:startDate>2025-01-01</xbrli:startDate><xbrli:endDate>2025-12-31</xbrli:endDate></xbrli:period></xbrli:context>
 <xbrli:context id='prior'><xbrli:period><xbrli:startDate>2024-01-01</xbrli:startDate><xbrli:endDate>2024-12-31</xbrli:endDate></xbrli:period></xbrli:context>
 <xbrli:context id='curI'><xbrli:period><xbrli:instant>2025-12-31</xbrli:instant></xbrli:period></xbrli:context>
 <xbrli:context id='parent'><xbrli:entity><xbrli:segment><xbrldi:explicitMember dimension='s'>ParentCompany</xbrldi:explicitMember></xbrli:segment></xbrli:entity><xbrli:period><xbrli:startDate>2025-01-01</xbrli:startDate><xbrli:endDate>2025-12-31</xbrli:endDate></xbrli:period></xbrli:context>
 <ix:nonFraction name='cas:OperatingRevenue' contextRef='cur' scale='4'>3,712.4</ix:nonFraction>
 <ix:nonFraction name='cas:OperatingRevenue' contextRef='parent'>100</ix:nonFraction>
 <ix:nonFraction name='cas:OperatingRevenue' contextRef='prior' scale='4'>3,000</ix:nonFraction>
 <ix:nonFraction name='cas:NetCashFlowsFromInvestingActivities' contextRef='cur' sign='-'>500</ix:nonFraction>
 <ix:nonFraction name='cas:Assets' contextRef='curI'>9000</ix:nonFraction>
</xbrl>"""


def test_xbrl_extracts_fact():
    data = b"<?xml version='1.0'?><root xmlns:ix='http://www.xbrl.org/2013/inlineXBRL'><ix:nonFraction name='Revenue' contextRef='c1'>37124</ix:nonFraction></root>"
    facts = _xbrl_facts(data, '.xml')
    assert facts and facts[0]['metric'] == 'revenue' and facts[0]['value'] == 37124


def test_xbrl_contexts_scale_sign():
    facts = _xbrl_facts(XBRL, ".xml")
    chosen = {(f["metric"], f["consolidation_scope"]): f for f in select_xbrl_facts(facts, "2025-12-31")}
    assert chosen[("revenue", "CONSOLIDATED_DEFAULT")]["value"] == 37_124_000  # prior year ignored, scale applied
    assert chosen[("revenue", "DIM:ParentCompany")]["value"] == 100
    assert chosen[("investing_cash_flow", "CONSOLIDATED_DEFAULT")]["value"] == -500
    assert chosen[("total_assets", "CONSOLIDATED_DEFAULT")]["value"] == 9000


def test_extract_financials_finds_reports_and_validates(company, tmp_path):
    # v0.7 filtered on kinds the classifier never produced: nothing extracted.
    from ashare.financials import extract_financials, validate_financials
    pdf = make_pdf(tmp_path / "a.pdf", ["2025年年度报告", "单位：元",
                                        "资产总计 1,000.00", "负债合计 400.00", "所有者权益合计 600.00",
                                        "<PAGE>", "分季度主要财务指标 第一季度"])
    add_disclosure(company, "2025年年度报告", "2026-03-30", pdf, ann_id="A1")
    add_disclosure(company, "2025年年度报告摘要", "2026-03-30", pdf, ann_id="A2")
    r = extract_financials("600519")
    assert r["documents"] == 1 and r["facts_inserted"] == 3
    v = validate_financials("600519")
    assert v["passed"] == 1 and v["failed"] == 0
