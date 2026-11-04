"""Guidance against outcome (v2.2, plan section B5).

Each earnings forecast (业绩预告) or flash report (业绩快报) range, against the profit the company later reported in
its periodic report, as known on a date: how well management guidance tracks outcomes, and so how far it can stand in
for investors' expectations in the topology view.

An observed association, not evidence of cause. Only a periodic report's figure counts as the outcome (never a figure
read from the forecast or flash report itself), and only one published after the guidance.
"""
from __future__ import annotations

import statistics
from datetime import date

from ..data import Context, ParamError, check_date
from ..registry import register
from ..series import series_snapshot
from ..view import View, Built
from . import _checks

BINS = [round(-1 + 0.1 * i, 1) for i in range(21)]          # relative error, -100% to +100% in 10-point bins


@register
class GuidanceOutcomeView(View):
    id = "guidance_outcome"
    family = "econometric"
    title = "Guidance against outcome"
    intro = ("Each earnings forecast or flash report range against the profit later reported in the periodic report: "
             "how often the outcome falls within the range, and by how much it differs from the midpoint.")
    evidence = "OBSERVED_ASSOCIATION"
    params = [
        {"key": "codes", "label": "Companies", "kind": "text", "default": "", "flag": "--codes",
         "hint": "Comma-separated codes; blank for every company.", "required": False},
        {"key": "start", "label": "From year", "kind": "year", "default": "2021", "flag": "--start", "hint": "",
         "required": False},
        {"key": "end", "label": "To year", "kind": "year", "default": str(date.today().year), "flag": "--end",
         "hint": "", "required": False},
        {"key": "as_of", "label": "As published by", "kind": "date", "default": "", "flag": "--as-of",
         "hint": "Blank: today.", "required": False},
        {"key": "out", "label": "Folder", "kind": "folder", "default": "visualise/guidance_outcome", "flag": "--out",
         "hint": "", "required": False},
    ]
    requires = [_checks.guidance(), _checks.periodic_figures()]

    def build(self, params: dict) -> Built:
        from ...models import Company, ExpectationObservation, FinancialFact, Disclosure
        from ...disclosures import REPORT_KINDS
        try:
            y0 = int(params.get("start") or 2021)
            y1 = int(params.get("end") or date.today().year)
        except ValueError:
            raise ParamError("the years must be numbers such as 2021")
        if y0 > y1:
            raise ParamError("the first year is after the last")
        raw = params.get("codes") or ""
        codes = sorted({c.strip().zfill(6) for c in (raw if isinstance(raw, list) else str(raw).split(","))
                        if str(c).strip()})
        with Context(check_date(params.get("as_of"), "As published by"), bool(params.get("include_licensed")),
                     params.get("key")) as ctx:
            s = ctx.s
            comps = {c.id: c for c in s.query(Company)}
            ids = None
            if codes:
                ids = {cid for cid, c in comps.items() if c.security_code in codes}
                missing = sorted(set(codes) - {comps[i].security_code for i in ids})
                if missing:
                    raise ParamError(f"not in the company list: {', '.join(missing)}")
            guid = [e for e in s.query(ExpectationObservation).filter(
                ExpectationObservation.source_kind == "MANAGEMENT_GUIDANCE",
                ExpectationObservation.measure == "net_profit_parent")
                if (e.published_date or "9999") <= ctx.as_of and (ids is None or e.company_id in ids)
                and e.reporting_period and y0 <= int(e.reporting_period[:4]) <= y1
                and e.low is not None and e.high is not None]
            reports = {d.id: d for d in s.query(Disclosure).filter(Disclosure.kind.in_(REPORT_KINDS))}
            outcomes: dict[tuple, list] = {}
            for f in s.query(FinancialFact).filter(FinancialFact.metric == "net_profit_parent"):
                d = reports.get(f.disclosure_id)
                if d is None or (d.announcement_date or "9999") > ctx.as_of:
                    continue
                outcomes.setdefault((f.company_id, f.reporting_period), []).append((d.announcement_date, f))
            rows = []
            for e in sorted(guid, key=lambda e: (comps[e.company_id].security_code, e.reporting_period,
                                                 e.published_date or "", e.id)):
                later = [(p, f) for p, f in outcomes.get((e.company_id, e.reporting_period), [])
                         if p >= (e.published_date or "")]
                if not later:
                    continue
                p, f = min(later, key=lambda x: (x[0], x[1].id))         # the first report after the guidance
                lo, hi = sorted((e.low, e.high))
                mid = (lo + hi) / 2
                err = (f.value - mid) / abs(mid) if mid else None
                rows.append({"code": comps[e.company_id].security_code, "period": e.reporting_period,
                             "kind": e.document_kind or "FORECAST", "direction": e.direction,
                             "guidance_published": e.published_date, "low": lo, "high": hi, "midpoint": mid,
                             "actual": f.value, "actual_published": p,
                             "within_range": int(lo <= f.value <= hi), "relative_error": round(err, 6)
                             if err is not None else None, "guidance_disclosure_id": e.disclosure_id,
                             "guidance_page": e.source_page, "actual_disclosure_id": f.disclosure_id,
                             "actual_page": f.source_page, "actual_method": f.extraction_method,
                             "label": f"{comps[e.company_id].security_code} {e.reporting_period}"})
            errs = [r["relative_error"] for r in rows if r["relative_error"] is not None]
            hist = []
            for i in range(len(BINS) - 1):
                a, b = BINS[i], BINS[i + 1]
                n = sum(1 for x in errs if a <= x < b or (b == 1.0 and x == 1.0))
                hist.append({"bin": f"{a:+.0%} to {b:+.0%}", "from": a, "to": b, "pairs": n})
            outside = sum(1 for x in errs if x < -1 or x > 1)
            by_year = []
            for y in range(y0, y1 + 1):
                for kind in ("FORECAST", "FLASH"):
                    rs = [r for r in rows if r["period"][:4] == str(y) and r["kind"] == kind]
                    if rs:
                        by_year.append({"year": y, "kind": kind, "pairs": len(rs),
                                        "within_range": round(sum(r["within_range"] for r in rs) / len(rs), 4),
                                        "median_abs_error": round(statistics.median(
                                            abs(r["relative_error"]) for r in rs if r["relative_error"] is not None), 4)
                                        if any(r["relative_error"] is not None for r in rs) else None})
            cols = ["code", "period", "kind", "direction", "guidance_published", "low", "high", "midpoint", "actual",
                    "actual_published", "within_range", "relative_error", "guidance_disclosure_id", "guidance_page",
                    "actual_disclosure_id", "actual_page", "actual_method", "label"]
            tables = {
                "pairs": {"title": "Guidance ranges against the profit reported (net profit attributable, yuan)",
                          "columns": cols, "rows": rows,
                          "chart": {"type": "scatter", "x": "actual", "y": "midpoint", "low": "low", "high": "high",
                                    "tip": "label", "x_label": "reported net profit attributable (yuan)",
                                    "y_label": "guidance midpoint (yuan)", "range_label": "guidance range"}},
                "errors": {"title": "Relative error of the midpoint ((reported − midpoint) / |midpoint|)",
                           "columns": ["bin", "from", "to", "pairs"], "rows": hist,
                           "chart": {"type": "bars", "x": "bin", "y": "pairs", "x_label": "relative error",
                                     "y_label": "pairs"}},
                "by_year": {"title": "Share within the range and median absolute error, by year and kind",
                            "columns": ["year", "kind", "pairs", "within_range", "median_abs_error"],
                            "rows": by_year},
            }
            n_guid = len(guid)
            summary = [{"label": "Guidance with a later report", "value": f"{len(rows):,} of {n_guid:,}"},
                       {"label": "Within the range", "value": (f"{sum(r['within_range'] for r in rows) / len(rows):.0%}"
                                                              if rows else "–")},
                       {"label": "Median absolute error",
                        "value": f"{statistics.median(abs(x) for x in errs):.1%}" if errs else "–"}]
            notes = [
                "An observed association between documented values; not evidence of cause.",
                "The outcome is the net profit attributable in the first periodic report published after the "
                "guidance; figures read from the forecast or flash report itself are never used.",
                "Flash reports (业绩快报) are near-final figures, so they track outcomes far more closely than "
                "forecasts; the two kinds are kept apart.",
                f"Errors beyond ±100% are counted in the summary but not in the histogram ({outside:,}).",
                f"Guidance without a later report published by {ctx.as_of} is left out "
                f"({n_guid - len(rows):,}).",
            ]
            p = {"codes": codes, "start": y0, "end": y1, "as_of": ctx.as_of,
                 "title": f"Guidance against outcome {y0}–{y1}, as of {ctx.as_of}"}
            snap = series_snapshot(self.id, p, ctx.policy(), tables, [], notes, self.evidence, summary)
            return Built(snap, _figures(snap))


