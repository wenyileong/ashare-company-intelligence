"""v1.1: industry classification and management."""
import json
from helpers import make_pdf, add_disclosure


def _companies(n=4):
    from ashare.storage import upsert_ashares
    codes = ["600519", "000858", "600809", "000568"][:n]
    upsert_ashares([{"code": c, "exchange": "SSE" if c.startswith("6") else "SZSE", "legal_name_cn": f"公司{c}",
                     "short_name_cn": f"简称{c}"} for c in codes])
    return codes


def _fy(code, metric, value, year=2025):
    from ashare.models import SessionLocal, Company, FinancialFact, Disclosure
    s = SessionLocal()
    c = s.query(Company).filter_by(security_code=code).one()
    d = s.query(Disclosure).filter_by(company_id=c.id, announcement_id=f"FY{code}{year}").one_or_none()
    if d is None:
        d = Disclosure(company_id=c.id, announcement_id=f"FY{code}{year}", announcement_date=f"{year + 1}-03-30",
                       title_cn=f"{year}年年度报告", kind="annual_report", source="CNINFO")
        s.add(d); s.flush()
    s.add(FinancialFact(company_id=c.id, disclosure_id=d.id, reporting_period=f"{year}-12-31", period_type="FY",
                        metric=metric, value=value, extraction_method="XBRL", confidence=0.98, unit="CNY",
                        consolidation_scope="CONSOLIDATED_DEFAULT", source_document="x"))
    s.commit(); s.close()


def test_csrc_validation_and_parsing():
    from ashare.industry import parse_csrc_code, validate_classification
    assert parse_csrc_code("C-15") == ("C", "C15") and parse_csrc_code("c27") == ("C", "C27")
    assert validate_classification("CSRC_2012", "C", None, "C15") == []
    assert validate_classification("CSRC_2012", "C", None, "C55")  # outside 13-43
    assert validate_classification("CSRC_2012", "Z", None, None)
    assert validate_classification("SW_2021", None, "食品饮料") == []
    assert validate_classification("SW_2021", None, "白酒类")


def test_industry_import_peers_and_stats(db, tmp_path):
    from ashare.industry import import_industry_csv, peers, industry_stats, industry_summary, industry_history
    _companies()
    f = tmp_path / "csrc.csv"
    f.write_text("证券代码,大类代码,大类名称\n600519,C15,酒、饮料和精制茶制造业\n000858,C15,酒、饮料和精制茶制造业\n"
                 "600809,C15,酒、饮料和精制茶制造业\n000568,C-27,医药制造业\n", encoding="utf-8")
    r = import_industry_csv(str(f), "CSRC_2012", source="CSRC", effective_date="2025-12-31")
    assert r["inserted"] == 4 and r["invalid_codes"] == 0
    [h] = industry_history("600519")
    assert (h.level1_code, h.level1_name, h.level2_code) == ("C", "制造业", "C15")
    # reclassification later in 2026
    g = tmp_path / "csrc2.csv"
    g.write_text("security_code,level2_code\n000568,C15\n", encoding="utf-8")
    import_industry_csv(str(g), "CSRC_2012", source="CSRC", effective_date="2026-06-30")
    assert len(peers("600519", as_of="2026-01-01")["peers"]) == 3
    assert len(peers("600519")["peers"]) == 4  # point in time
    for code, rev, np_ in (("600519", 1000, 500), ("000858", 800, 300), ("600809", 400, 100), ("000568", 300, 30)):
        _fy(code, "revenue", rev); _fy(code, "net_profit", np_)
    st = industry_stats("600519", "net_margin")
    assert st["with_value"] == 4 and st["median"] == (0.375 + 0.25) / 2 and st["company_percentile"] == 0.875
    st0 = industry_stats("600519", "revenue", as_of="2026-01-01")
    assert st0["peers"] == 3 and st0["with_value"] == 0 and st0["missing"] == 3  # FY2025 not yet published
    assert industry_summary(level=2)[0] == {"code": "C15", "name": "酒、饮料和精制茶制造业", "companies": 4}


def test_invalid_codes_are_flagged(db, tmp_path):
    from ashare.industry import import_industry_csv
    from ashare.crossvalidation import cross_validate
    _companies(1)
    f = tmp_path / "bad.csv"
    f.write_text("security_code,level1_code,level2_code\n600519,C,C55\n", encoding="utf-8")
    assert import_industry_csv(str(f), "CSRC_2012", effective_date="2025-12-31")["invalid_codes"] == 1
    assert cross_validate("600519")["flags"]["INDUSTRY_CODE_INVALID"] == 1


RESIGN = ("关于董事、副总经理辞职的公告",
          "公司董事会于2026年5月8日收到董事、副总经理张三先生提交的书面辞职报告。张三先生因个人原因申请辞去公司"
          "第九届董事会董事、副总经理职务，辞职后不再在公司担任任何职务。辞职报告自送达董事会之日起生效。")
APPOINT = ("关于聘任高级管理人员的公告",
           "公司于2026年5月20日召开第九届董事会第十次会议，同意聘任李四女士为公司副总经理、财务总监，任期至第九届董事会届满。"
           "同意聘任欧阳志远先生为公司董事会秘书。")
