"""v1.8: top-10 holders, pledges, control and ownership type, entities, persons, interlocks, diagrams."""
import json
import random

import pytest

from ashare.control import (parse_top10_pages, parse_top10_tradable_pages, parse_pledge_text, classify_pledge_title,
                            classify_ownership, parse_control_text, valid_credit_code, find_credit_codes,
                            normalise_name, _CREDIT_CHARS, _CREDIT_W)

TOP10 = ["（二）截至报告期末前十名股东持股情况", "单位：股",
         "股东名称（全称） 报告期内增减 期末持股数量 比例(%) 持有有限售条件股份数量 质押、标记或冻结情况 股东性质",
         "中国贵州茅台酒厂（集团）有限责任公司 0 678,291,955 54.00 0 无 0 国有法人",
         "香港中央结算有限公司 -5,000,000 89,000,000 7.09 0 未知 境外法人",
         "张三 1,000,000 12,000,000 0.96 0 质押 6,000,000 境内自然人",
         "（三）前十名无限售条件股东持股情况", "股东名称 持有无限售条件流通股的数量 股份种类 数量",
         "中国贵州茅台酒厂（集团）有限责任公司 678,291,955 人民币普通股 678,291,955",
         "香港中央结算有限公司 89,000,000 人民币普通股 89,000,000",
         "上述股东关联关系或一致行动的说明 未知"]


def test_top10_tables():
    rows = parse_top10_pages(["\n".join(TOP10)])
    assert [r["shareholder_name"] for r in rows] == ["中国贵州茅台酒厂（集团）有限责任公司", "香港中央结算有限公司", "张三"]
    a, b, c = rows
    assert (a["shares"], a["ownership_pct"], a["shareholder_nature"], a["pledged_shares"]) == (678291955, 54.0, "国有法人", None)
    assert b["change_shares"] == -5e6 and b["shareholder_type"] == "FOREIGN_LEGAL_PERSON"
    assert c["pledged_shares"] == 6e6 and c["rank"] == 3
    t = parse_top10_tradable_pages(["\n".join(TOP10)])
    assert [x["tradable_shares"] for x in t] == [678291955, 89e6]


def test_pledges():
    assert classify_pledge_title("关于控股股东部分股份质押的公告") == "PLEDGE"
    assert classify_pledge_title("关于控股股东部分股份解除质押的公告") == "RELEASE"
    assert classify_pledge_title("关于开展股票质押式回购交易业务的公告") is None
    [r] = parse_pledge_text("公司控股股东甲集团有限公司将其持有的本公司20,000,000股无限售条件流通股质押给中信证券股份有限公司，"
                            "本次质押股份占其所持股份比例为5.00%，占公司总股本比例为1.20%。质押起始日2025年3月1日。"
                            "截至公告日，累计质押股份数量为8,000万股。", "PLEDGE")
    assert (r["pledgor"], r["shares"], r["pledgee"]) == ("甲集团有限公司", 2e7, "中信证券股份有限公司")
    assert (r["pct_of_holding"], r["pct_of_total"], r["start_date"]) == (0.05, 0.012, "2025-03-01")
    assert r["cumulative_pledged"] == 8e7 and r["is_controlling_shareholder"] is True
    [t] = parse_pledge_text("股东名称 是否为控股股东 本次质押股数 质押起始日 质押到期日 质权人 占其所持股份比例 占公司总股本比例\n"
                            "李四 是 3,000,000 2025年1月2日 2026年1月2日 某某证券股份有限公司 10.00% 1.00%", "PLEDGE")
    assert (t["pledgor"], t["shares"], t["end_date"], t["pct_of_total"]) == ("李四", 3e6, "2026-01-02", 0.01)


