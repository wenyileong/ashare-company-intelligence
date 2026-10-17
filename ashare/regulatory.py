"""v0.9 regulatory, legal and listing-status events.

Sources, in order of authority:

1. Regulator documents (CSRC and its local bureaus, SSE, SZSE), imported
   from a local file or a URL the user supplies (``import-regulatory-document``).
   No regulator endpoint is guessed or crawled.
2. Company announcements on CNINFO, already catalogued by the disclosure
   layer. Listed companies must announce the receipt of investigation
   notices, penalty decisions, supervisory measures, disciplinary sanctions,
   material litigation and arbitration, risk warnings and suspensions.
3. Structured data from authorised vendors (``import-regulatory-csv``).

The event model separates the *instrument* (legal classification) from the
*procedural stage* (status). An investigation (立案), a prior notice of
penalty (行政处罚事先告知书) and a penalty decision (行政处罚决定书) are
three events at different stages; v0.9 does not merge them, and the status
summary reports investigations without a later decision as "possibly open"
rather than asserting that they are open.
"""
from __future__ import annotations

import csv
import hashlib
import json
import re
from pathlib import Path

from .evaluation import calibrated_confidence
from .timeutil import utcnow
from .models import SessionLocal, Company, Disclosure, RegulatoryEvent, init_db
from .corporate_actions import _clean, parse_cn_date, _DATE, _document_pages, _page_of

# ---------------------------------------------------------------------------
# Vocabulary
# ---------------------------------------------------------------------------

LEGAL_CLASSIFICATIONS = {
    "ADMINISTRATIVE_INVESTIGATION": "CSRC investigation (立案调查), Securities Law art. 170",
    "ADMINISTRATIVE_PENALTY": "Administrative penalty (行政处罚), Administrative Penalty Law / Securities Law ch. 13",
    "ADMINISTRATIVE_SUPERVISORY_MEASURE": "Administrative supervisory measure (行政监管措施), not a penalty",
    "SELF_REGULATORY_DISCIPLINARY": "Exchange disciplinary sanction (纪律处分)",
    "SELF_REGULATORY_MEASURE": "Exchange self-regulatory measure (自律监管措施)",
    "SELF_REGULATORY_ENQUIRY": "Exchange enquiry / attention letter (问询函/关注函)",
    "CRIMINAL": "Criminal investigation or proceedings",
    "CIVIL_LITIGATION": "Civil litigation",
    "ARBITRATION": "Arbitration",
    "AUDIT_OPINION": "Auditor's opinion",
    "ACCOUNTING_IRREGULARITY": "Correction of prior-period accounting errors / restatement",
    "LISTING_STATUS": "Risk warning, delisting risk or termination of listing",
    "TRADING_STATUS": "Trading suspension or resumption",
}

EVENT_TYPES = (
    "CSRC_INVESTIGATION", "CRIMINAL_INVESTIGATION", "ADMINISTRATIVE_PENALTY",
    "SUPERVISORY_MEASURE", "EXCHANGE_DISCIPLINARY", "EXCHANGE_REGULATORY_MEASURE",
    "REGULATORY_ENQUIRY", "LITIGATION", "ARBITRATION", "AUDIT_OPINION",
    "ACCOUNTING_RESTATEMENT", "DELISTING_RISK", "TRADING_SUSPENSION",
)

VIOLATION_TERMS = {
    "FALSE_RECORDS": ("虚假记载",),
    "MISLEADING_STATEMENTS": ("误导性陈述",),
    "MATERIAL_OMISSION": ("重大遗漏",),
    "LATE_OR_NON_DISCLOSURE": ("未及时披露", "未按规定披露", "未披露"),
    "FINANCIAL_FRAUD": ("财务造假", "虚增营业收入", "虚增收入", "虚增利润", "虚构业务", "虚增资产"),
    "UNDISCLOSED_RELATED_PARTY": ("未披露关联", "关联交易未", "隐瞒关联"),
    "ILLEGAL_GUARANTEE": ("违规担保", "违规对外担保"),
    "FUND_OCCUPATION": ("资金占用", "非经营性占用"),
    "INSIDER_TRADING": ("内幕交易",),
    "MARKET_MANIPULATION": ("操纵证券市场", "操纵市场", "操纵股价"),
    "SHORT_SWING_TRADING": ("短线交易",),
    "ILLEGAL_SHARE_REDUCTION": ("违规减持",),
    "FUND_RAISING_MISUSE": ("募集资金使用", "变更募集资金用途"),
}

#: Violation categories that the build plan treats as "disclosure violations".
DISCLOSURE_VIOLATIONS = {"FALSE_RECORDS", "MISLEADING_STATEMENTS", "MATERIAL_OMISSION",
                         "LATE_OR_NON_DISCLOSURE", "UNDISCLOSED_RELATED_PARTY"}


def _ev(event_type, classification, status, subtype=None):
    return {"event_type": event_type, "legal_classification": classification,
            "status": status, "event_subtype": subtype}


_EXCLUDE = re.compile(r"(年度报告|半年度报告|季度报告)(?!.*(非标准|审计意见|差错))")


