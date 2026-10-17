"""v1.0 event linking.

Links separate observations of one matter so that its life-cycle can be
followed: investigation -> prior notice -> penalty decision; filing ->
judgment -> appeal; enquiry -> response; suspension -> resumption;
risk warning -> lifting; distribution proposal -> approval -> implementation.

Every link records its basis (``link_basis``). Links founded on an explicit
identifier (a court case number) are distinguished from links founded on
chronology within one company and authority family, which are heuristics
and are labelled as such. Links are regenerated on every run.
"""
from __future__ import annotations

import hashlib

from .models import SessionLocal, Company, RegulatoryEvent, CorporateAction, init_db

CSRC_FAMILY = {"CSRC", "CSRC_LOCAL_BUREAU", None}


def _key(*parts) -> str:
    return hashlib.sha256("|".join(str(p) for p in parts).encode()).hexdigest()[:24]


def _date(e):
    return e.event_date or e.announcement_date or ""


def link_regulatory_events(session, company: Company) -> int:
    events = sorted(session.query(RegulatoryEvent).filter(RegulatoryEvent.company_id == company.id).all(),
                    key=lambda e: (_date(e), e.id))
    for e in events:
        e.case_key, e.link_basis = None, None
    linked = 0

    def assign(group, basis, *key_parts):
        nonlocal linked
        k = _key(company.id, *key_parts)
        for e in group:
            e.case_key, e.link_basis = k, basis
        linked += len(group) if len(group) > 1 else 0

    # 1. Litigation / arbitration: explicit case number first, then same
    #    tribunal and amount in dispute.
    for etype in ("LITIGATION", "ARBITRATION"):
        rows = [e for e in events if e.event_type == etype]
        by_case = {}
        for e in rows:
            if e.case_number:
                by_case.setdefault(e.case_number.replace(" ", ""), []).append(e)
        for case, grp in by_case.items():
            assign(grp, "CASE_NUMBER", etype, case)
        rest = [e for e in rows if e.case_key is None]
        by_amt = {}
        for e in rest:
            if e.amount_in_dispute and e.authority_name:
                by_amt.setdefault((e.authority_name, round(e.amount_in_dispute)), []).append(e)
        for (tribunal, amt), grp in by_amt.items():
            if len(grp) > 1:
                assign(grp, "SAME_TRIBUNAL_AND_AMOUNT (heuristic)", etype, tribunal, amt)

    # 2. CSRC proceedings: an investigation opens a case; later prior notices,
    #    decisions and closures from the CSRC family join it until the next
    #    investigation (heuristic).
    proc = [e for e in events if e.authority in CSRC_FAMILY and (
        e.event_type == "CSRC_INVESTIGATION" or e.event_type == "ADMINISTRATIVE_PENALTY")]
    current = None
    for e in proc:
        if e.event_type == "CSRC_INVESTIGATION" and e.status == "INITIATED":
            current = [e]
            assign(current, "INVESTIGATION_OPENS_CASE", "CSRC", e.id)
            current_key = e.case_key
            continue
        if current is not None:
            current.append(e)
            e.case_key, e.link_basis = current_key, "CHRONOLOGICAL_SAME_AUTHORITY_FAMILY (heuristic)"
            linked += 1
            if e.event_type == "CSRC_INVESTIGATION" and e.status == "CONCLUDED":
                current = None
        elif e.event_type == "ADMINISTRATIVE_PENALTY":
            # A decision without a recorded investigation: pair it with its
            # own prior notice if one precedes it.
            notices = [n for n in proc if n.event_type == "ADMINISTRATIVE_PENALTY" and n.status == "PRIOR_NOTICE"
                       and _date(n) <= _date(e) and n.case_key is None and n is not e]
            if e.status == "DECIDED" and notices:
                assign([notices[-1], e], "PRIOR_NOTICE_THEN_DECISION (heuristic)", "PEN", notices[-1].id)

    # 3. Paired states: enquiry -> response, suspension -> resumption,
    #    risk warning -> lifting.
    def pair(open_pred, close_pred, basis, tag):
        opened = []
        for e in events:
            if open_pred(e) and e.case_key is None:
                opened.append(e)
            elif close_pred(e) and e.case_key is None:
                match = next((o for o in reversed(opened) if o.authority == e.authority or e.authority is None
                              or o.authority is None), None)
                if match:
                    opened.remove(match)
                    assign([match, e], basis, tag, match.id)

    pair(lambda e: e.event_type == "REGULATORY_ENQUIRY" and e.status == "RECEIVED",
         lambda e: e.event_type == "REGULATORY_ENQUIRY" and e.status == "RESPONDED",
         "RESPONSE_TO_EARLIER_ENQUIRY (heuristic)", "ENQ")
    pair(lambda e: e.event_type == "TRADING_SUSPENSION" and e.status == "ACTIVE",
         lambda e: e.event_type == "TRADING_SUSPENSION" and e.status == "LIFTED",
         "RESUMPTION_AFTER_SUSPENSION", "SUSP")
    for sub in ("DELISTING_RISK_WARNING", "OTHER_RISK_WARNING"):
        pair(lambda e, s=sub: e.event_type == "DELISTING_RISK" and e.event_subtype == s and e.status == "IMPOSED",
             lambda e, s=sub: e.event_type == "DELISTING_RISK" and e.event_subtype == s and e.status == "LIFTED",
             "LIFTING_OF_RISK_WARNING", "RW" + sub)
    # Report events that share a case with at least one other event; a
    # single event that merely opened a case is not "linked".
    from collections import Counter
    sizes = Counter(e.case_key for e in events if e.case_key)
    for e in events:
        if e.case_key and sizes[e.case_key] == 1:
            e.case_key, e.link_basis = None, None
    return sum(n for n in sizes.values() if n > 1)


