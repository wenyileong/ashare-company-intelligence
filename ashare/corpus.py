"""Synthetic golden corpus for CI (v1.4).

Generates annual-report-like documents from seeded random values, with the
layout variations seen in real reports (units of 元 or 万元, label variants,
note references between label and value, narrative sentences that mention
the same labels, offshore entities, wrapped role descriptions). The expected
values are the *true* values used to write each document, not the parser's
output, so the corpus measures the parsers rather than restating them.

A synthetic corpus checks that parsers do not regress; it is never used to
calibrate confidence, which needs a corpus verified against real reports.
"""
from __future__ import annotations

import json
import random
from pathlib import Path

SURNAMES = "王李张刘陈杨黄赵吴周徐孙马朱胡郭何林罗高"
GIVEN = "伟芳娜敏静丽强磊军洋勇艳杰涛明超秀霞平刚桂英华建国志红"
PRODUCTS = [("白酒", "系列酒", "其他业务"), ("新能源汽车动力电池系统", "储能电池及系统集成", "其他"), ("锂电池", "储能系统", "材料"), ("通信设备", "软件服务", "其他"),
            ("乘用车", "商用车", "零部件"), ("原料药", "制剂", "医疗器械")]
REGION_SETS = [("境内", "境外"), ("国内", "国外"), ("华东地区", "华南地区", "海外")]
PLACES = ["上海", "深圳", "北京", "杭州", "成都", "苏州", "武汉"]
OFFSHORE_PLACES = [("香港", "HONG_KONG"), ("开曼群岛", "OFFSHORE"), ("英属维尔京群岛", "OFFSHORE"), ("新加坡", "FOREIGN")]


def _fmt(v: float, decimals: int = 2) -> str:
    return f"{v:,.{decimals}f}"


def _pct(v: float) -> str:
    return f"{v * 100:.2f}%"


def _ratio(v: float) -> float:
    """The ratio as printed with two decimals of a percentage."""
    return float(f"{v * 100:.2f}") / 100


def _name(rng) -> str:
    return rng.choice(SURNAMES) + "".join(rng.choice(GIVEN) for _ in range(rng.choice((1, 2))))