def classify_event_title(title: str | None) -> list[dict]:
    """Return the regulatory/legal events signalled by an announcement title."""
    t = title or ""
    if not t or _EXCLUDE.search(t):
        return []
    out: list[dict] = []

    # Investigations
    if any(k in t for k in ("立案告知书", "立案调查", "被立案", "立案通知")):
        if any(k in t for k in ("公安", "刑事", "侦查")):
            out.append(_ev("CRIMINAL_INVESTIGATION", "CRIMINAL", "INITIATED"))
        else:
            status = "CONCLUDED" if any(k in t for k in ("结案", "终止调查", "调查结果")) else "INITIATED"
            out.append(_ev("CSRC_INVESTIGATION", "ADMINISTRATIVE_INVESTIGATION", status))
    elif any(k in t for k in ("结案通知书", "终止调查")):
        out.append(_ev("CSRC_INVESTIGATION", "ADMINISTRATIVE_INVESTIGATION", "CONCLUDED"))
    elif any(k in t for k in ("移送公安", "刑事立案", "被采取刑事强制措施", "提起公诉", "刑事判决")):
        out.append(_ev("CRIMINAL_INVESTIGATION", "CRIMINAL", "INITIATED"))

    # Administrative penalties
    if "事先告知书" in t:
        out.append(_ev("ADMINISTRATIVE_PENALTY", "ADMINISTRATIVE_PENALTY", "PRIOR_NOTICE"))
    elif "行政处罚决定" in t or ("行政处罚" in t and "决定书" in t):
        out.append(_ev("ADMINISTRATIVE_PENALTY", "ADMINISTRATIVE_PENALTY", "DECIDED"))

    # CSRC administrative supervisory measures
    if any(k in t for k in ("警示函", "责令改正", "监管谈话", "行政监管措施", "责令公开说明", "认定为不适当人选")):
        out.append(_ev("SUPERVISORY_MEASURE", "ADMINISTRATIVE_SUPERVISORY_MEASURE", "DECIDED"))

    # Exchange discipline and measures
    if any(k in t for k in ("纪律处分", "公开谴责", "通报批评", "公开认定")):
        out.append(_ev("EXCHANGE_DISCIPLINARY", "SELF_REGULATORY_DISCIPLINARY", "DECIDED"))
    elif any(k in t for k in ("监管函", "监管警示", "口头警示", "自律监管措施")):
        out.append(_ev("EXCHANGE_REGULATORY_MEASURE", "SELF_REGULATORY_MEASURE", "DECIDED"))

    # Enquiries
    if any(k in t for k in ("问询函", "关注函", "监管工作函", "审核问询")):
        status = "RESPONDED" if "回复" in t else "RECEIVED"
        out.append(_ev("REGULATORY_ENQUIRY", "SELF_REGULATORY_ENQUIRY", status))

    # Litigation and arbitration
    if "诉讼" in t or "起诉" in t or "判决" in t and "刑事" not in t:
        out.append(_ev("LITIGATION", "CIVIL_LITIGATION", _litigation_status(t)))
    if "仲裁" in t:
        out.append(_ev("ARBITRATION", "ARBITRATION", _litigation_status(t)))

    # Audit opinions
    opinion = _opinion_from(t)
    if opinion and opinion != "STANDARD_UNQUALIFIED":
        out.append(_ev("AUDIT_OPINION", "AUDIT_OPINION", "ISSUED", opinion))
    elif "非标准审计意见" in t or "非标准无保留" in t:
        out.append(_ev("AUDIT_OPINION", "AUDIT_OPINION", "ISSUED", "NON_STANDARD_UNSPECIFIED"))
    elif re.search(r"审计报告$|审计报告[(（]", t) and "募集资金" not in t and "专项" not in t:
        sub = "INTERNAL_CONTROL" if "内部控制" in t else None
        out.append(_ev("AUDIT_OPINION", "AUDIT_OPINION", "ISSUED", sub))

    # Accounting restatements
    if any(k in t for k in ("会计差错更正", "前期差错", "追溯调整", "追溯重述")):
        out.append(_ev("ACCOUNTING_RESTATEMENT", "ACCOUNTING_IRREGULARITY", "DISCLOSED"))

    # Listing status
    if "终止上市" in t and "可能" not in t:
        out.append(_ev("DELISTING_RISK", "LISTING_STATUS", "DECIDED", "TERMINATION_OF_LISTING"))
    elif "退市风险警示" in t:
        if "可能" in t:
            out.append(_ev("DELISTING_RISK", "LISTING_STATUS", "WARNED", "POSSIBLE_DELISTING_RISK_WARNING"))
        else:
            status = "LIFTED" if "撤销" in t else "IMPOSED"
            out.append(_ev("DELISTING_RISK", "LISTING_STATUS", status, "DELISTING_RISK_WARNING"))
    elif "其他风险警示" in t:
        status = "LIFTED" if "撤销" in t else ("WARNED" if "可能" in t else "IMPOSED")
        out.append(_ev("DELISTING_RISK", "LISTING_STATUS", status, "OTHER_RISK_WARNING"))
    elif "可能被终止上市" in t or "可能终止上市" in t:
        out.append(_ev("DELISTING_RISK", "LISTING_STATUS", "WARNED", "POSSIBLE_TERMINATION"))
    elif "退市整理期" in t:
        out.append(_ev("DELISTING_RISK", "LISTING_STATUS", "DECIDED", "DELISTING_CONSOLIDATION_PERIOD"))

    # Trading status
    if "停牌" in t or "复牌" in t:
        if "停复牌" in t:
            status = "ANNOUNCED"
        elif "复牌" in t:
            status = "LIFTED"
        else:
            status = "ACTIVE"
        reason = None
        if any(k in t for k in ("重大资产重组", "筹划", "重大事项", "控制权变更")):
            reason = "PLANNED_CORPORATE_EVENT"
        elif "异常波动" in t or "核查" in t:
            reason = "ABNORMAL_TRADING"
        elif any(e["legal_classification"] == "LISTING_STATUS" for e in out):
            reason = "LISTING_STATUS"
        out.append(_ev("TRADING_SUSPENSION", "TRADING_STATUS", status, reason))
    return out


