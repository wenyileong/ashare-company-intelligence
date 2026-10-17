import json
from helpers import make_pdf, add_disclosure
from ashare.corporate_actions import (
    classify_action_title, classify_action_status, parse_action_text, parse_cn_date,
    capital_effective_date,
)


def test_title_classification():
    assert classify_action_title("2025年年度权益分派实施公告")[:1] == ["CASH_DIVIDEND"]
    assert classify_action_title("关于回购股份实施结果暨股份变动的公告") == ["SHARE_BUYBACK"]
    assert classify_action_title("关于注销已回购股份的公告") == ["SHARE_CANCELLATION"]
    assert classify_action_title("关于可转债转股结果暨股份变动公告") == ["CONVERTIBLE_CONVERSION"]
    assert classify_action_title("向特定对象发行A股股票上市公告书") == ["PRIVATE_PLACEMENT"]
    assert classify_action_title("配股发行公告") == ["RIGHTS_ISSUE"]
    assert classify_action_title("关于向不特定对象发行可转换公司债券的预案") == []
    assert classify_action_title("2025年年度报告") == []
    assert classify_action_title("2025年年度股东大会决议公告") == []
    assert classify_action_title("关于2025年年度报告问询函的回复") == []
    assert classify_action_title("关于2025年度不进行利润分配的公告") == []
    assert classify_action_title("未来三年(2026-2028年)股东分红回报规划") == []


def test_status_lifecycle():
    assert classify_action_status("关于2025年度利润分配预案的公告") == "PROPOSED"
    assert classify_action_status("2025年年度权益分派实施公告") == "IMPLEMENTATION_ANNOUNCED"
    assert classify_action_status("关于回购股份实施结果暨股份变动的公告") == "COMPLETED"
    assert classify_action_status("关于终止非公开发行股票事项的公告") == "TERMINATED"
    assert classify_action_status("关于回购股份的进展公告") == "IN_PROGRESS"


def test_dates():
    assert parse_cn_date("2026年6月9日") == "2026-06-09"
    assert parse_cn_date("2026/6/19") == "2026-06-19"


def test_dividend_with_dash_table():
    text = ("本次利润分配以方案实施前的公司总股本1,256,197,800股为基数，每股派发现金红利27.673元（含税），"
            "共计派发现金红利34,763,961,659.40元。\n相关日期\n股份类别 股权登记日 最后交易日 除权（息）日 现金红利发放日\n"
            "A股 2026/6/18 － 2026/6/19 2026/6/19")
    [a] = parse_action_text(text, ["CASH_DIVIDEND", "BONUS_SHARES", "CAPITALISATION_ISSUE"], "IMPLEMENTATION_ANNOUNCED")
    f = a.fields
    assert a.action_type == "CASH_DIVIDEND" and f["cash_amount"] == 27.673 and f["tax_basis"] == "PRE_TAX"
    assert f["base_share_count"] == 1_256_197_800 and f["total_cash_amount"] == 34_763_961_659.40
    assert (f["record_date"], f["ex_date"], f["payment_date"]) == ("2026-06-18", "2026-06-19", "2026-06-19")


def test_combined_cash_and_capitalisation():
    text = ("以公司现有总股本 500,000,000 股为基数，向全体股东每10股派发现金红利3.00元（含税），以资本公积金向全体股东每10股转增4股。"
            "本次转增后，公司总股本由500,000,000股增加至700,000,000股。股权登记日：2026年5月20日；除权除息日：2026年5月21日")
    acts = {a.action_type: a for a in parse_action_text(text, ["CASH_DIVIDEND", "BONUS_SHARES", "CAPITALISATION_ISSUE"], "IMPLEMENTATION_ANNOUNCED")}
    assert set(acts) == {"CASH_DIVIDEND", "CAPITALISATION_ISSUE"}
    assert acts["CASH_DIVIDEND"].fields["cash_amount"] == 0.3
    cap = acts["CAPITALISATION_ISSUE"].fields
    assert cap["ratio"] == 0.4 and cap["share_delta"] == 200_000_000 and cap["new_share_count"] == 700_000_000
    assert capital_effective_date({**cap, "action_type": "CAPITALISATION_ISSUE"}) == "2026-05-21"


