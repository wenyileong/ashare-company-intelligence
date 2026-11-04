"""Data coverage (v2.2, plan section B5): what the data can and cannot support, as known on a date.

* by layer, group and year: the share of companies listed at the year end that have data in the layer;
* the confidence classes of the financial figures, by year;
* the panel's balance: companies listed at each year end, new listings, delistings, and how many have figures.

Groups are CSRC sections once the classification is imported, and boards until then. The figure a methods section
needs, and a guide to what to collect next.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date

from ..data import Context, ParamError, check_date
from ..registry import register
from ..series import series_snapshot
from ..view import View, Built
from . import _checks

LAYERS = ("fundamentals", "capability", "expectations", "valuation", "ownership", "control", "institutional")
LAYER_LABELS = {"fundamentals": "fundamentals (revenue or net profit)", "capability": "capability (R&D)",
                "expectations": "expectations (guidance)", "valuation": "valuation (a price in the year)",
                "ownership": "ownership (top-10 table)", "control": "control (controller read)",
                "institutional": "institutional (classification or regulatory event)"}


@register
class CoverageView(View):
    id = "coverage"
    family = "coverage"
    title = "Data coverage"
    intro = ("Which layers, groups and years have data, as known on a date: the share of listed companies with data "
             "in each layer, the confidence of the financial figures, and the panel's balance (listings, delistings, "
             "companies with figures).")
    evidence = "DOCUMENTED_FACT"
    params = [
        {"key": "start", "label": "From year", "kind": "year", "default": "2021", "flag": "--start", "hint": "",
         "required": False},
        {"key": "end", "label": "To year", "kind": "year", "default": str(date.today().year - 1), "flag": "--end",
         "hint": "", "required": False},
        {"key": "as_of", "label": "As published by", "kind": "date", "default": "", "flag": "--as-of",
         "hint": "Blank: today.", "required": False},
        {"key": "group_by", "label": "Groups", "kind": "choice:auto,board,csrc", "default": "auto",
         "flag": "--group-by", "hint": "auto: CSRC sections when classifications are imported, boards otherwise.",
         "required": False},
        {"key": "out", "label": "Folder", "kind": "folder", "default": "visualise/coverage", "flag": "--out",
         "hint": "", "required": False},
    ]
    requires = [_checks.periodic_figures(), _checks.industry()]

    def build(self, params: dict) -> Built:
        from ...models import (Company, FinancialFact, Disclosure, HumanCapitalObservation, ExpectationObservation,
                               MarketBar, OwnershipObservation, ControlObservation, IndustryClassification,
                               RegulatoryEvent, ListingEvent)
        from ...crossvalidation import confidence_class
        try:
            y0 = int(params.get("start") or 2021)
            y1 = int(params.get("end") or date.today().year - 1)
        except ValueError:
            raise ParamError("the years must be numbers such as 2021")
        if y0 > y1 or y1 - y0 > 30:
            raise ParamError("give a span of 1 to 30 years, the first before the last")
        years = list(range(y0, y1 + 1))
        group_by = params.get("group_by") or "auto"
        if group_by not in ("auto", "board", "csrc"):
            raise ParamError("groups must be auto, board or csrc")
        with Context(check_date(params.get("as_of"), "As published by"), bool(params.get("include_licensed")),
                     params.get("key")) as ctx:
            s = ctx.s
            comps = {c.id: c for c in s.query(Company)}
            # who is listed at each year end, as known on the date
            delisted = {}
            for e in s.query(ListingEvent).filter(ListingEvent.event_type == "DELISTING"):
                if (e.event_date or "9999") <= ctx.as_of:
                    delisted[e.company_id] = min(delisted.get(e.company_id, "9999"), e.event_date)
            listed = {y: {cid for cid, c in comps.items() if c.listing_date and c.listing_date <= f"{y}-12-31"
                          and delisted.get(cid, "9999") > f"{y}-12-31"} for y in years}
            # groups
            csrc = {}
            for r in s.query(IndustryClassification).filter(IndustryClassification.scheme == "CSRC_2012"):
                if (r.effective_date or "") <= ctx.as_of and r.level1_code:
                    if r.company_id not in csrc or (r.effective_date, r.id) > csrc[r.company_id][0]:
                        csrc[r.company_id] = ((r.effective_date, r.id), r.level1_code)
            use_csrc = group_by == "csrc" or (group_by == "auto" and len(csrc) >= 0.5 * max(len(comps), 1))
            group = {cid: (csrc[cid][1] if cid in csrc else "unclassified") if use_csrc else (c.board or c.exchange or
                                                                                           "unknown")
                     for cid, c in comps.items()}
            pub = {d.id: d.announcement_date for d in s.query(Disclosure.id, Disclosure.announcement_date)}
            have: dict[str, dict[int, set]] = {layer: defaultdict(set) for layer in LAYERS}

            def year_of(period):
                try:
                    return int(str(period)[:4])
                except (TypeError, ValueError):
                    return None
            conf = defaultdict(lambda: defaultdict(int))
            for f in s.query(FinancialFact.company_id, FinancialFact.reporting_period, FinancialFact.metric,
                             FinancialFact.disclosure_id, FinancialFact.confidence, FinancialFact.validation_status):
                if (pub.get(f.disclosure_id) or "9999") > ctx.as_of:
                    continue
                y = year_of(f.reporting_period)
                if y in listed:
                    if f.metric in ("revenue", "net_profit_parent"):
                        have["fundamentals"][y].add(f.company_id)
                        conf[y][confidence_class(f.confidence, f.validation_status)] += 1
                    if f.metric in ("rd_expense",):
                        have["capability"][y].add(f.company_id)
            for h in s.query(HumanCapitalObservation.company_id, HumanCapitalObservation.reporting_period,
                             HumanCapitalObservation.item, HumanCapitalObservation.disclosure_id):
                if h.item in ("rd_investment", "rd_staff") and (pub.get(h.disclosure_id) or "9999") <= ctx.as_of:
                    y = year_of(h.reporting_period)
                    if y in listed:
                        have["capability"][y].add(h.company_id)
            for e in s.query(ExpectationObservation.company_id, ExpectationObservation.reporting_period,
                             ExpectationObservation.published_date, ExpectationObservation.source_kind):
                if e.source_kind == "MANAGEMENT_GUIDANCE" and (e.published_date or "9999") <= ctx.as_of:
                    y = year_of(e.reporting_period)
                    if y in listed:
                        have["expectations"][y].add(e.company_id)
            for y in years:
                hi = min(f"{y}-12-31", ctx.as_of)
                for (cid,) in s.query(MarketBar.company_id).filter(MarketBar.trade_date >= f"{y}-01-01",
                                                                   MarketBar.trade_date <= hi).distinct():
                    have["valuation"][y].add(cid)
            for o in s.query(OwnershipObservation.company_id, OwnershipObservation.observation_date,
                             OwnershipObservation.disclosure_id).filter(OwnershipObservation.rank.isnot(None)):
                if (pub.get(o.disclosure_id) or o.observation_date or "9999") <= ctx.as_of:
                    y = year_of(o.observation_date)
                    if y in listed:
                        have["ownership"][y].add(o.company_id)
            for o in s.query(ControlObservation.company_id, ControlObservation.observation_date,
                             ControlObservation.disclosure_id):
                if (pub.get(o.disclosure_id) or o.observation_date or "9999") <= ctx.as_of:
                    y = year_of(o.observation_date)
                    if y in listed:
                        have["control"][y].add(o.company_id)
            for cid in csrc:
                for y in years:
                    if csrc[cid][0][0] <= f"{y}-12-31":
                        have["institutional"][y].add(cid)
            for e in s.query(RegulatoryEvent.company_id, RegulatoryEvent.announcement_date, RegulatoryEvent.event_date):
                when = e.announcement_date or e.event_date
                if when and when <= ctx.as_of and year_of(when) in listed:
                    have["institutional"][year_of(when)].add(e.company_id)

            rows = []
            groups = sorted({group[cid] for y in years for cid in listed[y]})
            for layer in LAYERS:
                for grp in groups:
                    for y in years:
                        base = {cid for cid in listed[y] if group[cid] == grp}
                        if not base:
                            continue
                        n = len(base & have[layer][y])
                        rows.append({"layer": layer, "group": grp, "year": y, "listed": len(base), "with_data": n,
                                     "share": round(n / len(base), 4), "row": f"{layer} · {grp}"})
            totals = []
            for layer in LAYERS:
                for y in years:
                    n = len(listed[y] & have[layer][y])
                    totals.append({"layer": LAYER_LABELS[layer], "year": y, "listed": len(listed[y]),
                                   "with_data": n, "share": round(n / len(listed[y]), 4) if listed[y] else None})
            conf_rows = [{"year": y, "class": k, "figures": conf[y].get(k, 0)}
                         for y in years for k in ("HIGH", "MEDIUM", "LOW", "UNVALIDATED")]
            balance = []
            for y in years:
                new = sum(1 for c in comps.values() if c.listing_date and c.listing_date[:4] == str(y))
                gone = sum(1 for cid, d in delisted.items() if d[:4] == str(y))
                balance.append({"year": y, "listed": len(listed[y]), "new_listings": new, "delistings": gone,
                                "with_figures": len(listed[y] & have["fundamentals"][y])})
            tables = {
                "coverage": {"title": "Share of listed companies with data, by layer, group and year",
                             "columns": ["layer", "group", "year", "listed", "with_data", "share", "row"],
                             "rows": rows, "chart": {"type": "heatmap", "row": "row", "col": "year",
                                                     "value": "share", "row_label": "layer · group"}},
                "coverage_total": {"title": "Share of listed companies with data, by layer and year (all groups)",
                                   "columns": ["layer", "year", "listed", "with_data", "share"], "rows": totals,
                                   "chart": {"type": "heatmap", "row": "layer", "col": "year", "value": "share",
                                             "row_label": "layer"}},
                "confidence": {"title": "Financial figures by confidence class and year",
                               "columns": ["year", "class", "figures"], "rows": conf_rows},
                "panel_balance": {"title": "The panel's balance: listed at the year end, listings, delistings, "
                                           "companies with figures",
                                  "columns": ["year", "listed", "new_listings", "delistings", "with_figures"],
                                  "rows": balance, "chart": {"type": "bars", "x": "year", "y": "with_figures",
                                                             "x_label": "year", "y_label": "companies with figures"}},
            }
            undated = sum(1 for c in comps.values() if not c.listing_date)
            notes = [
                "A company counts in a year if it was listed at the year end, as known on the date; companies "
                f"without a listing date are left out ({undated:,} now).",
                "Groups are " + ("CSRC sections (unclassified: no classification imported)." if use_csrc else
                                 "boards; import the CSRC classification to group by industry."),
                "Data are counted only if published by the date. A share is of companies, not of figures.",
            ]
            last = years[-1]
            summary = [{"label": "Listed at the end of " + str(last), "value": f"{len(listed[last]):,}"},
                       {"label": "With financial figures", "value": f"{len(listed[last] & have['fundamentals'][last]):,}"},
                       {"label": "Groups", "value": "CSRC sections" if use_csrc else "boards"}]
            p = {"start": y0, "end": y1, "as_of": ctx.as_of, "group_by": "csrc" if use_csrc else "board",
                 "title": f"Data coverage {y0}–{y1}, as of {ctx.as_of}"}
            snap = series_snapshot(self.id, p, ctx.policy(), tables, [], notes, self.evidence, summary)
            return Built(snap, _figures(snap))


def _figures(snap) -> list:
    from ...charts.spec import ChartSpec, Series, Point
    t = snap["tables"]["coverage_total"]["rows"]
    heat = ChartSpec("heatmap", "Share of listed companies with data, by layer and year",
                     [Series("share", [Point(str(r["year"]), r["share"], {"row": r["layer"]}) for r in t])],
                     subtitle=f"As published by {snap['parameters']['as_of']}; white: no company with data",
                     caption="Source: the program's database; data counted only if published by the date.")
    heat.height = 60 + 34 * len(LAYERS) + 60
    b = snap["tables"]["panel_balance"]["rows"]
    bars = ChartSpec("bar", "The panel's balance", [
        Series("listed at the year end", [Point(str(r["year"]), r["listed"]) for r in b]),
        Series("with financial figures", [Point(str(r["year"]), r["with_figures"]) for r in b])],
        y_label="companies", subtitle="Companies listed at each year end, and those with figures read",
        caption="New listings and delistings are in panel_balance.csv.")
    return [("coverage_heatmap", heat), ("panel_balance", bars)]
