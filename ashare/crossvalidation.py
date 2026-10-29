"""v1.0 integrated validation (build plan, section 7).

Stage 1  schema            -> validate_database (universe), missing provenance
Stage 2  internal          -> validate_financials, validate_ownership, reconcile_capital
Stage 3  cross-document    -> restatement/discrepancy, interim vs annual
Stage 4  cross-source      -> same observation from different sources
Stage 5  confidence class  -> confidence_class()

Findings are written to ``validation_flags`` and regenerated on every run.
Observations are never altered (principle 4: conflicts before overwrites).
"""
from __future__ import annotations

import json
from collections import defaultdict

from .timeutil import utcnow
from .models import (
    SessionLocal, Company, Disclosure, FinancialFact, MarketBar, OwnershipObservation,
    CapitalStructureObservation, ValidationFlag, RegulatoryEvent, init_db,
)

FLOW_METRICS = {"revenue", "cost_of_revenue", "operating_profit", "profit_before_tax",
                "income_tax", "net_profit", "net_profit_parent", "rd_expense"}


def confidence_class(confidence: float | None, validation_status: str | None = None) -> str:
    """HIGH / MEDIUM / LOW / UNVALIDATED (build plan, stage 5).

    A failed validation caps the class at LOW whatever the extraction
    confidence; HIGH requires either native-XBRL confidence or a passed check.
    """
    vs = (validation_status or "").upper()
    if confidence is None:
        return "UNVALIDATED"
    if vs.startswith("FAILED") or vs in ("IN_UNRECONCILED_WINDOW",):
        return "LOW"
    passed = vs.startswith("VALIDATED") or vs.startswith("RECONCILED")
    if confidence >= 0.95 or (confidence >= 0.85 and passed):
        return "HIGH"
    if confidence >= 0.6 or passed:
        return "MEDIUM"
    return "LOW"


def _close(a: float, b: float, rel: float = 0.005, abs_: float = 1000.0) -> bool:
    return abs(a - b) <= max(abs(a), abs(b)) * rel or abs(a - b) <= abs_


def _flag(session, rule, severity, layer, company_id, table, row_ids, details, seen):
    key = (rule, table, json.dumps(sorted(row_ids)))
    if key in seen:
        return
    seen.add(key)
    session.add(ValidationFlag(rule=rule, severity=severity, layer=layer, company_id=company_id,
                               table_name=table, row_ids=key[2],
                               details=json.dumps(details, ensure_ascii=False, default=str),
                               run_at=utcnow()))


_REVISED = __import__("re").compile(r"更正后|修订版|修订稿|更新后")


def _difference_pattern(a, b) -> str:
    """v2.0.8: what kind of difference two readings show, to guide review (findings 84 and 85)."""
    from .numbers import glue_split, power_of_ten

    def raw(x):
        return x.raw_value or (f"{x.value:,.2f}" if x.value is not None else "")
    if glue_split(raw(a), raw(b)) or glue_split(raw(b), raw(a)):
        return "DIGITS_GLUED"
    if power_of_ten(a.value, b.value) is not None:
        return "POWER_OF_TEN"
    if a.value and b.value and abs(abs(a.value) - abs(b.value)) <= 0.001 * abs(a.value):
        return "SIGN"
    return "OTHER"


