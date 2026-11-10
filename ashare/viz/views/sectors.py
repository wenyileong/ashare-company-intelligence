"""Sectors (v2.3.0, plan Part D): by CSRC section (or board) and year, as known on a date: the companies listed and
the share with figures; the median and interquartile range of net margin and revenue growth (descriptive proxies,
definitions ``nvf-0``); the share under state control; the share of late annual reports; and regulatory events per
company.
"""
from __future__ import annotations

import statistics
from collections import defaultdict
from datetime import date

from ..data import Context, ParamError, check_date
from ..registry import register
from ..series import series_snapshot
from ..view import View, Built
from . import _checks, _groups

MEASURES = {
    "with_figures": "share of listed companies with revenue read",
    "net_margin_median": "net margin (net profit attributable / revenue), median",
    "growth_median": "revenue growth on the year before, median",
    "state_controlled": "share with a state actual controller",
    "late_annual": "share of annual reports published late",
    "reg_events_per_company": "regulatory events per listed company",
}


def _q(values, p):
    v = sorted(values)
    if not v:
        return None
    k = (len(v) - 1) * p
    f, c = int(k), min(int(k) + 1, len(v) - 1)
    return v[f] + (v[c] - v[f]) * (k - f)


@register
class SectorsView(View):
    id = "sectors"
    family = "econometric"
    title = "Sectors"
    intro = ("By CSRC section and year: coverage, median net margin and revenue growth with their spread, state "
             "control, late annual reports and regulatory events.")
    evidence = "DOCUMENTED_FACT"
    params = [
        {"key": "start", "label": "From year", "kind": "year", "default": "2021", "flag": "--start", "hint": "",
         "required": False},
        {"key": "end", "label": "To year", "kind": "year", "default": str(date.today().year - 1), "flag": "--end",
         "hint": "", "required": False},
        {"key": "as_of", "label": "As published by", "kind": "date", "default": "", "flag": "--as-of",
         "hint": "Blank: today.", "required": False},
        {"key": "group_by", "label": "Groups", "kind": "choice:auto,board,csrc", "default": "auto",
         "flag": "--group-by", "hint": "", "required": False},
        {"key": "out", "label": "Folder", "kind": "folder", "default": "visualise/sectors", "flag": "--out",
         "hint": "", "required": False},
    ]
    requires = [_checks.periodic_figures(), _checks.industry(), _checks.control(), _checks.regulatory()]

    def build(self, params: dict) -> Built:
        from ...models import Company, FinancialFact, Disclosure, ControlObservation, RegulatoryEvent
        from ...timeliness import report_rows
        try:
            y0 = int(params.get("start") or 2021)
            y1 = int(params.get("end") or date.today().year - 1)
        except ValueError:
            raise ParamError("the years must be numbers such as 2021")
        if y0 > y1 or y1 - y0 > 30:
            raise ParamError("give a span of 1 to 30 years, the first before the last")
        years = list(range(y0, y1 + 1))
        with Context(check_date(params.get("as_of"), "As published by"), bool(params.get("include_licensed")),
                     params.get("key")) as ctx:
            s = ctx.s
            comps = {c.id: c for c in s.query(Company)}
            group, basis = _groups.groups(s, comps, ctx.as_of, params.get("group_by") or "auto")
            listed = {y: _groups.listed_on(s, comps, f"{y}-12-31") for y in years}
            pub = {d.id: d.announcement_date for d in s.query(Disclosure.id, Disclosure.announcement_date)}
            fin: dict = defaultdict(dict)                                  # (company, year) -> metric -> value
            for f in s.query(FinancialFact).filter(FinancialFact.metric.in_(("revenue", "net_profit_parent")),
                                                   FinancialFact.period_type == "FY"):
                if (pub.get(f.disclosure_id) or "9999") <= ctx.as_of and f.value is not None:
                    fin[(f.company_id, int(f.reporting_period[:4]))].setdefault(f.metric, f.value)
            state: dict = {}
            for o in s.query(ControlObservation):
                if o.ownership_type and ctx.known(ctx.published(o.disclosure_id), o.observation_date):
                    y = int((o.observation_date or "0000")[:4] or 0)
                    state[(o.company_id, y)] = o.ownership_type in ("CENTRAL_SOE", "LOCAL_SOE", "SOE")
            late: dict = {}
            for r in report_rows(s, None, ctx.as_of):
                if r["kind"] == "annual_report" and r["late"] is not None:
                    late[(r["company_id"], int(r["period"][:4]))] = r["late"]
            reg = defaultdict(int)
            for e in s.query(RegulatoryEvent):
                d = e.announcement_date or e.event_date
                if d and d <= ctx.as_of:
                    reg[(e.company_id, int(d[:4]))] += 1
            rows = []
            for y in years:
                by_g = defaultdict(list)
                for cid in listed[y]:
                    by_g[group.get(cid, "unknown")].append(cid)
                for gname, cids in sorted(by_g.items()):
                    margins, growth = [], []
                    for cid in cids:
                        cur, prev = fin.get((cid, y), {}), fin.get((cid, y - 1), {})
                        if cur.get("revenue") and cur.get("net_profit_parent") is not None and cur["revenue"] > 0:
                            margins.append(cur["net_profit_parent"] / cur["revenue"])
                        if cur.get("revenue") and prev.get("revenue") and prev["revenue"] > 0:
                            growth.append(cur["revenue"] / prev["revenue"] - 1)
                    st = [state[(c, y)] for c in cids if (c, y) in state]
                    lt = [late[(c, y)] for c in cids if (c, y) in late]
                    n = len(cids)
                    rows.append({
                        "group": gname, "year": y, "listed": n,
                        "with_figures": round(sum(1 for c in cids if fin.get((c, y), {}).get("revenue")) / n, 4),
                        "net_margin_median": _r(statistics.median(margins)) if margins else None,
                        "net_margin_q1": _r(_q(margins, .25)), "net_margin_q3": _r(_q(margins, .75)),
                        "growth_median": _r(statistics.median(growth)) if growth else None,
                        "growth_q1": _r(_q(growth, .25)), "growth_q3": _r(_q(growth, .75)),
                        "state_controlled": round(sum(st) / len(st), 4) if st else None,
                        "late_annual": round(sum(lt) / len(lt), 4) if lt else None,
                        "reg_events_per_company": round(sum(reg[(c, y)] for c in cids) / n, 4),
                        "n_margin": len(margins), "n_growth": len(growth)})
            cols = ["group", "year", "listed", "with_figures", "net_margin_median", "net_margin_q1", "net_margin_q3",
                    "growth_median", "growth_q1", "growth_q3", "state_controlled", "late_annual",
                    "reg_events_per_company", "n_margin", "n_growth"]
            tables = {"sectors": {"title": "By group and year", "columns": cols, "rows": rows}}
            for m in ("with_figures", "state_controlled", "late_annual"):
                tables[f"heat_{m}"] = {"title": MEASURES[m].capitalize(), "columns": ["group", "year", m],
                                       "rows": [{"group": r["group"], "year": str(r["year"]), m: r[m]} for r in rows],
                                       "chart": {"type": "heatmap", "row": "group", "col": "year", "value": m,
                                                 "row_label": "group"}}
            notes = [
                f"Groups: {'CSRC sections' if basis == 'csrc' else 'boards (import the CSRC classification for sections)'}; "
                "companies counted if listed at the year end.",
                "Net margin and revenue growth are descriptive proxies (definitions nvf-0), from annual figures "
                "published by the date; q1 and q3 are the quartiles, n_margin and n_growth the companies behind them.",
                "Late annual reports follow the rules in rules/disclosure_deadlines.json; state control, the "
                "controller's ownership type read from reports.",
            ]
            from ...timeliness import rules_note
            notes.append(rules_note())
            p = {"start": y0, "end": y1, "as_of": ctx.as_of, "group_basis": basis,
                 "title": f"Sectors {y0}–{y1}, as of {ctx.as_of}"}
            snap = series_snapshot(self.id, p, ctx.policy(), tables, [], notes, self.evidence,
                                   [{"label": "Groups", "value": f"{len({r['group'] for r in rows}):,}"}])
            return Built(snap, _figures(snap))


def _r(v):
    return None if v is None else round(v, 6)


def _figures(snap):
    from ...charts.spec import ChartSpec, Series, Point
    rows = snap["tables"]["sectors"]["rows"]
    spec = ChartSpec("heatmap", "Median net margin by group and year",
                     [Series("median", [Point(str(r["year"]), r["net_margin_median"], {"row": r["group"]})
                                        for r in rows])],
                     subtitle=f"As published by {snap['parameters']['as_of']}; descriptive proxy (nvf-0)",
                     caption="Net profit attributable over revenue; blank: no company with both.")
    spec.height = 60 + 26 * len({r["group"] for r in rows}) + 60
    return [("net_margin_by_group", spec)]
