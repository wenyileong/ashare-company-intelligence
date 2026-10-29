"""Point-in-time security master (v1.6, build plan section 18.6).

Listing events (IPO, delisting, name, code and board changes) come from three
places, each kept with its source:

* announcement titles and texts (上市公告书, 终止上市/摘牌, 变更证券简称 …);
* changes noticed between two downloads of CNINFO's official list (dated
  when detected, so labelled DETECTED rather than EFFECTIVE);
* imported historical lists (authorised datasets), which take precedence.

``rebuild_security_history`` turns the events, the risk-warning events of
the regulatory layer and the current company record into dated identity
periods, and ``universe_at`` answers "which companies were listed on date D,
and under what name", including companies delisted since, so that studies
avoid survivorship bias.

Index membership, the trading calendar, suspension days and the
sustainability-reporting mandate check also live here.
"""
from __future__ import annotations

import csv
import re
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

from .timeutil import utcnow
from .models import (SessionLocal, init_db, Company, Disclosure, ListingEvent, SecurityHistory, IndexConstituent,
                     TradingDay, MarketBar, RegulatoryEvent)
from .corporate_actions import parse_cn_date, _DATE, _clean, _document_pages
from .ownership import normalise_date

EVENT_TYPES = ("IPO", "DELISTING", "NAME_CHANGE", "LEGAL_NAME_CHANGE", "CODE_CHANGE", "BOARD_TRANSFER",
               "MISSING_FROM_LIST")
_Q = r"[“\"「『]?\s*([^”\"」』，,。；;（(）)\s]{2,20})\s*[”\"」』]?"


# --- events from announcements -------------------------------------------------

def classify_listing_title(title: str | None) -> list[str]:
    t = re.sub(r"\s+", "", title or "")
    out = []
    if "上市公告书" in t and ("首次公开发行" in t or "首发" in t) and "转板" not in t:
        out.append("IPO")
    if "转板" in t and "上市" in t and "风险" not in t:
        out.append("BOARD_TRANSFER")
    if ("终止上市" in t or "摘牌" in t) and not any(k in t for k in ("可能", "风险提示", "风险警示", "撤销", "听证",
                                                                    "退市整理期")):
        out.append("DELISTING")
    if re.search(r"变更(?:公司)?(?:证券)?简称|证券简称变更|简称变更", t) or ("变更" in t and "证券简称" in t):
        out.append("NAME_CHANGE")
    if re.search(r"变更公司(?:中文)?(?:名称|全称)|公司名称变更", t):
        out.append("LEGAL_NAME_CHANGE")
    if re.search(r"证券代码变更|变更证券代码", t):
        out.append("CODE_CHANGE")
    return out


def parse_listing_text(text: str, types: list[str]) -> list[dict]:
    t = _clean(text or "")
    # names are matched on text that keeps line breaks: _clean() joins CJK
    # lines, which would run one field into the next
    tn = re.sub(r"[ \t\u3000]+", " ", text or "")
    out = []

    def date_after(patterns):
        for p in patterns:
            m = re.search(p, t)
            if m:
                return parse_cn_date(m.group(1))
        return None
    for typ in types:
        rec = {"event_type": typ, "event_date": None, "old_value": None, "new_value": None, "date_basis": None}
        if typ == "IPO":
            rec["event_date"] = date_after([r"上市日期[:：为]?\s*" + _DATE, r"将?于\s*" + _DATE + r"\s*在[^。]{0,30}上市"])
        elif typ == "BOARD_TRANSFER":
            rec["event_date"] = date_after([r"上市日期[:：为]?\s*" + _DATE, r"将?于\s*" + _DATE + r"[^。]{0,30}上市"])
            m = re.search(r"(?:转板)?(?:至|到)\s*(深圳证券交易所创业板|上海证券交易所科创板|创业板|科创板)", t)
            if m:
                rec["new_value"] = "CHINEXT" if "创业板" in m.group(1) else "STAR"
        elif typ == "DELISTING":
            rec["event_date"] = date_after([r"摘牌日期[:：为]?\s*" + _DATE, r"终止上市日期[:：为]?\s*" + _DATE,
                                            r"(?:将)?(?:于|在)\s*" + _DATE + r"[^。]{0,20}(?:予以)?摘牌",
                                            r"(?:自|于)\s*" + _DATE + r"[^。]{0,20}终止上市"])
        elif typ in ("NAME_CHANGE", "LEGAL_NAME_CHANGE"):
            what = "证券简称" if typ == "NAME_CHANGE" else "(?:公司)?(?:中文)?(?:名称|全称)"
            m = re.search(what + r"由\s*" + _Q + r"\s*变更为\s*" + _Q, tn)
            if m:
                rec["old_value"], rec["new_value"] = m.group(1), m.group(2)
            else:
                m = re.search(r"变更后的?" + what + r"[:：为]?\s*" + _Q, tn)
                if m:
                    rec["new_value"] = m.group(1)
                m = re.search(r"变更前的?" + what + r"[:：为]?\s*" + _Q, tn)
                if m:
                    rec["old_value"] = m.group(1)
            rec["event_date"] = date_after([r"(?:自|从)\s*" + _DATE + r"\s*(?:起)?[^。]{0,30}(?:变更|启用|使用)",
                                            r"(?:变更|启用)日期[:：为]?\s*" + _DATE])
        elif typ == "CODE_CHANGE":
            m = re.search(r"证券代码由\s*[“\"]?(\d{6})[”\"]?\s*变更为\s*[“\"]?(\d{6})", t)
            if m:
                rec["old_value"], rec["new_value"] = m.group(1), m.group(2)
            rec["event_date"] = date_after([r"(?:自|从)\s*" + _DATE + r"\s*(?:起)?"])
        rec["date_basis"] = "EFFECTIVE" if rec["event_date"] else None
        out.append(rec)
    return out


