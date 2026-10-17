"""Market measures (v1.7): own price-adjustment factors, market capitalisation
and point-in-time valuation ratios.

Adjustment factors
    For each ex-date, from the recorded corporate actions:
        reference price = (P − cash + rights ratio × rights price) / (1 + share ratio + rights ratio)
        factor = P / reference price
    where P is the last unadjusted close before the ex-date, cash is the
    dividend per share, and share ratio the bonus plus capitalisation shares
    per share. The cumulative factor F(t) is the product of factors with
    ex-date ≤ t. Backward-adjusted close = close × F(t); forward-adjusted close
    = close × F(t) / F(latest). Adjusted returns then no longer depend on a
    provider's adjustment; provider-adjusted series are kept and compared.

Valuation
    Market cap = close × total shares (latest capital observation on or
    before the date); free-float cap uses tradable shares. Ratios use only
    financial values published on or before the date:
        P/E = market cap / TTM net profit to the parent
        P/B = market cap / equity attributable to the parent (else total equity)
        P/S = market cap / TTM revenue
        EV  = market cap + interest-bearing debt − cash
              (short- and long-term borrowings, bonds payable, current portion
              of non-current liabilities, lease liabilities)
"""
from __future__ import annotations

import bisect
import json
from collections import defaultdict

from .timeutil import utcnow
from .models import (SessionLocal, init_db, Company, CorporateAction, MarketBar, CapitalStructureObservation,
                     AdjustmentFactor, MarketSnapshot, FinancialFact, Disclosure)

ADJ_TYPES = ("CASH_DIVIDEND", "BONUS_SHARES", "CAPITALISATION_ISSUE", "RIGHTS_ISSUE")
_STATUS_RANK = {"COMPLETED": 3, "IMPLEMENTATION_ANNOUNCED": 2}
DEBT_ITEMS = ("short_term_borrowings", "long_term_borrowings", "bonds_payable",
              "non_current_liabilities_due_within_one_year", "lease_liabilities")


def _companies(session, code):
    q = session.query(Company)
    if code:
        q = q.filter(Company.security_code == str(code).zfill(6))
    return q.all()


def _closes(session, company_id, adjustment="none") -> list[tuple[str, float]]:
    rows = (session.query(MarketBar.trade_date, MarketBar.close, MarketBar.source)
            .filter(MarketBar.company_id == company_id, MarketBar.adjustment == adjustment,
                    MarketBar.close.isnot(None)).order_by(MarketBar.trade_date).all())
    by_day = {}
    for d, c, src in rows:          # one close per day; prefer a licensed/import source over the public feed
        if d not in by_day or src != "EASTMONEY_PUBLIC":
            by_day[d] = c
    return sorted(by_day.items())


def compute_adjustment_factors(security_code: str | None = None) -> dict:
    init_db()
    s = SessionLocal()
    totals = {"companies": 0, "ex_dates": 0, "skipped_no_price": 0}
    try:
        for c in _companies(s, security_code):
            acts = [a for a in s.query(CorporateAction).filter(CorporateAction.company_id == c.id,
                                                               CorporateAction.action_type.in_(ADJ_TYPES),
                                                               CorporateAction.ex_date.isnot(None))
                    if a.status not in ("TERMINATED", "PROPOSED")]
            if not acts:
                continue
            # one record per (type, ex-date): the most advanced status wins
            best = {}
            for a in acts:
                k = (a.action_type, a.ex_date)
                if k not in best or _STATUS_RANK.get(a.status, 0) > _STATUS_RANK.get(best[k].status, 0):
                    best[k] = a
            by_date = defaultdict(list)
            for a in best.values():
                by_date[a.ex_date].append(a)
            closes = _closes(s, c.id)
            days = [d for d, _ in closes]
            s.query(AdjustmentFactor).filter_by(company_id=c.id, source="OWN").delete()
            cum = 1.0
            for ex in sorted(by_date):
                i = bisect.bisect_left(days, ex) - 1
                if i < 0:
                    totals["skipped_no_price"] += 1
                    continue
                p = closes[i][1]
                cash = sum(a.cash_amount or 0 for a in by_date[ex] if a.action_type == "CASH_DIVIDEND")
                shares = sum(a.ratio or 0 for a in by_date[ex] if a.action_type in ("BONUS_SHARES", "CAPITALISATION_ISSUE"))
                rights = [a for a in by_date[ex] if a.action_type == "RIGHTS_ISSUE" and a.ratio and a.subscription_price]
                r_ratio = sum(a.ratio for a in rights)
                r_price = (sum(a.ratio * a.subscription_price for a in rights) / r_ratio) if r_ratio else 0.0
                ref = (p - cash + r_ratio * r_price) / (1 + shares + r_ratio)
                if ref <= 0:
                    continue
                factor = p / ref
                cum *= factor
                s.add(AdjustmentFactor(company_id=c.id, ex_date=ex, prev_close=p, cash_per_share=cash or None,
                                       share_ratio=shares or None, rights_ratio=r_ratio or None,
                                       rights_price=r_price or None, reference_price=ref, factor=factor,
                                       cumulative=cum, action_ids=json.dumps([a.id for a in by_date[ex]]),
                                       source="OWN", computed_at=utcnow()))
                totals["ex_dates"] += 1
            totals["companies"] += 1
        s.commit()
        return totals
    finally:
        s.close()


