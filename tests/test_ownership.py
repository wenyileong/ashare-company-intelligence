from ashare.ownership import classify_ownership_title, _num, _flag, normalise_date


def test_classify_ownership_titles():
    assert classify_ownership_title("关于公司股东部分股份质押及解除质押的公告") == "PLEDGE"
    assert classify_ownership_title("关于股东增减持计划的公告") == "OWNERSHIP_CHANGE"
    assert classify_ownership_title("关于实际控制人变更的公告") == "CONTROL"
    assert classify_ownership_title("2026年半年度报告") is None
    # v0.7 misclassified shareholders' meeting notices as register disclosures.
    assert classify_ownership_title("关于召开2025年年度股东大会的通知") is None


def test_quantity_scaling_and_flags():
    assert _num("1.5万股") == 15_000
    assert _num("2亿股") == 200_000_000
    assert _num("12.34%") == 12.34
    assert _flag(None) is None and _flag("") is None and _flag("是") is True and _flag("0") is False
    assert normalise_date("2026年6月30日") == "2026-06-30"
    assert normalise_date("20260630") == "2026-06-30"


def test_ownership_import_and_validation(company, tmp_path):
    from ashare.ownership import import_ownership_csv, import_capital_csv, validate_ownership, show_ownership
    own = tmp_path / "own.csv"
    own.write_text(
        "security_code,observation_date,shareholder_name,rank,shares,ownership_pct,pledged_shares\n"
        "600519,2026/06/30,中国贵州茅台酒厂(集团)有限责任公司,1,678000000,54.0,0\n"
        "600519,2026/06/30,香港中央结算有限公司,2,80000000,6.4,90000000\n", encoding="utf-8")
    cap = tmp_path / "cap.csv"
    cap.write_text("security_code,observation_date,total_shares,tradable_shares,restricted_shares\n"
                   "600519,2026-06-30,1256197800,1256197800,0\n", encoding="utf-8")
    assert import_ownership_csv(str(own))["inserted"] == 2
    assert import_ownership_csv(str(own))["updated"] == 2
    assert import_capital_csv(str(cap))["inserted"] == 1
    rows = show_ownership("600519")
    assert rows[0].observation_date == "2026-06-30" and rows[0].is_controlling_shareholder is None
    v = validate_ownership("600519")
    assert v["ownership_failed"] == 1 and v["capital_failed"] == 0
    assert any("pledged > shares" in p for p in v["errors"][0]["problems"])
