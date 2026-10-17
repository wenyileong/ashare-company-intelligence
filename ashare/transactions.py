"""Remaining event types (v1.9): major asset restructurings, related-party
transactions, external guarantees and shareholder-meeting resolutions.

Each announcement becomes one or more ``transaction_events`` rows with the
fields the text gives (counterparty, amount, nature, approval body, related
party, overdue guarantees, votes). Restructuring announcements are staged
(planning → plan → draft → shareholder approval → regulator approval →
completed, or terminated) and the stages of one deal share a ``case_key``.
"""
from __future__ import annotations

import hashlib
import re
from collections import defaultdict
from pathlib import Path

from sqlalchemy import Integer, String, Text, DateTime, ForeignKey, UniqueConstraint, Boolean
from sqlalchemy.orm import Mapped, mapped_column

from .timeutil import utcnow
from .models import Base, SessionLocal, init_db, Company, Disclosure
from .corporate_actions import parse_cn_date, _DATE, _clean, _document_pages

_NUM = r"(\d[\d,]*(?:\.\d+)?)"
_SCALE = r"\s*(亿|万)?\s*元"

STAGES = ("PLANNING", "PLAN", "DRAFT", "SHAREHOLDER_APPROVED", "REGULATOR_APPROVED", "COMPLETED", "TERMINATED")


def classify_transaction_title(title: str | None) -> list[tuple[str, str | None]]:
    """[(event_type, stage)] for MAJOR_RESTRUCTURING, RELATED_PARTY, GUARANTEE, SHAREHOLDER_MEETING."""
    t = re.sub(r"\s+", "", title or "")
    out = []
    if re.search(r"重大资产重组|发行股份购买资产|重大资产购买|重大资产出售|重组上市", t) and "风险提示" not in t:
        if re.search(r"终止", t):
            stage = "TERMINATED"
        elif re.search(r"实施完成|实施情况|过户完成|交割|完成", t):
            stage = "COMPLETED"
        elif re.search(r"注册|核准|审核通过|并购重组委|批复", t):
            stage = "REGULATOR_APPROVED"
        elif re.search(r"股东大会", t) and "决议" in t:
            stage = "SHAREHOLDER_APPROVED"
        elif "草案" in t or "报告书" in t:
            stage = "DRAFT"
        elif "预案" in t:
            stage = "PLAN"
        elif re.search(r"停牌|筹划|进展", t):
            stage = "PLANNING"
        else:
            stage = None
        out.append(("MAJOR_RESTRUCTURING", stage))
    if "关联交易" in t and not out:          # a restructuring's related-party nature is a field of it
        out.append(("RELATED_PARTY", "ESTIMATE" if re.search(r"预计", t) else None))
    if "担保" in t and not re.search(r"担保物|质押|股票质押", t):
        out.append(("GUARANTEE", None))
    if re.search(r"股东大会决议公告|股东会决议公告", t):
        out.append(("SHAREHOLDER_MEETING", None))
    return out


def _amount(num, scale):
    v = float(num.replace(",", ""))
    return v * {"亿": 1e8, "万": 1e4}.get(scale or "", 1.0)


def _approval(t: str) -> str | None:
    if re.search(r"(?:尚需|需|提交)(?:提交)?(?:公司)?股东大会审议", t) or re.search(r"股东大会审议通过", t):
        return "SHAREHOLDER_MEETING"
    if re.search(r"董事会(?:审议通过|审议)", t):
        return "BOARD"
    return None


