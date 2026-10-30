"""Standard chart of CAS line items and the statement-table parser (v1.7).

``CHART`` maps the line items of the consolidated statements prescribed by
the Chinese Accounting Standards (企业会计准则, general-enterprise formats)
to standard codes. The mapping is versioned (``CHART_VERSION``); each value
extracted with it records the version in ``source_context`` so that a later
change of mapping is visible.

The parser reads only the consolidated statement pages (合并资产负债表,
合并利润表, 合并现金流量表), stopping at the parent-company statements, so
that a label met earlier in the narrative or later in the notes is not
mistaken for the statement line. The current-period column is taken
(the first amount after an optional note reference).
"""
from __future__ import annotations

import re

CHART_VERSION = "CAS-GE-2026.1"

# code, statement (BS/IS/CF), labels (first = canonical), sign hint
_BS = [
    ("cash", ["货币资金"]), ("settlement_reserves", ["结算备付金"]), ("lending_funds", ["拆出资金"]),
    ("trading_financial_assets", ["交易性金融资产"]), ("derivative_assets", ["衍生金融资产"]),
    ("notes_receivable", ["应收票据"]), ("accounts_receivable", ["应收账款"]),
    ("receivables_financing", ["应收款项融资"]), ("prepayments", ["预付款项", "预付账款"]),
    ("other_receivables", ["其他应收款"]), ("inventory", ["存货"]), ("contract_assets", ["合同资产"]),
    ("held_for_sale_assets", ["持有待售资产"]), ("non_current_assets_due_within_one_year", ["一年内到期的非流动资产"]),
    ("other_current_assets", ["其他流动资产"]), ("total_current_assets", ["流动资产合计"]),
    ("debt_investments", ["债权投资"]), ("other_debt_investments", ["其他债权投资"]),
    ("long_term_receivables", ["长期应收款"]), ("long_term_equity_investments", ["长期股权投资"]),
    ("other_equity_instrument_investments", ["其他权益工具投资"]),
    ("other_non_current_financial_assets", ["其他非流动金融资产"]), ("investment_property", ["投资性房地产"]),
    ("fixed_assets", ["固定资产"]), ("construction_in_progress", ["在建工程"]),
    ("productive_biological_assets", ["生产性生物资产"]), ("right_of_use_assets", ["使用权资产"]),
    ("intangible_assets", ["无形资产"]), ("development_expenditure", ["开发支出"]), ("goodwill", ["商誉"]),
    ("long_term_prepaid_expenses", ["长期待摊费用"]), ("deferred_tax_assets", ["递延所得税资产"]),
    ("other_non_current_assets", ["其他非流动资产"]), ("total_non_current_assets", ["非流动资产合计"]),
    ("total_assets", ["资产总计"]),
    ("short_term_borrowings", ["短期借款"]), ("trading_financial_liabilities", ["交易性金融负债"]),
    ("derivative_liabilities", ["衍生金融负债"]), ("notes_payable", ["应付票据"]),
    ("accounts_payable", ["应付账款"]), ("advances_from_customers", ["预收款项", "预收账款"]),
    ("contract_liabilities", ["合同负债"]), ("employee_benefits_payable", ["应付职工薪酬"]),
    ("taxes_payable", ["应交税费"]), ("other_payables", ["其他应付款"]),
    ("held_for_sale_liabilities", ["持有待售负债"]),
    ("non_current_liabilities_due_within_one_year", ["一年内到期的非流动负债"]),
    ("other_current_liabilities", ["其他流动负债"]), ("total_current_liabilities", ["流动负债合计"]),
    ("long_term_borrowings", ["长期借款"]), ("bonds_payable", ["应付债券"]), ("lease_liabilities", ["租赁负债"]),
    ("long_term_payables", ["长期应付款"]), ("provisions", ["预计负债"]), ("deferred_income", ["递延收益"]),
    ("deferred_tax_liabilities", ["递延所得税负债"]), ("other_non_current_liabilities", ["其他非流动负债"]),
    ("total_non_current_liabilities", ["非流动负债合计"]), ("total_liabilities", ["负债合计"]),
    ("share_capital", ["实收资本（或股本）", "实收资本(或股本)", "股本", "实收资本"]),
    ("other_equity_instruments", ["其他权益工具"]), ("capital_reserve", ["资本公积"]),
    ("treasury_shares", ["减：库存股", "库存股"]), ("other_comprehensive_income", ["其他综合收益"]),
    ("special_reserve", ["专项储备"]), ("surplus_reserve", ["盈余公积"]),
    ("general_risk_reserve", ["一般风险准备"]), ("retained_earnings", ["未分配利润"]),
    ("equity_parent", ["归属于母公司所有者权益（或股东权益）合计", "归属于母公司所有者权益(或股东权益)合计",
                       "归属于母公司所有者权益合计", "归属于母公司股东权益合计"]),
    ("minority_interests", ["少数股东权益"]),
    ("equity", ["所有者权益（或股东权益）合计", "所有者权益(或股东权益)合计", "所有者权益合计", "股东权益合计"]),
    ("total_liabilities_and_equity", ["负债和所有者权益（或股东权益）总计", "负债和所有者权益(或股东权益)总计",
                                      "负债和所有者权益总计", "负债和股东权益总计"]),
]
_IS = [
    ("total_operating_revenue", ["营业总收入"]), ("revenue", ["营业收入"]),
    ("total_operating_costs", ["营业总成本"]), ("cost_of_revenue", ["营业成本"]),
    ("taxes_and_surcharges", ["税金及附加"]), ("selling_expenses", ["销售费用"]),
    ("administrative_expenses", ["管理费用"]), ("rd_expense", ["研发费用"]), ("finance_expenses", ["财务费用"]),
    ("interest_expense", ["其中：利息费用", "利息费用"]), ("interest_income", ["利息收入"]),
    ("other_income", ["其他收益"]), ("investment_income", ["投资收益（损失以“－”号填列）", "投资收益"]),
    ("fair_value_change_gains", ["公允价值变动收益（损失以“－”号填列）", "公允价值变动收益"]),
    ("credit_impairment_losses", ["信用减值损失（损失以“-”号填列）", "信用减值损失"]),
    ("asset_impairment_losses", ["资产减值损失（损失以“-”号填列）", "资产减值损失"]),
    ("asset_disposal_gains", ["资产处置收益（损失以“－”号填列）", "资产处置收益"]),
    ("operating_profit", ["营业利润（亏损以“－”号填列）", "营业利润"]),
    ("non_operating_income", ["营业外收入"]), ("non_operating_expenses", ["营业外支出"]),
    ("profit_before_tax", ["利润总额（亏损总额以“－”号填列）", "利润总额"]),
    ("income_tax", ["所得税费用"]),
    ("net_profit", ["净利润（净亏损以“－”号填列）", "净利润"]),
    ("net_profit_continuing", ["持续经营净利润（净亏损以“－”号填列）", "持续经营净利润"]),
    ("net_profit_discontinued", ["终止经营净利润（净亏损以“－”号填列）", "终止经营净利润"]),
    ("net_profit_parent", ["归属于母公司股东的净利润（净亏损以“-”号填列）", "归属于母公司股东的净利润",
                           "归属于母公司所有者的净利润"]),
    ("minority_profit", ["少数股东损益（净亏损以“-”号填列）", "少数股东损益"]),
    ("other_comprehensive_income_net", ["其他综合收益的税后净额"]),
    ("total_comprehensive_income", ["综合收益总额"]),
    ("eps_basic", ["（一）基本每股收益(元/股)", "（一）基本每股收益（元/股）", "基本每股收益(元/股)",
                   "基本每股收益（元/股）", "基本每股收益"]),
    ("eps_diluted", ["（二）稀释每股收益(元/股)", "（二）稀释每股收益（元/股）", "稀释每股收益(元/股)",
                     "稀释每股收益（元/股）", "稀释每股收益"]),
]
_CF = [
    ("cash_from_sales", ["销售商品、提供劳务收到的现金"]), ("tax_refunds_received", ["收到的税费返还"]),
    ("other_operating_cash_in", ["收到其他与经营活动有关的现金"]),
    ("operating_cash_inflow", ["经营活动现金流入小计"]),
    ("cash_paid_for_goods", ["购买商品、接受劳务支付的现金"]),
    ("cash_paid_to_employees", ["支付给职工及为职工支付的现金", "支付给职工以及为职工支付的现金"]),
    ("taxes_paid", ["支付的各项税费"]), ("other_operating_cash_out", ["支付其他与经营活动有关的现金"]),
    ("operating_cash_outflow", ["经营活动现金流出小计"]),
    ("operating_cash_flow", ["经营活动产生的现金流量净额"]),
    ("cash_from_investment_recovery", ["收回投资收到的现金"]),
    ("cash_from_investment_income", ["取得投资收益收到的现金"]),
    ("cash_from_asset_disposals", ["处置固定资产、无形资产和其他长期资产收回的现金净额"]),
    ("investing_cash_inflow", ["投资活动现金流入小计"]),
    ("capex", ["购建固定资产、无形资产和其他长期资产支付的现金"]),
    ("cash_paid_for_investments", ["投资支付的现金"]),
    ("investing_cash_outflow", ["投资活动现金流出小计"]),
    ("investing_cash_flow", ["投资活动产生的现金流量净额"]),
    ("cash_from_capital_contributions", ["吸收投资收到的现金"]),
    ("cash_from_borrowings", ["取得借款收到的现金"]),
    ("financing_cash_inflow", ["筹资活动现金流入小计"]),
    ("cash_paid_for_debt", ["偿还债务支付的现金"]),
    ("cash_paid_for_dividends_interest", ["分配股利、利润或偿付利息支付的现金"]),
    ("financing_cash_outflow", ["筹资活动现金流出小计"]),
    ("financing_cash_flow", ["筹资活动产生的现金流量净额"]),
    ("fx_effect_on_cash", ["汇率变动对现金及现金等价物的影响"]),
    ("net_change_in_cash", ["现金及现金等价物净增加额"]),
    ("cash_at_beginning", ["期初现金及现金等价物余额"]),
    ("cash_at_end", ["期末现金及现金等价物余额"]),
]
CHART = {code: {"statement": st, "labels": labels}
         for st, items in (("BS", _BS), ("IS", _IS), ("CF", _CF)) for code, labels in items}