def _annual_report(rng: random.Random, idx: int) -> tuple[str, list[list[str]], dict]:
    year = rng.choice((2021, 2022, 2023, 2024, 2025))
    unit_label, mult = rng.choice((("元", 1.0), ("万元", 1e4)))
    company = f"示例{idx:02d}科技股份有限公司"
    title = f"{company}{year}年年度报告"
    exp: dict = {}
    table = rng.random() < 0.5          # half the reports draw tables cell by cell
    valign = rng.choice(("middle", "top"))

    def row(*cells):
        """A table row: drawn by cell in 'table' reports, as one line otherwise."""
        if table:
            return {"row": [c if isinstance(c, list) else str(c) for c in cells], "valign": valign}
        return " ".join(_join_wrapped(c) if isinstance(c, list) else str(c) for c in cells)

    def wrap(text, n):
        if not table or len(text) <= n:
            return text
        if " " in text:  # Latin names wrap at a space
            if len(text) <= 2 * n:
                return text
            cut = text.rfind(" ", 0, 2 * n)
            return [text[:cut], text[cut + 1:]] if cut > 0 else text
        return [text[:n], text[n:]]

    # ---- financial statements -------------------------------------------------
    revenue = round(rng.uniform(5e4, 5e6), 2)            # in table units
    cost = round(revenue * rng.uniform(0.3, 0.8), 2)
    op_profit = round(revenue * rng.uniform(0.05, 0.3), 2)
    pbt = round(op_profit * rng.uniform(0.95, 1.05), 2)
    tax = round(pbt * 0.15, 2)
    net = round(pbt - tax, 2)
    parent = round(net * rng.uniform(0.85, 1.0), 2)
    parent_ex = round(parent * rng.uniform(0.8, 1.05), 2)
    assets = round(revenue * rng.uniform(1.0, 3.0), 2)
    liabilities = round(assets * rng.uniform(0.2, 0.7), 2)
    equity = round(assets - liabilities, 2)
    cash = round(assets * rng.uniform(0.05, 0.3), 2)
    rd_exp = round(revenue * rng.uniform(0.01, 0.08), 2)
    ocf = round(net * rng.uniform(0.6, 1.4), 2) * (-1 if rng.random() < 0.2 else 1)
    prior = lambda v: round(v / rng.uniform(1.02, 1.3), 2)  # noqa: E731
    p1 = [f"{title}", "第二节 公司简介和主要财务指标", "七、主要会计数据和财务指标", f"单位：{unit_label} 币种：人民币"]
    if rng.random() < 0.5:
        p1.append(f"报告期内，公司营业收入同比增长{rng.uniform(2, 30):.2f}%，经营情况稳定。")
    p1 += [
        f"主要会计数据 {year}年 {year - 1}年 本期比上年同期增减",
        row("营业收入", _fmt(revenue), _fmt(prior(revenue)), f"{rng.uniform(2, 30):.2f}%"),
        row(wrap("归属于上市公司股东的净利润", 9), _fmt(parent), _fmt(prior(parent)), f"{rng.uniform(2, 30):.2f}%"),
        row(wrap("归属于上市公司股东的扣除非经常性损益的净利润", 9), _fmt(parent_ex), _fmt(prior(parent_ex)),
            f"{rng.uniform(2, 30):.2f}%"),
    ]
    ocf_row = f"{_fmt(ocf)} {_fmt(prior(ocf))} {rng.uniform(2, 30):.2f}%"
    if table:
        p1.append(row(wrap("经营活动产生的现金流量净额", 9), _fmt(ocf), _fmt(prior(ocf)), f"{rng.uniform(2, 30):.2f}%"))
    elif rng.random() < 0.3:
        # a label wrapped onto its own line, as text extraction often leaves it
        p1 += ["经营活动产生的现金流量净额", ocf_row]
    else:
        p1.append(f"经营活动产生的现金流量净额 {ocf_row}")
    eq_label = rng.choice(("所有者权益合计", "所有者权益（或股东权益）合计", "股东权益合计"))
    p2 = ["第十节 财务报告", "合并资产负债表", f"单位：{unit_label}", "项目 附注 期末余额 期初余额",
          f"货币资金 七、1 {_fmt(cash)} {_fmt(prior(cash))}",
          f"资产总计 {_fmt(assets)} {_fmt(prior(assets))}",
          f"负债合计 {_fmt(liabilities)} {_fmt(prior(liabilities))}",
          f"{eq_label} {_fmt(equity)} {_fmt(prior(equity))}",
          "合并利润表",
          f"营业成本 七、61 {_fmt(cost)} {_fmt(prior(cost))}",
          f"研发费用 七、65 {_fmt(rd_exp)} {_fmt(prior(rd_exp))}",
          f"营业利润 {_fmt(op_profit)} {_fmt(prior(op_profit))}",
          f"利润总额 {_fmt(pbt)} {_fmt(prior(pbt))}",
          f"所得税费用 七、76 {_fmt(tax)} {_fmt(prior(tax))}",
          f"净利润 {_fmt(net)} {_fmt(prior(net))}"]
    exp["financials"] = {"complete": False, "records": [
        {"metric": m, "value": v * mult} for m, v in (
            ("revenue", revenue), ("net_profit_parent", parent), ("net_profit_parent_ex_nonrecurring", parent_ex),
            ("operating_cash_flow", ocf), ("cash", cash),
            ("total_assets", assets), ("total_liabilities", liabilities), ("equity", equity),
            ("cost_of_revenue", cost), ("rd_expense", rd_exp), ("operating_profit", op_profit),
            ("profit_before_tax", pbt), ("income_tax", tax), ("net_profit", net))]}

    exp["statements"] = {"complete": True, "records": [
        {"metric": m, "value": v * mult} for m, v in (
            ("cash", cash), ("total_assets", assets), ("total_liabilities", liabilities), ("equity", equity),
            ("cost_of_revenue", cost), ("rd_expense", rd_exp), ("operating_profit", op_profit),
            ("profit_before_tax", pbt), ("income_tax", tax), ("net_profit", net))]}

    # ---- segments -------------------------------------------------------------------
    names = rng.choice(PRODUCTS)
    weights = [rng.uniform(1, 10) for _ in names]
    seg_rev = [round(revenue * w / sum(weights), 2) for w in weights]
    seg_rev[-1] = round(revenue - sum(seg_rev[:-1]), 2)
    regions = rng.choice(REGION_SETS)
    rw = [rng.uniform(5, 10)] + [rng.uniform(0.2, 2) for _ in regions[1:]]
    reg_rev = [round(revenue * w / sum(rw), 2) for w in rw]
    reg_rev[-1] = round(revenue - sum(reg_rev[:-1]), 2)
    p3 = ["第三节 管理层讨论与分析", "四、主营业务分析", "（1）营业收入构成", f"单位：{unit_label}",
          f"项目 {year}年 {year - 1}年 同比增减", "金额 占营业收入比重 金额 占营业收入比重",
          f"营业收入合计 {_fmt(revenue)} 100% {_fmt(prior(revenue))} 100% {rng.uniform(2, 30):.2f}%", "分产品"]
    seg_records = [{"dimension": "TOTAL", "segment_name": "营业收入合计", "revenue": revenue * mult}]
    for n, v in zip(names, seg_rev):
        pr = prior(v)
        p3.append(row(wrap(n, 6), _fmt(v), _pct(v / revenue), _fmt(pr), _pct(pr / revenue), _pct(v / pr - 1)))
        seg_records.append({"dimension": "PRODUCT", "segment_name": n, "revenue": v * mult,
                            "revenue_share": _ratio(v / revenue), "revenue_prior": pr * mult})
    p3.append("分地区")
    for n, v in zip(regions, reg_rev):
        pr = prior(v)
        p3.append(row(n, _fmt(v), _pct(v / revenue), _fmt(pr), _pct(pr / revenue), _pct(v / pr - 1)))
        seg_records.append({"dimension": "REGION", "segment_name": n, "revenue": v * mult,
                            "revenue_share": _ratio(v / revenue), "revenue_prior": pr * mult})
    p4 = ["（2）主营业务分行业、分产品、分地区、分销售模式情况", f"单位：{unit_label}",
          "营业收入 营业成本 毛利率 营业收入比上年增减 营业成本比上年增减 毛利率比上年增减", "分产品"]
    for n, v in zip(names, seg_rev):
        c = round(v * rng.uniform(0.2, 0.8), 2)
        gm = _ratio(1 - c / v)
        p4.append(row(wrap(n, 6), _fmt(v), _fmt(c), f"{gm * 100:.2f}%", f"{rng.uniform(-5, 30):.2f}%",
                      f"{rng.uniform(-5, 30):.2f}%", f"{rng.uniform(-3, 3):.2f}%"))
        rec = next(r for r in seg_records if r["segment_name"] == n)
        rec["cost"], rec["gross_margin"] = c * mult, gm
    exp["segments"] = {"complete": True, "records": seg_records}

    # ---- group ----------------------------------------------------------------------
    p5 = ["十、在其他主体中的权益", "1、在子公司中的权益", "（1）企业集团的构成",
          "子公司名称 主要经营地 注册地 业务性质 持股比例(%) 取得方式", "直接 间接"]
    subs = []
    for j in range(rng.randint(3, 6)):
        if j == 0 or rng.random() < 0.7:
            place, jur = rng.choice(PLACES), "MAINLAND"
            ename = f"{place}示例{idx:02d}{j}" + rng.choice(("有限公司", "智能装备销售有限公司", "新材料科技有限公司"))
        else:
            place, jur = rng.choice(OFFSHORE_PLACES)
            ename = f"Example {idx:02d}{j} Holdings Limited"
        direct = rng.choice((100.0, 100.0, 70.0, 51.0, None))
        indirect = None if direct is not None else rng.choice((100.0, 60.0))
        acq = rng.choice(("设立", "非同一控制下企业合并", "同一控制下企业合并"))
        acq_code = {"设立": "ESTABLISHED", "非同一控制下企业合并": "BUSINESS_COMBINATION_NOT_COMMON_CONTROL",
                    "同一控制下企业合并": "BUSINESS_COMBINATION_COMMON_CONTROL"}[acq]
        d_txt = f"{direct:.2f}" if direct is not None else "-"
        i_txt = f"{indirect:.2f}" if indirect is not None else "-"
        p5.append(row(wrap(ename, 10), place, place, "产品销售", d_txt, i_txt, acq))
        subs.append({"entity_name": ename, "registered_place": place, "principal_place": place,
                     "jurisdiction_class": jur, "direct_pct": direct, "indirect_pct": indirect,
                     "total_pct": (direct or 0) + (indirect or 0), "acquisition_method": acq_code,
                     "relationship": "SUBSIDIARY"})
    exp["subsidiaries"] = {"complete": True, "records": subs}

    # ---- R&D and workforce -----------------------------------------------------------
    rd_staff = rng.randint(100, 3000)
    employees = rd_staff * rng.randint(4, 12)
    rd_inv = round(rd_exp * rng.uniform(1.0, 1.2), 2)
    rd_cap = round(rd_inv * rng.uniform(0, 0.3), 2)
    p6 = ["5、研发投入", "（1）研发投入情况表", rng.choice((f"单位：{unit_label}", f"金额单位：{unit_label} 币种：人民币", f"单位：人民币{unit_label}")),
          f"本期费用化研发投入 {_fmt(round(rd_inv - rd_cap, 2))}", f"本期资本化研发投入 {_fmt(rd_cap)}",
          f"研发投入合计 {_fmt(rd_inv)}", f"研发投入总额占营业收入比例（%） {rd_inv / revenue * 100:.2f}",
          f"研发投入资本化的比重（%） {rd_cap / rd_inv * 100:.2f}",
          f"公司研发人员的数量 {rd_staff:,}", f"研发人员数量占公司总人数的比例（%） {rd_staff / employees * 100:.2f}"]
    comp_items = [("生产人员", "staff_production"), ("销售人员", "staff_sales"), ("技术人员", "staff_technical"),
                  ("财务人员", "staff_finance"), ("行政人员", "staff_admin")]
    cw = [rng.uniform(1, 10) for _ in comp_items]
    comp = [int(employees * w / sum(cw)) for w in cw]
    comp[0] += employees - sum(comp)
    edu_items = [("博士研究生", "edu_doctorate"), ("硕士研究生", "edu_master"), ("本科", "edu_bachelor"),
                 ("专科", "edu_college"), ("高中及以下", "edu_below_college")]
    ew = [0.2, 2, 6, 5, 4]
    edu = [int(employees * w / sum(ew)) for w in ew]
    edu[-1] += employees - sum(edu)
    parent_staff = int(employees * rng.uniform(0.2, 0.6))
    p7 = ["九、报告期末母公司和主要子公司的员工情况", "（一）员工情况",
          f"母公司在职员工的数量 {parent_staff:,}", f"主要子公司在职员工的数量 {employees - parent_staff:,}",
          f"在职员工的数量合计 {employees:,}", "专业构成", "专业构成类别 专业构成人数"]
    p7 += [f"{lab} {v:,}" for (lab, _), v in zip(comp_items, comp)] + [f"合计 {employees:,}", "教育程度",
                                                                      "教育程度类别 数量（人）"]
    p7 += [f"{lab} {v:,}" for (lab, _), v in zip(edu_items, edu)] + [f"合计 {employees:,}"]
    hc = [{"item": "rd_investment", "value": rd_inv * mult}, {"item": "rd_capitalised", "value": rd_cap * mult},
          {"item": "rd_ratio", "value": _ratio(rd_inv / revenue)},
          {"item": "rd_expensed", "value": round(rd_inv - rd_cap, 2) * mult},
          {"item": "rd_capitalised_ratio", "value": _ratio(rd_cap / rd_inv)},
          {"item": "rd_staff_ratio", "value": _ratio(rd_staff / employees)}, {"item": "rd_staff", "value": float(rd_staff)},
          {"item": "employees_total", "value": float(employees)}, {"item": "employees_parent", "value": float(parent_staff)}]
    hc += [{"item": code, "value": float(v)} for (_, code), v in zip(comp_items, comp)]
    hc += [{"item": code, "value": float(v)} for (_, code), v in zip(edu_items, edu)]
    exp["human_capital"] = {"complete": False, "records": hc}

    # ---- officers ------------------------------------------------------------------
    p8 = ["第四节 公司治理", "（一）现任及报告期内离任董事、监事和高级管理人员持股变动及报酬情况", "单位：股",
          "姓名 职务 性别 年龄 任期起始日期 任期终止日期 年初持股数 年末持股数 年度内股份增减变动量 "
          "报告期内从公司获得的税前报酬总额（万元） 是否在公司关联方获取报酬"]
    roles = [("董事长", "CHAIR"), (rng.choice(("董事、总经理", "董事、总经理、党委副书记")), "DIRECTOR|GENERAL_MANAGER"), ("董事", "DIRECTOR"),
             ("独立董事", "INDEPENDENT_DIRECTOR"), ("独立董事", "INDEPENDENT_DIRECTOR"),
             ("监事会主席", "SUPERVISOR_CHAIR"), ("财务总监", "CFO"), ("董事会秘书", "BOARD_SECRETARY")]
    roster, used = [], set()
    start = f"{year - 1}年{rng.randint(1, 12)}月{rng.randint(1, 28)}日"
    end = f"{year + 2}年{rng.randint(1, 12)}月{rng.randint(1, 28)}日"
    for role_text, codes in roles:
        nm = _name(rng)
        while nm in used:
            nm = _name(rng)
        used.add(nm)
        g = rng.choice(("男", "女"))
        age = rng.randint(38, 68)
        pay = round(rng.uniform(10, 300), 2)
        status = rng.choice(("现任", "现任", "现任", "离任"))
        p8.append(row(nm, wrap(role_text, 6), g, age, status, start, end, 0, 0, 0, pay, "否"))
        roster.append({"person_name": nm, "role_codes": codes, "gender": g, "age": age,
                       "status": {"现任": "SERVING", "离任": "LEFT"}[status], "remuneration": pay * 1e4})
    exp["roster"] = {"complete": True, "records": roster}

    # ---- ESG ------------------------------------------------------------------------
    key_unit = rng.random() < 0.5
    cod = round(rng.uniform(10, 500), 1)
    donation_wan = rng.randint(50, 5000)
    p9 = ["第五节 环境和社会责任", "一、环境信息情况",
          "公司属于环境保护部门公布的重点排污单位。" if key_unit else "公司不属于环境保护部门公布的重点排污单位。"]
    esg = [{"item": "key_pollutant_discharge_unit", "value": 1.0 if key_unit else 0.0}]
    if key_unit:
        p9.append(f"化学需氧量 排放总量 {cod} 吨；")
        esg.append({"item": "emission_cod", "value": cod})
    p9.append(f"报告期内公司对外捐赠合计 {donation_wan:,} 万元。")
    esg.append({"item": "donations", "value": donation_wan * 1e4})
    exp["esg"] = {"complete": False, "records": esg}

    # ---- shareholders and control --------------------------------------------------
    total_shares = rng.randint(2, 40) * 1e8
    soe = rng.random() < 0.5
    if soe:
        prov = rng.choice(("贵州", "江苏", "浙江", "四川", "山东"))
        holder = f"{prov}省示例{idx:02d}投资集团有限公司"
        controller, c_nature, c_type, h_nature = f"{prov}省人民政府国有资产监督管理委员会", "地方国资管理机构", \
            "LOCAL_SOE", "国有法人"
    else:
        controller = _name(rng)
        holder, c_nature, c_type, h_nature = controller, "境内自然人", "PRIVATE", "境内自然人"
    holders = [(holder, h_nature, rng.uniform(25, 55))]
    holders.append(("香港中央结算有限公司", "境外法人", rng.uniform(2, 8)))
    for k in range(rng.randint(3, 6)):
        if rng.random() < 0.5:
            holders.append((f"中国工商银行股份有限公司－示例{idx:02d}{k}混合型证券投资基金", "其他", rng.uniform(0.5, 2)))
        else:
            holders.append((_name(rng), "境内自然人", rng.uniform(0.3, 1.5)))
    holders.sort(key=lambda h: -h[2])
    # v2.0.7 (finding 68): odd-numbered reports use the layout with the nature after the name (as in the
    # Shenzhen templates); every fourth has the nature glued to the name, as PDF text often gives it. Chosen by
    # the report number, so the random sequence (and every other document) is unchanged.
    layout_b, glued = idx % 2 == 1, idx % 4 == 1
    p10 = ["第七节 股份变动及股东情况", "（二）截至报告期末前十名股东持股情况", "单位：股",
           "股东名称 股东性质 持股比例(%) 报告期末持股数量 报告期内增减变动情况 持有有限售条件的股份数量 "
           "持有无限售条件的股份数量 质押、标记或冻结情况" if layout_b else
           "股东名称（全称） 报告期内增减 期末持股数量 比例(%) 持有有限售条件股份数量 质押、标记或冻结情况 股东性质"]
    top10, trad = [], []
    for name, nature, pct in holders:
        pct = round(pct, 2)
        shares = round(total_shares * pct / 100)
        change = rng.choice((0, rng.randint(-5, 5) * 100000))
        pledged = rng.choice((None, None, round(shares * 0.2)))
        state = ("质押", f"{pledged:,}") if pledged else ("无", "0")
        if layout_b and glued:
            p10.append(row(wrap(name + nature, 12), f"{pct:.2f}", f"{shares:,}", f"{change:,}", "0", f"{shares:,}",
                           state[0], state[1]))
        elif layout_b:
            p10.append(row(wrap(name, 12), nature, f"{pct:.2f}", f"{shares:,}", f"{change:,}", "0", f"{shares:,}",
                           state[0], state[1]))
        else:
            p10.append(row(wrap(name, 12), f"{change:,}", f"{shares:,}", f"{pct:.2f}", "0", state[0], state[1],
                           nature))
        top10.append({"shareholder_name": name, "shares": float(shares), "ownership_pct": pct,
                      "change_shares": float(change), "pledged_shares": float(pledged) if pledged else None,
                      "shareholder_nature": nature})
    p10 += ["（三）前十名无限售条件股东持股情况", "股东名称 持有无限售条件流通股的数量 股份种类 数量"]
    for name, nature, pct in holders:
        shares = round(total_shares * round(pct, 2) / 100)
        p10.append(row(wrap(name, 12), f"{shares:,}", "人民币普通股", f"{shares:,}"))
        trad.append({"shareholder_name": name, "tradable_shares": float(shares)})
    p10 += ["上述股东关联关系或一致行动的说明 未知"]
    exp["top10"] = {"complete": True, "records": top10}
    exp["top10_tradable"] = {"complete": True, "records": trad}
    p11 = ["四、控股股东和实际控制人情况", "（一）控股股东情况", "1 法人" if soe else "1 自然人",
           f"名称 {holder}" if soe else f"姓名 {holder}", "单位负责人或法定代表人 " + _name(rng) if soe else "国籍 中国",
           "（二）实际控制人情况", f"名称 {controller}" if soe else f"姓名 {controller}",
           f"实际控制人性质 {c_nature}"]
    exp["control"] = {"complete": False, "records": [{"record": "control", "controlling_shareholder": holder,
                                                        "actual_controller": controller, "ownership_type": c_type}]}

    pages = [p1, p2, p3, p4, p5, p6, p7, p8, p9, p10, p11]
    pages = [[line for line in p if line] for p in pages]
    return title, pages, exp


