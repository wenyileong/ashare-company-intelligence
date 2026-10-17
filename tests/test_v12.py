"""v1.2: segments and group structure."""
from helpers import make_pdf, add_disclosure

SEG_LINES = [
    "2025年年度报告", "四、主营业务分析", "（1）营业收入构成", "单位：元",
    "项目 2025年 2024年 同比增减",
    "营业收入合计 150,000.00 100% 135,000.00 100% 11.11%",
    "分产品",
    "茅台酒 130,000.00 86.67% 118,000.00 87.41% 10.17%",
    "系列酒 19,000.00 12.67% 16,000.00 11.85% 18.75%",
    "其他 1,000.00 0.67% 1,000.00 0.74% 0.00%",
    "分地区",
    "国内 145,000.00 96.67% 131,000.00 97.04% 10.69%",
    "国外 3,000.00 2.00% 4,000.00 2.96% -25.00%",
    "<PAGE>",
    "营业收入 营业成本 毛利率 营业收入比上年同期增减 营业成本比上年同期增减 毛利率比上年同期增减",
    "分行业情况 单位：元",
    "分产品",
    "茅台酒 130,000.00 7,000.00 94.62% 10.17% 8.00% 0.10%",
    "<PAGE>",
    "十、在其他主体中的权益", "（1）企业集团的构成",
    "子公司名称 主要经营地 注册地 业务性质 持股比例 取得方式",
    "贵州茅台酱香酒营销有限公司 贵州仁怀 贵州仁怀 酒类销售 100.00 - 设立",
    "Moutai Holdings Limited 开曼群岛 开曼群岛 投资控股 100.00 - 设立",
    "深圳某某科技有限公司 深圳 深圳 技术服务 40.00 - 非同一控制下企业合并",
]


def test_places():
    from ashare.places import jurisdiction_class, region_class
    assert jurisdiction_class("开曼群岛") == "OFFSHORE" and jurisdiction_class("British Virgin Islands") == "OFFSHORE"
    assert jurisdiction_class("中国香港") == "HONG_KONG" and jurisdiction_class("贵州仁怀") == "MAINLAND"
    assert jurisdiction_class("Singapore") == "FOREIGN" and jurisdiction_class("Atlantis") == "UNKNOWN"
    assert region_class("境外") == "OVERSEAS" and region_class("华东地区") == "DOMESTIC" and region_class("其他") == "UNKNOWN"


def test_segment_and_group_extraction(company, tmp_path):
    from ashare.segments import extract_segments, segments, segment_history
    from ashare.group import extract_subsidiaries, subsidiaries
    from ashare.crossvalidation import cross_validate, show_flags
    pdf = make_pdf(tmp_path / "ar.pdf", SEG_LINES)
    add_disclosure(company, "2025年年度报告", "2026-03-30", pdf, ann_id="AR25")
    r = extract_segments("600519")
    assert r["reports"] == 1 and r["segments"] == 6  # total + 3 products + 2 regions (margin row merged)
    v = segments("600519")
    prod = v["dimensions"]["PRODUCT"]
    names = [s["name"] for s in prod["segments"]]
    assert names == ["茅台酒", "系列酒", "其他"]
    top = prod["segments"][0]
    assert top["revenue"] == 130_000 and abs(top["share"] - 130 / 150) < 1e-9 and abs(top["gross_margin"] - 0.9462) < 1e-9
    assert abs(prod["hhi"] - ((130 / 150) ** 2 + (19 / 150) ** 2 + (1 / 150) ** 2)) < 1e-9
    reg = v["dimensions"]["REGION"]
    assert abs(reg["regional"]["overseas_share"] - 3 / 150) < 1e-9
    assert segments("600519", as_of="2026-01-01")["dimensions"] == {}  # not yet published
    assert segment_history("600519")[0]["segment"] in names
    g = extract_subsidiaries("600519")
    assert g["entities"] == 3
    s = subsidiaries("600519")
    assert s["summary"]["subsidiaries"] == 3 and s["summary"]["wholly_owned"] == 2
    assert s["summary"]["offshore_entities"] == ["Moutai Holdings Limited"]
    assert s["summary"]["consolidated_below_50pct"] == ["深圳某某科技有限公司"]
    flags = cross_validate("600519")["flags"]
    # regions sum to 148,000 against a total of 150,000: flagged, not corrected
    assert flags.get("SEGMENT_SUM_MISMATCH") == 1 and flags.get("CONSOLIDATED_WITH_MINORITY_STAKE") == 1
    [f] = show_flags("600519", rule="SEGMENT_SUM_MISMATCH")
    assert '"REGION"' in f.details


def test_csv_imports_and_scope_changes(company, tmp_path):
    from ashare.segments import import_segments_csv, segments
    from ashare.group import import_subsidiaries_csv, scope_changes
    seg = tmp_path / "s.csv"
    seg.write_text("security_code,reporting_period,dimension,segment_name,revenue,gross_margin\n"
                   "600519,2025-12-31,分地区,境内,90,50%\n600519,2025-12-31,REGION,境外,10,0.4\n"
                   "600519,2025-12-31,BOGUS,x,1,\n", encoding="utf-8")
    r = import_segments_csv(str(seg))
    assert r["inserted"] == 2 and len(r["errors"]) == 1
    reg = segments("600519")["dimensions"]["REGION"]
    assert reg["regional"]["overseas_share"] == 0.1 and reg["segments"][0]["gross_margin"] == 0.5
    sub = tmp_path / "g.csv"
    sub.write_text("security_code,observation_date,entity_name,relationship,registered_place,direct_pct,indirect_pct,acquisition_method\n"
                   "600519,2024-12-31,甲有限公司,子公司,上海,100,,设立\n600519,2024-12-31,乙有限公司,子公司,北京,60,,设立\n"
                   "600519,2025-12-31,甲有限公司,子公司,上海,100,,设立\n600519,2025-12-31,乙有限公司,子公司,北京,80,,设立\n"
                   "600519,2025-12-31,丙 Limited,子公司,British Virgin Islands,,100,非同一控制下企业合并\n", encoding="utf-8")
    assert import_subsidiaries_csv(str(sub))["inserted"] == 5
    ch = scope_changes("600519")
    assert [a["name"] for a in ch["added"]] == ["丙 Limited"] and ch["added"][0]["jurisdiction"] == "OFFSHORE"
    assert ch["removed"] == [] and ch["stake_or_status_changed"][0] == {
        "name": "乙有限公司", "from_pct": 60.0, "to_pct": 80.0, "from_relationship": "SUBSIDIARY", "to_relationship": "SUBSIDIARY"}


def test_report_includes_v12(company, tmp_path):
    from ashare.report import write_profile_report
    pdf = make_pdf(tmp_path / "ar.pdf", SEG_LINES)
    add_disclosure(company, "2025年年度报告", "2026-03-30", pdf, ann_id="AR25")
    from ashare.segments import extract_segments
    from ashare.group import extract_subsidiaries
    extract_segments(); extract_subsidiaries()
    html = open(write_profile_report("600519", str(tmp_path / "r.html")), encoding="utf-8").read()
    assert "Business segments" in html and "Group structure" in html and "Moutai Holdings Limited" in html
