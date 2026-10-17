"""Research panel builder and codebook (v1.7, build plan section 18.7).

A panel has one row per company and period: company-year or company-quarter
(fiscal alignment), or company-date (point-in-time alignment, e.g. every
30 April or every month end).

Alignment
    fiscal  The row is a fiscal period; each financial variable is the value
            for that period (latest vintage known at ``as_of``), with its
            publication date. Market variables are measured at the period end.
    pit     The row is a date D; each variable is what was published on or
            before D (minus an optional reporting lag), so the panel can be
            used for prediction without look-ahead.

Whatever the alignment, with ``as_of`` no value published after ``as_of``
enters the panel, and periods ending after ``as_of`` are dropped. The
builder checks this and records the latest publication date in the manifest.
"""
from __future__ import annotations

import csv
import hashlib
import json
import math
import statistics
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path
from typing import Callable

from . import __version__
from .timeutil import utcnow


@dataclass
class Variable:
    name: str
    label: str
    unit: str
    group: str
    definition: str
    formula: str = ""
    source: str = ""
    pit_rule: str = "value published on or before the row's cut-off date"
    confidence: str = "carries the confidence class of its inputs; filtered by --min-class"
    getter: Callable | None = None   # (ctx, company) -> (value, published, class, review)


VARIABLES: dict[str, Variable] = {}


def _var(name, label, unit, group, definition, formula="", source="", pit_rule=None, getter=None, confidence=None):
    v = Variable(name, label, unit, group, definition, formula, source, getter=getter)
    if pit_rule:
        v.pit_rule = pit_rule
    if confidence:
        v.confidence = confidence
    VARIABLES[name] = v
    return v


# --- context ------------------------------------------------------------------------

@dataclass
class RowContext:
    code: str
    period: str | None          # fiscal period end (fiscal alignment) or None
    cutoff: str                 # latest publication date usable for this row
    measure_date: str           # date for market and status variables
    unit: str
    cache: dict = field(default_factory=dict)


def _series(ctx: RowContext, metric: str) -> dict[str, dict]:
    from .intelligence import financial_series
    key = ("fin", metric, ctx.cutoff)
    if key not in ctx.cache:
        ctx.cache[key] = {p["period"]: p for p in financial_series(ctx.code, metric, as_of=ctx.cutoff)}
    return ctx.cache[key]


def _period_for(ctx: RowContext, series: dict, annual: bool) -> str | None:
    """Fiscal alignment: the row's period. PIT: the latest period published by the cut-off."""
    if ctx.period:
        return ctx.period
    pts = [p for p in series.values() if (p.get("published") or "") <= ctx.cutoff
           and (not annual or p["period"].endswith("12-31"))]
    return max(pts, key=lambda p: p["period"])["period"] if pts else None


def _fin(metric):
    def get(ctx):
        from .derived import is_flow
        s = _series(ctx, metric)
        annual = ctx.unit == "year"
        if ctx.unit == "quarter" and is_flow(metric):
            from .derived import quarterly_series
            key = ("q", metric, ctx.cutoff)
            if key not in ctx.cache:
                ctx.cache[key] = {q["period"]: q for q in quarterly_series(ctx.code, metric, as_of=ctx.cutoff)}
            qs = ctx.cache[key]
            p = _period_for(ctx, qs, False)
            q = qs.get(p) if p else None
            return (q["value"], q["published"], q["confidence_class"], None) if q else (None, None, None, None)
        p = _period_for(ctx, s, annual)
        x = s.get(p) if p else None
        return (x["value"], x["published"], x["confidence_class"], x.get("review")) if x else (None, None, None, None)
    return get


def _ttm(metric):
    def get(ctx):
        from .derived import ttm_series
        key = ("ttm", metric, ctx.cutoff)
        if key not in ctx.cache:
            ctx.cache[key] = {p["period"]: p for p in ttm_series(ctx.code, metric, as_of=ctx.cutoff)}
        s = ctx.cache[key]
        p = ctx.period if ctx.period else _period_for(ctx, s, False)
        x = s.get(p) if p else None
        return (x["value"], x["published"], x["confidence_class"], None) if x else (None, None, None, None)
    return get


def _ratio(num_get, den_get, minus_one=False, invert=False):
    def get(ctx):
        a, pa, ca, _ = num_get(ctx)
        b, pb, cb, _ = den_get(ctx)
        if a is None or b in (None, 0):
            return None, None, None, None
        v = a / b
        if invert:
            v = 1 - v
        if minus_one:
            v -= 1
        order = {"HIGH": 3, "MEDIUM": 2, "LOW": 1, "UNVALIDATED": 0}
        cls = min((ca or "UNVALIDATED", cb or "UNVALIDATED"), key=lambda c: order.get(c, 0))
        return v, max(pa or "", pb or "") or None, cls, None
    return get


def _prior_year(getter):
    """Same variable for the fiscal period one year earlier."""
    def get(ctx):
        if not ctx.period:
            return None, None, None, None
        p = f"{int(ctx.period[:4]) - 1}{ctx.period[4:]}"
        sub = RowContext(ctx.code, p, ctx.cutoff, ctx.measure_date, ctx.unit, ctx.cache)
        return getter(sub)
    return get


def _first(*getters):
    def get(ctx):
        for g in getters:
            r = g(ctx)
            if r[0] is not None:
                return r
        return None, None, None, None
    return get


# --- variable catalogue ----------------------------------------------------------------

