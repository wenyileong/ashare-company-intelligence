"""Event studies (v1.7).

Abnormal returns around events under the market model, market-adjusted
returns or mean-adjusted returns.

Day 0 is the first trading day of the company on or after the event date.
The estimation window and event window are in trading days relative to day
0 (defaults: estimation −250 to −31, event −1 to +1). Returns are daily
simple returns of closes adjusted with the program's own factors (falling
back to unadjusted closes when no factors exist).

Benchmark: an equal-weighted average of all securities with prices on each
day ("ew"), or a CSV file of an index (columns date and close, or date and
return).

Statistics: per event CAR; across events the mean CAR, its cross-sectional
standard deviation, t = mean / (sd / √N) and the share of positive CARs;
per relative day the average abnormal return and the cumulative average with
a 95% band (± 1.96 × cross-sectional standard error).
"""
from __future__ import annotations

import csv
import math
import statistics
from bisect import bisect_left
from collections import defaultdict
from pathlib import Path

from .models import (SessionLocal, init_db, Company, CorporateAction, RegulatoryEvent, ManagementEvent,
                     ListingEvent, MarketBar)


def _returns(closes: list[tuple[str, float]]) -> list[tuple[str, float]]:
    return [(d1, c1 / c0 - 1) for (d0, c0), (d1, c1) in zip(closes, closes[1:]) if c0]


def company_returns(code: str) -> list[tuple[str, float]]:
    from .valuation import adjusted_closes
    rows = adjusted_closes(code, "backward")
    return _returns([(r["date"], r["adjusted"]) for r in rows])


def benchmark_returns(benchmark: str = "ew") -> dict[str, float]:
    if benchmark != "ew":
        rows = list(csv.DictReader(open(benchmark, encoding="utf-8-sig")))
        if rows and "return" in rows[0]:
            return {r["date"][:10]: float(r["return"]) for r in rows if r.get("return") not in (None, "")}
        closes = [(r["date"][:10], float(r["close"])) for r in rows if r.get("close") not in (None, "")]
        return dict(_returns(sorted(closes)))
    init_db()
    s = SessionLocal()
    try:
        codes = [c.security_code for c in s.query(Company).join(MarketBar, MarketBar.company_id == Company.id).distinct()]
    finally:
        s.close()
    acc = defaultdict(list)
    for code in codes:
        for d, r in company_returns(code):
            acc[d].append(r)
    return {d: sum(v) / len(v) for d, v in acc.items()}


def select_events(source: str, security_code: str | None = None, date_field: str | None = None) -> list[dict]:
    """``source`` is 'corporate_actions:CASH_DIVIDEND', 'regulatory:ADMINISTRATIVE_PENALTY',
    'management:RESIGNATION', 'listing:NAME_CHANGE' or a CSV path with columns code, date[, label]."""
    if ":" not in source or Path(source).exists():
        rows = list(csv.DictReader(open(source, encoding="utf-8-sig")))
        return [{"code": str(r["code"]).zfill(6), "date": r["date"][:10], "label": r.get("label") or ""} for r in rows]
    table, typ = source.split(":", 1)
    model, type_col, default_date = {
        "corporate_actions": (CorporateAction, "action_type", "announcement_date"),
        "regulatory": (RegulatoryEvent, "event_type", "announcement_date"),
        "management": (ManagementEvent, "event_type", "announcement_date"),
        "listing": (ListingEvent, "event_type", "event_date"),
    }[table]
    init_db()
    s = SessionLocal()
    try:
        q = s.query(model, Company.security_code).join(Company, model.company_id == Company.id).filter(
            getattr(model, type_col) == typ)
        if security_code:
            q = q.filter(Company.security_code == str(security_code).zfill(6))
        out, seen = [], set()
        for row, code in q.all():
            d = getattr(row, date_field or default_date, None) or getattr(row, "announcement_date", None)
            if not d or (code, d) in seen:
                continue
            seen.add((code, d))
            out.append({"code": code, "date": d[:10], "label": f"{typ} #{row.id}"})
        return sorted(out, key=lambda e: (e["date"], e["code"]))
    finally:
        s.close()