HAND_CODED = [  # (actual controller, nature text, hand-coded type)
    ("国务院国有资产监督管理委员会", "中央国资管理机构", "CENTRAL_SOE"), ("中华人民共和国财政部", "", "CENTRAL_SOE"),
    ("中央汇金投资有限责任公司", "", "CENTRAL_SOE"), ("贵州省人民政府国有资产监督管理委员会", "地方国资管理机构", "LOCAL_SOE"),
    ("深圳市人民政府国有资产监督管理委员会", "", "LOCAL_SOE"), ("上海市国有资产监督管理委员会", "地方国有控股", "LOCAL_SOE"),
    ("重庆市国资委", "", "LOCAL_SOE"), ("杭州市人民政府", "", "LOCAL_SOE"), ("宜宾市国有资产管理局", "", "LOCAL_SOE"),
    ("江苏省财政厅", "", "LOCAL_SOE"), ("北京市海淀区人民政府国有资产监督管理委员会", "", "LOCAL_SOE"),
    ("王传福", "境内自然人", "PRIVATE"), ("曹德旺", "", "PRIVATE"), ("钟睒睒", "境内自然人", "PRIVATE"),
    ("马化腾、张志东", "", "PRIVATE"), ("何享健", "自然人", "PRIVATE"), ("刘永好", "民营", "PRIVATE"),
    ("John Smith", "境外自然人", "FOREIGN"), ("某外国公司", "境外法人", "FOREIGN"),
    ("华西村村民委员会", "", "COLLECTIVE"), ("某镇集体资产管理委员会", "集体", "COLLECTIVE"),
    ("某某经济合作社", "", "COLLECTIVE"), (None, "", "NO_CONTROLLER"), ("李书福", "境内自然人", "PRIVATE"),
    ("雷军", "", "PRIVATE"), ("国家开发投资集团有限公司", "中央国有控股", "CENTRAL_SOE"),
    ("山东省人民政府", "地方国有控股", "LOCAL_SOE"), ("周群飞", "境内自然人", "PRIVATE"),
    ("广东省人民政府国有资产监督管理委员会", "", "LOCAL_SOE"), ("某某大学", "", "UNKNOWN"),
]


def test_ownership_type_agrees_with_hand_coding():
    agree = 0
    for name, nature, expected in HAND_CODED:
        typ, basis = classify_ownership(name, nature, no_controller=name is None)
        agree += typ == expected
        assert basis
    assert agree / len(HAND_CODED) >= 0.97


def test_control_text():
    pages = ["四、控股股东和实际控制人情况\n（一）控股股东情况\n1 法人\n名称 中国贵州茅台酒厂（集团）有限责任公司\n"
             "单位负责人或法定代表人 某某\n（二）实际控制人情况\n名称 贵州省人民政府国有资产监督管理委员会\n"
             "实际控制人性质 地方国资管理机构"]
    r = parse_control_text(pages)
    assert r["controlling_shareholder"] == "中国贵州茅台酒厂（集团）有限责任公司"
    assert r["actual_controller"] == "贵州省人民政府国有资产监督管理委员会"
    assert classify_ownership(r["actual_controller"], r["controller_nature"])[0] == "LOCAL_SOE"
    r = parse_control_text(["（一）控股股东情况\n1 自然人\n姓名 王五\n国籍 中国\n（二）实际控制人情况\n公司不存在实际控制人。"])
    assert r["controlling_shareholder"] == "王五" and r["no_actual_controller"] and r["actual_controller"] is None


def _make_code(prefix17):
    total = sum(_CREDIT_CHARS.index(ch) * w for ch, w in zip(prefix17, _CREDIT_W))
    return prefix17 + _CREDIT_CHARS[(31 - total % 31) % 31]


def test_credit_codes_and_names():
    code = _make_code("91520000214434146")
    assert valid_credit_code(code) and not valid_credit_code(code[:-1] + ("0" if code[-1] != "0" else "1"))
    assert find_credit_codes(f"统一社会信用代码：{code}，注册地") == [code]
    assert normalise_name("中国贵州茅台酒厂(集团)有限责任公司 ") == normalise_name("中国贵州茅台酒厂（集团）有限责任公司")
    assert normalise_name("ＡＢＣ Limited") == "ABCLIMITED"


def _synthetic_report(company, tmp_path, seed=11, table=True):
    from helpers import add_disclosure
    from ashare.corpus import _annual_report, _write_pdf
    rng = random.Random(seed)
    for _ in range(60):
        title, pages, exp = _annual_report(rng, 1)
        if any(isinstance(x, dict) for x in pages[9]) == table:
            break
    pdf = tmp_path / f"ar{seed}.pdf"
    _write_pdf(pdf, pages)
    year = title[title.index("公司") + 2:title.index("年")]
    add_disclosure(company, f"{year}年年度报告", f"{int(year) + 1}-03-30", pdf, ann_id=f"AR{seed}")
    return exp, f"{year}-12-31"