def _register_financials():
    from .financials import METRICS
    from .cas import CHART
    names = dict((k, v["cn"]) for k, v in METRICS.items())
    for code, spec in CHART.items():
        names.setdefault(code, spec["labels"][0])
    for m, cn in names.items():
        unit = "PERSON" if m == "employees" else ("CNY_PER_SHARE" if m.startswith("eps_") else "CNY")
        _var(m, f"{m} ({cn})", unit, "financial", f"{cn}, consolidated, as reported",
             "reported value (single quarter for flow items in quarterly panels)",
             "financial_facts (XBRL > CSV import > statement table > PDF text); manual corrections applied",
             getter=_fin(m))
    for m in ("revenue", "net_profit", "net_profit_parent", "operating_profit", "operating_cash_flow"):
        _var(f"ttm_{m}", f"TTM {m}", "CNY", "derived", f"trailing twelve months of {m}",
             "YTD(q) + FY(y−1) − YTD(y−1, q)", "financial_facts", getter=_ttm(m))
    _var("non_recurring_items", "non-recurring items", "CNY", "derived", "net profit to the parent minus the same "
         "excluding non-recurring items", "net_profit_parent − net_profit_parent_ex_nonrecurring", "financial_facts",
         getter=_ratio_diff("net_profit_parent", "net_profit_parent_ex_nonrecurring"))
    f = _fin
    eq = _first(f("equity_parent"), f("equity"))
    for name, label, num, den, kw, formula in (
            ("roa", "return on assets", f("net_profit"), f("total_assets"), {}, "net_profit / total_assets"),
            ("roe", "return on equity", f("net_profit_parent"), eq, {}, "net_profit_parent / equity attributable "
                                                                        "to the parent (total equity if absent)"),
            ("net_margin", "net margin", f("net_profit"), f("revenue"), {}, "net_profit / revenue"),
            ("gross_margin", "gross margin", f("cost_of_revenue"), f("revenue"), {"invert": True},
             "1 − cost_of_revenue / revenue"),
            ("leverage", "liabilities to assets", f("total_liabilities"), f("total_assets"), {},
             "total_liabilities / total_assets"),
            ("rd_intensity", "R&D intensity", f("rd_expense"), f("revenue"), {}, "rd_expense / revenue"),
            ("cfo_to_assets", "operating cash flow to assets", f("operating_cash_flow"), f("total_assets"), {},
             "operating_cash_flow / total_assets"),
            ("sales_growth", "revenue growth", f("revenue"), _prior_year(f("revenue")), {"minus_one": True},
             "revenue / revenue of the same period a year earlier − 1"),
            ("asset_growth", "asset growth", f("total_assets"), _prior_year(f("total_assets")), {"minus_one": True},
             "total_assets / total_assets a year earlier − 1")):
        _var(name, label, "RATIO", "ratio", label, formula, "financial_facts", getter=_ratio(num, den, **kw))


def _ratio_diff(a, b):
    def get(ctx):
        x, px, cx, _ = _fin(a)(ctx)
        y, py, cy, _ = _fin(b)(ctx)
        if x is None or y is None:
            return None, None, None, None
        return x - y, max(px or "", py or "") or None, cx if cx == cy else "MEDIUM", None
    return get


def _market(field_name):
    def get(ctx):
        from .valuation import Knowledge, valuation_from, _closes
        from .models import SessionLocal, Company, CapitalStructureObservation
        key = ("mkt", ctx.code)
        if key not in ctx.cache:
            s = SessionLocal()
            try:
                c = s.query(Company).filter_by(security_code=ctx.code).first()
                closes = _closes(s, c.id) if c else []
                caps = sorted((x.observation_date, x.total_shares, x.tradable_shares) for x in s.query(
                    CapitalStructureObservation).filter(CapitalStructureObservation.company_id == c.id,
                                                        CapitalStructureObservation.total_shares.isnot(None))) if c else []
            finally:
                s.close()
            ctx.cache[key] = (closes, caps, Knowledge(ctx.code) if closes else None)
        closes, caps, know = ctx.cache[key]
        d = min(ctx.measure_date, ctx.cutoff)
        cl = [x for x in closes if x[0] <= d]
        if not cl:
            return None, None, None, None
        day, close = cl[-1]
        if (date.fromisoformat(d) - date.fromisoformat(day)).days > 31:
            return None, None, None, None      # no price in the month before: treat as missing
        cap = [x for x in caps if x[0] <= d]
        k = know.at(min(d, ctx.cutoff)) if know else {}
        val = valuation_from(close, cap[-1][1] if cap else None, cap[-1][2] if cap else None, k)
        val["close"] = close
        pub = max([day] + [(x.get("published") or "") for x in k.values()]) if field_name in ("pe", "pb", "ps", "ev") else day
        return val.get(field_name), pub, "MEDIUM", None
    return get


def _return_vol(kind):
    def get(ctx):
        from .valuation import adjusted_closes
        key = ("adj", ctx.code)
        if key not in ctx.cache:
            ctx.cache[key] = adjusted_closes(ctx.code, "backward")
        rows = ctx.cache[key]
        end = min(ctx.measure_date, ctx.cutoff)
        months = {"year": 12, "quarter": 3, "month": 1}.get(ctx.unit, 12)
        start = (date.fromisoformat(end) - timedelta(days=round(months * 30.44))).isoformat()
        win = [r for r in rows if start < r["date"] <= end]
        before = [r for r in rows if r["date"] <= start]
        if len(win) < 2:
            return None, None, None, None
        if kind == "return":
            base = before[-1]["adjusted"] if before else None
            if base is None:
                return None, None, None, None
            return win[-1]["adjusted"] / base - 1, win[-1]["date"], "MEDIUM", None
        rets = [b["adjusted"] / a["adjusted"] - 1 for a, b in zip(win, win[1:])]
        if len(rets) < 10:
            return None, None, None, None
        return statistics.stdev(rets) * math.sqrt(244), win[-1]["date"], "MEDIUM", None
    return get


