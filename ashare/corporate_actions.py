"""v0.8 corporate actions and distributions.

Pipeline:

    disclosures (CNINFO, already catalogued)
        -> title classification (action types + lifecycle status)
        -> document text (downloaded PDF) or, failing that, the title
        -> regex extraction of standard PRC disclosure phrasing
        -> idempotent CorporateAction observations with provenance

Every observation retains the matched text excerpt (``raw_value``), the
normalised fields as JSON (``normalised_value``), the page on which the
defining phrase was found, the extraction method and a confidence score.
Nothing is inferred silently: where a quantity is not disclosed it is left
null and the reconciliation layer reports the gap.
"""
from __future__ import annotations

from .evaluation import calibrated_confidence
from .timeutil import utcnow

import csv
import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from .models import SessionLocal, Company, Disclosure, CorporateAction, init_db

# ---------------------------------------------------------------------------
# Vocabulary
# ---------------------------------------------------------------------------

ACTION_TYPES = (
    "CASH_DIVIDEND", "BONUS_SHARES", "CAPITALISATION_ISSUE", "RIGHTS_ISSUE",
    "PRIVATE_PLACEMENT", "PUBLIC_OFFERING", "SHARE_ISSUANCE", "SHARE_BUYBACK",
    "SHARE_CANCELLATION", "STOCK_SPLIT", "SHARE_CONSOLIDATION",
    "CONVERTIBLE_CONVERSION", "WARRANT_CONVERSION", "RESTRICTED_SHARE_UNLOCK",
    "OTHER_CAPITAL_CHANGE",
)

#: Ratio actions scale issued capital multiplicatively.
RATIO_TYPES = {"BONUS_SHARES", "CAPITALISATION_ISSUE", "STOCK_SPLIT", "SHARE_CONSOLIDATION"}
#: Additive actions change issued capital by an absolute number of shares.
ISSUE_TYPES = {"RIGHTS_ISSUE", "PRIVATE_PLACEMENT", "PUBLIC_OFFERING", "SHARE_ISSUANCE",
               "CONVERTIBLE_CONVERSION", "WARRANT_CONVERSION", "OTHER_CAPITAL_CHANGE"}
REDUCTION_TYPES = {"SHARE_CANCELLATION"}
#: Actions that do not alter issued share capital.
NON_CAPITAL_TYPES = {"CASH_DIVIDEND", "SHARE_BUYBACK", "RESTRICTED_SHARE_UNLOCK"}

STATUSES = ("PROPOSED", "APPROVED", "IMPLEMENTATION_ANNOUNCED", "IN_PROGRESS",
            "COMPLETED", "TERMINATED", "ANNOUNCED")

# Titles that mention capital terms but are not themselves corporate actions.
_EXCLUDE_TITLE = ("问询函", "关注函", "回复", "法律意见书", "核查意见", "独立意见",
                  "保荐", "会议通知", "股东大会决议", "股东会决议",
                  "摘要")
# Periodic reports mention distributions but are handled by financials.py.
_REPORT_TITLE = re.compile(r"(年度报告|半年度报告|季度报告)(?!.*(权益分派|利润分配))")


def classify_action_status(title: str | None) -> str:
    t = title or ""
    if any(k in t for k in ("终止", "取消", "撤回", "不予", "未获通过")):
        return "TERMINATED"
    if any(k in t for k in ("实施结果", "完成", "结果暨股份变动", "上市公告书",
                            "登记完成", "注销完成", "发行情况报告书", "转股结果",
                            "股份变动公告")):
        return "COMPLETED"
    if ("实施公告" in t or "实施的公告" in t or "派发" in t or "发放" in t
            or "上市流通" in t):
        return "IMPLEMENTATION_ANNOUNCED"
    if "进展" in t:
        return "IN_PROGRESS"
    if any(k in t for k in ("审议通过", "获得批复", "注册批复", "核准", "同意注册")):
        return "APPROVED"
    if any(k in t for k in ("预案", "提议", "草案", "方案", "计划")):
        return "PROPOSED"
    return "ANNOUNCED"