def cross_validate(security_code: str | None = None) -> dict:
    init_db()
    session = SessionLocal()
    counts: dict[str, int] = defaultdict(int)
    seen: set = set()
    try:
        cq = session.query(Company)
        if security_code:
            cq = cq.filter(Company.security_code == str(security_code).zfill(6))
        companies = cq.all()
        ids = [c.id for c in companies]
        # regenerate flags for the companies in scope
        if ids:
            session.query(ValidationFlag).filter(ValidationFlag.company_id.in_(ids)).delete(synchronize_session=False)
        session.flush()

        dates = {d.id: d.announcement_date for d in session.query(Disclosure.id, Disclosure.announcement_date)}
        titles = {d.id: d.title_cn or "" for d in session.query(Disclosure.id, Disclosure.title_cn)}
        for c in companies:
            facts = session.query(FinancialFact).filter(FinancialFact.company_id == c.id).all()

            # Stage 1: provenance
            for f in facts:
                if not f.source_document:
                    _flag(session, "MISSING_PROVENANCE", "ERROR", "financials", c.id, "financial_facts",
                          [f.id], {"metric": f.metric, "period": f.reporting_period}, seen)
                    counts["MISSING_PROVENANCE"] += 1

            # Stage 3a: same period/metric/scope reported in different documents
            groups = defaultdict(list)
            for f in facts:
                if f.value is None or f.reporting_period is None:
                    continue
                scope = f.consolidation_scope if f.consolidation_scope not in (None, "CONSOLIDATED_DEFAULT") else "DEFAULT"
                groups[(f.reporting_period, f.metric, scope)].append(f)
            restatements = [e for e in session.query(RegulatoryEvent).filter(
                RegulatoryEvent.company_id == c.id, RegulatoryEvent.event_type == "ACCOUNTING_RESTATEMENT")]
            for (period, metric, scope), rows in groups.items():
                by_doc = {}
                for r in rows:
                    by_doc.setdefault(r.disclosure_id, r)
                if len(by_doc) < 2:
                    continue
                ordered = sorted(by_doc.values(), key=lambda r: (dates.get(r.disclosure_id) or "", r.id))
                for a, b in zip(ordered, ordered[1:]):
                    if _close(a.value, b.value):
                        continue
                    da, db = dates.get(a.disclosure_id) or "", dates.get(b.disclosure_id) or ""
                    # v2.0.8 (finding 86): between documents filed the same day, any restatement filed that day
                    # "explained" the difference; it explains nothing. A corrected report is named as such.
                    explained = [e.id for e in restatements if da <= (e.event_date or e.announcement_date or "") <= db] \
                        if da != db else []
                    corrected = any(_REVISED.search(titles.get(x.disclosure_id, "")) for x in (a, b))
                    both_xbrl = a.extraction_method.startswith("XBRL") and b.extraction_method.startswith("XBRL")
                    rule = "RESTATEMENT_EXPLAINED" if explained else "CORRECTED_REPORT" if corrected else (
                        "RESTATEMENT_OR_DISCREPANCY" if both_xbrl else "EXTRACTION_DISCREPANCY")
                    sev = "INFO" if explained or corrected else "WARN"
                    _flag(session, rule, sev, "financials", c.id, "financial_facts", [a.id, b.id], {
                        "period": period, "metric": metric, "scope": scope,
                        "earlier": {"value": a.value, "published": da, "method": a.extraction_method, "disclosure_id": a.disclosure_id},
                        "later": {"value": b.value, "published": db, "method": b.extraction_method, "disclosure_id": b.disclosure_id},
                        "relative_change": (b.value - a.value) / abs(a.value) if a.value else None,
                        "pattern": _difference_pattern(a, b),
                        "restatement_announcements": explained}, seen)
                    counts[rule] += 1

            # Stage 3b: cumulative interim figures exceeding the annual figure
            best = {}
            for (period, metric, scope), rows in groups.items():
                if metric in FLOW_METRICS and scope == "DEFAULT":
                    best[(period, metric)] = max(rows, key=lambda r: (dates.get(r.disclosure_id) or "", r.confidence or 0))
            for (period, metric), fy in list(best.items()):
                if not period.endswith("12-31") or fy.period_type not in ("FY", None):
                    continue
                y = period[:4]
                for p in (f"{y}-06-30", f"{y}-09-30"):
                    it = best.get((p, metric))
                    if it and fy.value is not None and it.value is not None and fy.value > 0 \
                            and it.value > fy.value * 1.005:
                        _flag(session, "INTERIM_EXCEEDS_ANNUAL", "WARN", "financials", c.id, "financial_facts",
                              [it.id, fy.id], {"metric": metric, "interim_period": p, "interim": it.value,
                                               "annual": fy.value}, seen)
                        counts["INTERIM_EXCEEDS_ANNUAL"] += 1

            # Stage 3c: ownership percentage vs shares / total shares
            totals = {}
            for cap in session.query(CapitalStructureObservation).filter(
                    CapitalStructureObservation.company_id == c.id, CapitalStructureObservation.total_shares.isnot(None)):
                totals.setdefault(cap.observation_date, cap)
            for o in session.query(OwnershipObservation).filter(OwnershipObservation.company_id == c.id):
                cap = totals.get(o.observation_date)
                if cap and o.shares and o.ownership_pct is not None:
                    implied = o.shares / cap.total_shares * 100
                    if abs(implied - o.ownership_pct) > 0.05:
                        _flag(session, "OWNERSHIP_PCT_INCONSISTENT", "WARN", "ownership", c.id,
                              "ownership_observations", [o.id], {
                                  "shareholder": o.shareholder_name, "date": o.observation_date,
                                  "reported_pct": o.ownership_pct, "implied_pct": round(implied, 4),
                                  "capital_observation_id": cap.id}, seen)
                        counts["OWNERSHIP_PCT_INCONSISTENT"] += 1

            # Stage 3d: distribution terms changed between proposal and
            # implementation (same scheme, linked by action_group)
            from .models import CorporateAction
            schemes = defaultdict(list)
            for a in session.query(CorporateAction).filter(CorporateAction.company_id == c.id,
                                                           CorporateAction.action_group.isnot(None)):
                if a.action_type in ("CASH_DIVIDEND", "BONUS_SHARES", "CAPITALISATION_ISSUE"):
                    schemes[a.action_group].append(a)
            for grp in schemes.values():
                prop = [a for a in grp if a.status in ("PROPOSED", "APPROVED")]
                impl = [a for a in grp if a.status in ("IMPLEMENTATION_ANNOUNCED", "COMPLETED")]
                field = "cash_amount" if grp[0].action_type == "CASH_DIVIDEND" else "ratio"
                for p_ in prop:
                    for i_ in impl:
                        pv, iv = getattr(p_, field), getattr(i_, field)
                        if pv is not None and iv is not None and abs(pv - iv) > 1e-6:
                            # Per-share amounts are commonly adjusted when the share base
                            # changes before the record date (total amount held constant).
                            _flag(session, "DISTRIBUTION_TERMS_CHANGED", "INFO", "corporate_actions", c.id,
                                  "corporate_actions", [p_.id, i_.id],
                                  {"type": p_.action_type, "field": field, "proposed": pv, "implemented": iv,
                                   "fiscal_period": p_.fiscal_period}, seen)
                            counts["DISTRIBUTION_TERMS_CHANGED"] += 1

            # v1.1: industry classifications
            from .models import IndustryClassification, ManagementObservation, ManagementEvent
            from .industry import validate_classification
            cls_rows = session.query(IndustryClassification).filter(IndustryClassification.company_id == c.id).all()
            for ic in cls_rows:
                probs = validate_classification(ic.scheme, ic.level1_code, ic.level1_name, ic.level2_code)
                if probs:
                    _flag(session, "INDUSTRY_CODE_INVALID", "ERROR", "industry", c.id, "industry_classifications",
                          [ic.id], {"scheme": ic.scheme, "date": ic.effective_date, "problems": probs}, seen)
                    counts["INDUSTRY_CODE_INVALID"] += 1
            by_sd = defaultdict(list)
            for ic in cls_rows:
                by_sd[(ic.scheme, ic.effective_date)].append(ic)
            for (scheme, d), rows in by_sd.items():
                keys = {(r.level1_code or r.level1_name, r.level2_code or r.level2_name) for r in rows}
                if len(rows) > 1 and len(keys) > 1:
                    _flag(session, "INDUSTRY_SOURCE_CONFLICT", "WARN", "industry", c.id, "industry_classifications",
                          [r.id for r in rows], {"scheme": scheme, "date": d,
                                                 "by_source": {r.source: [r.level1_code or r.level1_name, r.level2_code or r.level2_name] for r in rows}}, seen)
                    counts["INDUSTRY_SOURCE_CONFLICT"] += 1

            # v1.1: management observations and events
            mobs = session.query(ManagementObservation).filter(ManagementObservation.company_id == c.id).all()
            for o in mobs:
                if o.tenure_start and o.tenure_end and o.tenure_end < o.tenure_start:
                    _flag(session, "TENURE_END_BEFORE_START", "ERROR", "management", c.id, "management_observations",
                          [o.id], {"person": o.person_name, "role": o.role, "start": o.tenure_start, "end": o.tenure_end}, seen)
                    counts["TENURE_END_BEFORE_START"] += 1
            evs = session.query(ManagementEvent).filter(ManagementEvent.company_id == c.id).all()
            for e in evs:
                if e.event_type not in ("RESIGNATION", "DISMISSAL", "DEATH") or not e.person_name or not e.effective_date:
                    continue
                reappointed = any(x.person_name == e.person_name and x.role == e.role and
                                  x.event_type in ("APPOINTMENT", "ELECTION") and (x.event_date or "") > e.effective_date
                                  for x in evs)
                later = [o for o in mobs if o.person_name == e.person_name and o.role == e.role
                         and o.observation_date > e.effective_date and o.status != "LEFT"]
                if later and not reappointed:
                    _flag(session, "SERVING_AFTER_DEPARTURE", "WARN", "management", c.id, "management_observations",
                          [o.id for o in later] + [e.id], {"person": e.person_name, "role": e.role,
                                                          "departure": e.effective_date,
                                                          "later_rosters": [o.observation_date for o in later],
                                                          "note": "row ids: roster observations, then the event id"}, seen)
                    counts["SERVING_AFTER_DEPARTURE"] += 1
            if mobs or evs:
                from .management import governance
                g = governance(c.security_code)
                for chk in g.get("legal_reference_checks", []):
                    if chk["result"] in ("NOT MET", "CHECK"):
                        rule = {"Independent directors at least one third of the board": "INDEPENDENT_DIRECTORS_BELOW_ONE_THIRD",
                                "Independent director tenure not above six consecutive years": "INDEPENDENT_DIRECTOR_TENURE_OVER_SIX_YEARS"}.get(chk["rule"])
                        if rule:
                            _flag(session, rule, "WARN", "management", c.id, "companies", [c.id],
                                  {"value": chk["value"], "reference": chk["reference"],
                                   "basis_roster": g.get("base_roster_date")}, seen)
                            counts[rule] += 1

            # v1.2: segments — each dimension should sum to reported revenue
            from .models import SegmentObservation, SubsidiaryObservation
            segs = session.query(SegmentObservation).filter(SegmentObservation.company_id == c.id).all()
            by_doc = defaultdict(lambda: defaultdict(list))
            for sg in segs:
                by_doc[(sg.disclosure_id, sg.source, sg.reporting_period)][sg.dimension].append(sg)
            for (did, src, period), dims in by_doc.items():
                overall = next((x for x in dims.get("TOTAL", []) if x.is_total and x.revenue), None)
                rev_fact = next((f for f in facts if f.metric == "revenue" and f.reporting_period == period
                                 and f.value and f.extraction_method != "XBRL_COMPARATIVE"), None)
                for dim, items in dims.items():
                    if dim == "TOTAL":
                        continue
                    parts = [x for x in items if not x.is_total and x.revenue is not None]
                    own_total = next((x.revenue for x in items if x.is_total and x.revenue
                                      and x.segment_name != "小计"), None)
                    # v2.0.8 (finding 83): the margin table lists only segments above 10% of revenue; without its
                    # own total row it is not compared with the whole revenue.
                    if parts and not own_total and all(getattr(x, "table_kind", None) == "margin" for x in parts):
                        continue
                    total = own_total or \
                        (overall.revenue if overall else None) or (rev_fact.value if rev_fact else None)
                    if not parts or not total:
                        continue
                    ssum = sum(x.revenue for x in parts)
                    if abs(ssum - total) > max(abs(total) * 0.01, 1000.0):
                        _flag(session, "SEGMENT_SUM_MISMATCH", "WARN", "segments", c.id, "segment_observations",
                              [x.id for x in parts], {"period": period, "dimension": dim, "segment_sum": ssum,
                                                      "reported_total": total,
                                                      "total_basis": "table total" if (overall or any(x.is_total for x in items)) else "revenue fact",
                                                      "difference_pct": (ssum - total) / total * 100}, seen)
                        counts["SEGMENT_SUM_MISMATCH"] += 1

            # v1.2: subsidiaries
            for so in session.query(SubsidiaryObservation).filter(SubsidiaryObservation.company_id == c.id):
                probs = [f"{k} = {v}" for k, v in (("direct_pct", so.direct_pct), ("indirect_pct", so.indirect_pct),
                                                    ("total_pct", so.total_pct)) if v is not None and not 0 <= v <= 100.0001]
                if probs:
                    _flag(session, "SUBSIDIARY_PCT_INVALID", "ERROR", "group", c.id, "subsidiary_observations",
                          [so.id], {"entity": so.entity_name, "date": so.observation_date, "problems": probs}, seen)
                    counts["SUBSIDIARY_PCT_INVALID"] += 1
                elif so.consolidated and so.relationship == "SUBSIDIARY" and so.total_pct is not None and so.total_pct < 50:
                    _flag(session, "CONSOLIDATED_WITH_MINORITY_STAKE", "INFO", "group", c.id, "subsidiary_observations",
                          [so.id], {"entity": so.entity_name, "date": so.observation_date, "pct": so.total_pct,
                                    "note": "control may rest on agreements (e.g. VIE), board control or voting arrangements"}, seen)
                    counts["CONSOLIDATED_WITH_MINORITY_STAKE"] += 1

            # v1.3: R&D and workforce internal consistency
            from .models import HumanCapitalObservation
            hc = defaultdict(dict)
            for h in session.query(HumanCapitalObservation).filter(HumanCapitalObservation.company_id == c.id):
                hc[(h.reporting_period, h.disclosure_id, h.source)][h.item] = h
            for (period, did, src), v in hc.items():
                val = lambda k: v[k].value if k in v and v[k].value is not None else None
                rev = next((f.value for f in facts if f.metric == "revenue" and f.reporting_period == period and f.value
                            and f.extraction_method != "XBRL_COMPARATIVE"
                            and f.consolidation_scope in (None, "CONSOLIDATED_DEFAULT")), None)
                if val("rd_ratio") is not None and val("rd_investment") and rev:
                    computed = val("rd_investment") / rev
                    if abs(computed - val("rd_ratio")) > 0.005:
                        _flag(session, "RD_RATIO_INCONSISTENT", "WARN", "human_capital", c.id, "human_capital_observations",
                              [v["rd_ratio"].id, v["rd_investment"].id], {"period": period, "reported": val("rd_ratio"),
                                                                         "computed": computed, "revenue": rev}, seen)
                        counts["RD_RATIO_INCONSISTENT"] += 1
                if val("rd_investment") and val("rd_expensed") is not None and val("rd_capitalised") is not None:
                    if abs(val("rd_expensed") + val("rd_capitalised") - val("rd_investment")) > max(val("rd_investment") * 0.005, 1000):
                        _flag(session, "RD_COMPONENTS_MISMATCH", "WARN", "human_capital", c.id, "human_capital_observations",
                              [v[k].id for k in ("rd_investment", "rd_expensed", "rd_capitalised")],
                              {"period": period, "investment": val("rd_investment"), "expensed": val("rd_expensed"),
                               "capitalised": val("rd_capitalised")}, seen)
                        counts["RD_COMPONENTS_MISMATCH"] += 1
                total = val("employees_total")
                for prefix, rule in (("staff_", "WORKFORCE_COMPOSITION_MISMATCH"), ("edu_", "EDUCATION_SUM_MISMATCH")):
                    parts = [h for k, h in v.items() if k.startswith(prefix) and not k.endswith("_total") and h.value is not None]
                    if total and parts:
                        ssum = sum(h.value for h in parts)
                        if abs(ssum - total) > max(total * 0.001, 1):  # head counts should add up exactly
                            _flag(session, rule, "WARN", "human_capital", c.id, "human_capital_observations",
                                  [h.id for h in parts], {"period": period, "sum_of_categories": ssum,
                                                          "employees_total": total}, seen)
                            counts[rule] += 1

            # Stage 1/2: market bar sanity
            bars = session.query(MarketBar).filter(MarketBar.company_id == c.id).all()
            for b in bars:
                probs = []
                if None not in (b.high, b.low) and b.high < b.low:
                    probs.append("high < low")
                if None not in (b.close, b.high, b.low) and not (b.low - 1e-9 <= b.close <= b.high + 1e-9):
                    probs.append("close outside [low, high]")
                if b.volume is not None and b.volume < 0:
                    probs.append("negative volume")
                if probs:
                    _flag(session, "MARKET_BAR_INCONSISTENT", "ERROR", "market", c.id, "market_bars", [b.id],
                          {"date": b.trade_date, "problems": probs, "source": b.source}, seen)
                    counts["MARKET_BAR_INCONSISTENT"] += 1

            # Stage 4: cross-source comparison of closes and total shares
            by_key = defaultdict(list)
            for b in bars:
                if b.close is not None:
                    by_key[(b.trade_date, b.adjustment)].append(b)
            for (d, adj), rows in by_key.items():
                srcs = {r.source: r for r in rows}
                if len(srcs) > 1:
                    vals = [r.close for r in srcs.values()]
                    if max(vals) - min(vals) > max(0.011, max(vals) * 0.0005):
                        _flag(session, "CROSS_SOURCE_PRICE_CONFLICT", "WARN", "market", c.id, "market_bars",
                              [r.id for r in srcs.values()], {"date": d, "adjustment": adj,
                                                              "closes": {s: r.close for s, r in srcs.items()}}, seen)
                        counts["CROSS_SOURCE_PRICE_CONFLICT"] += 1
            caps = defaultdict(dict)
            for cap in session.query(CapitalStructureObservation).filter(
                    CapitalStructureObservation.company_id == c.id, CapitalStructureObservation.total_shares.isnot(None)):
                caps[cap.observation_date][cap.source] = cap
            for d, srcs in caps.items():
                if len(srcs) > 1:
                    vals = [x.total_shares for x in srcs.values()]
                    if max(vals) - min(vals) > 1:
                        _flag(session, "CROSS_SOURCE_CAPITAL_CONFLICT", "WARN", "ownership", c.id,
                              "capital_structure_observations", [x.id for x in srcs.values()],
                              {"date": d, "total_shares": {s: x.total_shares for s, x in srcs.items()}}, seen)
                        counts["CROSS_SOURCE_CAPITAL_CONFLICT"] += 1

            # v1.8: ownership and control
            from .models import ControlObservation
            ctl = session.query(ControlObservation).filter(ControlObservation.company_id == c.id).order_by(
                ControlObservation.observation_date).all()
            for o in ctl:
                if o.ownership_type == "UNKNOWN":
                    _flag(session, "OWNERSHIP_TYPE_UNKNOWN", "INFO", "control", c.id, "control_observations", [o.id],
                          {"date": o.observation_date, "controller": o.actual_controller, "nature": o.controller_nature,
                           "basis": o.ownership_basis}, seen)
                    counts["OWNERSHIP_TYPE_UNKNOWN"] += 1
            from .control import normalise_name as _nn
            named = [o for o in ctl if o.actual_controller]
            for a, b in zip(named, named[1:]):
                if _nn(a.actual_controller) != _nn(b.actual_controller):
                    _flag(session, "ACTUAL_CONTROLLER_CHANGED", "INFO", "control", c.id, "control_observations",
                          [a.id, b.id], {"from": a.actual_controller, "to": b.actual_controller,
                                         "between": [a.observation_date, b.observation_date]}, seen)
                    counts["ACTUAL_CONTROLLER_CHANGED"] += 1
            by_date = defaultdict(list)
            for o in session.query(OwnershipObservation).filter(OwnershipObservation.company_id == c.id,
                                                                OwnershipObservation.rank.isnot(None)):
                by_date[(o.observation_date, o.source)].append(o)
            for (d, src), rows in by_date.items():
                tot = sum(r.ownership_pct or 0 for r in rows)
                if tot > 100.5:
                    _flag(session, "TOP_HOLDERS_EXCEED_100PCT", "ERROR", "ownership", c.id, "ownership_observations",
                          [r.id for r in rows], {"date": d, "source": src, "sum_pct": round(tot, 2)}, seen)
                    counts["TOP_HOLDERS_EXCEED_100PCT"] += 1

            # v1.6: mandatory sustainability report not observed after its deadline
            from .security_master import sustainability_mandate, MANDATE_FIRST_YEAR
            from datetime import date as _date
            for fy in range(MANDATE_FIRST_YEAR, _date.today().year):
                deadline = f"{fy + 1}-04-30"
                if _date.today().isoformat() <= deadline:
                    continue
                m = sustainability_mandate(c.security_code, fy)
                if not m.get("mandatory"):
                    continue
                published = session.query(Disclosure).filter(
                    Disclosure.company_id == c.id, Disclosure.kind == "sustainability_report",
                    Disclosure.announcement_date > f"{fy}-12-31", Disclosure.announcement_date <= deadline).count()
                if not published:
                    _flag(session, "SUSTAINABILITY_REPORT_NOT_OBSERVED", "WARN", "esg", c.id, "companies", [c.id],
                          {"fiscal_year": fy, "deadline": deadline, "indices": m.get("indices"),
                           "note": "no sustainability report catalogued by the deadline; catalogue with kind 'all' "
                                   "before concluding it was not published"}, seen)
                    counts["SUSTAINABILITY_REPORT_NOT_OBSERVED"] += 1

            # v1.5: the plain and layout extractors read different values
            from .models import (ManagementObservation, SegmentObservation, SubsidiaryObservation,
                                 HumanCapitalObservation)
            for model, layer in ((FinancialFact, "financials"), (SegmentObservation, "segments"),
                                 (SubsidiaryObservation, "group"), (HumanCapitalObservation, "human_capital"),
                                 (ManagementObservation, "management")):
                for row in session.query(model).filter(model.company_id == c.id,
                                                       model.extraction_note.like('%"DISAGREE"%')):
                    try:
                        note = json.loads(row.extraction_note)
                    except ValueError:
                        continue
                    label = next((getattr(row, a) for a in ("metric", "segment_name", "entity_name", "item",
                                                             "person_name") if hasattr(row, a)), None)
                    _flag(session, "PARSER_DISAGREEMENT", "WARN", layer, c.id, model.__tablename__, [row.id],
                          {"label": label, "kept": note.get("variant"),
                           "alternative": note.get("alternative")}, seen)
                    counts["PARSER_DISAGREEMENT"] += 1
        session.commit()
        return {"companies": len(companies), "flags": dict(counts), "total_flags": sum(counts.values())}
    finally:
        session.close()