def _litigation_status(t: str) -> str:
    if "撤诉" in t or "撤回" in t:
        return "WITHDRAWN"
    if "和解" in t or "调解" in t:
        return "SETTLED"
    if "执行" in t:
        return "ENFORCEMENT"
    if "二审" in t or "终审" in t or "再审" in t:
        return "APPEAL_OR_FINAL"
    if "判决" in t or "裁决" in t or "裁定" in t:
        return "JUDGMENT_OR_AWARD"
    if "进展" in t:
        return "ONGOING"
    if any(k in t for k in ("起诉", "受理", "提起", "收到")):
        return "FILED"
    return "ONGOING"


_OPINIONS = (
    ("DISCLAIMER", ("无法表示意见",)),
    ("ADVERSE", ("否定意见",)),
    ("QUALIFIED", ("保留意见",)),
    ("UNQUALIFIED_WITH_EMPHASIS", ("带强调事项段的无保留意见", "带有强调事项段的无保留意见",
                                   "强调事项段的无保留意见", "带持续经营重大不确定性段落的无保留意见")),
    ("STANDARD_UNQUALIFIED", ("标准无保留意见", "标准的无保留意见")),
)


def _opinion_from(text: str) -> str | None:
    """Most severe opinion type named in ``text`` (保留意见 inside
    无保留意见 is not a qualified opinion)."""
    for code, terms in _OPINIONS:
        for term in terms:
            for m in re.finditer(re.escape(term), text):
                if code == "QUALIFIED" and text[max(0, m.start() - 1):m.start()] == "无":
                    continue
                return code
    if re.search(r"(?<!标准)无保留意见", text):
        return "UNQUALIFIED_UNSPECIFIED"
    return None


# ---------------------------------------------------------------------------
# Authorities
# ---------------------------------------------------------------------------

_AUTHORITY_PATTERNS = (
    ("CSRC_LOCAL_BUREAU", (r"中国证券监督管理委员会([\u4e00-\u9fff]{2,6}监管局)", r"([\u4e00-\u9fff]{2,6}证监局)")),
    ("CSRC", (r"(中国证券监督管理委员会)", r"(中国证监会)", r"(证监会)")),
    ("ENVIRONMENT", (r"([\u4e00-\u9fff]{2,20}?生态环境(?:局|厅|部))", r"([\u4e00-\u9fff]{2,20}?环境保护局)")),
    ("TAX", (r"([\u4e00-\u9fff]{2,20}?税务(?:局|总局))",)),
    ("MARKET_REGULATION", (r"([\u4e00-\u9fff]{2,20}?市场监督管理(?:局|总局))",)),
    ("SAFETY", (r"([\u4e00-\u9fff]{2,20}?应急管理(?:局|厅|部))",)),
    ("SSE", (r"(上海证券交易所)", r"(上交所)")),
    ("SZSE", (r"(深圳证券交易所)", r"(深交所)")),
    ("BSE", (r"(北京证券交易所)",)),
    ("COURT", (r"([\u4e00-\u9fff]{2,20}?人民法院)",)),
    ("ARBITRAL_BODY", (r"([\u4e00-\u9fff]{2,20}?仲裁委员会)", r"([\u4e00-\u9fff]{2,20}?国际仲裁中心)")),
    ("POLICE", (r"([\u4e00-\u9fff]{2,20}?公安(?:局|厅|部))",)),
    ("AUDITOR", (r"([\u4e00-\u9fff]{2,30}?会计师事务所(?:\(特殊普通合伙\))?)",)),
)
_CANONICAL = {"中国证监会": "中国证券监督管理委员会", "证监会": "中国证券监督管理委员会",
              "上交所": "上海证券交易所", "深交所": "深圳证券交易所"}


# Only unambiguous lead-in words: single characters such as 和 or 日 also
# begin place names (和田, 日照) and must not be stripped.
_NAME_LEAD = re.compile(r"^.*(?:收到|接到|送达|获悉|出具|作出|根据|依据|关于|公司向|公司被|已向)")


def _trim_name(name: str) -> str:
    """Drop words that precede an institution's name in running text
    (公司于…日收到北京市第一中级人民法院 -> 北京市第一中级人民法院)."""
    for suffix in ("人民法院", "仲裁委员会", "国际仲裁中心", "会计师事务所", "公安局", "公安厅", "监管局", "证监局",
                   "生态环境局", "生态环境厅", "环境保护局", "税务局", "市场监督管理局", "应急管理局"):
        i = name.find(suffix)
        if i > 0:
            head, tail = name[:i], name[i:]
            trimmed = _NAME_LEAD.sub("", head)
            return (trimmed or head) + tail
    return name


def detect_authority(text: str, prefer: tuple[str, ...] = ()) -> tuple[str | None, str | None]:
    """Return (authority_code, authority_name) of the issuing body.

    ``prefer`` puts the expected kinds of body first: a securities
    misrepresentation suit names the CSRC, but is decided by a court.
    """
    t = (text or "").replace("（", "(").replace("）", ")")
    order = [x for x in _AUTHORITY_PATTERNS if x[0] in prefer] + \
            [x for x in _AUTHORITY_PATTERNS if x[0] not in prefer]
    for code, patterns in order:
        for pat in patterns:
            m = re.search(pat, t)
            if m:
                name = _trim_name(m.group(1))
                return code, _CANONICAL.get(name, name)
    return None, None


# ---------------------------------------------------------------------------
# Text parsing
# ---------------------------------------------------------------------------

_CN_DIGITS = {"零": 0, "〇": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5,
              "六": 6, "七": 7, "八": 8, "九": 9}
_CN_UNITS = {"十": 10, "百": 100, "千": 1000}


def cn_to_int(s: str) -> int | None:
    """Convert a Chinese numeral (一百九十七) or Arabic string to int."""
    s = s.strip()
    if s.isdigit():
        return int(s)
    total, current = 0, 0
    for ch in s:
        if ch in _CN_DIGITS:
            current = _CN_DIGITS[ch]
        elif ch in _CN_UNITS:
            total += (current or 1) * _CN_UNITS[ch]
            current = 0
        else:
            return None
    return total + current