def classify_action_title(title: str | None) -> list[str]:
    """Return candidate action types suggested by an announcement title.

    The list is a *candidate* set: a 权益分派实施公告 may carry a cash
    dividend, bonus shares and a capitalisation issue at once, and the text
    parser decides which are actually present.
    """
    t = title or ""
    if not t or any(k in t for k in _EXCLUDE_TITLE) or _REPORT_TITLE.search(t):
        return []
    # Policies and nil distributions are not corporate actions.
    if any(k in t for k in ("回报规划", "分红规划", "不进行利润分配", "不派发现金红利", "不分配", "不送红股")):
        return []
    types: list[str] = []

    def add(x):
        if x not in types:
            types.append(x)

    if any(k in t for k in ("权益分派", "利润分配", "分红派息", "现金红利", "分红")):
        add("CASH_DIVIDEND")
        add("BONUS_SHARES")
        add("CAPITALISATION_ISSUE")
    if "送股" in t or "送红股" in t:
        add("BONUS_SHARES")
    if "转增" in t:
        add("CAPITALISATION_ISSUE")
    if "配股" in t:
        add("RIGHTS_ISSUE")
    if any(k in t for k in ("非公开发行", "向特定对象发行", "定向增发")):
        add("PRIVATE_PLACEMENT")
    elif any(k in t for k in ("公开发行", "向不特定对象发行", "公开增发")) and "可转换" not in t and "可转债" not in t:
        add("PUBLIC_OFFERING")
    if ("发行股份购买资产" in t or "发行股份及支付现金" in t) and "PRIVATE_PLACEMENT" not in types:
        add("SHARE_ISSUANCE")
    if ("限制性股票" in t or "股票期权" in t) and any(k in t for k in ("授予", "登记完成", "行权")):
        add("SHARE_ISSUANCE")
    if "回购" in t and "注销" in t:
        add("SHARE_CANCELLATION")
        if "回购股份" in t and "实施结果" in t:
            add("SHARE_BUYBACK")
    elif "回购" in t:
        add("SHARE_BUYBACK")
    elif "注销" in t and "股" in t:
        add("SHARE_CANCELLATION")
    if ("可转债" in t or "可转换公司债券" in t) and "转股" in t:
        add("CONVERTIBLE_CONVERSION")
    if "权证" in t and "行权" in t:
        add("WARRANT_CONVERSION")
    if "拆细" in t or "拆股" in t:
        add("STOCK_SPLIT")
    if "缩股" in t or "合并股份" in t:
        add("SHARE_CONSOLIDATION")
    if ("限售" in t or "解禁" in t) and "上市流通" in t:
        add("RESTRICTED_SHARE_UNLOCK")
    if not types and "股份变动" in t:
        add("OTHER_CAPITAL_CHANGE")
    return types


# ---------------------------------------------------------------------------
# Text parsing
# ---------------------------------------------------------------------------

_DATE = r"(\d{4}\s*年\s*\d{1,2}\s*月\s*\d{1,2}\s*日|\d{4}-\d{1,2}-\d{1,2}|\d{4}/\d{1,2}/\d{1,2})"
_NUM = r"([\d][\d,，]*(?:\.\d+)?)"
_SCALE = r"\s*(万|亿)?"


def parse_cn_date(value: str | None) -> str | None:
    if not value:
        return None
    m = re.match(r"(\d{4})\s*[年\-/]\s*(\d{1,2})\s*[月\-/]\s*(\d{1,2})", value.strip())
    if not m:
        return None
    return f"{int(m.group(1)):04d}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"


def _f(raw: str | None, scale: str | None = None) -> float | None:
    if raw is None:
        return None
    try:
        v = float(raw.replace(",", "").replace("，", ""))
    except ValueError:
        return None
    if scale == "万":
        v *= 1e4
    elif scale == "亿":
        v *= 1e8
    return v


def _per10(unit: str) -> float:
    return 10.0 if unit in ("10", "十") else 1.0


def _clean(text: str) -> str:
    # Remove spaces/newlines inside CJK text produced by PDF extraction, but
    # keep a single space between numeric tokens.
    text = text.replace("　", " ").replace("（", "(").replace("）", ")").replace("：", ":")
    text = re.sub(r"[ \t\r\n]+", " ", text)
    text = re.sub(r"(?<=[一-鿿()]) (?=[一-鿿()])", "", text)
    return text


