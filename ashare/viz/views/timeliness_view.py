"""Disclosure timeliness (v2.3.0, plan Part D): the distribution of reporting delays by year and kind, the share of
reports published after their legal deadlines, and the late reports, as known on a date. The rules and their sources
are in ``rules/disclosure_deadlines.json``.
"""
from __future__ import annotations

import statistics
from collections import defaultdict
from datetime import date

from ..data import Context, ParamError, check_date
from ..registry import register
from ..series import series_snapshot
from ..view import View, Built
from . import _checks

KIND_LABEL = {"annual_report": "annual", "interim_report": "half-year", "quarterly_report": "quarterly"}


@register
class TimelinessView(View):
    id = "timeliness"
    family = "econometric"
    title = "Disclosure timeliness"
    intro = ("Days from the end of each period to its report, against the legal deadlines: the spread by year and "
             "kind, the share published late, and the late reports.")
    evidence = "DOCUMENTED_FACT"
    params = [
        {"key": "start", "label": "From year", "kind": "year", "default": "2021", "flag": "--start", "hint": "",
         "required": False},
        {"key": "end", "label": "To year", "kind": "year", "default": str(date.today().year - 1), "flag": "--end",
         "hint": "", "required": False},
        {"key": "as_of", "label": "As published by", "kind": "date", "default": "", "flag": "--as-of",
         "hint": "Blank: today.", "required": False},
        {"key": "out", "label": "Folder", "kind": "folder", "default": "visualise/timeliness", "flag": "--out",
         "hint": "", "required": False},
    ]
    requires = [_checks._req("reports", "periodic reports catalogued", "Disclosure", "Catalogue announcements",
                             filters=lambda m: (m.kind.in_(("annual_report", "interim_report", "quarterly_report")),))]

    def build(self, params: dict) -> Built:
        from ...timeliness import report_rows, rules, rules_note
        try:
            y0 = int(params.get("start") or 2021)
            y1 = int(params.get("end") or date.today().year - 1)
        except ValueError:
            raise ParamError("the years must be numbers such as 2021")
        if y0 > y1:
            raise ParamError("the first year is after the last")
        with Context(check_date(params.get("as_of"), "As published by"), bool(params.get("include_licensed")),
                     params.get("key")) as ctx:
            rows = [r for r in report_rows(ctx.s, None, ctx.as_of) if y0 <= int(r["period"][:4]) <= y1]
            by = defaultdict(list)
            for r in rows:
                by[(int(r["period"][:4]), KIND_LABEL[r["kind"]])].append(r)
            dist = []
            for (y, k), rs in sorted(by.items()):
                d = [r["delay_days"] for r in rs]
                judged = [r for r in rs if r["late"] is not None]
                dist.append({"year": y, "kind": k, "reports": len(rs), "median_days": statistics.median(d),
                             "max_days": max(d), "judged": len(judged),
                             "late": sum(r["late"] for r in judged),
                             "late_share": round(sum(r["late"] for r in judged) / len(judged), 4) if judged else None,
                             "label": f"{y} {k}"})
            late = [{k: r[k] for k in ("code", "kind", "period", "published", "deadline", "days_late", "title",
                                       "disclosure_id")} for r in rows if r["late"]]
            late.sort(key=lambda r: (-r["days_late"], r["code"]))
            annual = [x for x in dist if x["kind"] == "annual"]
            tables = {
                "by_year_kind": {"title": "Reporting delays by year and kind", "columns":
                                 ["year", "kind", "reports", "median_days", "max_days", "judged", "late",
                                  "late_share", "label"], "rows": dist},
                "late_share_annual": {"title": "Share of annual reports published late", "columns":
                                      ["year", "late_share"], "rows": [{"year": str(x["year"]),
                                                                        "late_share": x["late_share"]} for x in annual],
                                      "chart": {"type": "bars", "x": "year", "y": "late_share", "x_label": "year",
                                                "y_label": "share late"}},
                "late_reports": {"title": "Reports published after their deadlines", "columns":
                                 ["code", "kind", "period", "published", "deadline", "days_late", "title",
                                  "disclosure_id"], "rows": late},
            }
            notes = [f"Deadlines: rules {rules()['version']} (annual four months, half-year two, quarterly one); "
                     "a report whose deadline fell before a rule took effect is not judged.", rules_note(),
                     "Only the first publication of a report counts; corrections published later are not late "
                     "filings."]
            summary = [{"label": "Reports", "value": f"{len(rows):,}"},
                       {"label": "Late", "value": f"{len(late):,}"}]
            p = {"start": y0, "end": y1, "as_of": ctx.as_of, "title": f"Disclosure timeliness {y0}–{y1}"}
            snap = series_snapshot(self.id, p, ctx.policy(), tables, [], notes, self.evidence, summary)
            return Built(snap, _figures(snap))


def _figures(snap):
    from ...charts.spec import ChartSpec, Series, Point
    rows = [r for r in snap["tables"]["by_year_kind"]["rows"] if r["kind"] == "annual"]
    spec = ChartSpec("bar", "Median days from the year end to the annual report",
                     [Series("median days", [Point(str(r["year"]), r["median_days"]) for r in rows])],
                     y_label="days", subtitle="The legal deadline is four months after the year end",
                     caption="First publication of each annual report; rules in rules/disclosure_deadlines.json.")
    return [("annual_delay", spec)]