def _upsert_event(session, company_id, rec, source, disclosure_id=None, raw=None, method=None, confidence=None):
    q = session.query(ListingEvent).filter_by(company_id=company_id, event_type=rec["event_type"],
                                              event_date=rec.get("event_date"), new_value=rec.get("new_value"),
                                              source=source)
    row = q.one_or_none()
    created = row is None
    if created:
        row = ListingEvent(company_id=company_id, event_type=rec["event_type"], event_date=rec.get("event_date"),
                           new_value=rec.get("new_value"), source=source)
        session.add(row)
    row.old_value = rec.get("old_value")
    row.date_basis = rec.get("date_basis")
    row.disclosure_id, row.raw_value = disclosure_id, raw
    row.extraction_method, row.confidence, row.retrieved_at = method, confidence, utcnow()
    return created


def extract_listing_events(security_code: str | None = None, use_documents: bool = True) -> dict:
    """Read listing events from catalogued announcements (titles, then text)."""
    init_db()
    s = SessionLocal()
    totals = {"announcements": 0, "events": 0, "inserted": 0, "by_type": defaultdict(int)}
    try:
        q = s.query(Disclosure, Company).join(Company, Disclosure.company_id == Company.id)
        if security_code:
            q = q.filter(Company.security_code == str(security_code).zfill(6))
        for d, c in q.all():
            types = classify_listing_title(d.title_cn)
            if not types:
                continue
            totals["announcements"] += 1
            text, method, conf = d.title_cn or "", "TITLE_ONLY", 0.4
            if use_documents and d.local_path and Path(d.local_path).exists():
                try:
                    pages = _document_pages(Path(d.local_path))
                    if any(p.strip() for p in pages):
                        text, method, conf = (d.title_cn or "") + "\n" + "\n".join(pages), "DOCUMENT_TEXT_REGEX", 0.7
                except Exception:
                    pass
            for rec in parse_listing_text(text, types):
                if rec["event_date"] is None:
                    rec["event_date"], rec["date_basis"] = d.announcement_date, "ANNOUNCED"
                c_conf = conf if rec["date_basis"] == "EFFECTIVE" else min(conf, 0.5)
                if _upsert_event(s, c.id, rec, d.source or "CNINFO", d.id, (d.title_cn or "")[:300], method, c_conf):
                    totals["inserted"] += 1
                totals["events"] += 1
                totals["by_type"][rec["event_type"]] += 1
        s.commit()
        totals["by_type"] = dict(totals["by_type"])
        return totals
    finally:
        s.close()


def record_snapshot_change(session, company: Company, item: dict, board: str | None, source: str) -> None:
    """Called while the official list is stored: record a changed short name,
    full name or board as an event dated when it was detected."""
    today = date.today().isoformat()
    checks = (("NAME_CHANGE", company.short_name_cn, item.get("short_name_cn")),
              ("LEGAL_NAME_CHANGE", company.legal_name_cn, item.get("legal_name_cn")),
              ("BOARD_TRANSFER", company.board, board))
    for typ, old, new in checks:
        if old and new and old != new:
            _upsert_event(session, company.id, {"event_type": typ, "event_date": today, "old_value": old,
                                                "new_value": new, "date_basis": "DETECTED"},
                          f"{source}_SNAPSHOT", None, f"{old} -> {new}", "LIST_COMPARISON", 0.6)


