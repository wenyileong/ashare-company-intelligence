import json
from helpers import make_pdf, add_disclosure
from ashare.regulatory import (
    classify_event_title, parse_event_text, parse_cited_provisions, parse_sanctions,
    cn_to_int, detect_authority, _opinion_from,
)


class Co:
    legal_name_cn = "示例科技股份有限公司"
    short_name_cn = "示例股份"
    exchange = "SSE"
    security_code = "600519"


def kinds(title):
    return [(e["event_type"], e["status"], e["event_subtype"]) for e in classify_event_title(title)]


def test_title_classification():
    assert kinds("关于收到中国证券监督管理委员会立案告知书的公告") == [("CSRC_INVESTIGATION", "INITIATED", None)]
    assert kinds("关于收到《行政处罚事先告知书》的公告") == [("ADMINISTRATIVE_PENALTY", "PRIOR_NOTICE", None)]
    assert kinds("关于收到中国证监会行政处罚决定书的公告") == [("ADMINISTRATIVE_PENALTY", "DECIDED", None)]
    assert kinds("关于公司及相关人员收到浙江证监局警示函的公告") == [("SUPERVISORY_MEASURE", "DECIDED", None)]
    assert kinds("关于受到上海证券交易所纪律处分的公告") == [("EXCHANGE_DISCIPLINARY", "DECIDED", None)]
    assert kinds("关于对深圳证券交易所关注函回复的公告") == [("REGULATORY_ENQUIRY", "RESPONDED", None)]
    assert kinds("关于重大诉讼进展暨收到一审判决的公告") == [("LITIGATION", "JUDGMENT_OR_AWARD", None)]
    assert kinds("关于前期会计差错更正及追溯调整的公告") == [("ACCOUNTING_RESTATEMENT", "DISCLOSED", None)]
    assert kinds("关于公司股票被实施退市风险警示暨停牌的公告") == [
        ("DELISTING_RISK", "IMPOSED", "DELISTING_RISK_WARNING"), ("TRADING_SUSPENSION", "ACTIVE", "LISTING_STATUS")]
    assert kinds("关于撤销其他风险警示的公告") == [("DELISTING_RISK", "LIFTED", "OTHER_RISK_WARNING")]
    assert kinds("关于股票复牌的公告") == [("TRADING_SUSPENSION", "LIFTED", None)]
    assert kinds("2025年年度报告") == [] and kinds("关于召开股东大会的通知") == []
    # legal character: a warning letter is a supervisory measure, not a penalty
    assert classify_event_title("关于收到警示函的公告")[0]["legal_classification"] == "ADMINISTRATIVE_SUPERVISORY_MEASURE"


def test_numerals_and_provisions():
    assert [cn_to_int(x) for x in ("一百九十七", "十", "二十三", "一千零五", "78")] == [197, 10, 23, 1005, 78]
    p = parse_cited_provisions("违反了《证券法》第七十八条第二款、第七十九条的规定，构成《中华人民共和国证券法》第一百九十七条第二款所述")
    assert [(x["instrument_code"], x["article"], x["paragraph"]) for x in p] == [
        ("SECURITIES_LAW", 78, 2), ("SECURITIES_LAW", 79, None), ("SECURITIES_LAW", 197, 2)]


PENALTY = """示例科技股份有限公司关于收到中国证监会行政处罚决定书的公告
本公司于2026年9月15日收到中国证券监督管理委员会《行政处罚决定书》（〔2026〕88号）。
经查明，公司2022年至2024年年度报告存在虚假记载，虚增营业收入合计12.5亿元，且未按规定披露关联交易。
上述行为违反了《证券法》第七十八条第二款的规定，构成《证券法》第一百九十七条第二款所述的违法行为。中国证监会决定：
一、对示例科技股份有限公司责令改正，给予警告，并处以1,000万元罚款；
二、对张某给予警告，并处以500万元罚款；
三、对李某给予警告，并处以200万元罚款，采取终身证券市场禁入措施。"""


def test_penalty_decision_parsing():
    ev = classify_event_title("关于收到中国证监会行政处罚决定书的公告")[0]
    f = parse_event_text(PENALTY, ev, Co())
    assert (f["authority"], f["event_date"], f["document_number"]) == ("CSRC", "2026-09-15", "〔2026〕88号")
    assert {"FALSE_RECORDS", "FINANCIAL_FRAUD", "LATE_OR_NON_DISCLOSURE"} <= set(f["violation_categories"])
    parties = {s["party"]: s for s in f["sanctions"]}
    assert parties["示例科技股份有限公司"]["fine"] == 10_000_000
    assert parties["李某"]["market_ban_years"] == "LIFE"
    assert f["fine_amount_total"] == 17_000_000 and f["fine_amount_company"] == 10_000_000