_LAWS = (
    ("SECURITIES_LAW", ("中华人民共和国证券法", "证券法")),
    ("COMPANY_LAW", ("中华人民共和国公司法", "公司法")),
    ("CRIMINAL_LAW", ("中华人民共和国刑法", "刑法")),
    ("ADMIN_PENALTY_LAW", ("中华人民共和国行政处罚法", "行政处罚法")),
    ("INFO_DISCLOSURE_MEASURES", ("上市公司信息披露管理办法", "信息披露管理办法")),
    ("SSE_LISTING_RULES", ("上海证券交易所股票上市规则", "上海证券交易所科创板股票上市规则")),
    ("SZSE_LISTING_RULES", ("深圳证券交易所股票上市规则", "深圳证券交易所创业板股票上市规则")),
)


def parse_cited_provisions(text: str) -> list[dict]:
    """Extract cited statutory provisions, e.g. 《证券法》第一百九十七条第二款."""
    out, seen = [], set()
    for m in re.finditer(r"《([^》]{2,40})》((?:第[一二三四五六七八九十百千零〇\d]+条(?:第[一二三四五六七八九十\d]+款)?(?:第[（(]?[一二三四五六七八九十\d]+[）)]?项)?[、和及,，]?)+)", text):
        title = m.group(1)
        code = next((c for c, names in _LAWS if title in names), None)
        for a in re.finditer(r"第([一二三四五六七八九十百千零〇\d]+)条(?:第([一二三四五六七八九十\d]+)款)?", m.group(2)):
            art = cn_to_int(a.group(1))
            para = cn_to_int(a.group(2)) if a.group(2) else None
            key = (title, art, para)
            if art is None or key in seen:
                continue
            seen.add(key)
            out.append({"instrument": title, "instrument_code": code, "article": art, "paragraph": para})
    return out


def parse_violations(text: str) -> list[str]:
    return [code for code, terms in VIOLATION_TERMS.items() if any(term in text for term in terms)]


_AMOUNT = r"([\d][\d,，]*(?:\.\d+)?)\s*(万|亿)?\s*元"


def _amount(num: str, scale: str | None) -> float:
    v = float(num.replace(",", "").replace("，", ""))
    return v * (1e4 if scale == "万" else 1e8 if scale == "亿" else 1)


def parse_sanctions(text: str) -> list[dict]:
    """Per-party sanctions from a penalty or disciplinary decision.

    Decisions are drafted as a sequence of clauses: 对X责令改正，给予警告，
    并处以500万元罚款；对Y给予警告，并处以200万元罚款；对Z采取10年证券
    市场禁入措施。Each clause is parsed separately so that fines are not
    attributed to the wrong party.
    """
    out = []
    for clause in re.split(r"[；;。]", text):
        m = re.search(r"(?:^|[:：、\s])\s*对\s*([^，,：:；;、]{2,60}?)\s*(?:责令|给予|处以|并处|采取|予以|没收|作出|公开|通报)", clause)
        if not m:
            continue
        party = m.group(1).strip()
        body = clause[m.end(1):]
        measures = []
        for code, terms in (("ORDER_TO_RECTIFY", ("责令改正",)), ("WARNING", ("给予警告", "警告")),
                            ("PUBLIC_CENSURE", ("公开谴责",)), ("CIRCULATED_CRITICISM", ("通报批评",)),
                            ("UNSUITABLE_PERSON", ("不适当人选",)), ("CONFISCATION", ("没收违法所得",))):
            if any(term in body for term in terms):
                measures.append(code)
        fine = None
        fm = re.search(r"(?:罚款|并处|处以)\s*" + _AMOUNT, body) or re.search(_AMOUNT + r"\s*(?:的)?罚款", body)
        if fm:
            fine = _amount(fm.group(1), fm.group(2))
            measures.append("FINE")
        conf = re.search(r"没收(?:违法所得|其违法所得)\s*" + _AMOUNT, body)
        ban = re.search(r"(终身|[\d一二三四五六七八九十]+\s*年)\s*(?:证券)?市场禁入", body)
        if ban:
            measures.append("MARKET_BAN")
        if not measures:
            continue
        out.append({
            "party": party,
            "measures": measures,
            "fine": fine,
            "confiscation": _amount(conf.group(1), conf.group(2)) if conf else None,
            "market_ban_years": (None if not ban else ("LIFE" if ban.group(1) == "终身"
                                                     else cn_to_int(ban.group(1).replace("年", "").strip()))),
        })
    return out


def _company_names(company: Company | None) -> list[str]:
    if company is None:
        return []
    return [n for n in (company.legal_name_cn, company.short_name_cn) if n]


def _trim_docnum(value: str) -> str:
    """Keep the issuing prefix of a document number (沪证监决〔2026〕12号) but
    drop running text before it (…行政处罚决定书〔2026〕88号 -> 〔2026〕88号)."""
    i = re.search(r"[〔\[［(（]", value).start()
    prefix, rest = value[:i], value[i:]
    for sep in ("决定书", "告知书", "函", "书", "文号", "编号", "号为", "为"):
        j = prefix.rfind(sep)
        if j >= 0:
            prefix = prefix[j + len(sep):]
    return prefix[-8:] + rest


