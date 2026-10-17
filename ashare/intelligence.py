"""v1.0 integrated company intelligence.

All views accept ``as_of``: only information *published* on or before that
date is used (financial facts by the announcement date of their source
document; corporate actions and regulatory events by their announcement or
event date; market bars by trading date; ownership and capital by
observation date, the only date those sources carry). This prevents
look-ahead bias in research that uses the data historically.
"""
from __future__ import annotations

import json
import math
from collections import defaultdict

from .models import (
    SessionLocal, Company, Disclosure, FinancialFact, MarketBar, OwnershipObservation,
    CapitalStructureObservation, CorporateAction, RegulatoryEvent, ValidationFlag,
    CapitalReconciliation, init_db,
)
from .crossvalidation import confidence_class
from .corporate_actions import capital_effective_date

METHOD_RANK = {"XBRL": 3, "XBRL_COMPARATIVE": 3, "CSV_IMPORT": 2, "PDF_STATEMENT_TABLE": 1.5, "PDF_TEXT_HEURISTIC": 1}


def _company(session, code):
    return session.query(Company).filter_by(security_code=str(code).strip().zfill(6)).first()


# ---------------------------------------------------------------------------
# Financial series
# ---------------------------------------------------------------------------

def financial_series(code: str, metric: str, as_of: str | None = None, period_type: str | None = None,
                     vintage: str = "latest", scope: str = "DEFAULT") -> list[dict]:
    """Point-in-time series of one metric.

    ``vintage='latest'``: for each period, the most recently published value
    known at ``as_of`` (reflects restatements disclosed as comparatives).
    ``vintage='original'``: the first published value (as originally reported).
    Each point carries its source, publication date, method, confidence class
    and the number of vintages, with ``restated`` set when vintages differ.
    """
    init_db()
    session = SessionLocal()
    try:
        c = _company(session, code)
        if not c:
            return []
        rows = (session.query(FinancialFact, Disclosure.announcement_date, Disclosure.title_cn)
                .outerjoin(Disclosure, FinancialFact.disclosure_id == Disclosure.id)
                .filter(FinancialFact.company_id == c.id, FinancialFact.metric == metric).all())
        from .review import CorrectionIndex
        reviews = CorrectionIndex(session, "financial_facts")
        by_period = defaultdict(list)
        for f, published, title in rows:
            value, review = reviews.apply(f, f.value)
            if value is None or f.reporting_period is None:
                continue
            if as_of and (published is None or published > as_of):
                continue
            fscope = "DEFAULT" if f.consolidation_scope in (None, "CONSOLIDATED_DEFAULT") else f.consolidation_scope
            if fscope != scope:
                continue
            if period_type and f.period_type != period_type:
                continue
            by_period[f.reporting_period].append((f, published or "", title, value, review))
        out = []
        for period in sorted(by_period):
            cands = by_period[period]
            # One value per document: prefer the stronger method within a document.
            per_doc = {}
            for cand in cands:
                f = cand[0]
                k = f.disclosure_id
                rank = METHOD_RANK.get(f.extraction_method, 0) + (10 if cand[4] else 0)  # reviewed values first
                if k not in per_doc or rank > per_doc[k][1]:
                    per_doc[k] = (cand, rank)
            vintages = sorted((c for c, _ in per_doc.values()),
                              key=lambda x: (x[1], METHOD_RANK.get(x[0].extraction_method, 0)))
            f, pub, title, value, review = vintages[-1] if vintage == "latest" else vintages[0]
            values = [v[3] for v in vintages]
            restated = len(values) > 1 and (max(values) - min(values)) > max(1000.0, abs(max(values, key=abs)) * 0.005)
            out.append({
                "period": period, "period_type": f.period_type, "value": value, "unit": f.unit,
                "published": pub or None, "source_title": title, "fact_id": f.id,
                "method": f.extraction_method, "confidence": f.confidence,
                "confidence_class": "HIGH" if review in ("ACCEPTED", "CORRECTED") else
                confidence_class(f.confidence, f.validation_status),
                "validation": f.validation_status, "vintages": len(vintages), "restated": restated,
                "review": review, "original_value": f.value if review == "CORRECTED" else None,
            })
        return out
    finally:
        session.close()