def validate_all(security_code: str | None = None) -> dict:
    """Run every validation stage in order and summarise."""
    from .validation import validate_database
    from .financials import validate_financials
    from .ownership import validate_ownership
    from .reconciliation import reconcile_capital
    universe = validate_database()
    if security_code:
        code = str(security_code).zfill(6)
        universe = [p for p in universe if p.get("code") == code]
    fin = validate_financials(security_code)
    own = validate_ownership(security_code)
    from .linking import link_all
    links = link_all(security_code)
    rec = reconcile_capital(security_code)
    cross = cross_validate(security_code)
    return {
        "stage1_universe_problems": len(universe),
        "event_linking": links,
        "stage2_financial_balance": {k: fin[k] for k in ("groups_checked", "passed", "failed", "insufficient")},
        "stage2_ownership": {k: v for k, v in own.items() if k != "errors"},
        "stage2_capital_reconciliation": {k: rec[k] for k in ("windows", "RECONCILED", "UNEXPLAINED_DIFFERENCE", "INSUFFICIENT_DATA")}
                                         | {"tradable": rec.get("tradable", {})},
        "stage3_4_cross_validation": cross,
    }


def show_flags(security_code: str | None = None, severity: str | None = None, rule: str | None = None):
    init_db()
    session = SessionLocal()
    try:
        q = session.query(ValidationFlag)
        if security_code:
            c = session.query(Company).filter_by(security_code=str(security_code).zfill(6)).first()
            q = q.filter(ValidationFlag.company_id == (c.id if c else -1))
        if severity:
            q = q.filter(ValidationFlag.severity == severity.upper())
        if rule:
            q = q.filter(ValidationFlag.rule == rule.upper())
        return q.order_by(ValidationFlag.severity, ValidationFlag.rule, ValidationFlag.id).all()
    finally:
        session.close()