def parse_transaction_text(text: str, event_type: str) -> list[dict]:
    t = _clean(text or "")
    rec: dict = {}
    if event_type == "MAJOR_RESTRUCTURING":
        m = re.search(r"(?:交易对方|交易对象)(?:为|是|[:：])\s*([^，,。；;]{2,60})", t)
        rec["counterparty"] = m.group(1).strip() if m else None
        m = re.search(r"(?:标的资产|标的公司)(?:为|是|[:：])?\s*([^，,。；;]{2,60})", t)
        rec["subject"] = m.group(1).strip() if m else None
        m = re.search(r"(?:交易(?:价格|作价|金额)|交易对价)(?:合计|暂定|确定)?(?:为)?\s*(?:人民币)?\s*" + _NUM + _SCALE, t)
        rec["amount"] = _amount(m.group(1), m.group(2)) if m else None
        rec["related_party"] = True if re.search(r"构成关联交易", t) and not re.search(r"不构成关联交易", t) else \
            (False if "不构成关联交易" in t else None)
        rec["nature"] = "ISSUE_SHARES_FOR_ASSETS" if "发行股份" in t else ("SALE" if "出售" in t else "PURCHASE")
        return [rec]
    if event_type == "RELATED_PARTY":
        m = re.search(r"(?:关联方|关联人|交易对方)(?:名称)?(?:为|[:：])\s*([^，,。；;\s]{2,60})", t) or \
            re.search(r"与(?:公司)?(?:控股股东|关联方)?([^，,。；;\s]{2,40}?(?:公司|集团|银行|财务公司))(?:发生|进行|签署|开展)", t)
        rec["counterparty"] = m.group(1).strip() if m else None
        m = re.search(r"(?:交易金额|金额|总额|预计金额|合计金额)(?:不超过|为|约|合计)?\s*(?:人民币)?\s*" + _NUM + _SCALE, t)
        rec["amount"] = _amount(m.group(1), m.group(2)) if m else None
        for k, nature in (("采购", "PURCHASE"), ("销售", "SALE"), ("租赁", "LEASE"), ("借款", "LOAN"), ("存款", "DEPOSIT"),
                          ("担保", "GUARANTEE"), ("增资", "CAPITAL_INJECTION"), ("股权转让", "EQUITY_TRANSFER")):
            if k in t:
                rec["nature"] = nature
                break
        rec["approval_body"] = _approval(t)
        rec["related_party"] = True
        return [rec]
    if event_type == "GUARANTEE":
        m = re.search(r"为\s*(?:(?:全资|控股|下属)?(?:子公司|孙公司)\s*)?([^，,。；;\s]{2,60}?(?:有限责任公司|股份有限公司|有限公司|"
                      r"集团|企业|合伙企业(?:（有限合伙）)?))\s*(?:的)?(?:[^，。]{0,20})?提供(?:连带责任)?(?:保证)?担保", t) or \
            re.search(r"被担保人(?:名称)?[:：]\s*([^，,。；;\s]{2,60})", t)
        rec["counterparty"] = m.group(1).strip() if m else None
        m = re.search(r"(?:担保金额|担保额度|担保总额|本次担保)(?:不超过|为|合计)?\s*(?:人民币)?\s*" + _NUM + _SCALE, t)
        rec["amount"] = _amount(m.group(1), m.group(2)) if m else None
        rec["related_party"] = True if re.search(r"关联担保|为关联方", t) else None
        m = re.search(r"逾期(?:对外)?担保(?:累计)?(?:数量|金额)?(?:为)?\s*(?:人民币)?\s*" + _NUM + _SCALE, t)
        if m:
            rec["overdue_amount"] = _amount(m.group(1), m.group(2))
            rec["overdue"] = rec["overdue_amount"] > 0
        elif re.search(r"(?:无|不存在|没有)逾期(?:对外)?担保", t):
            rec["overdue"], rec["overdue_amount"] = False, 0.0
        m = re.search(r"对外担保(?:余额|总额)(?:为)?\s*(?:人民币)?\s*" + _NUM + _SCALE, t)
        rec["cumulative_amount"] = _amount(m.group(1), m.group(2)) if m else None
        rec["approval_body"] = _approval(t)
        return [rec]
    if event_type == "SHAREHOLDER_MEETING":
        out = []
        # "1、审议通过《关于…的议案》 … 同意 X 股，占 … Y%；反对 X 股，占 … Y%；弃权 X 股，占 … Y%"
        parts = re.split(r"(?=(?:\d+(?:\.\d+)?[、.．]|议案名称[:：])\s*(?:审议(?:通过)?)?\s*《)", t)
        for part in parts:
            name = re.search(r"《([^》]{2,80})》", part)
            fo = re.search(r"同意\s*" + _NUM + r"\s*股\s*[，,]?\s*占[^%]{0,40}?(\d+(?:\.\d+)?)%", part)
            if not (name and fo):
                continue
            ag = re.search(r"反对\s*" + _NUM + r"\s*股\s*[，,]?\s*占[^%]{0,40}?(\d+(?:\.\d+)?)%", part)
            ab = re.search(r"弃权\s*" + _NUM + r"\s*股\s*[，,]?\s*占[^%]{0,40}?(\d+(?:\.\d+)?)%", part)
            fpct = float(fo.group(2))
            out.append({"proposal": name.group(1), "votes_for_pct": fpct / 100,
                        "votes_against_pct": float(ag.group(2)) / 100 if ag else None,
                        "votes_abstain_pct": float(ab.group(2)) / 100 if ab else None,
                        "resolution_passed": None if re.search(r"特别决议", part) and fpct < 66.67 else fpct > 50})
        m = re.search(r"(?:召开(?:时间|日期)|会议召开时间)[:：]?\s*" + _DATE, t)
        for r in out:
            r["event_date"] = parse_cn_date(m.group(1)) if m else None
        return out
    return [rec]