def _gov(field_name):
    def get(ctx):
        from .management import governance
        key = ("gov", ctx.measure_date)
        if key not in ctx.cache:
            try:
                ctx.cache[key] = governance(ctx.code, min(ctx.measure_date, ctx.cutoff))
            except Exception:
                ctx.cache[key] = {}
        g = ctx.cache[key] or {}
        pub = _roster_published(ctx, g.get("base_roster_date"))
        if pub and pub > ctx.cutoff:
            return None, None, None, None    # the roster had not been published by the cut-off
        v = g.get(field_name)
        if isinstance(v, bool):
            v = int(v)
        return v, pub, "MEDIUM", None
    return get


def _roster_published(ctx, roster_date):
    """Publication date of the report that gave the roster (None for imports without one)."""
    if not roster_date:
        return None
    key = ("roster_pub", roster_date)
    if key not in ctx.cache:
        from .models import SessionLocal, Company, ManagementObservation, Disclosure
        s = SessionLocal()
        try:
            c = s.query(Company).filter_by(security_code=ctx.code).first()
            d = (s.query(Disclosure.announcement_date).join(ManagementObservation,
                                                            ManagementObservation.disclosure_id == Disclosure.id)
                 .filter(ManagementObservation.company_id == c.id,
                         ManagementObservation.observation_date == roster_date).first())
            ctx.cache[key] = d[0] if d else None
        finally:
            s.close()
    return ctx.cache[key]


def _hc(item, derived=False):
    def get(ctx):
        from .human_capital import human_capital
        key = ("hc", ctx.period, ctx.cutoff)
        if key not in ctx.cache:
            ctx.cache[key] = human_capital(ctx.code, ctx.period, ctx.cutoff) if ctx.period else \
                human_capital(ctx.code, None, ctx.cutoff)
        h = ctx.cache[key]
        v = (h.get("derived") if derived else h.get("values", {})).get(item) if h else None
        if isinstance(v, dict):
            v = v.get("value")
        return v, None, "MEDIUM", None
    return get


def _seg(kind):
    def get(ctx):
        from .segments import segments
        key = ("seg", ctx.period, ctx.cutoff)
        if key not in ctx.cache:
            ctx.cache[key] = segments(ctx.code, ctx.period, None, ctx.cutoff)
        dims = (ctx.cache[key] or {}).get("dimensions") or {}
        if kind == "product_hhi":
            return (dims.get("PRODUCT") or {}).get("hhi"), None, "MEDIUM", None
        if kind == "industry_hhi":
            return (dims.get("INDUSTRY") or {}).get("hhi"), None, "MEDIUM", None
        reg = ((dims.get("REGION") or {}).get("regional") or {})
        return reg.get("overseas_share"), None, "MEDIUM", None
    return get


def _top1(ctx):
    from .models import SessionLocal, Company, OwnershipObservation
    s = SessionLocal()
    try:
        c = s.query(Company).filter_by(security_code=ctx.code).first()
        rows = [o for o in s.query(OwnershipObservation).filter(OwnershipObservation.company_id == c.id,
                                                                OwnershipObservation.observation_date <= ctx.measure_date)]
    finally:
        s.close()
    if not rows:
        return None, None, None, None
    d = max(o.observation_date for o in rows)
    pct = [o.ownership_pct for o in rows if o.observation_date == d and o.ownership_pct is not None]
    return (max(pct) / 100 if pct and max(pct) > 1 else (max(pct) if pct else None)), d, "MEDIUM", None


def _index_member(index_code):
    def get(ctx):
        from .security_master import company_indices
        on = min(ctx.measure_date, ctx.cutoff)
        return int(any(m["index_code"] == index_code for m in company_indices(ctx.code, on))), None, "HIGH", None
    return get


def _status(field_name):
    def get(ctx):
        from .security_master import name_at
        from .models import SessionLocal, Company
        on = min(ctx.measure_date, ctx.cutoff)
        if field_name == "listed_years":
            s = SessionLocal()
            try:
                c = s.query(Company).filter_by(security_code=ctx.code).first()
                ld = c.listing_date if c else None
            finally:
                s.close()
            from .ownership import normalise_date
            ld = normalise_date(ld)
            if not ld or ld > on:
                return None, None, None, None
            return round((date.fromisoformat(on) - date.fromisoformat(ld)).days / 365.25, 2), None, "HIGH", None
        n = name_at(ctx.code, on)
        if field_name == "risk_warning":
            return (int(bool(n and n.get("risk_warning"))) if n else None), None, "MEDIUM", None
        return (n or {}).get(field_name), None, "HIGH", None
    return get


def _industry(scheme, level):
    def get(ctx):
        from .industry import classification_at
        from .models import SessionLocal, Company
        s = SessionLocal()
        try:
            c = s.query(Company).filter_by(security_code=ctx.code).first()
            cls = classification_at(s, c.id, scheme, min(ctx.measure_date, ctx.cutoff)) if c else None
            v = (getattr(cls, f"level{level}_code") or getattr(cls, f"level{level}_name")) if cls else None
            return v, cls.effective_date if cls else None, "HIGH", None
        finally:
            s.close()
    return get


def _regulatory(kind):
    def get(ctx):
        from .models import SessionLocal, Company, RegulatoryEvent
        end = min(ctx.measure_date, ctx.cutoff)
        start = (date.fromisoformat(end) - timedelta(days=365 if ctx.unit == "year" else 91)).isoformat()
        s = SessionLocal()
        try:
            c = s.query(Company).filter_by(security_code=ctx.code).first()
            evs = [e for e in s.query(RegulatoryEvent).filter(RegulatoryEvent.company_id == c.id)
                   if start < (e.event_date or e.announcement_date or "") <= end
                   and (e.announcement_date or e.event_date or "") <= ctx.cutoff]
        finally:
            s.close()
        if kind == "penalties":
            return float(sum(1 for e in evs if e.legal_classification in ("ADMINISTRATIVE_PENALTY",
                                                                         "SELF_REGULATORY_DISCIPLINARY"))), None, "MEDIUM", None
        return float(sum(e.fine_amount_company or 0 for e in evs)), None, "MEDIUM", None
    return get