def _dividend_notice(rng: random.Random, idx: int):
    year = rng.choice((2022, 2023, 2024, 2025))
    base = rng.randint(2, 40) * 50_000_000
    per10 = round(rng.uniform(0.5, 30), 2)
    total = round(base * per10 / 10, 2)
    rd = (year + 1, rng.randint(5, 7), rng.randint(1, 20))
    title = f"示例{idx:02d}股份有限公司{year}年年度权益分派实施公告"
    lines = [title, "一、通过分配方案的股东大会届次和日期",
             f"本次利润分配以方案实施前的公司总股本{base:,}股为基数，向全体股东每10股派发现金红利{per10}元（含税），"
             f"共计派发现金红利{total:,.2f}元。",
             "相关日期",
             f"股权登记日：{rd[0]}年{rd[1]}月{rd[2]}日 除权（息）日：{rd[0]}年{rd[1]}月{rd[2] + 1}日 "
             f"现金红利发放日：{rd[0]}年{rd[1]}月{rd[2] + 1}日"]
    exp = {"corporate_actions": {"complete": False, "records": [{
        "action_type": "CASH_DIVIDEND", "cash_amount": round(per10 / 10, 6), "base_share_count": float(base),
        "total_cash_amount": total, "tax_basis": "PRE_TAX",
        "record_date": f"{rd[0]}-{rd[1]:02d}-{rd[2]:02d}", "ex_date": f"{rd[0]}-{rd[1]:02d}-{rd[2] + 1:02d}",
        "payment_date": f"{rd[0]}-{rd[1]:02d}-{rd[2] + 1:02d}"}]}}
    return title, [lines], exp