def mark_missing_from_list(seen_ids: set[int], source: str = "CNINFO") -> int:
    """Companies on the previous list but not on this one: recorded, not delisted.

    Absence can be a data glitch, so it is an event for review; a delisting
    needs an announcement or an imported record.
    """
    s = SessionLocal()
    n = 0
    try:
        for c in s.query(Company).filter(Company.source_last_seen == source).all():
            if c.id in seen_ids or c.status == "DELISTED":
                continue
            _upsert_event(s, c.id, {"event_type": "MISSING_FROM_LIST", "event_date": date.today().isoformat(),
                                    "date_basis": "DETECTED"}, f"{source}_SNAPSHOT", None, None, "LIST_COMPARISON", 0.3)
            n += 1
        s.commit()
        return n
    finally:
        s.close()


# --- imports ------------------------------------------------------------------------

def _company_for(session, code: str, exchange: str | None = None, name: str | None = None,
                 create: bool = True) -> Company | None:
    from .universe import infer_exchange, infer_board
    code = str(code).strip().zfill(6)
    q = session.query(Company).filter_by(security_code=code)
    if exchange:
        q = q.filter_by(exchange=exchange.upper())
    c = q.first()
    if c is None and create:
        ex = (exchange or infer_exchange(code) or "").upper() or None
        if ex is None:
            return None
        c = Company(security_code=code, exchange=ex, board=infer_board(ex, code), short_name_cn=name,
                    source_last_seen="IMPORT")
        session.add(c)
        session.flush()
    return c


def import_listing_events_csv(path: str, source: str = "CSV_IMPORT") -> dict:
    """Columns: security_code, event_type (IPO, DELISTING, NAME_CHANGE,
    LEGAL_NAME_CHANGE, CODE_CHANGE, BOARD_TRANSFER), event_date, old_value,
    new_value, [exchange]. Delisted companies not yet in the database are added."""
    init_db()
    s = SessionLocal()
    inserted, errors = 0, []
    try:
        with Path(path).open("r", encoding="utf-8-sig", newline="") as fh:
            rows = list(csv.DictReader(fh))
        for i, r in enumerate(rows, 1):
            typ = (r.get("event_type") or "").strip().upper()
            if typ not in EVENT_TYPES:
                errors.append({"row": i, "error": f"unknown event_type {typ!r}"})
                continue
            c = _company_for(s, r.get("security_code") or "", r.get("exchange"),
                             r.get("new_value") if typ == "NAME_CHANGE" else None)
            if c is None:
                errors.append({"row": i, "error": "unsupported security code"})
                continue
            rec = {"event_type": typ, "event_date": normalise_date(r.get("event_date")),
                   "old_value": (r.get("old_value") or "").strip() or None,
                   "new_value": (r.get("new_value") or "").strip() or None, "date_basis": "EFFECTIVE"}
            if _upsert_event(s, c.id, rec, source, None, None, "CSV_IMPORT", 0.95):
                inserted += 1
        s.commit()
        return {"rows": len(rows), "inserted": inserted, "errors": errors}
    finally:
        s.close()