def compare(codes: list[str], metrics: list[str], period: str | None = None, period_type: str | None = "FY",
            as_of: str | None = None) -> dict:
    """Cross-company comparison. With ``period``: one row per company and a
    column per metric. Without: the latest period per company. Values carry
    their confidence class so comparisons of unlike quality are visible."""
    table = []
    for code in codes:
        row = {"code": str(code).zfill(6)}
        for m in metrics:
            series = financial_series(code, m, as_of=as_of, period_type=period_type)
            pt = next((p for p in series if p["period"] == period), None) if period else (series[-1] if series else None)
            row[m] = pt["value"] if pt else None
            row[f"{m}__period"] = pt["period"] if pt else None
            row[f"{m}__class"] = pt["confidence_class"] if pt else None
        # common ratios where inputs exist
        if row.get("net_profit") is not None and row.get("revenue"):
            row["net_margin"] = row["net_profit"] / row["revenue"]
        if row.get("total_liabilities") is not None and row.get("total_assets"):
            row["liabilities_to_assets"] = row["total_liabilities"] / row["total_assets"]
        if row.get("rd_expense") is not None and row.get("revenue"):
            row["rd_intensity"] = row["rd_expense"] / row["revenue"]
        table.append(row)
    return {"period": period, "period_type": period_type, "as_of": as_of, "metrics": metrics, "rows": table}


# ---------------------------------------------------------------------------
# Market statistics
# ---------------------------------------------------------------------------

def market_stats(code: str, start: str | None = None, end: str | None = None,
                 adjustment: str = "none", source: str | None = None) -> dict:
    """Return, volatility, drawdown and liquidity for one series.

    A single adjustment type and a single source are used; mixing series is
    refused. Returns over unadjusted prices are price returns and ignore
    distributions; use a forward/backward-adjusted series for total-return
    approximations.
    """
    init_db()
    session = SessionLocal()
    try:
        c = _company(session, code)
        if not c:
            return {"error": "company not found"}
        q = session.query(MarketBar).filter(MarketBar.company_id == c.id, MarketBar.adjustment == adjustment)
        if start:
            q = q.filter(MarketBar.trade_date >= start)
        if end:
            q = q.filter(MarketBar.trade_date <= end)
        bars = q.order_by(MarketBar.trade_date).all()
        sources = sorted({b.source for b in bars})
        if source:
            bars = [b for b in bars if b.source == source]
        elif len(sources) > 1:
            return {"error": "several sources for this series; choose one with --source", "sources": sources}
        bars = [b for b in bars if b.close is not None]
        if len(bars) < 2:
            return {"code": c.security_code, "bars": len(bars), "error": "fewer than two bars"}
        closes = [b.close for b in bars]
        rets = [closes[i] / closes[i - 1] - 1 for i in range(1, len(closes)) if closes[i - 1]]
        mean = sum(rets) / len(rets)
        sd = math.sqrt(sum((r - mean) ** 2 for r in rets) / (len(rets) - 1)) if len(rets) > 1 else 0.0
        peak, mdd = closes[0], 0.0
        for x in closes:
            peak = max(peak, x)
            mdd = min(mdd, x / peak - 1)
        amounts = [b.amount for b in bars if b.amount is not None]
        turnover = [b.turnover_rate for b in bars if b.turnover_rate is not None]
        return {
            "code": c.security_code, "source": source or (sources[0] if sources else None),
            "adjustment": adjustment, "start": bars[0].trade_date, "end": bars[-1].trade_date,
            "bars": len(bars), "first_close": closes[0], "last_close": closes[-1],
            "price_return": closes[-1] / closes[0] - 1,
            "daily_volatility": sd, "annualised_volatility": sd * math.sqrt(244),
            "max_drawdown": mdd, "high": max(b.high for b in bars if b.high is not None) if any(b.high is not None for b in bars) else None,
            "low": min(b.low for b in bars if b.low is not None) if any(b.low is not None for b in bars) else None,
            "average_amount": sum(amounts) / len(amounts) if amounts else None,
            "average_turnover_rate": sum(turnover) / len(turnover) if turnover else None,
            "note": "price return; distributions excluded" if adjustment == "none" else "adjusted series as supplied by the provider",
        }
    finally:
        session.close()


# ---------------------------------------------------------------------------
# Timeline and profile
# ---------------------------------------------------------------------------