def _register_others():
    for name, label, fld, unit in (("market_cap", "market capitalisation", "market_cap", "CNY"),
                                   ("float_market_cap", "free-float market capitalisation", "float_market_cap", "CNY"),
                                   ("pe", "price to earnings (TTM)", "pe", "RATIO_X"),
                                   ("pb", "price to book", "pb", "RATIO_X"), ("ps", "price to sales (TTM)", "ps", "RATIO_X"),
                                   ("ev", "enterprise value", "ev", "CNY"), ("close", "closing price", "close", "CNY")):
        _var(name, label, unit, "market", label,
             {"pe": "market_cap / TTM net_profit_parent", "pb": "market_cap / equity attributable to the parent",
              "ps": "market_cap / TTM revenue", "ev": "market_cap + interest-bearing debt − cash",
              "market_cap": "close × total shares", "float_market_cap": "close × tradable shares",
              "close": "unadjusted close"}[name],
             "market_bars, capital_structure_observations, financial_facts",
             "close on the last trading day on or before the measurement date (missing if none in the month "
             "before); financials published on or before the cut-off", getter=_market(fld))
    _var("ret", "stock return over the period", "RATIO", "market", "buy-and-hold return over the row's period",
         "adjusted close(end) / adjusted close(start) − 1, own adjustment factors", "market_bars, adjustment_factors",
         getter=_return_vol("return"))
    _var("volatility", "return volatility (annualised)", "RATIO", "market", "standard deviation of daily returns "
         "over the period × √244", "", "market_bars, adjustment_factors", getter=_return_vol("vol"))
    for name, fld, label in (("board_size", "board_size", "board size"),
                             ("independence_ratio", "independence_ratio", "share of independent directors"),
                             ("female_directors", "female_directors", "number of female directors"),
                             ("ceo_duality", "ceo_duality", "chair is also general manager (1/0)")):
        _var(name, label, "RATIO" if name == "independence_ratio" else "COUNT", "governance", label, "",
             "management_observations, management_events",
             "roster at the measurement date, used only once the report that gave it was published",
             getter=_gov(fld))
    for name, item, derived, label in (("employees_total", "employees_total", False, "employees"),
                                       ("rd_staff", "rd_staff", False, "R&D staff"),
                                       ("rd_staff_share", "rd_staff_share", True, "R&D staff share"),
                                       ("postgraduate_share", "postgraduate_share", True, "postgraduate share")):
        _var(name, label, "PERSON" if not derived else "RATIO", "human_capital", label, "",
             "human_capital_observations", getter=_hc(item, derived))
    _var("product_hhi", "product revenue concentration (HHI)", "RATIO", "segments", "sum of squared product shares",
         "Σ share²", "segment_observations", getter=_seg("product_hhi"))
    _var("industry_hhi", "industry revenue concentration (HHI)", "RATIO", "segments", "sum of squared industry shares",
         "Σ share²", "segment_observations", getter=_seg("industry_hhi"))
    _var("overseas_share", "overseas revenue share", "RATIO", "segments", "revenue outside the Mainland / total",
         "", "segment_observations", getter=_seg("overseas"))
    _var("top1_pct", "largest shareholder's stake", "RATIO", "ownership", "ownership share of the largest holder",
         "", "ownership_observations", "latest observation on or before the measurement date", getter=_top1)
    for code, nm in (("000300", "csi300"), ("000905", "csi500"), ("000010", "sse180"), ("000688", "star50")):
        _var(f"in_{nm}", f"constituent of {nm.upper()}", "DUMMY", "index", f"index {code} member (1/0)", "",
             "index_constituents", "membership on the measurement date", getter=_index_member(code))
    _var("listed_years", "years since listing", "YEARS", "listing", "years from listing to the measurement date", "",
         "companies", getter=_status("listed_years"))
    _var("risk_warning", "under ST or *ST (1/0)", "DUMMY", "listing", "risk warning in force", "", "security_history",
         getter=_status("risk_warning"))
    _var("board", "listing board", "TEXT", "listing", "board on the measurement date", "", "security_history",
         getter=_status("board"))
    _var("csrc_section", "CSRC 2012 section", "TEXT", "industry", "CSRC industry section (letter)", "",
         "industry_classifications", getter=_industry("CSRC_2012", 1))
    _var("sw_level1", "Shenwan 2021 level 1", "TEXT", "industry", "Shenwan level-1 industry", "",
         "industry_classifications", getter=_industry("SW_2021", 1))
    _var("penalties", "administrative and disciplinary penalties", "COUNT", "regulatory",
         "penalties dated in the 12 months (3 for quarters) to the measurement date", "", "regulatory_events",
         getter=_regulatory("penalties"))
    _var("fines_company", "fines on the company", "CNY", "regulatory", "fines on the company in the same window", "",
         "regulatory_events", getter=_regulatory("fines"))


def _control(field_name):
    def get(ctx):
        from .control import control_at
        key = ("ctl", ctx.cutoff)
        if key not in ctx.cache:
            ctx.cache[key] = control_at(ctx.code, min(ctx.measure_date, ctx.cutoff) if ctx.cutoff != "9999-12-31"
                                        else ctx.measure_date)
        c = (ctx.cache[key] or {}).get("control") or {}
        if field_name == "soe":
            t = c.get("ownership_type")
            return (int(t in ("CENTRAL_SOE", "LOCAL_SOE")) if t and t != "UNKNOWN" else None), c.get("published"), "MEDIUM", None
        return c.get(field_name), c.get("published"), "MEDIUM", None
    return get