def test_extraction_entities_and_chain(db, company, tmp_path):
    from ashare.control import extract_top_holders, extract_control, control_at, resolve_entities, entity_profile
    from ashare.crossvalidation import cross_validate
    exp, period = _synthetic_report(company, tmp_path)
    r = extract_top_holders("600519")
    truth = {x["shareholder_name"]: x for x in exp["top10"]["records"]}
    assert r["holders"] == len(truth)
    from ashare.models import SessionLocal, OwnershipObservation
    s = SessionLocal()
    got = {o.shareholder_name: o for o in s.query(OwnershipObservation)}
    s.close()
    assert set(got) == set(truth)                                  # wrapped long fund names rebuilt by the layout run
    for n, t in truth.items():
        assert got[n].shares == t["shares"] and got[n].ownership_pct == t["ownership_pct"]
        assert got[n].tradable_shares == t["shares"]
    c = extract_control("600519")
    assert c["reports"] == 1
    ctl = control_at("600519")
    want = exp["control"]["records"][0]
    assert ctl["control"]["actual_controller"] == want["actual_controller"]
    assert ctl["control"]["ownership_type"] == want["ownership_type"]
    first = next(e for e in ctl["chain"] if e["child"] == "贵州茅台酒股份有限公司")
    assert first["parent"] == want["controlling_shareholder"]
    assert first["pct"] == truth[want["controlling_shareholder"]]["ownership_pct"]
    assert control_at("600519", as_of=period)["control"] is None   # the report was published later
    e = resolve_entities()
    assert e["entities"] >= len(truth) - sum(1 for n in truth if len(n) <= 4)
    prof = entity_profile("香港中央结算有限公司")
    assert "600519" in prof["shareholdings"]
    assert "TOP_HOLDERS_EXCEED_100PCT" not in cross_validate("600519")["flags"]


def test_persons_interlocks_and_diagrams(db, tmp_path):
    from ashare.storage import upsert_ashares
    from ashare.management import import_management_csv
    from ashare.control import resolve_persons, interlocks, import_control_csv, common_controllers
    from ashare.charts.builders import interlock_chart, control_chart
    from ashare.charts import render_svg
    import xml.etree.ElementTree as ET
    upsert_ashares([{"code": c, "exchange": "SSE", "legal_name_cn": f"公司{c}", "short_name_cn": f"简{c}"}
                    for c in ("600001", "600002", "600003")])
    f = tmp_path / "m.csv"
    f.write_text("security_code,observation_date,person_name,role,gender,age\n"
                 "600001,2025-12-31,王伟,独立董事,男,55\n600002,2025-12-31,王伟,独立董事,男,56\n"
                 "600003,2025-12-31,王伟,董事,男,40\n600001,2025-12-31,李娜,董事长,女,50\n"
                 "600003,2025-12-31,李娜,董事,女,\n", encoding="utf-8")
    import_management_csv(str(f))
    r = resolve_persons()
    assert r["multi_company"] == 1                 # the two 王伟 aged 55/56 are one person; the 40-year-old is not
    il = interlocks()
    assert [(x["company_a"], x["company_b"], x["shared_directors"]) for x in il] == [("600001", "600002", ["王伟"])]
    svg = render_svg(interlock_chart())
    ET.fromstring(svg)
    assert "王伟" in svg
    c = tmp_path / "c.csv"
    c.write_text("security_code,observation_date,controlling_shareholder,actual_controller\n"
                 "600001,2025-12-31,甲集团有限公司,深圳市人民政府国有资产监督管理委员会\n"
                 "600002,2025-12-31,乙集团有限公司,深圳市人民政府国有资产监督管理委员会\n"
                 "600003,2025-12-31,丙有限公司,某某大学\n", encoding="utf-8")
    import_control_csv(str(c))
    [g] = common_controllers()
    assert g["companies"] == ["600001", "600002"] and g["ownership_type"] == "LOCAL_SOE"
    from ashare.crossvalidation import cross_validate
    assert cross_validate("600003")["flags"].get("OWNERSHIP_TYPE_UNKNOWN") == 1
    ET.fromstring(render_svg(control_chart("600001")))


def test_group_tree_and_panel_variables(db, company, tmp_path):
    from ashare.group import extract_subsidiaries
    from ashare.control import extract_top_holders, extract_control
    from ashare.charts.builders import group_tree_chart
    from ashare.charts import render_svg
    from ashare.panel import build_panel
    exp, period = _synthetic_report(company, tmp_path, seed=12)
    extract_subsidiaries("600519")
    extract_top_holders("600519")
    extract_control("600519")
    svg = render_svg(group_tree_chart("600519"))
    assert all(x["entity_name"][:6] in svg for x in exp["subsidiaries"]["records"])
    from ashare.models import SessionLocal, Company
    s = SessionLocal()
    s.query(Company).first().listing_date = "2001-08-27"
    s.commit()
    s.close()
    year = int(period[:4])
    r = build_panel(["soe", "ownership_type", "top10_pct"], "year", f"{year}-01-01", f"{year + 1}-12-31", "pit",
                    pit_day="06-30", with_dates=True)
    rows = {x["period"][:4]: x for x in r["rows"]}
    want = exp["control"]["records"][0]["ownership_type"]
    assert rows[str(year + 1)]["ownership_type"] == want
    assert rows[str(year + 1)]["soe"] == int(want == "LOCAL_SOE")
    assert rows[str(year + 1)]["top10_pct"] == pytest.approx(sum(x["ownership_pct"] for x in exp["top10"]["records"]) / 100)
    assert rows[str(year)]["ownership_type"] is None        # not yet published at mid-year