def test_litigation_and_audit():
    lit = ("关于公司涉及重大诉讼的公告\n本公司于2026年8月1日收到北京市第一中级人民法院送达的《民事起诉状》，"
           "案号为（2026）京01民初1234号。\n原告：某某银行股份有限公司 被告：示例科技股份有限公司\n"
           "诉讼请求金额合计人民币3.2亿元。该诉讼系投资者以中国证监会认定的虚假陈述为由提起。")
    f = parse_event_text(lit, classify_event_title("关于公司涉及重大诉讼的公告")[0], Co())
    assert (f["authority"], f["authority_name"]) == ("COURT", "北京市第一中级人民法院")
    assert f["case_number"] == "(2026)京01民初1234号" and f["amount_in_dispute"] == 320_000_000
    assert f["company_role"] == "DEFENDANT" and f["status"] == "FILED"
    assert _opinion_from("出具了标准无保留意见的审计报告") == "STANDARD_UNQUALIFIED"
    assert _opinion_from("出具了带强调事项段的无保留意见") == "UNQUALIFIED_WITH_EMPHASIS"
    assert _opinion_from("一、保留意见 我们审计了") == "QUALIFIED"
    assert _opinion_from("无法表示意见") == "DISCLAIMER"
    aud = parse_event_text("2025年度审计报告\n天健会计师事务所（特殊普通合伙）\n一、保留意见",
                           classify_event_title("2025年度审计报告")[0], Co())
    assert aud["event_subtype"] == "QUALIFIED" and aud["authority_name"] == "天健会计师事务所(特殊普通合伙)"


def test_authority_names_not_truncated():
    assert detect_authority("公司收到和田地区中级人民法院")[1] == "和田地区中级人民法院"
    assert detect_authority("公司收到中国证券监督管理委员会浙江监管局") == ("CSRC_LOCAL_BUREAU", "浙江监管局")


def test_end_to_end_status(company, tmp_path):
    from ashare.regulatory import extract_regulatory_events, regulatory_status, show_events
    pdf = make_pdf(tmp_path / "p.pdf", PENALTY.replace("示例科技股份有限公司", "贵州茅台酒股份有限公司").split("\n"))
    add_disclosure(company, "关于收到中国证券监督管理委员会立案告知书的公告", "2025-03-01", None, ann_id="R1")
    add_disclosure(company, "关于收到中国证监会行政处罚决定书的公告", "2026-09-16", pdf, ann_id="R2")
    add_disclosure(company, "关于公司股票被实施其他风险警示的公告", "2026-09-20", None, ann_id="R3")
    add_disclosure(company, "关于收到上海证券交易所问询函的公告", "2026-04-01", None, ann_id="R4")
    add_disclosure(company, "关于公司涉及诉讼的公告", "2026-05-01", None, ann_id="R5")
    r1 = extract_regulatory_events("600519")
    r2 = extract_regulatory_events("600519")
    assert r1["inserted"] == 5 and r2["updated"] == 5 and r2["inserted"] == 0
    events = {e.event_type: e for e in show_events("600519")}
    pen = events["ADMINISTRATIVE_PENALTY"]
    assert pen.extraction_method == "DOCUMENT_TEXT_REGEX" and pen.fine_amount_company == 10_000_000
    assert pen.event_date == "2026-09-15" and json.loads(pen.cited_provisions)[0]["article"] == 78
    # point in time: before the decision the investigation is possibly open
    early = regulatory_status("600519", as_of="2026-06-30")
    assert early["investigations"][0]["state"] == "POSSIBLY_OPEN"
    assert early["listing_status"] == "NO_RISK_WARNING_RECORDED"
    late = regulatory_status("600519")
    assert late["investigations"][0]["state"] == "FOLLOWED_BY_DECISION_OR_CLOSURE"
    assert late["listing_status"] == "OTHER_RISK_WARNING (ST)"
    assert late["disclosure_violation_events"] and late["litigation_open"]


def test_regulator_document_import(company, tmp_path):
    from ashare.regulatory import import_regulatory_document
    doc = tmp_path / "decision.txt"
    doc.write_text("中国证券监督管理委员会行政处罚决定书（贵州茅台酒股份有限公司、张某）〔2026〕88号\n"
                   "当事人：贵州茅台酒股份有限公司，证券代码600519。\n"
                   "依据《证券法》第一百九十七条第二款的规定，我会决定：\n"
                   "一、对贵州茅台酒股份有限公司责令改正，给予警告，并处以1,000万元罚款；", encoding="utf-8")
    r = import_regulatory_document(str(doc))
    assert r["company"] == "600519" and r["company_resolution"] == "CODE_IN_TEXT"
    [e] = r["events"]
    assert e["type"] == "ADMINISTRATIVE_PENALTY" and e["authority"] == "CSRC" and e["fine_total"] == 10_000_000
    assert import_regulatory_document(str(doc))["events"][0]["result"] == "updated"


def test_export(company, tmp_path):
    from ashare.export import export_table
    [(path, n)] = export_table("companies", str(tmp_path / "out"))
    assert n == 1 and open(path, encoding="utf-8-sig").readline().startswith("id,")
    assert len(export_table("all", str(tmp_path / "out2"), "600519")) >= 5


def test_document_number_trimming():
    from ashare.regulatory import _trim_docnum
    assert _trim_docnum("监督管理委员会行政处罚决定书〔2026〕88号") == "〔2026〕88号"
    assert _trim_docnum("沪证监决〔2026〕12号") == "沪证监决〔2026〕12号"
    assert _trim_docnum("公司收到的文号为深证上〔2026〕301号") == "深证上〔2026〕301号"


def test_regulator_document_signature_date(company, tmp_path):
    from ashare.regulatory import import_regulatory_document, show_events
    doc = tmp_path / "d.txt"
    doc.write_text("中国证券监督管理委员会行政处罚决定书〔2026〕90号\n当事人：贵州茅台酒股份有限公司\n"
                   "一、对贵州茅台酒股份有限公司给予警告；\n中国证监会\n2026年9月10日", encoding="utf-8")
    import_regulatory_document(str(doc))
    [e] = show_events("600519")
    assert e.event_date == "2026-09-10" and e.document_number == "〔2026〕90号"