DATE_LABELS = {
    "record_date": ("股权登记日", "股份登记日"),
    "ex_date": ("除权除息日", "除权(息)日", "除权日", "除息日"),
    "payment_date": ("现金红利发放日", "红利发放日", "股息发放日", "派息日"),
    "listing_date": ("新增无限售条件流通股份上市日", "新增可流通股份上市日", "新增股份上市日",
                     "上市流通日", "上市日期", "上市日"),
}


def _parse_dates(text: str) -> dict[str, str]:
    """Parse labelled dates, handling both 'label: date' and header tables."""
    out: dict[str, str] = {}
    for fld, labels in DATE_LABELS.items():
        for lab in labels:
            m = re.search(re.escape(lab) + r"\s*(?:为|是|:)?\s*" + _DATE, text)
            if m:
                out[fld] = parse_cn_date(m.group(1))
                break
    if out:
        return out
    # Table mode: header row of labels followed by a row of dates, e.g.
    # 股权登记日 | 除权(息)日 | 新增无限售条件流通股份上市日 | 现金红利发放日
    positions = []
    for fld, labels in DATE_LABELS.items():
        for lab in labels:
            i = text.find(lab)
            if i >= 0:
                positions.append((i, fld, lab))
                break
    if len(positions) >= 2:
        positions.sort()
        tail = text[positions[-1][0] + len(positions[-1][2]):][:300]
        # Tokens are dates or dash placeholders (SSE tables print "－" for
        # an inapplicable column such as 最后交易日 for A shares).
        # findall returns the date group, or "" for a placeholder.
        dates = [parse_cn_date(tok) if tok else None
                 for tok in re.findall(_DATE + r"|(?<![\d])[－—–-](?![\d])", tail)]
        # A-share tables often include 最后交易日 between record date and ex
        # date; count it as a column if present so dates stay aligned.
        header = text[positions[0][0]:positions[-1][0] + len(positions[-1][2])]
        columns = [p[1] for p in positions]
        if "最后交易日" in header:
            idx = header.find("最后交易日")
            ordered = sorted([(header.find(p[2]), p[1]) for p in positions] + [(idx, "_last_trade")])
            columns = [c for _, c in ordered]
        if len(dates) >= len(columns):
            for col, d in zip(columns, dates):
                if not col.startswith("_") and d:
                    out[col] = d
    return out


@dataclass
class ParsedAction:
    action_type: str
    status: str
    fields: dict = field(default_factory=dict)
    excerpt: str | None = None
    page: int | None = None
    confidence: float = 0.6


def _excerpt(text: str, m: re.Match, pad: int = 60) -> str:
    return text[max(0, m.start() - pad): m.end() + pad]