_DISTRIBUTION = {"CASH_DIVIDEND", "BONUS_SHARES", "CAPITALISATION_ISSUE"}
_LIFECYCLE = {"PRIVATE_PLACEMENT", "PUBLIC_OFFERING", "RIGHTS_ISSUE", "SHARE_BUYBACK", "SHARE_ISSUANCE"}
_TERMINAL = {"COMPLETED", "TERMINATED"}


def link_corporate_actions(session, company: Company) -> int:
    actions = sorted(session.query(CorporateAction).filter(CorporateAction.company_id == company.id).all(),
                     key=lambda a: (a.announcement_date or a.ex_date or "", a.id))
    for a in actions:
        a.action_group = None
    linked = 0
    # Distributions: one scheme per fiscal period and action type.
    groups = {}
    for a in actions:
        if a.action_type in _DISTRIBUTION and a.fiscal_period:
            groups.setdefault((a.action_type, a.fiscal_period), []).append(a)
    for (t, fp), grp in groups.items():
        k = _key(company.id, "DIST", t, fp)
        for a in grp:
            a.action_group = k
        linked += len(grp) if len(grp) > 1 else 0
    # Issues and buybacks: a programme runs from its first announcement to
    # completion or termination (heuristic).
    for t in _LIFECYCLE:
        current = None
        for a in (x for x in actions if x.action_type == t):
            if current is None:
                current = _key(company.id, "PROG", t, a.id)
            a.action_group = current
            if a.status in _TERMINAL:
                current = None
    linked += sum(1 for a in actions if a.action_type in _LIFECYCLE and a.action_group)
    return linked


def link_all(security_code: str | None = None) -> dict:
    init_db()
    session = SessionLocal()
    try:
        q = session.query(Company)
        if security_code:
            q = q.filter(Company.security_code == str(security_code).zfill(6))
        reg = act = 0
        companies = q.all()
        for c in companies:
            reg += link_regulatory_events(session, c)
            act += link_corporate_actions(session, c)
        session.commit()
        return {"companies": len(companies), "regulatory_events_linked": reg, "corporate_actions_grouped": act}
    finally:
        session.close()