def test_issue_cancellation_conversion_buyback_rights():
    [p] = parse_action_text("本次向特定对象发行股票的数量为 50,000,000 股，发行价格为 12.50 元/股。新增股份上市日：2026年8月10日",
                            ["PRIVATE_PLACEMENT"], "COMPLETED")
    assert p.fields["share_delta"] == 50_000_000 and p.fields["issue_price"] == 12.5 and p.fields["listing_date"] == "2026-08-10"
    [proposed] = parse_action_text("本次向特定对象发行股票的数量不超过...拟发行数量为 50,000,000 股", ["PRIVATE_PLACEMENT"], "PROPOSED")
    assert "share_delta" not in proposed.fields  # a proposal has not changed capital
    [c] = parse_action_text("本次注销已回购股份 3,000,000 股。注销完成后，公司总股本由 700,000,000 股减少至 697,000,000 股。",
                            ["SHARE_CANCELLATION"], "COMPLETED")
    assert c.fields["share_delta"] == -3_000_000 and c.fields["old_share_count"] == 700_000_000
    [cv] = parse_action_text("截至2026年9月30日，累计转股数量为 1,200 股。2026年7月1日至2026年9月30日期间，共有5,000元转债转换成公司股份，转股数量为 500 股。",
                             ["CONVERTIBLE_CONVERSION"], "COMPLETED")
    assert cv.fields["share_delta"] == 500 and cv.fields["cumulative_converted_shares"] == 1200
    assert cv.fields["effective_date"] == "2026-09-30"
    [b] = parse_action_text("累计回购公司股份 2,500,000 股，支付的总金额为人民币 3,000 万元", ["SHARE_BUYBACK"], "COMPLETED")
    assert b.fields["share_delta"] == 0 and b.fields["shares_affected"] == 2_500_000 and b.fields["total_cash_amount"] == 30_000_000
    [r] = parse_action_text("按每10股配3股的比例向全体股东配售，配股价格为 5.20 元/股。本次配股实际配售股份数量为 140,000,000 股",
                            ["RIGHTS_ISSUE"], "COMPLETED")
    assert (r.fields["ratio"], r.fields["subscription_price"], r.fields["share_delta"]) == (0.3, 5.2, 140_000_000)


def test_extraction_from_disclosures_is_idempotent(company, tmp_path):
    from ashare.corporate_actions import extract_corporate_actions, show_actions
    pdf = make_pdf(tmp_path / "fh.pdf", [
        "贵州茅台2025年年度权益分派实施公告",
        "本次利润分配以方案实施前的公司总股本1,256,197,800股为基数，",
        "每股派发现金红利27.673元（含税）",
        "<PAGE>",
        "股权登记日：2026年6月18日 除权（息）日：2026年6月19日 现金红利发放日：2026年6月19日",
    ])
    add_disclosure(company, "贵州茅台2025年年度权益分派实施公告", "2026-06-12", pdf, ann_id="D1")
    add_disclosure(company, "关于回购股份的进展公告", "2026-07-01", None, ann_id="D2")
    add_disclosure(company, "2025年年度报告", "2026-03-30", None, ann_id="D3")
    r1 = extract_corporate_actions("600519")
    r2 = extract_corporate_actions("600519")
    assert r1["action_disclosures"] == 2 and r1["inserted"] == 2 and r2["updated"] == 2 and r2["inserted"] == 0
    rows = {r.action_type: r for r in show_actions("600519")}
    div = rows["CASH_DIVIDEND"]
    assert div.cash_amount == 27.673 and div.ex_date == "2026-06-19" and div.fiscal_period == "2025-12-31"
    assert div.extraction_method == "DOCUMENT_TEXT_REGEX" and div.source_page == 1
    assert json.loads(div.normalised_value)["base_share_count"] == 1_256_197_800
    bb = rows["SHARE_BUYBACK"]
    assert bb.extraction_method == "TITLE_ONLY" and bb.confidence == 0.3 and bb.status == "IN_PROGRESS"


def test_csv_import(company, tmp_path):
    from ashare.corporate_actions import import_corporate_actions_csv, show_actions
    p = tmp_path / "ca.csv"
    p.write_text("security_code,action_type,status,announcement_date,ex_date,ratio,cash_amount\n"
                 "600519,CASH_DIVIDEND,COMPLETED,2026-06-12,2026/06/19,,27.673\n"
                 "600519,NOT_A_TYPE,COMPLETED,2026-06-12,2026/06/19,,1\n", encoding="utf-8")
    r = import_corporate_actions_csv(str(p), source="VENDOR")
    assert r["inserted"] == 1 and len(r["errors"]) == 1
    assert import_corporate_actions_csv(str(p), source="VENDOR")["updated"] == 1
    [row] = show_actions("600519")
    assert row.ex_date == "2026-06-19" and row.source == "VENDOR"
