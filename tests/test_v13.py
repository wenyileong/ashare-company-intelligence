"""v1.3: R&D, human capital and ESG."""
from helpers import make_pdf, add_disclosure

AR_LINES = [
    "2025年年度报告", "5、研发投入", "2025年 2024年 变动比例",
    "研发人员数量（人） 1,200 1,100 9.09%",
    "研发人员数量占比 12.00% 11.50% 0.50%",
    "研发投入金额（元） 500,000,000.00 450,000,000.00 11.11%",
    "研发投入占营业收入比例 5.00% 3.33% 1.67%",
    "研发投入资本化的金额（元） 50,000,000.00 40,000,000.00 25.00%",
    "资本化研发投入占研发投入的比例 10.00% 8.89% 1.11%",
    "报告期内研发投入金额同比增长11%。",
    "<PAGE>",
    "九、员工情况",
    "母公司在职员工的数量（人） 5,000", "主要子公司在职员工的数量（人） 5,000", "在职员工的数量合计（人） 10,000",
    "专业构成", "生产人员 6,000", "销售人员 1,500", "技术人员 1,200", "财务人员 300", "行政人员 900", "合计 9,900",
    "教育程度", "博士 20", "硕士 600", "本科 3,000", "大专 3,380", "大专以下 3,000", "合计 10,000",
    "公司累计获得授权专利356项，其中发明专利120项。",
    "<PAGE>",
    "第五节 环境和社会责任", "公司属于环境保护部门公布的重点排污单位。",
    "化学需氧量 排放总量 120.5 吨；二氧化硫年排放量1,050 吨。",
    "报告期内温室气体排放总量为 35.6 万吨二氧化碳当量。",
    "报告期内公司对外捐赠合计 2,000 万元。",
]


def test_human_capital_and_esg_extraction(company, tmp_path):
    from ashare.human_capital import extract_human_capital, human_capital, human_capital_history
    from ashare.esg import extract_esg, esg_profile, import_esg_ratings_csv
    from ashare.crossvalidation import cross_validate
    from ashare.models import SessionLocal, FinancialFact
    pdf = make_pdf(tmp_path / "ar.pdf", AR_LINES)
    d = add_disclosure(company, "2025年年度报告", "2026-03-30", pdf, ann_id="AR25")
    s = SessionLocal()
    s.add(FinancialFact(company_id=company.id, disclosure_id=d.id, reporting_period="2025-12-31", period_type="FY",
                        metric="revenue", value=12_500_000_000.0, extraction_method="XBRL", confidence=0.98,
                        consolidation_scope="CONSOLIDATED_DEFAULT", source_document="x", unit="CNY"))
    s.commit(); s.close()
    r = extract_human_capital("600519")
    assert r["reports"] == 1 and r["values"] >= 20
    h = human_capital("600519")
    v, dv = h["values"], h["derived"]
    assert v["rd_investment"] == 500_000_000 and v["rd_ratio"] == 0.05 and v["employees_total"] == 10_000
    assert dv["rd_intensity_computed"] == 0.04 and dv["rd_capitalisation_share"] == 0.1
    assert abs(dv["postgraduate_share"] - 0.062) < 1e-9 and dv["revenue_per_employee"] == 1_250_000
    assert v["patents_granted_cum"] == 356 and v["invention_patents_granted_cum"] == 120
    assert "rd_investment" in [x["item"] for x in human_capital_history("600519")]
    assert human_capital("600519", as_of="2026-01-01")["values"] == {}
    flags = cross_validate("600519")["flags"]
    # reported 5.00% vs 500m / 12.5bn = 4.00%; functions sum to 9,900 against 10,000 employees
    assert flags.get("RD_RATIO_INCONSISTENT") == 1 and flags.get("WORKFORCE_COMPOSITION_MISMATCH") == 1
    assert "EDUCATION_SUM_MISMATCH" not in flags
    e = extract_esg("600519")
    assert e["documents"] == 1 and e["values"] == 5
    add_disclosure(company, "2025年度可持续发展报告", "2026-04-20", None, ann_id="SR25")
    extract_esg("600519")
    rt = tmp_path / "r.csv"
    rt.write_text("security_code,provider,rating_date,rating,score\n600519,ProviderA,2026-06-30,A,78.5\n", encoding="utf-8")
    assert import_esg_ratings_csv(str(rt))["inserted"] == 1
    p = esg_profile("600519")
    assert p["year"] == 2025 and p["environmental"]["key_pollutant_discharge_unit"]["value"] == 1.0
    assert p["environmental"]["ghg_emissions"]["value"] == 356_000 and p["social"]["donations"]["value"] == 20_000_000
    assert p["social"]["employees"] == 10_000 and p["reporting"]["sustainability_report_published"] is True
    assert p["ratings"]["ProviderA"]["rating"] == "A"
    early = esg_profile("600519", as_of="2026-04-01")  # before the sustainability report and the rating
    assert early["reporting"]["sustainability_report_published"] is False and early["ratings"] == {}


def test_environmental_authority_in_regulatory_events(company, tmp_path):
    from ashare.regulatory import extract_regulatory_events, show_events
    from ashare.esg import esg_profile, import_esg_csv
    pdf = make_pdf(tmp_path / "e.pdf", ["关于子公司收到行政处罚决定书的公告",
                                        "公司子公司于2025年8月1日收到某某市生态环境局出具的《行政处罚决定书》，",
                                        "对其处以罚款人民币50万元。"])
    add_disclosure(company, "关于子公司收到行政处罚决定书的公告", "2025-08-02", pdf, ann_id="ENV1")
    extract_regulatory_events("600519")
    [ev] = show_events("600519")
    assert ev.authority == "ENVIRONMENT" and ev.authority_name == "某某市生态环境局"
    f = tmp_path / "esg.csv"
    f.write_text("security_code,reporting_period,item,value\n600519,2025-12-31,emission_nox,10\n600519,2025-12-31,bogus,1\n",
                 encoding="utf-8")
    assert import_esg_csv(str(f))["inserted"] == 1
    p = esg_profile("600519", year=2025)
    assert len(p["environmental"]["environmental_regulatory_actions"]) == 1
    assert p["governance"]["securities_regulatory_actions"] == 0


def test_report_includes_v13(company, tmp_path):
    from ashare.human_capital import extract_human_capital
    from ashare.esg import extract_esg
    from ashare.report import write_profile_report
    add_disclosure(company, "2025年年度报告", "2026-03-30", make_pdf(tmp_path / "ar.pdf", AR_LINES), ann_id="AR25")
    extract_human_capital(); extract_esg()
    html = open(write_profile_report("600519", str(tmp_path / "r.html")), encoding="utf-8").read()
    assert "R&amp;D and people" in html and "ESG (2025)" in html and "no composite ESG score" in html