def parse_event_text(text: str, event: dict, company: Company | None = None) -> dict:
    """Fill quantitative and procedural fields for one classified event."""
    t = _clean(text)
    f: dict = {}
    prefer = {"LITIGATION": ("COURT",), "ARBITRATION": ("ARBITRAL_BODY",),
              "AUDIT_OPINION": ("AUDITOR",), "CRIMINAL_INVESTIGATION": ("POLICE",)}.get(event["event_type"], ())
    # Detect on text that keeps line breaks: _clean() joins CJK across lines,
    # which would fuse a heading onto the institution's name.
    spaced = re.sub(r"[ \t\u3000]+", " ", text or "")
    authority, authority_name = detect_authority(spaced[:3000], prefer)
    f["authority"], f["authority_name"] = authority, authority_name
    if event["event_type"] in ("TRADING_SUSPENSION", "DELISTING_RISK") and authority is None:
        f["authority"] = "SSE" if company and company.exchange == "SSE" else ("SZSE" if company else None)

    m = re.search(r"于\s*" + _DATE + r"\s*(?:收到|接到|获悉)", t)
    if m:
        f["event_date"] = parse_cn_date(m.group(1))
    m = re.search(r"([一-鿿]{0,14}[〔\[［(（]\s*\d{4}\s*[〕\]］)）]\s*\d+\s*号)", t)
    if m and event["event_type"] not in ("LITIGATION", "ARBITRATION"):
        f["document_number"] = _trim_docnum(m.group(1))
    m = re.search(r"[(（]\s*\d{4}\s*[)）]\s*[一-鿿]{1,8}\d{0,4}[一-鿿]{1,6}\d+\s*号", t)
    if m and event["event_type"] in ("LITIGATION", "ARBITRATION"):
        f["case_number"] = m.group(0)

    if event["legal_classification"] in ("ADMINISTRATIVE_PENALTY", "SELF_REGULATORY_DISCIPLINARY",
                                         "ADMINISTRATIVE_SUPERVISORY_MEASURE", "SELF_REGULATORY_MEASURE",
                                         "ADMINISTRATIVE_INVESTIGATION", "CRIMINAL"):
        f["violation_categories"] = parse_violations(t)
        f["cited_provisions"] = parse_cited_provisions(t)
        sanctions = parse_sanctions(t)
        if sanctions:
            f["sanctions"] = sanctions
            fines = [s["fine"] for s in sanctions if s["fine"]]
            f["fine_amount_total"] = sum(fines) if fines else None
            names = _company_names(company)
            company_fines = [s["fine"] for s in sanctions if s["fine"] and (
                any(n and n in s["party"] for n in names) or s["party"].endswith("公司"))]
            f["fine_amount_company"] = sum(company_fines) if company_fines else None
            conf = [s["confiscation"] for s in sanctions if s["confiscation"]]
            f["confiscation_amount"] = sum(conf) if conf else None

    if event["event_type"] in ("LITIGATION", "ARBITRATION"):
        m = re.search(r"(?:涉案|诉讼|仲裁|标的)(?:金额|标的额|请求金额)(?:合计|共计|约|为)*\s*(?:人民币)?\s*" + _AMOUNT, t)
        if m:
            f["amount_in_dispute"] = _amount(m.group(1), m.group(2))
        role = None
        for code, pats in (("PLAINTIFF", (r"公司(?:作为|为)原告", r"原告[:：]\s*(?:本公司|公司)")),
                           ("DEFENDANT", (r"公司(?:作为|为)被告", r"被告[:：]\s*(?:本公司|公司)")),
                           ("APPLICANT", (r"公司(?:作为|为)(?:仲裁)?申请人", r"申请人[:：]\s*(?:本公司|公司)")),
                           ("RESPONDENT", (r"公司(?:作为|为)(?:仲裁)?被申请人", r"被申请人[:：]\s*(?:本公司|公司)")),
                           ("THIRD_PARTY", (r"公司(?:作为|为)第三人",))):
            if any(re.search(p, t) for p in pats):
                role = code
                break
        names = _company_names(company)
        if role is None and names:
            for code, label in (("RESPONDENT", "被申请人"), ("APPLICANT", "申请人"), ("DEFENDANT", "被告"), ("PLAINTIFF", "原告")):
                m = re.search(label + r"\s*(?:[一二三四五六七八九十\d]+)?\s*[:：]\s*([^，,；;。\s]{2,40})", t)
                if m and any(n in m.group(1) for n in names):
                    role = code
                    break
        f["company_role"] = role
        f["status"] = _litigation_status(t[:400]) if event["status"] == "ONGOING" else event["status"]

    if event["event_type"] == "AUDIT_OPINION":
        op = _opinion_from(t)
        if op:
            f["event_subtype"] = op if event.get("event_subtype") != "INTERNAL_CONTROL" else f"INTERNAL_CONTROL_{op}"

    if event["event_type"] == "TRADING_SUSPENSION":
        m = re.search(r"(?:自|于)\s*" + _DATE + r"\s*(?:\(\S{2,4}\))?\s*(?:开市起)?\s*(?:起)?\s*(?:停牌|复牌)", t)
        if m:
            f["event_date"] = parse_cn_date(m.group(1))
    if event["event_type"] == "DELISTING_RISK":
        m = re.search(r"(?:自|于)\s*" + _DATE + r"\s*(?:起)?\s*(?:被)?(?:实施|撤销)", t)
        if m:
            f["event_date"] = parse_cn_date(m.group(1))
    return f


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------

def event_id_for(company_id, event_type, subtype, announcement_id, source, extra="") -> str:
    key = f"{company_id}|{event_type}|{subtype or ''}|{announcement_id or ''}|{source}|{extra}"
    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:40]


_JSON_FIELDS = ("violation_categories", "cited_provisions", "sanctions")
_SCALAR_FIELDS = ("authority", "authority_name", "event_date", "document_number", "case_number",
                  "company_role", "amount_in_dispute", "fine_amount_total", "fine_amount_company",
                  "confiscation_amount")