def _top10(kind):
    def get(ctx):
        from .models import SessionLocal, Company, OwnershipObservation, Disclosure
        s = SessionLocal()
        try:
            c = s.query(Company).filter_by(security_code=ctx.code).first()
            rows = [(o, s.get(Disclosure, o.disclosure_id).announcement_date if o.disclosure_id else o.observation_date)
                    for o in s.query(OwnershipObservation).filter(OwnershipObservation.company_id == c.id,
                                                                  OwnershipObservation.rank.isnot(None),
                                                                  OwnershipObservation.observation_date <= ctx.measure_date)]
        finally:
            s.close()
        rows = [(o, p) for o, p in rows if (p or "") <= ctx.cutoff]
        if not rows:
            return None, None, None, None
        d = max(o.observation_date for o, _ in rows)
        cur = [(o, p) for o, p in rows if o.observation_date == d]
        pub = max(p or "" for _, p in cur) or None
        if kind == "sum":
            return sum(o.ownership_pct or 0 for o, _ in cur) / 100, pub, "MEDIUM", None
        top = min(cur, key=lambda x: x[0].rank or 99)[0]
        if not top.shares:
            return None, pub, None, None
        return (top.pledged_shares or 0) / top.shares, pub, "MEDIUM", None
    return get


def _register_control():
    _var("ownership_type", "ownership type", "TEXT", "control", "CENTRAL_SOE, LOCAL_SOE, PRIVATE, FOREIGN, COLLECTIVE, "
         "NO_CONTROLLER or UNKNOWN, from the actual controller", "", "control_observations",
         "latest report published by the cut-off", getter=_control("ownership_type"))
    _var("soe", "state-owned (1/0)", "DUMMY", "control", "actual controller is a central or local state body", "",
         "control_observations", getter=_control("soe"))
    _var("top10_pct", "top-10 holders' combined stake", "RATIO", "ownership", "sum of the top-10 holders' stakes", "",
         "ownership_observations (top-10 tables)", getter=_top10("sum"))
    _var("top_holder_pledged", "largest holder's pledged share", "RATIO", "ownership",
         "pledged shares of the largest holder / its shares", "", "ownership_observations", getter=_top10("pledge"))


_REGISTERED = False


def _ensure():
    global _REGISTERED
    if not _REGISTERED:
        _register_financials()
        _register_others()
        _register_control()
        _REGISTERED = True


def variables() -> dict[str, Variable]:
    _ensure()
    return VARIABLES


DEFAULT_VARIABLES = ["revenue", "net_profit_parent", "total_assets", "equity", "roa", "roe", "leverage",
                     "sales_growth", "market_cap", "pb", "ret", "board_size", "independence_ratio", "in_csi300",
                     "listed_years", "csrc_section"]
FINANCIAL_SECTIONS = {"J"}            # CSRC 2012 section J: finance
FINANCIAL_SW = {"银行", "非银金融"}


# --- building ---------------------------------------------------------------------------

def _rows_spec(unit, start, end, align, pit_day, as_of):
    """(period_end or None, measure date, cut-off) per row."""
    out = []
    y0, y1 = int(start[:4]), int(end[:4])
    if unit == "year" and align == "fiscal":
        for y in range(y0, y1 + 1):
            out.append((f"{y}-12-31", f"{y}-12-31", as_of or "9999-12-31"))
    elif unit == "quarter" and align == "fiscal":
        for y in range(y0, y1 + 1):
            for md in ("03-31", "06-30", "09-30", "12-31"):
                p = f"{y}-{md}"
                if start <= p <= end:
                    out.append((p, p, as_of or "9999-12-31"))
    elif unit == "year":
        for y in range(y0, y1 + 1):
            d = f"{y}-{pit_day}"
            out.append((None, d, d))
    else:  # month ends (pit) or quarter ends (pit)
        months = range(1, 13) if unit == "month" else (3, 6, 9, 12)
        for y in range(y0, y1 + 1):
            for m in months:
                nxt = date(y + (m == 12), m % 12 + 1, 1)
                d = (nxt - timedelta(days=1)).isoformat()
                if start <= d <= end:
                    out.append((None, d, d))
    if as_of:
        out = [(p, md, min(c, as_of)) for p, md, c in out if (p or md) <= as_of]
    return out


def _winsorise(rows, var, pct, by_period=True):
    groups = defaultdict(list)
    for r in rows:
        if isinstance(r.get(var), (int, float)) and not isinstance(r.get(var), bool):
            groups[r["period"] if by_period else 0].append(r)
    for rs in groups.values():
        vals = sorted(r[var] for r in rs)
        if len(vals) < 5:
            continue
        lo = vals[int(math.floor(pct / 100 * (len(vals) - 1)))]
        hi = vals[int(math.ceil((1 - pct / 100) * (len(vals) - 1)))]
        for r in rs:
            r[var] = min(max(r[var], lo), hi)