def import_security_history_csv(path: str, source: str = "CSV_IMPORT") -> dict:
    """Columns: security_code, valid_from, valid_to, short_name_cn,
    [legal_name_cn, exchange, board, listing_status (LISTED/DELISTED), risk_warning].
    Imported periods replace derived ones for the same company."""
    init_db()
    s = SessionLocal()
    inserted, errors = 0, []
    try:
        with Path(path).open("r", encoding="utf-8-sig", newline="") as fh:
            rows = list(csv.DictReader(fh))
        for i, r in enumerate(rows, 1):
            c = _company_for(s, r.get("security_code") or "", r.get("exchange"), r.get("short_name_cn"))
            if c is None:
                errors.append({"row": i, "error": "unsupported security code"})
                continue
            vf = normalise_date(r.get("valid_from"))
            if not vf:
                errors.append({"row": i, "error": "valid_from is required"})
                continue
            status = (r.get("listing_status") or "LISTED").strip().upper()
            if status not in ("LISTED", "DELISTED"):
                errors.append({"row": i, "error": f"listing_status must be LISTED or DELISTED, not {status}"})
                continue
            s.add(SecurityHistory(company_id=c.id, security_code=c.security_code,
                                  exchange=(r.get("exchange") or c.exchange or "").upper() or None,
                                  board=(r.get("board") or c.board), short_name_cn=r.get("short_name_cn") or None,
                                  legal_name_cn=r.get("legal_name_cn") or None, listing_status=status,
                                  risk_warning=(r.get("risk_warning") or "").strip() or None, valid_from=vf,
                                  valid_to=normalise_date(r.get("valid_to")) or None, source=source,
                                  basis="imported"))
            if status == "DELISTED":
                c.status = "DELISTED"
            inserted += 1
        s.commit()
        return {"rows": len(rows), "inserted": inserted, "errors": errors}
    finally:
        s.close()


# --- history ----------------------------------------------------------------------

def _risk_periods(session, company_id) -> list[tuple[str, str | None]]:
    """(date, warning) changes from the regulatory layer: '*ST', 'ST' or None."""
    out = []
    for e in session.query(RegulatoryEvent).filter(RegulatoryEvent.company_id == company_id,
                                                   RegulatoryEvent.event_type == "DELISTING_RISK"):
        d = e.event_date or e.announcement_date
        if not d:
            continue
        if e.event_subtype == "DELISTING_RISK_WARNING" and e.status in ("IMPOSED", "LIFTED"):
            out.append((d, "*ST" if e.status == "IMPOSED" else None))
        elif e.event_subtype == "OTHER_RISK_WARNING" and e.status in ("IMPOSED", "LIFTED"):
            out.append((d, "ST" if e.status == "IMPOSED" else None))
    return sorted(out)


def rebuild_security_history(security_code: str | None = None, codes: list[str] | None = None) -> dict:
    """Derive identity periods per company from events (imports keep priority).

    v2.0.8: ``codes`` limits the rebuild to those companies (used by "Update the company list" for the companies
    whose listing date or status it changed)."""
    init_db()
    s = SessionLocal()
    totals = {"companies": 0, "periods": 0, "imported_kept": 0}
    try:
        q = s.query(Company)
        if security_code:
            q = q.filter(Company.security_code == str(security_code).zfill(6))
        if codes is not None:
            if not codes:
                return totals
            q = q.filter(Company.security_code.in_([str(x).zfill(6) for x in codes]))
        for c in q.all():
            if s.query(SecurityHistory).filter(SecurityHistory.company_id == c.id,
                                               SecurityHistory.source != "DERIVED").count():
                totals["imported_kept"] += 1
                s.query(SecurityHistory).filter_by(company_id=c.id, source="DERIVED").delete()
                continue
            s.query(SecurityHistory).filter_by(company_id=c.id, source="DERIVED").delete()
            events = s.query(ListingEvent).filter(ListingEvent.company_id == c.id,
                                                  ListingEvent.event_date.isnot(None)).all()

            def best(typ):
                cands = [e for e in events if e.event_type == typ]
                cands.sort(key=lambda e: ({"EFFECTIVE": 0, "ANNOUNCED": 1, "DETECTED": 2}.get(e.date_basis, 3),
                                          -(e.confidence or 0)))
                return cands[0] if cands else None
            ipo, delist = best("IPO"), best("DELISTING")
            start = (ipo.event_date if ipo else None) or normalise_date(c.listing_date)
            end = delist.event_date if delist else None
            # change points: name, legal name, code, board, risk warning
            changes = defaultdict(dict)
            for e in events:
                if e.event_type in ("NAME_CHANGE", "LEGAL_NAME_CHANGE", "CODE_CHANGE", "BOARD_TRANSFER") \
                        and e.new_value:
                    key = {"NAME_CHANGE": "short_name_cn", "LEGAL_NAME_CHANGE": "legal_name_cn",
                           "CODE_CHANGE": "security_code", "BOARD_TRANSFER": "board"}[e.event_type]
                    changes[e.event_date][key] = (e.old_value, e.new_value)
            for d, warning in _risk_periods(s, c.id):
                changes[d]["risk_warning"] = (None, warning)
            # the state before the first change: old values, else today's values
            state = {"short_name_cn": c.short_name_cn, "legal_name_cn": c.legal_name_cn,
                     "security_code": c.security_code, "board": c.board, "risk_warning": None}
            for d in sorted(changes, reverse=True):
                for k, (old, new) in changes[d].items():
                    if k == "risk_warning":
                        continue
                    state[k] = old if old else state[k]
            # walk forward
            points = sorted(d for d in changes if (not start or d > start) and (not end or d < end))
            cur_from = start
            for d in [p for p in sorted(changes) if start and p <= start]:   # changes at or before listing
                for k, (old, new) in changes[d].items():
                    state[k] = new
            basis = ["listing date: " + ("IPO announcement" if ipo else "company record" if start else "unknown")]
            if not end and c.status in ("DELISTED", "NOT_IN_EXCHANGE_LIST"):   # v2.0.2/v2.0.8: date not yet known
                basis.append("DELISTING_DATE_UNKNOWN")
            for d in points + [None]:
                s.add(SecurityHistory(company_id=c.id, security_code=state["security_code"], exchange=c.exchange,
                                      board=state["board"], short_name_cn=state["short_name_cn"],
                                      legal_name_cn=state["legal_name_cn"], listing_status="LISTED",
                                      risk_warning=state["risk_warning"], valid_from=cur_from,
                                      valid_to=d if d else end, source="DERIVED", basis="; ".join(basis)))
                totals["periods"] += 1
                if d is None:
                    break
                for k, (old, new) in changes[d].items():
                    state[k] = new
                cur_from = d
            if end:
                s.add(SecurityHistory(company_id=c.id, security_code=state["security_code"], exchange=c.exchange,
                                      board=state["board"], short_name_cn=state["short_name_cn"],
                                      legal_name_cn=state["legal_name_cn"], listing_status="DELISTED",
                                      risk_warning=None, valid_from=end, valid_to=None, source="DERIVED",
                                      basis=f"delisting ({delist.date_basis or 'date unknown'})"))
                totals["periods"] += 1
                c.status = "DELISTED"
            totals["companies"] += 1
        s.commit()
        return totals
    finally:
        s.close()