INDEP = ("关于独立董事辞职的公告",
         "公司董事会于2026年6月1日收到独立董事王五先生的书面辞职报告。由于王五先生辞职将导致公司独立董事人数少于董事会成员的"
         "三分之一，其辞职将在公司股东大会选举产生新任独立董事后生效。")


def test_management_parsing():
    from ashare.management import parse_management_text, classify_management_title, split_roles
    r = parse_management_text("\n".join(RESIGN), classify_management_title(RESIGN[0]))
    assert {(x["person_name"], x["role"]) for x in r} == {("张三", "DIRECTOR"), ("张三", "DEPUTY_GM")}
    assert r[0]["effective_date"] == "2026-05-08" and r[0]["reason"] == "PERSONAL" and r[0]["remains_with_company"] is False
    a = parse_management_text("\n".join(APPOINT), classify_management_title(APPOINT[0]))
    assert {(x["person_name"], x["role"]) for x in a} == {("李四", "DEPUTY_GM"), ("李四", "CFO"), ("欧阳志远", "BOARD_SECRETARY")}
    [w] = parse_management_text("\n".join(INDEP), classify_management_title(INDEP[0]))
    assert w["role"] == "INDEPENDENT_DIRECTOR" and w["effective_date"] is None  # waits for a successor
    assert split_roles("董事长兼总经理") == [("CHAIR", "董事长"), ("GENERAL_MANAGER", "总经理")]
    assert classify_management_title("独立董事提名人声明") == []


def test_roster_governance_and_flags(company, tmp_path):
    from ashare.management import extract_management_events, extract_rosters, roster_at, governance
    from ashare.crossvalidation import cross_validate
    report = make_pdf(tmp_path / "ar.pdf", [
        "2025年年度报告", "董事、监事和高级管理人员情况", "单位：万元",
        "张三 董事、副总经理 男 52 现任 2023年5月10日 2026年5月9日 0 0 0 120.5 否",
        "赵六 董事长兼总经理 男 58 现任 2023年5月10日 2026年5月9日 0 0 0 200 否",
        "钱七 董事 女 50 现任 2023年5月10日 2026年5月9日 0 0 0 80 否",
        "王五 独立董事 男 66 现任 2018年5月10日 2026年5月9日 0 0 0 15 否",
        "孙八 监事会主席 男 55 现任 2023年5月10日 2026年5月9日 0 0 0 40 否",
    ])
    add_disclosure(company, "2025年年度报告", "2026-03-30", report, ann_id="AR25")
    for i, (title, body) in enumerate((RESIGN, APPOINT, INDEP)):
        pdf = make_pdf(tmp_path / f"m{i}.pdf", [title] + [body[j:j + 40] for j in range(0, len(body), 40)])
        add_disclosure(company, title, ["2026-05-09", "2026-05-21", "2026-06-02"][i], pdf, ann_id=f"M{i}")
    ev = extract_management_events("600519")
    assert ev["inserted"] == 6 and ev["title_only"] == 0
    ro = extract_rosters("600519")
    assert ro["rows"] == 7 and ro["inserted"] == 7  # 赵六 holds two roles
    before = roster_at("600519", "2026-04-30")
    assert {(m["person"], m["role"]) for m in before["members"]} >= {("张三", "DIRECTOR"), ("赵六", "CHAIR")}
    after = roster_at("600519", "2026-06-30")
    people = {(m["person"], m["role"]) for m in after["members"]}
    assert ("张三", "DIRECTOR") not in people and ("李四", "CFO") in people and ("王五", "INDEPENDENT_DIRECTOR") in people
    assert after["pending_resignations"][0]["person"] == "王五"
    g = governance("600519", "2026-06-30")
    assert g["board_size"] == 3 and g["independent_directors"] == 1 and g["ceo_duality"] is True
    assert g["key_role_departures_12m"]["CHAIR"] == 0 and g["female_directors"] == 1
    checks = {c["rule"]: c["result"] for c in g["legal_reference_checks"]}
    assert checks["Independent directors at least one third of the board"] == "MET"  # 1 of 3
    assert checks["Independent director tenure not above six consecutive years"] == "CHECK"  # since 2018
    flags = cross_validate("600519")["flags"]
    assert flags.get("INDEPENDENT_DIRECTOR_TENURE_OVER_SIX_YEARS") == 1


def test_profile_and_report_include_v11(company, tmp_path):
    from ashare.industry import import_industry_csv
    from ashare.management import import_management_csv
    from ashare.intelligence import company_profile
    from ashare.report import write_profile_report
    f = tmp_path / "i.csv"
    f.write_text("security_code,level2_code\n600519,C15\n", encoding="utf-8")
    import_industry_csv(str(f), "CSRC_2012", effective_date="2025-12-31")
    m = tmp_path / "m.csv"
    m.write_text("security_code,observation_date,person_name,role,gender\n600519,2025-12-31,赵六,董事长、总经理,男\n"
                 "600519,2025-12-31,王五,独立董事,男\n600519,2025-12-31,钱七,董事,女\n", encoding="utf-8")
    assert import_management_csv(str(m))["inserted"] == 4
    p = company_profile("600519")
    assert p["industry"]["CSRC_2012"]["level2"].startswith("C15") and p["governance"]["board_size"] == 3
    html = open(write_profile_report("600519", str(tmp_path / "r.html")), encoding="utf-8").read()
    assert "Board and management" in html and "Industry" in html