def _codes(session) -> dict[int, str]:
    return {c.id: c.security_code for c in session.query(Company.id, Company.security_code)}


def flag_summary(security_code: str | None = None, top: int = 20) -> dict:
    """v2.0.8 (finding 91): counts by rule and severity, and the companies with most findings."""
    from collections import Counter
    rows = show_flags(security_code)
    init_db()
    s = SessionLocal()
    try:
        codes = _codes(s)
    finally:
        s.close()
    by_rule = Counter((f.rule, f.severity) for f in rows)
    by_company = Counter(codes.get(f.company_id, "") for f in rows if f.company_id)
    order = {"ERROR": 0, "WARN": 1, "INFO": 2}
    return {"total": len(rows),
            "by_rule": [{"rule": r, "severity": sv, "count": n}
                        for (r, sv), n in sorted(by_rule.items(), key=lambda x: (order.get(x[0][1], 3), -x[1], x[0][0]))],
            "by_company": [{"code": c, "count": n} for c, n in by_company.most_common(top)]}


def flag_rows(security_code: str | None = None, severity: str | None = None, rule: str | None = None) -> list[dict]:
    rows = show_flags(security_code, severity, rule)
    s = SessionLocal()
    try:
        codes = _codes(s)
    finally:
        s.close()
    return [{"id": f.id, "code": codes.get(f.company_id, ""), "severity": f.severity, "rule": f.rule, "layer": f.layer,
             "table": f.table_name, "rows": f.row_ids, "details": f.details} for f in rows]


def export_flags(path: str, security_code: str | None = None, severity: str | None = None,
                 rule: str | None = None) -> str:
    """All findings (or a filtered set) to CSV, with the company code (UTF-8 with BOM, for Excel)."""
    import csv
    from pathlib import Path
    rows = flag_rows(security_code, severity, rule)
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["id", "code", "severity", "rule", "layer", "table", "rows", "details"])
        w.writeheader()
        w.writerows(rows)
    return str(p)