def _covers(row: SecurityHistory, d: str) -> bool:
    return (row.valid_from is None or row.valid_from <= d) and (row.valid_to is None or d < row.valid_to)


def universe_at(on: str, boards: list[str] | None = None, report: dict | None = None) -> list[dict]:
    """Companies listed on date ``on`` with their name and board on that date.

    Uses security_history where it exists; companies without history fall
    back to their listing date and status (and are marked so).

    v2.0.2: a company is included only when its listing is known to cover the
    date. Companies whose listing date is unknown, and delisted companies
    whose delisting date is unknown, are left out and counted in ``report``
    (``excluded_no_listing_date``, ``excluded_delisting_date_unknown``), so
    the list neither includes companies that had not yet listed nor silently
    claims completeness.
    """
    init_db()
    s = SessionLocal()
    rep = report if report is not None else {}
    rep.update({"excluded_no_listing_date": 0, "excluded_delisting_date_unknown": 0,
                "excluded_codes": []})       # v2.0.3: which companies, for the report-evidence fallback
    try:
        hist = defaultdict(list)
        for h in s.query(SecurityHistory).all():
            hist[h.company_id].append(h)
        out = []
        for c in s.query(Company).all():
            rows = hist.get(c.id)
            if rows and not any(r.source != "DERIVED" for r in rows) and \
                    not min(rows, key=lambda r: r.valid_from or "").valid_from and normalise_date(c.listing_date):
                # v2.0.8 (finding 92): a derived history built before the listing date was known has no start;
                # the company record, which now has the date, is used instead of excluding the company.
                rows = None
            if rows:
                imported = [r for r in rows if r.source != "DERIVED"]
                rows = imported or rows
                if not imported:
                    first = min(rows, key=lambda r: r.valid_from or "")
                    if not first.valid_from:
                        rep["excluded_no_listing_date"] += 1
                        rep["excluded_codes"].append(c.security_code)
                        continue
                cur = next((r for r in rows if _covers(r, on)), None)
                if cur is None or cur.listing_status != "LISTED":
                    continue
                if not imported and "DELISTING_DATE_UNKNOWN" in (cur.basis or ""):
                    rep["excluded_delisting_date_unknown"] += 1
                    rep["excluded_codes"].append(c.security_code)
                    continue
                rec = {"code": cur.security_code, "current_code": c.security_code, "name": cur.short_name_cn,
                       "board": cur.board, "risk_warning": cur.risk_warning, "basis": cur.source}
            else:
                ld = normalise_date(c.listing_date)
                if not ld:
                    rep["excluded_no_listing_date"] += 1
                    rep["excluded_codes"].append(c.security_code)
                    continue
                if ld > on:
                    continue
                if c.status in ("DELISTED", "NOT_IN_EXCHANGE_LIST"):
                    rep["excluded_delisting_date_unknown"] += 1
                    rep["excluded_codes"].append(c.security_code)
                    continue
                rec = {"code": c.security_code, "current_code": c.security_code, "name": c.short_name_cn,
                       "board": c.board, "risk_warning": None, "basis": "COMPANY_RECORD (no history built)"}
            if boards and rec["board"] not in boards:
                continue
            out.append(rec)
        return sorted(out, key=lambda r: r["code"])
    finally:
        s.close()