def timeline(code: str, since: str | None = None, until: str | None = None) -> list[dict]:
    """Chronological view across layers (corporate actions, regulatory events,
    capital observations, material disclosures, reconciliation results)."""
    init_db()
    session = SessionLocal()
    try:
        c = _company(session, code)
        if not c:
            return []
        items = []
        for a in session.query(CorporateAction).filter(CorporateAction.company_id == c.id):
            d = capital_effective_date(a) or a.announcement_date
            detail = {k: v for k, v in (("ratio", a.ratio), ("cash_per_share", a.cash_amount),
                                        ("share_delta", a.share_delta), ("shares_affected", a.shares_affected)) if v is not None}
            items.append({"date": d, "layer": "corporate_action", "type": a.action_type, "status": a.status,
                          "detail": detail, "id": a.id, "group": a.action_group, "confidence": a.confidence})
        for e in session.query(RegulatoryEvent).filter(RegulatoryEvent.company_id == c.id):
            detail = {k: v for k, v in (("authority", e.authority_name or e.authority), ("document", e.document_number),
                                        ("fine_total", e.fine_amount_total), ("amount_in_dispute", e.amount_in_dispute),
                                        ("subtype", e.event_subtype)) if v}
            items.append({"date": e.event_date or e.announcement_date, "layer": "regulatory", "type": e.event_type,
                          "status": e.status, "detail": detail, "id": e.id, "group": e.case_key, "confidence": e.confidence})
        for cap in session.query(CapitalStructureObservation).filter(CapitalStructureObservation.company_id == c.id):
            items.append({"date": cap.observation_date, "layer": "capital", "type": "CAPITAL_OBSERVATION",
                          "status": cap.validation_status, "detail": {"total_shares": cap.total_shares,
                                                                      "tradable_shares": cap.tradable_shares, "source": cap.source},
                          "id": cap.id, "group": None, "confidence": cap.confidence})
        for r in session.query(CapitalReconciliation).filter(CapitalReconciliation.company_id == c.id):
            items.append({"date": r.t1_date, "layer": "reconciliation", "type": "CAPITAL_RECONCILIATION",
                          "status": r.status, "detail": {"window": f"{r.t0_date}..{r.t1_date}", "residual": r.residual,
                                                         "tradable_status": r.tradable_status},
                          "id": r.id, "group": None, "confidence": None})
        for d in session.query(Disclosure).filter(Disclosure.company_id == c.id,
                                                   Disclosure.kind.in_(("annual_report", "interim_report", "quarterly_report",
                                                                        "earnings_forecast_or_flash"))):
            items.append({"date": d.announcement_date, "layer": "disclosure", "type": d.kind.upper(), "status": None,
                          "detail": {"title": d.title_cn}, "id": d.id, "group": None, "confidence": None})
        items = [i for i in items if i["date"] and (not since or i["date"] >= since) and (not until or i["date"] <= until)]
        return sorted(items, key=lambda i: (i["date"], i["layer"], i["id"]))
    finally:
        session.close()


PROFILE_METRICS = ("revenue", "net_profit", "net_profit_parent", "total_assets", "total_liabilities",
                   "equity", "operating_cash_flow", "rd_expense", "employees")