class TransactionEvent(Base):
    __tablename__ = "transaction_events"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), index=True)
    disclosure_id: Mapped[int | None] = mapped_column(ForeignKey("disclosures.id"), index=True)
    event_type: Mapped[str] = mapped_column(String(30), index=True)
    stage: Mapped[str | None] = mapped_column(String(30))
    case_key: Mapped[str | None] = mapped_column(String(40), index=True)
    announcement_date: Mapped[str | None] = mapped_column(String(20), index=True)
    event_date: Mapped[str | None] = mapped_column(String(20))
    counterparty: Mapped[str | None] = mapped_column(String(300))
    subject: Mapped[str | None] = mapped_column(String(300))
    amount: Mapped[float | None] = mapped_column()
    cumulative_amount: Mapped[float | None] = mapped_column()
    nature: Mapped[str | None] = mapped_column(String(40))
    approval_body: Mapped[str | None] = mapped_column(String(40))
    related_party: Mapped[bool | None] = mapped_column(Boolean)
    overdue: Mapped[bool | None] = mapped_column(Boolean)
    overdue_amount: Mapped[float | None] = mapped_column()
    proposal: Mapped[str | None] = mapped_column(String(300))
    votes_for_pct: Mapped[float | None] = mapped_column()
    votes_against_pct: Mapped[float | None] = mapped_column()
    votes_abstain_pct: Mapped[float | None] = mapped_column()
    resolution_passed: Mapped[bool | None] = mapped_column(Boolean)
    title_cn: Mapped[str | None] = mapped_column(String(500))
    source: Mapped[str] = mapped_column(String(100))
    extraction_method: Mapped[str | None] = mapped_column(String(50))
    confidence: Mapped[float | None] = mapped_column()
    retrieved_at: Mapped[object] = mapped_column(DateTime, default=utcnow)
    __table_args__ = (UniqueConstraint("company_id", "disclosure_id", "event_type", "proposal", "source",
                                       name="uq_transaction_event"),)