_HEADINGS = {"BS": r"合并资产负债表", "IS": r"合并利润表", "CF": r"合并现金流量表"}
_STOP = r"母公司资产负债表|母公司利润表|母公司现金流量表|合并所有者权益变动表|合并股东权益变动表"
_NUMTOK = r"-?\(?\d[\d,]*(?:\.\d+)?\)?|[-－—]"
_NOTE = r"(?:[一二三四五六七八九十]+[、.．]\s*\d+(?:[(（]\d+[)）])?|附注[\w、.．()（）]*|\d+(?:\.\d+)*|\([\d一二三四五六七八九十]+\)|（[\d一二三四五六七八九十]+）)"


def _labels_index():
    """Label -> (code, statement); longer labels first so they win."""
    out = []
    for code, spec in CHART.items():
        for lab in spec["labels"]:
            out.append((lab, code, spec["statement"]))
    out.sort(key=lambda x: -len(x[0]))
    return out


_LABELS = _labels_index()


def _norm_label(s: str) -> str:
    s = re.sub(r"\s+", "", s)
    s = re.sub(r"[（(][^（()）]*填列[)）]$", "", s)          # "（损失以“－”号填列）"
    s = re.sub(r"^(?:其中[:：]|加[:：]|减[:：]|[一二三四五六七八九十]+、|[（(][一二三四五六七八九十\d]+[)）]|\d+[.．、])", "", s)
    return s.replace("(", "（").replace(")", "）")