def name_at(security_code: str, on: str) -> dict | None:
    init_db()
    s = SessionLocal()
    try:
        c = s.query(Company).filter_by(security_code=str(security_code).zfill(6)).first()
        if not c:
            return None
        rows = s.query(SecurityHistory).filter_by(company_id=c.id).all()
        imported = [r for r in rows if r.source != "DERIVED"]
        r = next((r for r in (imported or rows) if _covers(r, on)), None)
        if r is None:
            return None
        return {"code": r.security_code, "short_name_cn": r.short_name_cn, "legal_name_cn": r.legal_name_cn,
                "board": r.board, "listing_status": r.listing_status, "risk_warning": r.risk_warning,
                "valid_from": r.valid_from, "valid_to": r.valid_to, "source": r.source}
    finally:
        s.close()


def security_history(security_code: str) -> dict:
    init_db()
    s = SessionLocal()
    try:
        c = s.query(Company).filter_by(security_code=str(security_code).zfill(6)).first()
        if not c:
            return {"error": "company not found"}
        hist = [{"from": h.valid_from, "to": h.valid_to, "code": h.security_code, "name": h.short_name_cn,
                 "board": h.board, "status": h.listing_status, "warning": h.risk_warning, "source": h.source}
                for h in s.query(SecurityHistory).filter_by(company_id=c.id).order_by(SecurityHistory.valid_from)]
        events = [{"date": e.event_date, "type": e.event_type, "old": e.old_value, "new": e.new_value,
                   "basis": e.date_basis, "source": e.source, "confidence": e.confidence}
                  for e in s.query(ListingEvent).filter_by(company_id=c.id).order_by(ListingEvent.event_date)]
        return {"code": c.security_code, "history": hist, "events": events}
    finally:
        s.close()


# --- index membership -------------------------------------------------------------

INDEX_NAMES = {"000300": "CSI 300", "000905": "CSI 500", "000852": "CSI 1000", "000010": "SSE 180",
               "000016": "SSE 50", "000688": "STAR 50", "399330": "SZSE 100", "399006": "ChiNext Index",
               "399001": "SZSE Component"}
# Indices whose constituents must publish a sustainability report from fiscal
# 2025 (SSE/SZSE self-regulatory guidelines on sustainability reporting,
# April 2024; first reports due by 30 April 2026). Companies listed overseas
# as well are also covered, which is not visible in this database.
MANDATE_INDICES = {"000010": "SSE 180", "000688": "STAR 50", "399330": "SZSE 100", "399006": "ChiNext Index"}
MANDATE_FIRST_YEAR = 2025