def extract_transactions(security_code: str | None = None, use_documents: bool = True) -> dict:
    init_db()
    s = SessionLocal()
    totals = {"announcements": 0, "events": 0, "by_type": defaultdict(int)}
    try:
        q = s.query(Disclosure, Company).join(Company, Disclosure.company_id == Company.id)
        if security_code:
            q = q.filter(Company.security_code == str(security_code).zfill(6))
        for d, c in q.order_by(Disclosure.announcement_date).all():
            kinds = classify_transaction_title(d.title_cn)
            if not kinds:
                continue
            totals["announcements"] += 1
            text, method, conf = d.title_cn or "", "TITLE_ONLY", 0.35
            if use_documents and d.local_path and Path(d.local_path).exists():
                pages = _document_pages(Path(d.local_path))
                if any(p.strip() for p in pages):
                    text, method, conf = (d.title_cn or "") + "\n" + "\n".join(pages), "DOCUMENT_TEXT_REGEX", 0.6
            for typ, stage in kinds:
                recs = parse_transaction_text(text, typ) if method != "TITLE_ONLY" else [{}]
                for r in recs or [{}]:
                    row = s.query(TransactionEvent).filter_by(company_id=c.id, disclosure_id=d.id, event_type=typ,
                                                              proposal=r.get("proposal"),
                                                              source=d.source or "CNINFO").one_or_none()
                    if row is None:
                        row = TransactionEvent(company_id=c.id, disclosure_id=d.id, event_type=typ,
                                               proposal=r.get("proposal"), source=d.source or "CNINFO")
                        s.add(row)
                    row.stage = stage
                    for k in ("event_date", "counterparty", "subject", "amount", "cumulative_amount", "nature",
                              "approval_body", "related_party", "overdue", "overdue_amount", "votes_for_pct",
                              "votes_against_pct", "votes_abstain_pct", "resolution_passed"):
                        setattr(row, k, r.get(k))
                    row.announcement_date, row.title_cn = d.announcement_date, (d.title_cn or "")[:500]
                    row.extraction_method, row.confidence, row.retrieved_at = method, conf, utcnow()
                    totals["events"] += 1
                    totals["by_type"][typ] += 1
        s.flush()
        _link_restructurings(s, security_code)
        s.commit()
        totals["by_type"] = dict(totals["by_type"])
        return totals
    finally:
        s.close()


def _link_restructurings(s, security_code=None):
    """One case per company and deal: a new case starts after a COMPLETED or TERMINATED stage."""
    q = s.query(TransactionEvent).filter(TransactionEvent.event_type == "MAJOR_RESTRUCTURING")
    if security_code:
        cid = s.query(Company.id).filter(Company.security_code == str(security_code).zfill(6)).scalar()
        q = q.filter(TransactionEvent.company_id == cid)
    by_company = defaultdict(list)
    for e in q.all():
        by_company[e.company_id].append(e)
    for cid, evs in by_company.items():
        evs.sort(key=lambda e: (e.announcement_date or "", e.id))
        n, open_case = 0, None
        for e in evs:
            if open_case is None:
                n += 1
                open_case = hashlib.sha256(f"{cid}|MR|{n}|{e.announcement_date}".encode()).hexdigest()[:40]
            e.case_key = open_case
            if e.stage in ("COMPLETED", "TERMINATED"):
                open_case = None


def show_transactions(security_code: str, event_type: str | None = None) -> list[dict]:
    init_db()
    s = SessionLocal()
    try:
        c = s.query(Company).filter_by(security_code=str(security_code).zfill(6)).first()
        if not c:
            return []
        q = s.query(TransactionEvent).filter_by(company_id=c.id)
        if event_type:
            q = q.filter_by(event_type=event_type.upper())
        return [{"date": e.announcement_date, "type": e.event_type, "stage": e.stage, "counterparty": e.counterparty,
                 "amount": e.amount, "nature": e.nature, "related": e.related_party, "approval": e.approval_body,
                 "proposal": e.proposal, "for": e.votes_for_pct, "against": e.votes_against_pct,
                 "passed": e.resolution_passed, "overdue": e.overdue, "case": (e.case_key or "")[:8]}
                for e in q.order_by(TransactionEvent.announcement_date, TransactionEvent.id)]
    finally:
        s.close()