def build_panel(variables_: list[str] | None = None, unit: str = "year", start: str = "2015-01-01",
                end: str | None = None, align: str = "fiscal", pit_day: str = "04-30", lag_days: int = 0,
                as_of: str | None = None, codes: list[str] | None = None, index_code: str | None = None,
                boards: list[str] | None = None, exclude_financials: bool = False, min_class: str | None = None,
                reviewed_only: bool = False, winsor: float | None = None, lags: dict[str, int] | None = None,
                with_dates: bool = False, universe_basis: str = "auto") -> dict:
    """Build a panel in memory; see :func:`write_panel` for files.

    ``universe_basis`` (v2.0.3, finding 4) decides which companies a row date
    covers. ``listing``: only companies whose listing record covers the date.
    ``auto`` (default): as ``listing``, and for yearly rows also companies
    whose listing record is incomplete (no listing date, or delisted on an
    unknown date) but who published a periodic report for that year;
    ``report-evidence``: yearly rows from report evidence alone. Every row
    says which in ``universe_basis`` (LISTING_RECORD or REPORT_EVIDENCE)."""
    _ensure()
    from .security_master import universe_at, index_members
    from .models import SessionLocal, Company
    end = end or date.today().isoformat()
    names = variables_ or DEFAULT_VARIABLES
    unknown = [n for n in names if n not in VARIABLES]
    if unknown:
        raise ValueError(f"unknown variable(s): {', '.join(unknown)} (see 'panel-variables')")
    if unit not in ("year", "quarter", "month"):
        raise ValueError("unit must be year, quarter or month")
    if unit == "month":
        align = "pit"
    universe_basis = (universe_basis or "auto").lower().replace("_", "-")
    if universe_basis not in ("auto", "listing", "report-evidence"):
        raise ValueError("universe_basis must be auto, listing or report-evidence")
    if universe_basis == "report-evidence" and unit != "year":
        raise ValueError("report evidence covers whole years only: use unit 'year', or universe basis 'listing'")
    evidence = _report_evidence() if unit == "year" and universe_basis != "listing" else {}
    order = {"HIGH": 3, "MEDIUM": 2, "LOW": 1, "UNVALIDATED": 0}
    min_rank = order.get((min_class or "UNVALIDATED").upper(), 0)
    spec = _rows_spec(unit, start, end, align, pit_day, as_of)
    s = SessionLocal()
    try:
        companies = {c.security_code: {"name": c.short_name_cn, "board": c.board} for c in s.query(Company)}
    finally:
        s.close()
    all_codes = sorted(companies)
    rows, dropped, max_pub = [], defaultdict(int), ""
    contexts: dict[str, dict] = {}
    for period, measure, cutoff in spec:
        if lag_days and align == "pit":
            cutoff = (date.fromisoformat(cutoff) - timedelta(days=lag_days)).isoformat()
        urep: dict = {}
        listed = {r["current_code"]: dict(r, universe_basis="LISTING_RECORD")
                  for r in universe_at(measure, report=urep)}
        if universe_basis == "report-evidence":
            listed = {}
        if evidence:
            year = int(measure[:4])
            pool = companies if universe_basis == "report-evidence" else urep.get("excluded_codes", [])
            for code in pool:
                pub = _evidence_for(evidence, code, year, align, cutoff)
                if pub and code not in listed:
                    listed[code] = {"current_code": code, "name": companies[code]["name"],
                                    "board": companies[code]["board"], "universe_basis": "REPORT_EVIDENCE"}
                    dropped["included_by_report_evidence"] += 1
        for k in ("excluded_no_listing_date", "excluded_delisting_date_unknown"):
            if urep.get(k):                                     # v2.0.2: reported, not silent
                dropped[k] = max(dropped.get(k, 0), urep[k])
        members = {m["code"] for m in index_members(index_code, measure)} if index_code else None
        for code in (codes or all_codes):
            u = listed.get(code)
            if u is None:
                continue
            if boards and u["board"] not in boards:
                continue
            if members is not None and code not in members:
                continue
            cache = contexts.setdefault(code, {})
            ctx = RowContext(code, period, cutoff, measure, unit, cache)
            if exclude_financials:
                sec = _industry("CSRC_2012", 1)(ctx)[0]
                sw = _industry("SW_2021", 1)(ctx)[0]
                if (sec and str(sec)[:1] in FINANCIAL_SECTIONS) or (sw in FINANCIAL_SW):
                    dropped["financial_sector"] += 1
                    continue
            row = {"code": code, "name": u["name"], "period": period or measure, "measure_date": measure,
                   "cutoff": "" if cutoff == "9999-12-31" else cutoff, "universe_basis": u["universe_basis"]}
            for n in names:
                try:
                    v, pub, cls, review = VARIABLES[n].getter(ctx)
                except Exception:
                    v, pub, cls, review = None, None, None, None
                if v is not None and VARIABLES[n].group in ("financial", "derived", "ratio"):
                    if order.get(cls or "UNVALIDATED", 0) < min_rank:
                        v = None
                        dropped[f"{n}: below {min_class}"] += 1
                    elif reviewed_only and review not in ("ACCEPTED", "CORRECTED"):
                        v = None
                        dropped[f"{n}: not reviewed"] += 1
                if v is not None and pub and pub > cutoff:   # leakage guard (should never trigger)
                    raise AssertionError(f"{code} {n}: published {pub} after cut-off {cutoff}")
                if v is not None and pub:
                    max_pub = max(max_pub, pub)
                row[n] = v
                if with_dates:
                    row[f"{n}__published"] = pub
            rows.append(row)
    rows.sort(key=lambda r: (r["code"], r["period"]))
    for var, k in (lags or {}).items():
        for step in range(1, abs(k) + 1):
            col = f"{var}_{'lag' if k > 0 else 'lead'}{step}"
            by_code = defaultdict(list)
            for r in rows:
                by_code[r["code"]].append(r)
            for rs in by_code.values():
                for i, r in enumerate(rs):
                    j = i - step if k > 0 else i + step
                    r[col] = rs[j].get(var) if 0 <= j < len(rs) else None
    if winsor:
        for n in names:
            if VARIABLES[n].unit not in ("TEXT", "DUMMY"):
                _winsorise(rows, n, winsor)
    params = {"variables": names, "unit": unit, "start": start, "end": end, "align": align, "pit_day": pit_day,
              "lag_days": lag_days, "as_of": as_of, "codes": codes, "index": index_code, "boards": boards,
              "exclude_financials": exclude_financials, "min_class": min_class, "reviewed_only": reviewed_only,
              "winsor": winsor, "lags": lags, "universe_basis": universe_basis}
    return {"rows": rows, "params": params, "max_published": max_pub or None, "dropped": dict(dropped),
            "companies": len(companies), "periods": len(spec)}