def _penalty_notice(rng: random.Random, idx: int):
    company = f"示例{idx:02d}股份有限公司"
    fine_wan = rng.choice((100, 200, 500, 1000))
    num = rng.randint(1, 120)
    year = rng.choice((2023, 2024, 2025, 2026))
    m, d = rng.randint(1, 12), rng.randint(1, 28)
    title = f"{company}关于收到中国证监会行政处罚决定书的公告"
    lines = [title, f"本公司于{year}年{m}月{d}日收到中国证券监督管理委员会《行政处罚决定书》（〔{year}〕{num}号）。",
             "经查明，公司未按规定披露关联交易，年度报告存在虚假记载。",
             "上述行为违反了《证券法》第七十八条第二款的规定，构成《证券法》第一百九十七条第二款所述的违法行为。",
             "中国证监会决定：",
             f"一、对{company}责令改正，给予警告，并处以{fine_wan:,}万元罚款；",
             f"二、对{_name(rng)}给予警告，并处以{fine_wan // 2:,}万元罚款。"]
    exp = {"regulatory": {"complete": False, "records": [{
        "event_type": "ADMINISTRATIVE_PENALTY", "legal_classification": "ADMINISTRATIVE_PENALTY",
        "authority": "CSRC", "event_date": f"{year}-{m:02d}-{d:02d}", "document_number": f"〔{year}〕{num}号",
        "fine_amount_total": fine_wan * 1e4 * 1.5, "fine_amount_company": fine_wan * 1e4}]}}
    return title, [lines], exp