def _persist(session, company, obs: dict) -> str:
    row = session.query(RegulatoryEvent).filter_by(event_id=obs["event_id"]).one_or_none()
    created = row is None
    if created:
        row = RegulatoryEvent(event_id=obs["event_id"], event_type=obs["event_type"],
                              legal_classification=obs["legal_classification"],
                              extraction_method=obs["method"], source=obs["source"])
        session.add(row)
    f = obs.get("fields") or {}
    row.company_id = company.id if company else None
    row.affected_security = company.security_code if company else obs.get("affected_security")
    row.disclosure_id = obs.get("disclosure_id")
    row.event_type = obs["event_type"]
    row.event_subtype = f.get("event_subtype") or obs.get("event_subtype")
    row.legal_classification = obs["legal_classification"]
    row.status = f.get("status") or obs.get("status")
    for k in _SCALAR_FIELDS:
        setattr(row, k, f.get(k))
    row.event_date = f.get("event_date") or obs.get("announcement_date")
    for k in _JSON_FIELDS:
        setattr(row, k, json.dumps(f[k], ensure_ascii=False) if f.get(k) else None)
    row.announcement_id = obs.get("announcement_id")
    row.announcement_date = obs.get("announcement_date")
    row.title_cn = obs.get("title")
    row.source_document = obs.get("source_document")
    row.primary_source_url = obs.get("primary_source_url")
    row.document_hash = obs.get("document_hash")
    row.source_page = obs.get("page")
    row.raw_value = obs.get("raw_value")
    row.normalised_value = json.dumps(f, ensure_ascii=False, sort_keys=True)
    row.extraction_method = obs["method"]
    row.confidence = obs.get("confidence")
    row.source = obs["source"]
    row.validation_status = "UNVALIDATED"
    row.retrieved_at = utcnow()
    return "inserted" if created else "updated"


def _excerpt_for(text: str, title: str) -> str:
    t = _clean(text)
    for kw in ("决定", "处罚", "立案", "警示", "处分", "诉讼", "仲裁", "审计意见", "风险警示", "停牌", "复牌", "差错"):
        i = t.find(kw, len(title))
        if i >= 0:
            return t[max(0, i - 80): i + 160]
    return t[:240]


def extract_from_disclosure(disclosure: Disclosure, company: Company | None, use_documents: bool = True) -> list[dict]:
    title = disclosure.title_cn or ""
    events = classify_event_title(title)
    if not events:
        return []
    pages: list[str] = []
    if use_documents and disclosure.local_path and Path(disclosure.local_path).exists():
        try:
            pages = _document_pages(Path(disclosure.local_path))
        except Exception:
            pages = []
    has_text = bool(pages) and any(p.strip() for p in pages)
    text = title + "\n" + "\n".join(pages) if has_text else title
    out = []
    for ev in events:
        fields = parse_event_text(text, ev, company)
        excerpt = _excerpt_for(text, title) if has_text else title
        out.append({
            **ev,
            "fields": fields,
            "event_id": event_id_for(company.id if company else None, ev["event_type"], ev.get("event_subtype"),
                                     disclosure.announcement_id, disclosure.source or "CNINFO"),
            "disclosure_id": disclosure.id,
            "announcement_id": disclosure.announcement_id,
            "announcement_date": disclosure.announcement_date,
            "title": title,
            "source_document": disclosure.local_path or disclosure.document_url,
            "primary_source_url": disclosure.document_url,
            "document_hash": disclosure.sha256,
            "page": _page_of(pages, excerpt) if has_text else None,
            "raw_value": excerpt,
            "method": "DOCUMENT_TEXT_REGEX" if has_text else "TITLE_ONLY",
            "confidence": calibrated_confidence("regulatory", 0.65) if has_text else 0.4,
            "source": disclosure.source or "CNINFO",
        })
    return out


def extract_regulatory_events(security_code: str | None = None, use_documents: bool = True) -> dict:
    """Scan catalogued company announcements for regulatory/legal events."""
    init_db()
    session = SessionLocal()
    totals = {"disclosures_scanned": 0, "event_disclosures": 0, "inserted": 0, "updated": 0,
              "title_only": 0, "errors": []}
    try:
        q = session.query(Disclosure, Company).join(Company, Disclosure.company_id == Company.id)
        if security_code:
            q = q.filter(Company.security_code == str(security_code).zfill(6))
        for disclosure, company in q.order_by(Disclosure.announcement_date).all():
            totals["disclosures_scanned"] += 1
            try:
                observations = extract_from_disclosure(disclosure, company, use_documents)
            except Exception as exc:
                totals["errors"].append({"disclosure_id": disclosure.id, "error": repr(exc)})
                continue
            if not observations:
                continue
            totals["event_disclosures"] += 1
            for obs in observations:
                if obs["method"] == "TITLE_ONLY":
                    totals["title_only"] += 1
                totals[_persist(session, company, obs)] += 1
            session.commit()
        return totals
    finally:
        session.close()


def _resolve_company(session, text: str, security_code: str | None):
    if security_code:
        return session.query(Company).filter_by(security_code=str(security_code).zfill(6)).first(), "GIVEN"
    for code in re.findall(r"(?<!\d)([036]\d{5})(?!\d)", text[:5000]):
        c = session.query(Company).filter_by(security_code=code).first()
        if c:
            return c, "CODE_IN_TEXT"
    head = text[:5000]
    for c in session.query(Company).filter(Company.legal_name_cn.isnot(None)).all():
        if c.legal_name_cn and len(c.legal_name_cn) >= 6 and c.legal_name_cn in head:
            return c, "NAME_IN_TEXT"
    return None, "UNRESOLVED"