def company_profile(code: str, as_of: str | None = None) -> dict:
    """One structured view of a company at a point in time."""
    from .regulatory import regulatory_status
    init_db()
    session = SessionLocal()
    try:
        c = _company(session, code)
        if not c:
            return {"error": "company not found"}
        ident = {"code": c.security_code, "exchange": c.exchange, "board": c.board, "legal_name_cn": c.legal_name_cn,
                 "short_name_cn": c.short_name_cn, "listing_date": c.listing_date, "org_id": c.org_id,
                 "status": c.status}
        # v1.6: identity and index membership on the as-of date
        from .security_master import name_at, company_indices
        from datetime import date as _date
        on = as_of or _date.today().isoformat()
        at = name_at(c.security_code, on)
        if at:
            ident.update({"short_name_at_date": at["short_name_cn"], "board_at_date": at["board"],
                          "listing_status_at_date": at["listing_status"], "risk_warning_at_date": at["risk_warning"]})
        ident["indices"] = [m["index_name"] or m["index_code"] for m in company_indices(c.security_code, on)]
        caps = [x for x in session.query(CapitalStructureObservation).filter(
            CapitalStructureObservation.company_id == c.id).order_by(CapitalStructureObservation.observation_date)
            if not as_of or x.observation_date <= as_of]
        capital = None
        if caps:
            x = caps[-1]
            capital = {"date": x.observation_date, "total_shares": x.total_shares, "tradable_shares": x.tradable_shares,
                       "restricted_shares": x.restricted_shares, "treasury_shares": x.treasury_shares,
                       "source": x.source, "validation": x.validation_status}
        owners = [o for o in session.query(OwnershipObservation).filter(OwnershipObservation.company_id == c.id)
                  if not as_of or o.observation_date <= as_of]
        top = []
        if owners:
            latest = max(o.observation_date for o in owners)
            top = [{"rank": o.rank, "shareholder": o.shareholder_name, "shares": o.shares, "pct": o.ownership_pct,
                    "pledged": o.pledged_shares, "controlling": o.is_controlling_shareholder,
                    "actual_controller": o.is_actual_controller, "source": o.source}
                   for o in sorted((o for o in owners if o.observation_date == latest), key=lambda o: (o.rank or 999))]
            top_date = latest
        flags = session.query(ValidationFlag).filter(ValidationFlag.company_id == c.id).all()
        n_disc = session.query(Disclosure).filter(Disclosure.company_id == c.id).count()
        bars = session.query(MarketBar).filter(MarketBar.company_id == c.id)
        if as_of:
            bars = bars.filter(MarketBar.trade_date <= as_of)
        last_bar = bars.order_by(MarketBar.trade_date.desc()).first()
    finally:
        session.close()

    financials = {}
    for m in PROFILE_METRICS:
        s = financial_series(code, m, as_of=as_of, period_type="FY")
        if s:
            financials[m] = s[-5:]
    actions = [i for i in timeline(code, until=as_of) if i["layer"] == "corporate_action"]
    from .industry import classification_at
    from .management import governance
    from .models import IndustryClassification, ManagementObservation, ManagementEvent
    session = SessionLocal()
    try:
        c2 = _company(session, code)
        schemes = sorted({x.scheme for x in session.query(IndustryClassification).filter_by(company_id=c2.id)})
        industry = {}
        for sch in schemes:
            cl = classification_at(session, c2.id, sch, as_of)
            if cl:
                industry[sch] = {"level1": f"{cl.level1_code or ''} {cl.level1_name or ''}".strip(),
                                 "level2": f"{cl.level2_code or ''} {cl.level2_name or ''}".strip() or None,
                                 "since": cl.effective_date, "source": cl.source}
        has_mgmt = (session.query(ManagementObservation).filter_by(company_id=c2.id).count()
                    + session.query(ManagementEvent).filter_by(company_id=c2.id).count()) > 0
    finally:
        session.close()
    gov = governance(code, as_of) if has_mgmt else None
    from .segments import segments as _segments
    from .group import subsidiaries as _subs
    seg = _segments(code, as_of=as_of)
    grp = _subs(code, as_of=as_of)
    from .human_capital import human_capital as _hc
    from .esg import esg_profile as _esg
    hc = _hc(code, as_of=as_of)
    esg = _esg(code, as_of=as_of)
    flag_summary = defaultdict(int)
    for f in flags:
        flag_summary[f"{f.severity}:{f.rule}"] += 1
    return {
        "as_of": as_of, "identity": ident, "capital": capital,
        "top_shareholders": {"date": top_date, "holders": top[:10]} if top else None,
        "financials_fy": financials,
        "market_last": ({"date": last_bar.trade_date, "close": last_bar.close, "adjustment": last_bar.adjustment,
                         "source": last_bar.source} if last_bar else None),
        "corporate_actions_recent": actions[-10:],
        "regulatory": regulatory_status(code, as_of),
        "industry": industry,
        "governance": gov,
        "segments": seg if seg.get("dimensions") else None,
        "group": {"date": grp["date"], "summary": grp["summary"]} if grp.get("entities") else None,
        "human_capital": hc if hc.get("values") else None,
        "esg": esg if esg.get("year") else None,
        "validation_flags": dict(flag_summary),
        "coverage": {"disclosures": n_disc, "fy_metrics": len(financials)},
    }