def _width(text: str, size: float = 8.0) -> float:
    return sum(size if ord(ch) > 0x2E80 else size * 0.55 for ch in text)


def _join_wrapped(parts: list[str]) -> str:
    out = parts[0]
    for p in parts[1:]:
        out += ("" if ord(out[-1]) > 0x2E80 or ord(p[0]) > 0x2E80 else " ") + p
    return out


def _line_text(item) -> str:
    if isinstance(item, dict):
        return " ".join(_join_wrapped(c) if isinstance(c, list) else c for c in item["row"])
    return item


def _pledge_notice(rng: random.Random, idx: int):
    company = f"示例{idx:02d}股份有限公司"
    holder = f"示例{idx:02d}控股集团有限公司"
    shares = rng.randint(1, 50) * 1_000_000
    hold_pct = round(rng.uniform(1, 30), 2)
    tot_pct = round(rng.uniform(0.2, 5), 2)
    y, m, d = rng.choice((2024, 2025)), rng.randint(1, 12), rng.randint(1, 28)
    pledgee = rng.choice(("中信证券股份有限公司", "华泰证券股份有限公司", "中国银行股份有限公司贵阳分行"))
    title = f"{company}关于控股股东部分股份质押的公告"
    lines = [title, f"公司于近日接到控股股东{holder}的通知，获悉其所持有本公司的部分股份被质押，具体如下：",
             f"公司控股股东{holder}将其持有的本公司{shares:,}股无限售条件流通股质押给{pledgee}，",
             f"本次质押股份占其所持股份比例为{hold_pct:.2f}%，占公司总股本比例为{tot_pct:.2f}%。",
             f"质押起始日{y}年{m}月{d}日。"]
    exp = {"pledges": {"complete": False, "records": [{
        "pledgor": holder, "shares": float(shares), "pledgee": pledgee, "pct_of_holding": hold_pct / 100,
        "pct_of_total": tot_pct / 100, "start_date": f"{y}-{m:02d}-{d:02d}", "event_type": "PLEDGE"}]}}
    return title, [lines], exp