def parse_action_text(text: str, candidate_types: list[str], status: str) -> list[ParsedAction]:
    """Extract corporate-action fields from (cleaned) disclosure text."""
    t = _clean(text)
    found: list[ParsedAction] = []
    dates = _parse_dates(t)

    base = None
    m = re.search(r"以[^。;；]{0,30}?(?:总股本|股本)[^\d。;；]{0,40}?" + _NUM + _SCALE + r"\s*股为基数", t)
    if m:
        base = _f(m.group(1), m.group(2))

    old_new = re.search(r"总股本(?:将)?由\s*" + _NUM + _SCALE + r"\s*股(?:变更|增加|减少|增至|减至)(?:为|至)?\s*" + _NUM + _SCALE + r"\s*股", t)
    old_total = _f(old_new.group(1), old_new.group(2)) if old_new else None
    new_total = _f(old_new.group(3), old_new.group(4)) if old_new else None

    def common(extra: dict) -> dict:
        d = dict(dates)
        if base is not None:
            d["base_share_count"] = base
        d.update(extra)
        return d

    # --- cash dividend ----------------------------------------------------
    if "CASH_DIVIDEND" in candidate_types:
        per_share = None
        m = re.search(r"每\s*(10|十)\s*股\s*派(?:发)?(?:现金)?(?:红利|股利|股息)?(?:人民币)?\s*" + _NUM + r"\s*元", t)
        if m:
            per_share = _f(m.group(2)) / 10.0
        else:
            m = re.search(r"每\s*(?:1\s*)?股\s*派(?:发)?(?:现金)?(?:红利|股利|股息)?(?:人民币)?\s*" + _NUM + r"\s*元", t)
            if m:
                per_share = _f(m.group(1))
        if m and per_share is not None:
            extra = {"cash_amount": per_share, "tax_basis": "PRE_TAX" if "含税" in _excerpt(t, m, 30) else None}
            tot = re.search(r"(?:共计|合计)?派(?:发)?(?:现金)?(?:红利|股利)?(?:总额)?(?:为)?(?:人民币)?\s*" + _NUM + _SCALE + r"\s*元", t[m.end():m.end() + 200])
            if tot:
                extra["total_cash_amount"] = _f(tot.group(1), tot.group(2))
            found.append(ParsedAction("CASH_DIVIDEND", status, common(extra), _excerpt(t, m), confidence=0.7))

    # --- bonus shares (送股) -----------------------------------------------
    if "BONUS_SHARES" in candidate_types:
        m = re.search(r"每\s*(10|十|1)\s*股\s*送(?:红股)?\s*" + _NUM + r"\s*股", t)
        if m:
            ratio = _f(m.group(2)) / _per10(m.group(1))
            extra = {"ratio": ratio}
            if base is not None:
                extra["share_delta"] = round(base * ratio)
            found.append(ParsedAction("BONUS_SHARES", status, common(extra), _excerpt(t, m), confidence=0.7))

    # --- capitalisation issue (资本公积转增) ---------------------------------
    if "CAPITALISATION_ISSUE" in candidate_types:
        m = re.search(r"每\s*(10|十|1)\s*股\s*(?:以资本公积(?:金)?)?转增\s*" + _NUM + r"\s*股", t)
        if m:
            ratio = _f(m.group(2)) / _per10(m.group(1))
            extra = {"ratio": ratio}
            if base is not None:
                extra["share_delta"] = round(base * ratio)
            found.append(ParsedAction("CAPITALISATION_ISSUE", status, common(extra), _excerpt(t, m), confidence=0.7))

    # A combined bonus + capitalisation scheme reports one aggregate change in
    # 总股本; attach it to the first ratio action only, to avoid double counting.
    ratio_actions = [a for a in found if a.action_type in ("BONUS_SHARES", "CAPITALISATION_ISSUE")]
    if ratio_actions and old_total and new_total:
        ratio_actions[0].fields.update(old_share_count=old_total, new_share_count=new_total)

    # --- rights issue ------------------------------------------------------
    if "RIGHTS_ISSUE" in candidate_types:
        m = re.search(r"每\s*(10|十)\s*股\s*配(?:售)?\s*" + _NUM + r"\s*股", t)
        price = re.search(r"配股价格(?:为)?(?:人民币)?\s*" + _NUM + r"\s*元", t)
        qty = re.search(r"(?:实际)?(?:配售|认购|配股)(?:的)?(?:股份|股票)?(?:数量|总数)(?:为|共计)?\s*" + _NUM + _SCALE + r"\s*股", t)
        if m or price or qty:
            extra = {}
            if m:
                extra["ratio"] = _f(m.group(2)) / _per10(m.group(1))
            if price:
                extra["subscription_price"] = _f(price.group(1))
            if qty and status == "COMPLETED":
                extra["share_delta"] = _f(qty.group(1), qty.group(2))
            anchor = m or price or qty
            found.append(ParsedAction("RIGHTS_ISSUE", status, common(extra), _excerpt(t, anchor), confidence=0.6))

    # --- placements / offerings / other issuances ---------------------------
    for typ in ("PRIVATE_PLACEMENT", "PUBLIC_OFFERING", "SHARE_ISSUANCE"):
        if typ not in candidate_types:
            continue
        qty = re.search(r"(?:本次)?(?:发行|新增|授予|登记)(?:的)?(?:A股)?(?:股票|股份|限制性股票)?(?:的)?(?:数量|总数)(?:为|共计)?\s*" + _NUM + _SCALE + r"\s*股", t)
        price = re.search(r"(?:发行|授予)价格(?:为)?(?:人民币)?\s*" + _NUM + r"\s*元", t)
        if qty or price:
            extra = {}
            if price:
                extra["issue_price"] = _f(price.group(1))
            if qty:
                n = _f(qty.group(1), qty.group(2))
                extra["shares_affected"] = n
                # Only a completed issuance has changed issued capital.
                if status == "COMPLETED":
                    extra["share_delta"] = n
            if old_total and new_total and status == "COMPLETED":
                extra.update(old_share_count=old_total, new_share_count=new_total)
            anchor = qty or price
            found.append(ParsedAction(typ, status, common(extra), _excerpt(t, anchor), confidence=0.6))

    # --- buyback (treasury; no change to issued capital) --------------------
    if "SHARE_BUYBACK" in candidate_types:
        qty = re.search(r"(?:累计)?(?:已)?(?:通过[^,，。]{0,30}?)?回购(?:公司)?(?:A股)?股份(?:数量)?(?:为|共计)?\s*" + _NUM + _SCALE + r"\s*股", t)
        amt = re.search(r"(?:支付的)?(?:资金)?总(?:金)?额(?:为)?(?:人民币)?\s*" + _NUM + _SCALE + r"\s*元", t)
        if qty or amt:
            extra = {"share_delta": 0.0}
            if qty:
                extra["shares_affected"] = _f(qty.group(1), qty.group(2))
            if amt:
                extra["total_cash_amount"] = _f(amt.group(1), amt.group(2))
            found.append(ParsedAction("SHARE_BUYBACK", status, common(extra), _excerpt(t, qty or amt), confidence=0.6))

    # --- cancellation --------------------------------------------------------
    if "SHARE_CANCELLATION" in candidate_types:
        qty = (re.search(r"注销(?:的)?(?:已回购)?(?:公司)?(?:股份|股票)(?:数量)?(?:为|共计)?\s*" + _NUM + _SCALE + r"\s*股", t)
               or re.search(r"(?:本次)?(?:拟)?注销\s*" + _NUM + _SCALE + r"\s*股", t))
        if qty or (old_total and new_total):
            extra = {}
            if qty:
                n = _f(qty.group(1), qty.group(2))
                extra["shares_affected"] = n
                if status == "COMPLETED":
                    extra["share_delta"] = -n
            if old_total and new_total:
                extra.update(old_share_count=old_total, new_share_count=new_total)
                if status == "COMPLETED" and "share_delta" not in extra:
                    extra["share_delta"] = new_total - old_total
            anchor = qty or old_new
            found.append(ParsedAction("SHARE_CANCELLATION", status, common(extra), _excerpt(t, anchor), confidence=0.6))

    # --- convertible bond conversions ----------------------------------------
    if "CONVERTIBLE_CONVERSION" in candidate_types:
        period = re.search(r"(?:期间|本季度|本期|报告期内)[^。]{0,80}?(?:转股数量|转换(?:成)?(?:公司)?股(?:份|票)?(?:数量)?|因转股形成的股份数量)(?:为|共计)?\s*" + _NUM + _SCALE + r"\s*股", t)
        cumulative = re.search(r"累计[^。]{0,60}?(?:转股数量|转换(?:成)?(?:公司)?股(?:份|票)?(?:数量)?|因转股形成的股份数量)(?:为|共计)?\s*" + _NUM + _SCALE + r"\s*股", t)
        if period or cumulative:
            extra = {}
            if cumulative:
                extra["cumulative_converted_shares"] = _f(cumulative.group(1), cumulative.group(2))
            if period:
                extra["shares_affected"] = _f(period.group(1), period.group(2))
                extra["share_delta"] = extra["shares_affected"]
            if old_total and new_total:
                extra.update(old_share_count=old_total, new_share_count=new_total)
            # Conversions accrue over a period; capital changes by its end,
            # not on the (later) announcement date.
            end = (re.search(r"至\s*" + _DATE + r"\s*(?:期间|止)", t)
                   or re.search(r"截至\s*" + _DATE, t))
            if end:
                extra["effective_date"] = parse_cn_date(end.group(1))
            found.append(ParsedAction("CONVERTIBLE_CONVERSION", "COMPLETED", common(extra),
                                      _excerpt(t, period or cumulative), confidence=0.6))

    # --- restricted share unlock ---------------------------------------------
    if "RESTRICTED_SHARE_UNLOCK" in candidate_types:
        qty = re.search(r"(?:本次)?(?:解除限售|上市流通)(?:的)?(?:限售)?(?:股份|股票)?(?:数量|总数)(?:为|共计)?\s*" + _NUM + _SCALE + r"\s*股", t)
        if qty:
            extra = {"shares_affected": _f(qty.group(1), qty.group(2)), "share_delta": 0.0}
            found.append(ParsedAction("RESTRICTED_SHARE_UNLOCK", status, common(extra), _excerpt(t, qty), confidence=0.6))

    # --- splits / consolidations ---------------------------------------------
    for typ, rx in (("STOCK_SPLIT", r"每\s*1\s*股\s*拆(?:细|分)?(?:为|成)\s*" + _NUM + r"\s*股"),
                    ("SHARE_CONSOLIDATION", r"每\s*" + _NUM + r"\s*股\s*(?:合并|缩)(?:为|成)\s*1\s*股")):
        if typ in candidate_types:
            m = re.search(rx, t)
            if m:
                n = _f(m.group(1))
                ratio = n if typ == "STOCK_SPLIT" else (1.0 / n if n else None)
                found.append(ParsedAction(typ, status, common({"ratio": ratio}), _excerpt(t, m), confidence=0.6))

    # Generic total-share change with no more specific match.
    if not found and old_total and new_total and candidate_types:
        typ = candidate_types[0] if candidate_types[0] not in NON_CAPITAL_TYPES else "OTHER_CAPITAL_CHANGE"
        found.append(ParsedAction(typ, status, common({
            "old_share_count": old_total, "new_share_count": new_total,
            "share_delta": new_total - old_total if status == "COMPLETED" else None,
        }), _excerpt(t, old_new), confidence=0.5))
    return found