def _figures(snap) -> list:
    from ...charts.spec import ChartSpec, Series, Point
    rows = snap["tables"]["pairs"]["rows"]
    pts = [Point(r["actual"] / 1e8, r["midpoint"] / 1e8,
                 {"label": r["label"], "range": f"{r['low'] / 1e8:.2f} to {r['high'] / 1e8:.2f}"})
           for r in rows if r["actual"] is not None]
    scatter = ChartSpec("scatter", "Guidance midpoint against the profit reported", [Series("pairs", pts)],
                        x_type="number", x_label="reported net profit attributable (CNY 100m)",
                        y_label="guidance midpoint (CNY 100m)", fit=False,
                        subtitle=f"{len(pts):,} pairs; ranges in the CSV",
                        caption="Observed association; outcome from the first periodic report after the guidance.")
    hist_rows = snap["tables"]["errors"]["rows"]
    bars = ChartSpec("bar", "Relative error of the guidance midpoint",
                     [Series("pairs", [Point(r["bin"], r["pairs"]) for r in hist_rows])],
                     y_label="pairs", subtitle="(reported − midpoint) / |midpoint|, in 10-point bins",
                     caption="Errors beyond ±100% are left out of the bins and counted in the notes.")
    bars.width = 760
    return [("guidance_scatter", scatter), ("guidance_errors", bars)]