def import_regulatory_document(path_or_url: str, security_code: str | None = None,
                               source: str | None = None) -> dict:
    """Import one regulator document (CSRC decision, exchange sanction...).

    ``path_or_url`` is a local PDF/HTML/TXT file or an http(s) URL that the
    user has identified. The document is archived and hashed; the issuing
    authority is detected from the text unless ``source`` is given.
    """
    from .storage import store_raw
    init_db()
    if re.match(r"^https?://", path_or_url):
        from .http import RateLimitedClient
        from .config import USER_AGENT, REQUESTS_PER_SECOND
        client = RateLimitedClient(USER_AGENT, REQUESTS_PER_SECOND)
        try:
            resp = client.get(path_or_url)
            data, ctype, url = resp.content, resp.headers.get("content-type", ""), str(resp.url)
        finally:
            client.close()
        suffix = ".pdf" if "pdf" in ctype.lower() or url.lower().endswith(".pdf") else ".html"
    else:
        p = Path(path_or_url)
        data, url, suffix = p.read_bytes(), None, p.suffix.lower()
        ctype = {"pdf": "application/pdf", "html": "text/html", "htm": "text/html"}.get(suffix.lstrip("."), "text/plain")
    archived = store_raw(source or "REGULATOR_DOCUMENT", url or path_or_url, data,
                         {"content_type": ctype, "origin": path_or_url})
    doc_path = Path(archived["payload_path"])
    typed = doc_path.with_suffix(suffix if suffix in (".pdf", ".html", ".htm", ".txt") else ".txt")
    if not typed.exists():
        typed.write_bytes(data)
    pages = _document_pages(typed)
    text = "\n".join(pages)
    clean = _clean(text)
    # Classify on the document's heading only: the body of a penalty decision
    # also contains 责令改正 etc., which are part of the penalty, not
    # separate supervisory measures.
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    heading = _clean(" ".join(lines[:2]))[:200] if lines else clean[:200]
    events = classify_event_title(heading) or classify_event_title(clean[:300])[:1]
    session = SessionLocal()
    try:
        company, how = _resolve_company(session, clean, security_code)
        result = {"document_hash": archived["sha256"], "company": company.security_code if company else None,
                  "company_resolution": how, "events": []}
        # A decision is dated where it is signed, at the end of the document.
        tail_dates = re.findall(_DATE, _clean(text)[-400:])
        signed = parse_cn_date(tail_dates[-1]) if tail_dates else None
        for ev in events:
            fields = parse_event_text(text, ev, company)
            if not fields.get("event_date") and signed:
                fields["event_date"] = signed
                fields["event_date_basis"] = "SIGNATURE_DATE"
            src = source or fields.get("authority") or "REGULATOR_DOCUMENT"
            obs = {**ev, "fields": fields, "event_id": event_id_for(
                company.id if company else None, ev["event_type"], ev.get("event_subtype"),
                fields.get("document_number") or archived["sha256"], src),
                "announcement_date": None, "title": heading[:200],
                "source_document": str(typed), "primary_source_url": url,
                "document_hash": archived["sha256"], "page": None,
                "raw_value": _excerpt_for(text, ""), "method": "REGULATOR_DOCUMENT_REGEX",
                "confidence": 0.75 if company else 0.5, "source": src,
                "affected_security": security_code}
            result["events"].append({"type": ev["event_type"], "status": fields.get("status") or ev["status"],
                                     "authority": fields.get("authority"), "fine_total": fields.get("fine_amount_total"),
                                     "document_number": fields.get("document_number"),
                                     "result": _persist(session, company, obs)})
        session.commit()
        return result
    finally:
        session.close()


def import_regulatory_csv(path: str, source: str = "CSV_IMPORT") -> dict:
    """Import structured events (security_code, event_type, legal_classification,
    status, authority, event_date, document_number, fine_amount_total, ...)."""
    from .ownership import normalise_date
    init_db()
    session = SessionLocal()
    inserted = updated = 0
    errors = []
    try:
        with Path(path).open("r", encoding="utf-8-sig", newline="") as fh:
            rows = list(csv.DictReader(fh))
        for i, r in enumerate(rows, 1):
            try:
                code = str(r.get("security_code") or "").strip().zfill(6)
                company = session.query(Company).filter_by(security_code=code).first()
                if not company:
                    raise ValueError("company not found")
                et = (r.get("event_type") or "").strip().upper()
                lc = (r.get("legal_classification") or "").strip().upper()
                if et not in EVENT_TYPES:
                    raise ValueError(f"unknown event_type {et!r}")
                if lc not in LEGAL_CLASSIFICATIONS:
                    raise ValueError(f"unknown legal_classification {lc!r}")
                fields = {k: r.get(k) or None for k in ("authority", "authority_name", "document_number",
                                                       "case_number", "company_role", "event_subtype", "status")}
                fields["event_date"] = normalise_date(r.get("event_date"))
                for k in ("amount_in_dispute", "fine_amount_total", "fine_amount_company", "confiscation_amount"):
                    fields[k] = float(r[k].replace(",", "")) if r.get(k) else None
                if r.get("violation_categories"):
                    fields["violation_categories"] = [x.strip() for x in r["violation_categories"].split(";") if x.strip()]
                obs = {"event_type": et, "legal_classification": lc, "status": fields.get("status"),
                       "fields": fields, "method": r.get("extraction_method") or "CSV_IMPORT", "source": source,
                       "event_id": event_id_for(company.id, et, fields.get("event_subtype"),
                                                r.get("event_key") or fields.get("document_number") or fields["event_date"], source),
                       "announcement_date": normalise_date(r.get("announcement_date")),
                       "source_document": r.get("source_document"), "primary_source_url": r.get("primary_source_url"),
                       "confidence": float(r["confidence"]) if r.get("confidence") else None}
                if _persist(session, company, obs) == "inserted":
                    inserted += 1
                else:
                    updated += 1
            except Exception as exc:
                errors.append({"row": i, "error": str(exc)})
        session.commit()
        return {"inserted": inserted, "updated": updated, "errors": errors}
    finally:
        session.close()