# ---------------------------------------------------------------------------
# Effective date for capital purposes
# ---------------------------------------------------------------------------

def capital_effective_date(a) -> str | None:
    """Date on which an action alters issued capital, by action type."""
    get = (lambda k: getattr(a, k, None)) if not isinstance(a, dict) else a.get
    if get("effective_date"):
        return get("effective_date")
    if get("action_type") in RATIO_TYPES:
        return get("listing_date") or get("ex_date") or get("record_date")
    return get("listing_date") or get("ex_date") or get("announcement_date")


# ---------------------------------------------------------------------------
# Document text
# ---------------------------------------------------------------------------

def _document_pages(path: Path) -> list[str]:
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        from .financials import _pdf_text_pages
        return _pdf_text_pages(path)
    if suffix in (".html", ".htm", ".txt", ".xml"):
        from bs4 import BeautifulSoup
        return [BeautifulSoup(path.read_bytes(), "lxml").get_text("\n")]
    return []


def _page_of(pages: list[str], excerpt: str | None) -> int | None:
    if not excerpt:
        return None
    probe = re.sub(r"\s+", "", excerpt)[20:40] or re.sub(r"\s+", "", excerpt)[:20]
    for i, page in enumerate(pages, start=1):
        if probe and probe in re.sub(r"\s+", "", _clean(page)):
            return i
    return None