def adjusted_closes(security_code: str, kind: str = "forward") -> list[dict]:
    """Closes adjusted with own factors: 'forward' (前复权) or 'backward' (后复权)."""
    init_db()
    s = SessionLocal()
    try:
        c = s.query(Company).filter_by(security_code=str(security_code).zfill(6)).first()
        if not c:
            return []
        closes = _closes(s, c.id)
        facts = [(f.ex_date, f.cumulative) for f in s.query(AdjustmentFactor).filter_by(company_id=c.id, source="OWN")
                 .order_by(AdjustmentFactor.ex_date)]
    finally:
        s.close()
    dates = [d for d, _ in facts]
    last = facts[-1][1] if facts else 1.0
    out = []
    for d, close in closes:
        i = bisect.bisect_right(dates, d) - 1
        F = facts[i][1] if i >= 0 else 1.0
        out.append({"date": d, "close": close, "factor": F,
                    "adjusted": close * F if kind == "backward" else close * F / last})
    return out


def compare_adjustments(security_code: str | None = None, tolerance: float = 0.005) -> list[dict]:
    """Own forward-adjusted closes against a provider's forward-adjusted closes."""
    init_db()
    s = SessionLocal()
    try:
        companies = _companies(s, security_code)
        pairs = []
        for c in companies:
            prov = dict(_closes(s, c.id, "forward"))
            if prov:
                pairs.append((c, prov))
    finally:
        s.close()
    out = []
    for c, prov in pairs:
        own = {r["date"]: r["adjusted"] for r in adjusted_closes(c.security_code, "forward")}
        common = sorted(set(own) & set(prov))
        if not common:
            continue
        bad = [d for d in common if prov[d] and abs(own[d] / prov[d] - 1) > tolerance]
        out.append({"code": c.security_code, "days": len(common), "within_tolerance": 1 - len(bad) / len(common),
                    "worst_days": [{"date": d, "own": round(own[d], 4), "provider": prov[d]} for d in bad[:5]]})
    return out


# --- point-in-time financial knowledge ----------------------------------------------

class Knowledge:
    """What was known about a company's financials on any date.

    States are computed at each publication date (when knowledge can change)
    and looked up by bisection."""

    def __init__(self, code: str):
        from .derived import ttm_series
        from .intelligence import financial_series
        self.code = code
        s = SessionLocal()
        try:
            c = s.query(Company).filter_by(security_code=str(code).zfill(6)).first()
            pubs = sorted({d for (d,) in s.query(Disclosure.announcement_date).join(
                FinancialFact, FinancialFact.disclosure_id == Disclosure.id).filter(
                FinancialFact.company_id == c.id) if d}) if c else []
        finally:
            s.close()
        self.dates = pubs
        self.states = []
        for d in pubs:
            st = {}
            for m, fn in (("ttm_net_profit_parent", lambda: ttm_series(code, "net_profit_parent", as_of=d)),
                          ("ttm_revenue", lambda: ttm_series(code, "revenue", as_of=d)),
                          ("ttm_operating_profit", lambda: ttm_series(code, "operating_profit", as_of=d))):
                pts = fn()
                if pts:
                    st[m] = pts[-1]
            for m in ("equity_parent", "equity", "cash") + DEBT_ITEMS:
                pts = financial_series(code, m, as_of=d)
                if pts:
                    st[m] = pts[-1]
            self.states.append(st)

    def at(self, on: str) -> dict:
        i = bisect.bisect_right(self.dates, on) - 1
        return self.states[i] if i >= 0 else {}