def _write_pdf(path: Path, pages: list[list]):
    """Lines are drawn one text object each; table rows are drawn cell by cell
    in one text object per page, the way many report generators do, so that
    pypdf returns wrapped cells as separate lines."""
    from reportlab.pdfgen import canvas
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.cidfonts import UnicodeCIDFont
    try:
        pdfmetrics.getFont("STSong-Light")
    except KeyError:
        pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))
    c = canvas.Canvas(str(path))
    line_h = 10
    for items in pages:
        c.setFont("STSong-Light", 8)
        y = 810
        i = 0
        while i < len(items):
            item = items[i]
            if not isinstance(item, dict):
                c.drawString(30, y, item)
                y -= 14
                i += 1
                continue
            j = i
            while j < len(items) and isinstance(items[j], dict):
                j += 1
            rows = items[i:j]
            ncol = max(len(r["row"]) for r in rows)
            widths = [0.0] * ncol
            for r in rows:
                for k, cell in enumerate(r["row"]):
                    widths[k] = max(widths[k], max(_width(x) for x in (cell if isinstance(cell, list) else [cell])))
            gap = 14
            xs, x = [], 30.0
            for w in widths:
                xs.append(x)
                x += w + gap
            t = c.beginText()
            t.setFont("STSong-Light", 8)
            for r in rows:
                n_lines = max(len(cell) if isinstance(cell, list) else 1 for cell in r["row"])
                for k, cell in enumerate(r["row"]):
                    parts = cell if isinstance(cell, list) else [cell]
                    if len(parts) == 1 and r["valign"] == "middle":
                        top = y - (n_lines - 1) * line_h / 2
                    else:
                        top = y
                    for m, part in enumerate(parts):
                        t.setTextOrigin(xs[k], top - m * line_h)
                        t.textOut(part)
                y -= n_lines * line_h + 6
            c.drawText(t)
            i = j
        c.showPage()
    c.save()