def _fiscal_period(title: str) -> str | None:
    m = re.search(r"(20\d{2})\s*年(?:度)?", title or "")
    if not m:
        return None
    if "半年" in title or "中期" in title:
        return f"{m.group(1)}-06-30"
    if "三季度" in title:
        return f"{m.group(1)}-09-30"
    if "一季度" in title:
        return f"{m.group(1)}-03-31"
    return f"{m.group(1)}-12-31"


def action_id_for(company_id: int, action_type: str, announcement_id: str | None, source: str, extra: str = "") -> str:
    key = f"{company_id}|{action_type}|{announcement_id or ''}|{source}|{extra}"
    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:40]


def extract_from_disclosure(disclosure: Disclosure, use_documents: bool = True) -> list[dict]:
    """Produce corporate-action observation dicts from one disclosure."""
    title = disclosure.title_cn or ""
    types = classify_action_title(title)
    if not types:
        return []
    status = classify_action_status(title)
    pages: list[str] = []
    method = "TITLE_ONLY"
    if use_documents and disclosure.local_path and Path(disclosure.local_path).exists():
        try:
            pages = _document_pages(Path(disclosure.local_path))
        except Exception:
            pages = []
    if pages and any(p.strip() for p in pages):
        method = "DOCUMENT_TEXT_REGEX"
        parsed = parse_action_text(title + "\n" + "\n".join(pages), types, status)
    else:
        parsed = parse_action_text(title, types, status)
        if parsed:
            method = "TITLE_REGEX"

    out = []
    if not parsed:
        # Keep a title-level observation so that the event is visible and the
        # gap (no quantities) is explicit; only for the primary candidate.
        primary = types[0]
        out.append({
            "action_type": primary, "status": status, "fields": {},
            "raw_value": title, "page": None, "method": "TITLE_ONLY", "confidence": 0.3,
        })
    for p in parsed:
        conf = calibrated_confidence("corporate_actions", p.confidence) if method == "DOCUMENT_TEXT_REGEX" else min(p.confidence, 0.5)
        out.append({
            "action_type": p.action_type, "status": p.status, "fields": p.fields,
            "raw_value": p.excerpt, "page": _page_of(pages, p.excerpt) if pages else None,
            "method": method, "confidence": conf,
        })
    for o in out:
        o["fiscal_period"] = _fiscal_period(title) if o["action_type"] in (
            "CASH_DIVIDEND", "BONUS_SHARES", "CAPITALISATION_ISSUE") else None
    return out