def import_index_csv(path: str, source: str = "CSV_IMPORT") -> dict:
    """Two layouts are accepted:

    * membership periods: index_code, security_code, valid_from, [valid_to, weight, index_name]
    * adjustments: index_code, security_code, effective_date, action (ADD/REMOVE or 调入/调出)

    Adjustments are turned into periods (an ADD opens one, a REMOVE closes it)."""
    init_db()
    s = SessionLocal()
    inserted, errors = 0, []
    try:
        with Path(path).open("r", encoding="utf-8-sig", newline="") as fh:
            rows = list(csv.DictReader(fh))
        if rows and "action" in rows[0]:
            seq = sorted(rows, key=lambda r: (r.get("index_code", ""), str(r.get("security_code", "")).zfill(6),
                                              normalise_date(r.get("effective_date")) or ""))
            open_from: dict[tuple, str] = {}
            periods = []
            for i, r in enumerate(seq, 1):
                key = (r["index_code"].strip(), str(r["security_code"]).strip().zfill(6))
                d = normalise_date(r.get("effective_date"))
                act = (r.get("action") or "").strip().upper()
                act = {"调入": "ADD", "纳入": "ADD", "调出": "REMOVE", "剔除": "REMOVE"}.get(act, act)
                if act == "ADD":
                    open_from.setdefault(key, d)
                elif act == "REMOVE":
                    if key in open_from:
                        periods.append((key, open_from.pop(key), d, r.get("index_name")))
                    else:
                        errors.append({"row": i, "error": f"REMOVE without an earlier ADD for {key}"})
                else:
                    errors.append({"row": i, "error": f"unknown action {act!r}"})
            periods += [(k, v, None, None) for k, v in open_from.items()]
            rows = [{"index_code": k[0], "security_code": k[1], "valid_from": f, "valid_to": t, "index_name": n}
                    for k, f, t, n in periods]
        for i, r in enumerate(rows, 1):
            code = str(r.get("security_code") or "").strip().zfill(6)
            vf = normalise_date(r.get("valid_from"))
            if not (r.get("index_code") and vf):
                errors.append({"row": i, "error": "index_code and valid_from are required"})
                continue
            idx = str(r["index_code"]).strip()
            c = s.query(Company).filter_by(security_code=code).first()
            row = s.query(IndexConstituent).filter_by(index_code=idx, security_code=code, valid_from=vf,
                                                      source=source).one_or_none()
            if row is None:
                row = IndexConstituent(index_code=idx, security_code=code, valid_from=vf, source=source)
                s.add(row)
                inserted += 1
            row.index_name = r.get("index_name") or INDEX_NAMES.get(idx)
            row.valid_to = normalise_date(r.get("valid_to")) or None
            row.company_id = c.id if c else None
            w = r.get("weight")
            row.weight = float(w) if w not in (None, "") else None
        s.commit()
        return {"rows": len(rows), "inserted": inserted, "errors": errors}
    finally:
        s.close()


def index_members(index_code: str, on: str) -> list[dict]:
    init_db()
    s = SessionLocal()
    try:
        rows = [r for r in s.query(IndexConstituent).filter_by(index_code=index_code) if _covers(r, on)]
        return [{"code": r.security_code, "weight": r.weight, "since": r.valid_from, "source": r.source}
                for r in sorted(rows, key=lambda r: r.security_code)]
    finally:
        s.close()


def company_indices(security_code: str, on: str) -> list[dict]:
    init_db()
    s = SessionLocal()
    try:
        rows = [r for r in s.query(IndexConstituent).filter_by(security_code=str(security_code).zfill(6))
                if _covers(r, on)]
        return [{"index_code": r.index_code, "index_name": r.index_name or INDEX_NAMES.get(r.index_code),
                 "since": r.valid_from, "weight": r.weight} for r in rows]
    finally:
        s.close()


def sustainability_mandate(security_code: str, fiscal_year: int) -> dict:
    """Whether index membership made a sustainability report mandatory for the year.

    Membership is tested at the fiscal year end. Returns the basis and the
    publication deadline (30 April of the following year)."""
    if fiscal_year < MANDATE_FIRST_YEAR:
        return {"mandatory": False, "basis": f"rules apply from fiscal {MANDATE_FIRST_YEAR}", "indices": []}
    members = [m for m in company_indices(security_code, f"{fiscal_year}-12-31") if m["index_code"] in MANDATE_INDICES]
    s = SessionLocal()
    try:
        any_index_data = s.query(IndexConstituent).filter(
            IndexConstituent.index_code.in_(list(MANDATE_INDICES))).count() > 0
    finally:
        s.close()
    if not any_index_data:
        return {"mandatory": None, "basis": "no membership data for SSE 180, STAR 50, SZSE 100 or ChiNext Index "
                                             "imported", "indices": []}
    return {"mandatory": bool(members), "indices": [m["index_name"] for m in members],
            "deadline": f"{fiscal_year + 1}-04-30",
            "basis": "constituent at fiscal year end" if members else "not a constituent of a mandate index at "
                                                                     "fiscal year end (overseas listings not checked)"}


# --- trading calendar and suspensions ---------------------------------------------