def _to_float(tok: str) -> float | None:
    t = tok.replace(",", "")
    if t in ("-", "－", "—"):
        return None
    neg = t.startswith("(") and t.endswith(")")
    t = t.strip("()")
    try:
        v = float(t)
    except ValueError:
        return None
    return -v if neg else v


_ROW_PATTERNS = (
    # label, note reference, current, prior
    re.compile(r"^(.*?)\s+" + _NOTE + r"\s+(" + _NUMTOK + r")\s+(" + _NUMTOK + r")\s*$"),
    # label, current, [prior]
    re.compile(r"^(.*?)\s+(" + _NUMTOK + r")(?:\s+(" + _NUMTOK + r"))?\s*$"),
    # label, Chinese-numeral note reference, current
    re.compile(r"^(.*?)\s+[一二三四五六七八九十]+[、.．]\s*\d+\s+(" + _NUMTOK + r")()\s*$"),
)


def _match_row(line: str):
    """A plain number after the label is a note reference only when two amounts
    follow it; otherwise it is the current amount ("净利润 450.00 400.00")."""
    for rx in _ROW_PATTERNS:
        m = rx.match(line)
        if m and not re.search(r"\d", re.sub(r"[（(][^）)]*[)）]", "", m.group(1))):
            return m
    return None