_MODEL_FIELDS = {
    "record_date", "ex_date", "payment_date", "listing_date", "effective_date",
    "base_share_count", "old_share_count", "new_share_count", "share_delta",
    "shares_affected", "ratio", "cash_amount", "total_cash_amount",
    "subscription_price", "issue_price", "tax_basis",
}


def _persist(session, company: Company, disclosure: Disclosure | None, obs: dict, source: str) -> str:
    ann_id = disclosure.announcement_id if disclosure else obs.get("announcement_id")
    aid = obs.get("action_id") or action_id_for(company.id, obs["action_type"], ann_id, source)
    row = session.query(CorporateAction).filter_by(company_id=company.id, action_id=aid).one_or_none()
    created = row is None
    if created:
        row = CorporateAction(company_id=company.id, action_id=aid, action_type=obs["action_type"],
                              extraction_method=obs["method"], source=source)
        session.add(row)
    fields = obs.get("fields") or {}
    row.disclosure_id = disclosure.id if disclosure else None
    row.action_type = obs["action_type"]
    row.status = obs.get("status")
    row.announcement_id = ann_id
    row.announcement_date = disclosure.announcement_date if disclosure else obs.get("announcement_date")
    row.fiscal_period = obs.get("fiscal_period")
    for k in _MODEL_FIELDS:
        setattr(row, k, fields.get(k))
    row.currency = fields.get("currency", "CNY")
    row.source_document = (disclosure.document_url or disclosure.local_path) if disclosure else obs.get("source_document")
    row.source_page = obs.get("page")
    row.raw_value = obs.get("raw_value")
    row.normalised_value = json.dumps(
        {k: v for k, v in fields.items()}, ensure_ascii=False, sort_keys=True)
    row.extraction_method = obs["method"]
    row.confidence = obs.get("confidence")
    row.source = source
    row.validation_status = "UNVALIDATED"
    row.retrieved_at = utcnow()
    return "inserted" if created else "updated"