def build_trading_calendar(min_share: float = 0.5, min_securities: int = 2) -> dict:
    """Derive trading days from stored daily bars: a weekday is open on an
    exchange when at least ``min_share`` of the securities with bars around
    then traded (and at least ``min_securities``). Imported calendars are kept."""
    init_db()
    s = SessionLocal()
    try:
        counts = defaultdict(lambda: defaultdict(set))
        for code_ex, d, cid in (s.query(Company.exchange, MarketBar.trade_date, MarketBar.company_id)
                                .join(Company, MarketBar.company_id == Company.id)):
            counts[code_ex][d].add(cid)
        added = 0
        for ex, days in counts.items():
            universe = len({c for ids in days.values() for c in ids})
            for d, ids in days.items():
                if len(ids) < min(min_securities, universe) or len(ids) < min_share * universe:
                    continue
                row = s.query(TradingDay).filter_by(exchange=ex, trade_date=d).one_or_none()
                if row is None:
                    s.add(TradingDay(exchange=ex, trade_date=d, is_open=1, source="DERIVED_FROM_BARS",
                                     securities_trading=len(ids)))
                    added += 1
                elif row.source == "DERIVED_FROM_BARS":
                    row.securities_trading = len(ids)
        s.commit()
        return {"exchanges": sorted(counts), "days_added": added}
    finally:
        s.close()


def import_calendar_csv(path: str, exchange: str = "SSE", source: str = "CSV_IMPORT") -> dict:
    """Columns: trade_date, [is_open (1/0)]. One row per calendar or trading day."""
    init_db()
    s = SessionLocal()
    n = 0
    try:
        with Path(path).open("r", encoding="utf-8-sig", newline="") as fh:
            for r in csv.DictReader(fh):
                d = normalise_date(r.get("trade_date"))
                if not d:
                    continue
                row = s.query(TradingDay).filter_by(exchange=exchange.upper(), trade_date=d).one_or_none()
                if row is None:
                    row = TradingDay(exchange=exchange.upper(), trade_date=d)
                    s.add(row)
                row.is_open = 0 if str(r.get("is_open", "1")).strip() in ("0", "false", "False", "N") else 1
                row.source = source
                n += 1
        s.commit()
        return {"days": n}
    finally:
        s.close()


def trading_days(start: str, end: str, exchange: str = "SSE") -> list[str]:
    init_db()
    s = SessionLocal()
    try:
        return [r.trade_date for r in s.query(TradingDay).filter(
            TradingDay.exchange == exchange.upper(), TradingDay.is_open == 1, TradingDay.trade_date >= start,
            TradingDay.trade_date <= end).order_by(TradingDay.trade_date)]
    finally:
        s.close()


def suspensions(security_code: str, start: str, end: str) -> dict:
    """Days on which the exchange was open but the security did not trade,
    grouped into spells, with suspension announcements alongside."""
    init_db()
    s = SessionLocal()
    try:
        c = s.query(Company).filter_by(security_code=str(security_code).zfill(6)).first()
        if not c:
            return {"error": "company not found"}
        open_days = trading_days(start, end, c.exchange)
        if not open_days:
            return {"code": c.security_code, "error": "no trading calendar for the period; run build-calendar or "
                                                       "import one"}
        bar_days = {b.trade_date for b in s.query(MarketBar).filter(MarketBar.company_id == c.id,
                                                                     MarketBar.trade_date >= start,
                                                                     MarketBar.trade_date <= end)}
        listed_from = normalise_date(c.listing_date) or start
        missing = [d for d in open_days if d not in bar_days and d >= listed_from]
        spells, cur = [], None
        idx = {d: i for i, d in enumerate(open_days)}
        for d in missing:
            if cur and idx[d] == idx[cur[1]] + 1:
                cur[1] = d
                cur[2] += 1
            else:
                cur = [d, d, 1]
                spells.append(cur)
        events = [{"date": e.event_date or e.announcement_date, "status": e.status, "reason": e.event_subtype,
                   "title": e.title_cn}
                  for e in s.query(RegulatoryEvent).filter(RegulatoryEvent.company_id == c.id,
                                                           RegulatoryEvent.event_type == "TRADING_SUSPENSION")
                  if start <= (e.event_date or e.announcement_date or "") <= end]
        return {"code": c.security_code, "open_days": len(open_days), "days_without_trading": len(missing),
                "spells": [{"from": a, "to": b, "trading_days": n} for a, b, n in spells],
                "suspension_announcements": events,
                "note": "Days without a bar may also be gaps in the price data; check against the announcements."}
    finally:
        s.close()