_YEAR_RE = None


def _report_evidence() -> dict[str, dict[int, str]]:
    """code -> {fiscal year: earliest publication date} from periodic reports
    in the catalogue (annual, interim and quarterly reports, summaries
    included). Publishing a report for a year shows the company was listed
    in that year."""
    import re
    from .models import SessionLocal, Company, Disclosure
    global _YEAR_RE
    _YEAR_RE = _YEAR_RE or re.compile(r"((?:19|20)\d{2})\s*年")
    s = SessionLocal()
    out: dict[str, dict[int, str]] = defaultdict(dict)
    try:
        codes = {c.id: c.security_code for c in s.query(Company)}
        q = s.query(Disclosure.company_id, Disclosure.title_cn, Disclosure.announcement_date).filter(
            Disclosure.kind.like("annual_report%") | Disclosure.kind.like("interim_report%")
            | Disclosure.kind.like("quarterly_report%"))
        for cid, title, pub in q:
            m = _YEAR_RE.search(title or "")
            code = codes.get(cid)
            if not m or not code or not pub:
                continue
            y = int(m.group(1))
            if y not in out[code] or pub < out[code][y]:
                out[code][y] = pub
    finally:
        s.close()
    return out


def _evidence_for(evidence, code, year, align, cutoff) -> str | None:
    """Publication date of a report showing ``code`` was listed in ``year``
    (and, for point-in-time rows, published by the cut-off), else None."""
    e = evidence.get(code) or {}
    if align == "fiscal":
        return e.get(year)
    for y in (year, year - 1):              # pit: a report for this year, or last year's published this year
        pub = e.get(y)
        if pub and pub <= cutoff and (y == year or pub[:4] == str(year)):
            return pub
    return None


def empty_reason(result: dict) -> str:
    """Why a panel has no rows, and what to do (finding 4)."""
    d, p = result.get("dropped") or {}, result.get("params") or {}
    if not result.get("companies"):
        return ("the company list is empty. Run 'Update the company list' (ashare-cli update-universe) first.")
    if not result.get("periods"):
        return (f"no row dates between {p.get('start')} and {p.get('end')} for unit '{p.get('unit')}'"
                + (f" and as-of {p['as_of']}" if p.get("as_of") else "") + ". Check the start, end and as-of dates.")
    missing = d.get("excluded_no_listing_date", 0) + d.get("excluded_delisting_date_unknown", 0)
    if missing and missing >= result["companies"] * 0.5:
        msg = (f"{d.get('excluded_no_listing_date', 0):,} companies have no listing date (and "
               f"{d.get('excluded_delisting_date_unknown', 0):,} were delisted on an unknown date), so no company "
               "is known to have been listed on the row dates. Listing dates come from the public quote list "
               "when the company list is updated; if that failed, run 'Diagnose the quote list' "
               "(ashare-cli diagnose-quote-list), then 'Update the company list' again.")
        if p.get("unit") == "year" and p.get("universe_basis") != "listing":
            msg += (" For yearly panels the report-evidence fallback found no periodic reports for these years "
                    "either: catalogue the reports first (catalogue-disclosures --kind reports).")
        elif p.get("unit") == "year":
            msg += " For yearly panels, '--universe-basis auto' counts companies that published a report that year."
        else:
            msg += " Alternatively build a yearly panel, which can use report evidence (--unit year)."
        return msg
    filters = [k for k in ("codes", "index", "boards") if p.get(k)]
    if filters:
        return (f"no company passes the filters ({', '.join(filters)}) on the row dates; widen them, or check the "
                "codes and board names (universe-at shows who was listed on a date).")
    if d.get("financial_sector"):
        return "every company was dropped as financial (--exclude-financials)."
    return ("no company was listed on any row date (universe-at shows who was listed on a date). Check the dates "
            "and that the company list has listing dates (validate-universe).")


def coverage(rows: list[dict], names: list[str]) -> dict[str, dict]:
    out = {}
    for n in names:
        by_year = defaultdict(lambda: [0, 0])
        for r in rows:
            y = str(r["period"])[:4]
            by_year[y][1] += 1
            if r.get(n) is not None:
                by_year[y][0] += 1
        out[n] = {y: round(a / b, 3) if b else None for y, (a, b) in sorted(by_year.items())}
    return out


def codebook(names: list[str], rows: list[dict] | None = None) -> list[dict]:
    _ensure()
    cov = coverage(rows, names) if rows is not None else {}
    out = []
    for n in names:
        v = VARIABLES[n]
        out.append({"name": n, "label": v.label, "unit": v.unit, "group": v.group, "definition": v.definition,
                    "formula": v.formula, "source": v.source, "point_in_time": v.pit_rule,
                    "confidence": v.confidence, "coverage": cov.get(n)})
    return out