def statement_pages(pages: list[str]) -> dict[str, list[tuple[int, str]]]:
    """Text of each consolidated statement, as (page number, text) pieces."""
    out: dict[str, list] = {"BS": [], "IS": [], "CF": []}
    current = None
    for pno, page in enumerate(pages, start=1):
        pieces = re.split(f"({'|'.join(_HEADINGS.values())}|{_STOP})", page)
        for piece in pieces:
            if not piece:
                continue
            hit = next((st for st, h in _HEADINGS.items() if re.fullmatch(h, piece)), None)
            if hit:
                current = hit
                continue
            if re.fullmatch(_STOP, piece):
                current = None
                continue
            if current:
                out[current].append((pno, piece))
    return out


def parse_statement_items(pages: list[str], unit_mult: float | None = None) -> list[dict]:
    """Line items of the consolidated statements (current-period column)."""
    from .units import first_declared, last_declared
    found: dict[str, dict] = {}
    for st, pieces in statement_pages(pages).items():
        carried = None
        for k, (pno, text) in enumerate(pieces):
            # v2.1: a statement continued on the next page keeps the unit declared on its first page (banks state
            # 百万元 once, under the heading); before its first piece, a declaration at the foot of the page
            # before the heading applies, as in the unit rule of v2.0.8
            declared = last_declared(text) or carried or first_declared(pages[pno - 1])
            if declared is None and k == 0 and pno >= 2:
                declared = last_declared(pages[pno - 2])
            carried = declared or carried
            mult = unit_mult or (declared[1] if declared else 1.0)
            for raw in text.splitlines():
                line = raw.replace("　", " ").strip()
                if not line:
                    continue
                m = _match_row(line)
                if not m:
                    continue
                label = _norm_label(m.group(1))
                if not label or re.search(r"\d", label):
                    continue
                hit = next(((code, s2) for lab, code, s2 in _LABELS
                            if s2 == st and _norm_label(lab) == label), None)
                if not hit:
                    continue
                code = hit[0]
                if code in found:
                    continue
                v = _to_float(m.group(2))
                if v is None:
                    continue
                per_share = code.startswith("eps_")
                # v2.0.8 (finding 85): an amount cut at a separator or line break ("22,103" for 22,103,629.82 in
                # yuan, "1,355.2") is not taken; statement amounts in yuan carry two decimals.
                from .numbers import well_formed_amount
                if not per_share and not well_formed_amount(m.group(2), mult):
                    continue
                found[code] = {"metric": code, "value": v if per_share else v * mult, "raw_value": m.group(2),
                               "label": m.group(1).strip(), "page": pno, "statement": st,
                               "prior_raw": m.group(3), "unit": "CNY_PER_SHARE" if per_share else "CNY"}
    return list(found.values())