def show_events(security_code: str, classification: str | None = None):
    init_db()
    session = SessionLocal()
    try:
        c = session.query(Company).filter_by(security_code=str(security_code).zfill(6)).first()
        if not c:
            return []
        q = session.query(RegulatoryEvent).filter(RegulatoryEvent.company_id == c.id)
        if classification:
            q = q.filter(RegulatoryEvent.legal_classification == classification.upper())
        return q.order_by(RegulatoryEvent.event_date, RegulatoryEvent.id).all()
    finally:
        session.close()


_RESOLVING_PENALTY = {("ADMINISTRATIVE_PENALTY", "DECIDED"), ("CSRC_INVESTIGATION", "CONCLUDED")}


def regulatory_status(security_code: str, as_of: str | None = None) -> dict:
    """Point-in-time regulatory profile of one company.

    Uses only events dated on or before ``as_of`` (default: all). Every
    derived state names the events it rests on.
    """
    events = [e for e in show_events(security_code) if not as_of or (e.event_date or "") <= as_of]
    profile = {"code": str(security_code).zfill(6), "as_of": as_of, "events": len(events),
               "by_classification": {}, "listing_status": "NO_RISK_WARNING_RECORDED",
               "trading_status": "NO_SUSPENSION_RECORDED", "investigations": [],
               "penalties": [], "disclosure_violation_events": [], "non_standard_audit_opinions": [],
               "litigation_open": [], "notes": []}
    for e in events:
        profile["by_classification"][e.legal_classification] = profile["by_classification"].get(e.legal_classification, 0) + 1

    listing = [e for e in events if e.event_type == "DELISTING_RISK" and e.status in ("IMPOSED", "LIFTED", "DECIDED")]
    if listing:
        last = listing[-1]
        if last.status == "LIFTED":
            profile["listing_status"] = "RISK_WARNING_LIFTED"
        elif last.event_subtype == "DELISTING_RISK_WARNING":
            profile["listing_status"] = "DELISTING_RISK_WARNING (*ST)"
        elif last.event_subtype == "OTHER_RISK_WARNING":
            profile["listing_status"] = "OTHER_RISK_WARNING (ST)"
        else:
            profile["listing_status"] = last.event_subtype or "LISTING_STATUS_EVENT"
        profile["listing_status_basis"] = last.id

    susp = [e for e in events if e.event_type == "TRADING_SUSPENSION"]
    susp = [e for e in susp if e.status in ("ACTIVE", "LIFTED")]
    if susp:
        profile["trading_status"] = "SUSPENDED" if susp[-1].status == "ACTIVE" else "TRADING (last suspension lifted)"
        profile["trading_status_basis"] = susp[-1].id

    decided = [e for e in events if (e.event_type, e.status) in _RESOLVING_PENALTY]
    for inv in (e for e in events if e.event_type == "CSRC_INVESTIGATION" and e.status == "INITIATED"):
        if inv.case_key:  # linked case (run link-events): use the case's own events
            later = [d for d in decided if d.case_key == inv.case_key]
            prior_notice = [d.id for d in events if d.case_key == inv.case_key and d.status == "PRIOR_NOTICE"]
        else:
            later = [d for d in decided if (d.event_date or "") >= (inv.event_date or "")]
            prior_notice = []
        state = "FOLLOWED_BY_DECISION_OR_CLOSURE" if later else (
            "PRIOR_NOTICE_ISSUED" if prior_notice else "POSSIBLY_OPEN")
        profile["investigations"].append({
            "event_id": inv.id, "date": inv.event_date, "authority": inv.authority,
            "case_key": inv.case_key, "state": state,
            "basis": [d.id for d in later] or prior_notice,
            "link_basis": inv.link_basis or "UNLINKED: any later CSRC decision or closure"})
    for p in (e for e in events if e.event_type == "ADMINISTRATIVE_PENALTY"):
        profile["penalties"].append({"event_id": p.id, "date": p.event_date, "status": p.status,
                                     "document_number": p.document_number,
                                     "fine_total": p.fine_amount_total, "fine_company": p.fine_amount_company})
    for e in events:
        cats = set(json.loads(e.violation_categories)) if e.violation_categories else set()
        if cats & DISCLOSURE_VIOLATIONS:
            profile["disclosure_violation_events"].append({"event_id": e.id, "date": e.event_date,
                                                           "categories": sorted(cats)})
        if e.event_type == "AUDIT_OPINION" and e.event_subtype and "STANDARD_UNQUALIFIED" not in e.event_subtype \
                and e.event_subtype not in ("INTERNAL_CONTROL",) and not e.event_subtype.endswith("UNSPECIFIED"):
            profile["non_standard_audit_opinions"].append({"event_id": e.id, "date": e.event_date,
                                                           "opinion": e.event_subtype})
    closed = {"WITHDRAWN", "SETTLED", "APPEAL_OR_FINAL", "ENFORCEMENT"}
    # With linked cases, only the latest event of each case decides its state.
    latest_by_case = {}
    for e in events:
        if e.event_type in ("LITIGATION", "ARBITRATION") and e.case_key:
            latest_by_case[e.case_key] = e
    for e in events:
        if e.event_type in ("LITIGATION", "ARBITRATION") and e.case_key and latest_by_case[e.case_key] is not e:
            continue
        if e.event_type in ("LITIGATION", "ARBITRATION") and e.status not in closed:
            profile["litigation_open"].append({"event_id": e.id, "date": e.event_date, "type": e.event_type,
                                               "status": e.status, "amount": e.amount_in_dispute,
                                               "role": e.company_role})
    if profile["litigation_open"]:
        profile["notes"].append("'open' means no closing-stage announcement is recorded for that matter; "
                                "unlinked events (no case_key) are assessed individually")
    return profile