def codebook_markdown(entries: list[dict], params: dict | None = None) -> str:
    lines = ["# Codebook", ""]
    if params:
        lines += ["Panel settings: " + ", ".join(f"{k} = {v}" for k, v in params.items() if v not in (None, [], {},
                                                                                                     False)), ""]
    lines += ["Identifiers: `code` (current security code), `name` (short name on the measurement date), "
              "`period` (fiscal period end or row date), `measure_date`, `cutoff` (latest publication date "
              "used), `universe_basis` (why the company is in the row: LISTING_RECORD, its listing record covers "
              "the date; REPORT_EVIDENCE, its listing record is incomplete but it published a periodic report for "
              "that year).", ""]
    for e in entries:
        lines += [f"## {e['name']}", "", f"*{e['label']}* ({e['unit']}; {e['group']})", "",
                  f"- Definition: {e['definition']}"]
        if e["formula"]:
            lines.append(f"- Formula: {e['formula']}")
        lines += [f"- Source: {e['source']}", f"- Point in time: {e['point_in_time']}",
                  f"- Confidence: {e['confidence']}"]
        if e.get("coverage"):
            lines.append("- Coverage (share non-missing by year): " +
                         ", ".join(f"{y}: {c:.0%}" for y, c in e["coverage"].items() if c is not None))
        lines.append("")
    return "\n".join(lines)


def codebook_html(md: str) -> str:
    import html
    out = ["<!doctype html><meta charset='utf-8'><title>Codebook</title><style>body{font:14px system-ui,sans-serif;"
           "max-width:56em;margin:2em auto;padding:0 1em}h2{margin-top:1.6em;font-size:1.1em}code{background:#f3f3f5;"
           "padding:0 3px}</style>"]
    for line in md.splitlines():
        t = html.escape(line)
        t = t.replace("`", "")
        if line.startswith("# "):
            out.append(f"<h1>{t[2:]}</h1>")
        elif line.startswith("## "):
            out.append(f"<h2>{t[3:]}</h2>")
        elif line.startswith("- "):
            out.append(f"<li>{t[2:]}</li>")
        elif line.startswith("*"):
            out.append(f"<p><em>{t.strip('*')}</em></p>")
        elif t:
            out.append(f"<p>{t}</p>")
    return "\n".join(out)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class EmptyPanel(ValueError):
    """A panel with no rows (v2.0.3: refused rather than written and reported as done)."""


def write_panel(result: dict, out_dir: str, name: str = "panel", formats: tuple[str, ...] = ("csv", "dta"),
                allow_empty: bool = False) -> dict:
    """Write the panel, a codebook, R helpers and a manifest. A panel with no
    rows raises :class:`EmptyPanel` with the reason, unless ``allow_empty``."""
    from .research import database_fingerprint
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    rows = result["rows"]
    names = result["params"]["variables"]
    cols = []
    for r in rows:
        for k in r:
            if k not in cols:
                cols.append(k)
    if not rows and not allow_empty:
        raise EmptyPanel(empty_reason(result))
    if not cols:
        cols = ["code", "name", "period", "measure_date", "cutoff", "universe_basis"] + names
    files = []
    if "csv" in formats:
        p = out / f"{name}.csv"
        with p.open("w", encoding="utf-8-sig", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=cols)
            w.writeheader()
            w.writerows(rows)
        files.append(p)
        # R: column types and a loader
        types = out / f"{name}_types.csv"
        with types.open("w", encoding="utf-8", newline="") as fh:
            w = csv.writer(fh)
            w.writerow(["column", "type", "label"])
            for c in cols:
                v = VARIABLES.get(c)
                kind = "character" if (v and v.unit == "TEXT") or c in ("code", "name", "period", "measure_date",
                                                                         "cutoff", "universe_basis") or c.endswith("__published") \
                    else "double"
                w.writerow([c, kind, v.label if v else c])
        files.append(types)
        loader = out / f"{name}_load.R"
        spec = ", ".join(f'`{c}` = "{("c" if c in ("code", "name", "period", "measure_date", "cutoff", "universe_basis") or c.endswith("__published") or (VARIABLES.get(c) and VARIABLES[c].unit == "TEXT") else "d")}"' for c in cols)
        loader.write_text(f'# Load the panel with readr, keeping codes as text\nlibrary(readr)\n'
                          f'{name} <- read_csv("{name}.csv", col_types = cols({spec}))\n', encoding="utf-8")
        files.append(loader)
    if "dta" in formats:
        from .stata import write_dta
        p = out / f"{name}.dta"
        write_dta(str(p), rows, cols, {c: VARIABLES[c].label[:80] for c in cols if c in VARIABLES},
                  f"A-share panel {result['params']['unit']} {result['params']['start'][:4]}-"
                  f"{(result['params']['end'] or '')[:4]}")
        files.append(p)
    if "parquet" in formats:
        try:
            import pyarrow as pa
            import pyarrow.parquet as pq
        except ImportError as exc:
            raise RuntimeError("Parquet output needs the optional pyarrow package") from exc
        table = pa.Table.from_pylist(rows) if rows else pa.table({c: [] for c in cols})
        p = out / f"{name}.parquet"
        pq.write_table(table, p)
        files.append(p)
    cb = codebook(names, rows)
    md = codebook_markdown(cb, result["params"])
    (out / f"{name}_codebook.md").write_text(md, encoding="utf-8")
    (out / f"{name}_codebook.html").write_text(codebook_html(md), encoding="utf-8")
    files += [out / f"{name}_codebook.md", out / f"{name}_codebook.html"]
    manifest = {"created_at": utcnow().isoformat(timespec="seconds") + "Z", "software": f"ashare {__version__}",
                "parameters": result["params"], "rows": len(rows), "columns": cols,
                "max_published_date": result["max_published"], "dropped": result["dropped"],
                "database_fingerprint": database_fingerprint(),
                "files": {p.name: _sha(p) for p in files}}
    (out / f"{name}_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"rows": len(rows), "columns": len(cols), "files": [str(p) for p in files] + [str(out / f"{name}_manifest.json")],
            "max_published_date": result["max_published"], "dropped": result["dropped"]}