def _ratio(num, den):
    return num / den if num is not None and den not in (None, 0) and den > 0 else None


def valuation_from(close: float, shares: float | None, tradable: float | None, k: dict) -> dict:
    mcap = close * shares if shares else None
    v = lambda m: (k.get(m) or {}).get("value")  # noqa: E731
    book = v("equity_parent") if v("equity_parent") is not None else v("equity")
    debt_parts = [v(m) for m in DEBT_ITEMS if v(m) is not None]
    ev = (mcap + sum(debt_parts) - (v("cash") or 0)) if mcap is not None and debt_parts else None
    return {"market_cap": mcap, "float_market_cap": close * tradable if tradable else None,
            "pe": _ratio(mcap, v("ttm_net_profit_parent")), "pb": _ratio(mcap, book),
            "ps": _ratio(mcap, v("ttm_revenue")), "ev": ev, "ev_to_ebit": _ratio(ev, v("ttm_operating_profit")),
            "inputs": {m: {"period": x.get("period"), "published": x.get("published"), "value": x.get("value")}
                       for m, x in k.items()}}


def build_market_snapshots(security_code: str | None = None, frequency: str = "month") -> dict:
    """Market cap and valuation ratios at each month end (or each day)."""
    init_db()
    s = SessionLocal()
    totals = {"companies": 0, "snapshots": 0, "without_capital": 0}
    try:
        companies = _companies(s, security_code)
        for c in companies:
            closes = _closes(s, c.id)
            if not closes:
                continue
            if frequency == "month":
                last = {}
                for d, cl in closes:
                    last[d[:7]] = (d, cl)
                closes = sorted(last.values())
            caps = sorted(((x.observation_date, x.total_shares, x.tradable_shares) for x in s.query(
                CapitalStructureObservation).filter(CapitalStructureObservation.company_id == c.id,
                                                    CapitalStructureObservation.total_shares.isnot(None))))
            cap_dates = [x[0] for x in caps]
            know = Knowledge(c.security_code)
            s.query(MarketSnapshot).filter_by(company_id=c.id, source="DERIVED").delete()
            for d, cl in closes:
                i = bisect.bisect_right(cap_dates, d) - 1
                if i < 0:
                    totals["without_capital"] += 1
                    shares = tradable = None
                else:
                    _, shares, tradable = caps[i]
                val = valuation_from(cl, shares, tradable, know.at(d))
                s.add(MarketSnapshot(company_id=c.id, trade_date=d, close=cl, market_cap=val["market_cap"],
                                     float_market_cap=val["float_market_cap"], shares_outstanding=shares,
                                     float_shares=tradable, pe=val["pe"], pb=val["pb"], ps=val["ps"], ev=val["ev"],
                                     ev_to_ebit=val["ev_to_ebit"], source="DERIVED",
                                     raw_json=json.dumps(val["inputs"], ensure_ascii=False, default=str),
                                     retrieved_at=utcnow()))
                totals["snapshots"] += 1
            totals["companies"] += 1
            s.commit()
        return totals
    finally:
        s.close()


def valuation_at(security_code: str, on: str) -> dict:
    """Valuation on one date from the latest close on or before it."""
    init_db()
    s = SessionLocal()
    try:
        c = s.query(Company).filter_by(security_code=str(security_code).zfill(6)).first()
        if not c:
            return {"error": "company not found"}
        closes = [x for x in _closes(s, c.id) if x[0] <= on]
        cap = (s.query(CapitalStructureObservation).filter(
            CapitalStructureObservation.company_id == c.id, CapitalStructureObservation.observation_date <= on,
            CapitalStructureObservation.total_shares.isnot(None))
            .order_by(CapitalStructureObservation.observation_date.desc()).first())
    finally:
        s.close()
    if not closes:
        return {"code": c.security_code, "error": "no prices on or before the date"}
    d, cl = closes[-1]
    out = valuation_from(cl, cap.total_shares if cap else None, cap.tradable_shares if cap else None,
                         Knowledge(c.security_code).at(on))
    out.update(code=c.security_code, date=d, close=cl, capital_date=cap.observation_date if cap else None)
    return out