def build_synthetic_corpus(out_dir: str | Path, n_reports: int = 8, n_notices: int = 4, seed: int = 20260101,
                           fmt: str = "auto") -> dict:
    """Write a synthetic corpus; ``fmt`` is 'pdf', 'txt' or 'auto' (pdf if reportlab is installed)."""
    if fmt == "auto":
        try:
            import reportlab  # noqa: F401
            fmt = "pdf"
        except ImportError:
            fmt = "txt"
    root = Path(out_dir)
    (root / "docs").mkdir(parents=True, exist_ok=True)
    (root / "expected").mkdir(parents=True, exist_ok=True)
    rng = random.Random(seed)
    docs = []
    builders = [("ar", _annual_report, n_reports), ("div", _dividend_notice, n_notices),
                ("pen", _penalty_notice, n_notices), ("plg", _pledge_notice, n_notices)]
    for prefix, builder, count in builders:
        for i in range(count):
            title, pages, exp = builder(rng, i + 1)
            doc_id = f"{prefix}{i + 1:02d}"
            file = root / "docs" / f"{doc_id}.{fmt}"
            if fmt == "pdf":
                _write_pdf(file, pages)
            else:
                file.write_text("\f".join("\n".join(_line_text(x) for x in p) for p in pages), encoding="utf-8")
            docs.append({"id": doc_id, "file": f"docs/{file.name}", "title": title,
                         "announcement_date": None, "security_code": None})
            (root / "expected" / f"{doc_id}.json").write_text(json.dumps(
                {"id": doc_id, "verified": True, "parsers": exp}, ensure_ascii=False, indent=2), encoding="utf-8")
    manifest = {"name": f"synthetic-{seed}", "synthetic": True, "version": 1, "seed": seed, "documents": docs}
    (root / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"corpus": str(root), "documents": len(docs), "format": fmt}