def extract_corporate_actions(security_code: str | None = None, use_documents: bool = True) -> dict:
    """Scan catalogued disclosures and store corporate-action observations."""
    init_db()
    session = SessionLocal()
    totals = {"disclosures_scanned": 0, "action_disclosures": 0, "inserted": 0,
              "updated": 0, "title_only": 0, "errors": []}
    try:
        q = session.query(Disclosure, Company).join(Company, Disclosure.company_id == Company.id)
        if security_code:
            q = q.filter(Company.security_code == str(security_code).zfill(6))
        for disclosure, company in q.order_by(Disclosure.announcement_date).all():
            totals["disclosures_scanned"] += 1
            try:
                observations = extract_from_disclosure(disclosure, use_documents=use_documents)
            except Exception as exc:
                totals["errors"].append({"disclosure_id": disclosure.id, "error": repr(exc)})
                continue
            if not observations:
                continue
            totals["action_disclosures"] += 1
            for obs in observations:
                if obs["method"] == "TITLE_ONLY":
                    totals["title_only"] += 1
                totals[_persist(session, company, disclosure, obs, disclosure.source or "CNINFO")] += 1
            session.commit()
        return totals
    finally:
        session.close()


def _num(v):
    if v in (None, ""):
        return None
    s = str(v).strip().replace(",", "").replace("，", "")
    mult = 1.0
    if s.endswith("万"):
        s, mult = s[:-1], 1e4
    elif s.endswith("亿"):
        s, mult = s[:-1], 1e8
    try:
        return float(s) * mult
    except ValueError:
        return None


def import_corporate_actions_csv(path: str, source: str = "CSV_IMPORT") -> dict:
    """Import authorised structured corporate-action data.

    Required columns: security_code, action_type. Recommended: action_id
    (vendor key), announcement_date, ex_date/effective_date, share_delta or
    ratio, cash_amount, status.
    """
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
                code = str(r.get("security_code") or r.get("code") or "").strip().zfill(6)
                company = session.query(Company).filter_by(security_code=code).first()
                if not company:
                    raise ValueError("company not found")
                typ = (r.get("action_type") or "").strip().upper()
                if typ not in ACTION_TYPES:
                    raise ValueError(f"unknown action_type {typ!r}")
                fields = {}
                for k in ("record_date", "ex_date", "payment_date", "listing_date", "effective_date"):
                    if r.get(k):
                        fields[k] = normalise_date(r[k])
                for k in ("base_share_count", "old_share_count", "new_share_count", "share_delta",
                          "shares_affected", "ratio", "cash_amount", "total_cash_amount",
                          "subscription_price", "issue_price"):
                    if r.get(k) not in (None, ""):
                        fields[k] = _num(r[k])
                if r.get("tax_basis"):
                    fields["tax_basis"] = r["tax_basis"]
                if r.get("currency"):
                    fields["currency"] = r["currency"]
                extra = r.get("action_id") or "|".join(str(fields.get(k, "")) for k in ("ex_date", "effective_date", "share_delta", "ratio", "cash_amount"))
                obs = {
                    "action_type": typ,
                    "status": (r.get("status") or "ANNOUNCED").strip().upper(),
                    "fields": fields,
                    "announcement_id": r.get("announcement_id"),
                    "announcement_date": normalise_date(r.get("announcement_date")),
                    "source_document": r.get("source_document"),
                    "page": int(r["source_page"]) if r.get("source_page") else None,
                    "raw_value": r.get("raw_value"),
                    "method": r.get("extraction_method") or "CSV_IMPORT",
                    "confidence": float(r["confidence"]) if r.get("confidence") else None,
                    "fiscal_period": normalise_date(r.get("fiscal_period")),
                    "action_id": action_id_for(company.id, typ, r.get("announcement_id"), source, extra),
                }
                if _persist(session, company, None, obs, source) == "inserted":
                    inserted += 1
                else:
                    updated += 1
            except Exception as exc:
                errors.append({"row": i, "error": str(exc)})
        session.commit()
        return {"inserted": inserted, "updated": updated, "errors": errors}
    finally:
        session.close()


def show_actions(security_code: str, action_type: str | None = None):
    init_db()
    session = SessionLocal()
    try:
        company = session.query(Company).filter_by(security_code=str(security_code).zfill(6)).first()
        if not company:
            return []
        q = session.query(CorporateAction).filter(CorporateAction.company_id == company.id)
        if action_type:
            q = q.filter(CorporateAction.action_type == action_type.upper())
        rows = q.all()
        return sorted(rows, key=lambda r: (capital_effective_date(r) or r.announcement_date or "", r.action_type))
    finally:
        session.close()
