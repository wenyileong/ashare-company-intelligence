"""Derived financial measures (v1.7): single quarters, trailing twelve months,
non-recurring items.

A-share interim and quarterly reports state flow items year to date
(Q1, H1, nine months, full year). Single quarters are differences of year-to-
date values, and TTM at quarter q of year y is YTD(y, q) + FY(y-1) − YTD(y-1, q).
Balance-sheet items are point-in-time and are never summed.

Every derived value carries the latest publication date of its inputs, so it
is point-in-time: it could not have been computed before that date. Its
confidence class is the lowest of its inputs'.
"""
from __future__ import annotations

from .intelligence import financial_series

_ORDER = {"HIGH": 3, "MEDIUM": 2, "LOW": 1, "UNVALIDATED": 0}
_QEND = {"03-31": 1, "06-30": 2, "09-30": 3, "12-31": 4}


def is_flow(metric: str) -> bool:
    from .cas import CHART
    from .financials import STATEMENT_TYPES
    if metric in CHART:
        return CHART[metric]["statement"] in ("IS", "CF") and not metric.startswith("eps_")
    return STATEMENT_TYPES.get(metric) in ("INCOME_STATEMENT", "CASH_FLOW")


def _ytd(code, metric, as_of, vintage) -> dict[str, dict]:
    return {p["period"]: p for p in financial_series(code, metric, as_of=as_of, vintage=vintage)
            if p["period"][5:] in _QEND}


def _combine(points, value, label):
    pts = [p for p in points if p]
    return {"value": value, "published": max((p.get("published") or "") for p in pts) or None,
            "confidence_class": min((p.get("confidence_class") or "UNVALIDATED" for p in pts), key=lambda c: _ORDER.get(c, 0)),
            "inputs": [f"{p['period']}={p['value']}" for p in pts], "formula": label}


def quarterly_series(code: str, metric: str, as_of: str | None = None, vintage: str = "latest") -> list[dict]:
    """Single-quarter values (flow items) or quarter-end values (balance items)."""
    ytd = _ytd(code, metric, as_of, vintage)
    out = []
    flow = is_flow(metric)
    for period in sorted(ytd):
        y, q = period[:4], _QEND[period[5:]]
        cur = ytd[period]
        if not flow or q == 1:
            rec = _combine([cur], cur["value"], "reported" if not flow else "Q1 = YTD Q1")
        else:
            prev_end = {2: "03-31", 3: "06-30", 4: "09-30"}[q]
            prev = ytd.get(f"{y}-{prev_end}")
            if prev is None:
                continue  # cannot difference without the previous year-to-date value
            rec = _combine([cur, prev], cur["value"] - prev["value"], f"YTD {period} − YTD {y}-{prev_end}")
        rec.update(period=period, quarter=f"{y}Q{q}", metric=metric)
        out.append(rec)
    return out


def ttm_series(code: str, metric: str, as_of: str | None = None, vintage: str = "latest") -> list[dict]:
    """Trailing-twelve-month sums of a flow item at each quarter end."""
    if not is_flow(metric):
        raise ValueError(f"{metric} is a balance-sheet item; TTM applies to flow items only")
    ytd = _ytd(code, metric, as_of, vintage)
    out = []
    for period in sorted(ytd):
        y = int(period[:4])
        cur = ytd[period]
        if period.endswith("12-31"):
            rec = _combine([cur], cur["value"], "FY")
        else:
            fy_prev, same_prev = ytd.get(f"{y - 1}-12-31"), ytd.get(f"{y - 1}{period[4:]}")
            if not fy_prev or not same_prev:
                continue
            rec = _combine([cur, fy_prev, same_prev], cur["value"] + fy_prev["value"] - same_prev["value"],
                           f"YTD {period} + FY {y - 1} − YTD {y - 1}{period[4:]}")
        rec.update(period=period, metric=metric)
        out.append(rec)
    return out


def ttm_at(code: str, metric: str, on: str) -> dict | None:
    """The latest TTM value that was known on date ``on``."""
    pts = [p for p in ttm_series(code, metric, as_of=on) if p["published"] and p["published"] <= on]
    return max(pts, key=lambda p: (p["period"], p["published"])) if pts else None


def non_recurring_series(code: str, as_of: str | None = None) -> list[dict]:
    """Non-recurring items = net profit to the parent − the same excluding non-recurring items."""
    a = {p["period"]: p for p in financial_series(code, "net_profit_parent", as_of=as_of)}
    b = {p["period"]: p for p in financial_series(code, "net_profit_parent_ex_nonrecurring", as_of=as_of)}
    out = []
    for period in sorted(set(a) & set(b)):
        rec = _combine([a[period], b[period]], a[period]["value"] - b[period]["value"],
                       "net_profit_parent − net_profit_parent_ex_nonrecurring")
        rec.update(period=period, metric="non_recurring_items",
                   share_of_net_profit=(rec["value"] / a[period]["value"]) if a[period]["value"] else None)
        out.append(rec)
    return out