def event_study(events: list[dict], est_window: tuple[int, int] = (-250, -31), event_window: tuple[int, int] = (-1, 1),
                model: str = "market", benchmark: str = "ew", min_estimation: int = 60) -> dict:
    if model not in ("market", "adjusted", "mean"):
        raise ValueError("model must be market, adjusted or mean")
    bench = benchmark_returns(benchmark) if model != "mean" else {}
    cache: dict[str, list] = {}
    results, skipped = [], []
    rel_days = list(range(event_window[0], event_window[1] + 1))
    for ev in events:
        code = ev["code"]
        if code not in cache:
            cache[code] = company_returns(code)
        rets = cache[code]
        dates = [d for d, _ in rets]
        i0 = bisect_left(dates, ev["date"])
        if i0 >= len(dates):
            skipped.append({**ev, "reason": "no prices on or after the event date"})
            continue
        lo, hi = i0 + est_window[0], i0 + est_window[1]
        e_lo, e_hi = i0 + event_window[0], i0 + event_window[1]
        if lo < 0 or e_hi >= len(rets) or e_lo < 0:
            skipped.append({**ev, "reason": "windows run beyond the available prices"})
            continue
        est = [(d, r) for d, r in rets[lo:hi + 1] if model == "mean" or d in bench]
        if len(est) < min_estimation:
            skipped.append({**ev, "reason": f"only {len(est)} estimation days (minimum {min_estimation})"})
            continue
        alpha = beta = None
        if model == "market":
            xs, ys = [bench[d] for d, _ in est], [r for _, r in est]
            mx, my = statistics.fmean(xs), statistics.fmean(ys)
            sxx = sum((x - mx) ** 2 for x in xs)
            if sxx == 0:
                skipped.append({**ev, "reason": "benchmark has no variance in the estimation window"})
                continue
            beta = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sxx
            alpha = my - beta * mx
            resid = [y - alpha - beta * x for x, y in zip(xs, ys)]
        elif model == "adjusted":
            resid = [r - bench[d] for d, r in est]
        else:
            mu = statistics.fmean(r for _, r in est)
            resid = [r - mu for _, r in est]
        sigma = statistics.stdev(resid) if len(resid) > 2 else None
        ars = []
        ok = True
        for k, (d, r) in zip(rel_days, rets[e_lo:e_hi + 1]):
            if model != "mean" and d not in bench:
                ok = False
                break
            if model == "market":
                ar = r - (alpha + beta * bench[d])
            elif model == "adjusted":
                ar = r - bench[d]
            else:
                ar = r - mu
            ars.append((k, d, ar))
        if not ok:
            skipped.append({**ev, "reason": "benchmark missing in the event window"})
            continue
        car = sum(a for _, _, a in ars)
        results.append({**ev, "day0": rets[i0][0], "alpha": alpha, "beta": beta, "estimation_days": len(est),
                        "sigma": sigma, "car": car, "ar": {k: a for k, _, a in ars},
                        "car_t": (car / (sigma * math.sqrt(len(ars)))) if sigma else None})
    n = len(results)
    cars = [r["car"] for r in results]
    summary = {"events": len(events), "used": n, "skipped": len(skipped), "model": model, "benchmark": benchmark,
               "estimation_window": est_window, "event_window": event_window,
               "mean_car": statistics.fmean(cars) if cars else None,
               "sd_car": statistics.stdev(cars) if n > 1 else None,
               "t": (statistics.fmean(cars) / (statistics.stdev(cars) / math.sqrt(n))) if n > 1 and statistics.stdev(cars) else None,
               "positive_share": sum(1 for c in cars if c > 0) / n if n else None}
    caar, cum = [], [0.0] * n
    for k in rel_days:
        day = [r["ar"][k] for r in results]
        for j in range(n):
            cum[j] += day[j]
        mean_cum = statistics.fmean(cum) if n else None
        se = statistics.stdev(cum) / math.sqrt(n) if n > 1 else None
        caar.append({"day": k, "aar": statistics.fmean(day) if n else None, "caar": mean_cum,
                     "low": mean_cum - 1.96 * se if se is not None else None,
                     "high": mean_cum + 1.96 * se if se is not None else None})
    return {"summary": summary, "events": results, "skipped": skipped, "caar": caar}


def caar_chart(result: dict, title: str = "Cumulative average abnormal return"):
    from .charts.spec import ChartSpec, Series, Point
    pts = [Point(str(r["day"]), r["caar"], {"aar": r["aar"], "low": r["low"], "high": r["high"]})
           for r in result["caar"]]
    band = [(r["low"], r["high"]) if r["low"] is not None else None for r in result["caar"]]
    s = result["summary"]
    sub = (f"N = {s['used']}; mean CAR {s['mean_car']:.2%}" if s["mean_car"] is not None else "No events") + \
        (f"; t = {s['t']:.2f}" if s.get("t") is not None else "") + "; shaded: 95% band"
    return ChartSpec("line", title, [Series("CAAR", pts, band=band)], x_type="category", unit="RATIO",
                     subtitle=sub, x_label="trading days relative to the event",
                     caption=f"Model: {s['model']}; benchmark: {s['benchmark']}; estimation window "
                             f"{s['estimation_window']}")


def write_event_study(result: dict, out_dir: str, name: str = "event_study") -> list[str]:
    from .charts.svg import render_svg
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    ev = out / f"{name}_events.csv"
    days = [r["day"] for r in result["caar"]]
    with ev.open("w", encoding="utf-8-sig", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["code", "event_date", "day0", "label", "alpha", "beta", "estimation_days", "sigma", "car", "car_t"]
                   + [f"ar_{d}" for d in days])
        for r in result["events"]:
            w.writerow([r["code"], r["date"], r["day0"], r.get("label"), r["alpha"], r["beta"], r["estimation_days"],
                        r["sigma"], r["car"], r["car_t"]] + [r["ar"].get(d) for d in days])
    cs = out / f"{name}_caar.csv"
    with cs.open("w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["day", "aar", "caar", "low", "high"])
        w.writeheader()
        w.writerows(result["caar"])
    sk = out / f"{name}_skipped.csv"
    with sk.open("w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["code", "date", "label", "reason"])
        w.writeheader()
        for r in result["skipped"]:
            w.writerow({k: r.get(k) for k in ("code", "date", "label", "reason")})
    svg = out / f"{name}_caar.svg"
    svg.write_text(render_svg(caar_chart(result)), encoding="utf-8")
    return [str(ev), str(cs), str(sk), str(svg)]
