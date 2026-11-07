"""Common ownership (v2.3.0, plan Part D): for a CSRC industry or a list of companies, who holds whom among the top
ten, which pairs of companies share holders, and the modified Herfindahl increment (MHHI delta, O'Brien and Salop) by
year.

An observed association between documented holdings; not evidence of coordination. Top-10 tables omit smaller
holders, so the increment is a lower bound.
"""
from __future__ import annotations

from datetime import date

from ..data import Context, ParamError, check_date
from ..registry import register
from ..series import series_snapshot
from ..view import View, Built
from . import _checks, _groups


@register
class CommonOwnershipView(View):
    id = "common_ownership"
    family = "relational"
    title = "Common ownership"
    intro = ("For an industry or a set of companies: the top-10 holders they share, the pairs linked by them, and "
             "the modified Herfindahl increment by year (a lower bound from top-10 stakes).")
    evidence = "OBSERVED_ASSOCIATION"
    params = [
        {"key": "industry", "label": "CSRC industry", "kind": "text", "default": "", "flag": "--industry",
         "hint": "A level-2 code such as C39; or name companies below.", "required": False},
        {"key": "codes", "label": "Companies", "kind": "text", "default": "", "flag": "--codes",
         "hint": "Comma-separated codes.", "required": False},
        {"key": "start", "label": "From year", "kind": "year", "default": "2021", "flag": "--start", "hint": "",
         "required": False},
        {"key": "end", "label": "To year", "kind": "year", "default": str(date.today().year - 1), "flag": "--end",
         "hint": "", "required": False},
        {"key": "as_of", "label": "As published by", "kind": "date", "default": "", "flag": "--as-of",
         "hint": "Blank: today.", "required": False},
        {"key": "out", "label": "Folder", "kind": "folder", "default": "visualise/common_ownership", "flag": "--out",
         "hint": "", "required": False},
    ]
    requires = [_checks.holders(), _checks.periodic_figures(), _checks.industry()]

    def build(self, params: dict) -> Built:
        from ...models import Company, FinancialFact, Disclosure
        from ...network_measures import latest_holders, mhhi_delta
        from ...util import parse_codes
        try:
            y0 = int(params.get("start") or 2021)
            y1 = int(params.get("end") or date.today().year - 1)
        except ValueError:
            raise ParamError("the years must be numbers such as 2021")
        if y0 > y1 or y1 - y0 > 30:
            raise ParamError("give a span of 1 to 30 years, the first before the last")
        industry = (params.get("industry") or "").strip().upper()
        codes = parse_codes(params.get("codes") or "")[0]
        if not industry and not codes:
            raise ParamError("name a CSRC industry or at least two companies")
        with Context(check_date(params.get("as_of"), "As published by"), bool(params.get("include_licensed")),
                     params.get("key")) as ctx:
            s = ctx.s
            comps = {c.id: c for c in s.query(Company)}
            if industry:
                ind = _groups.csrc(s, ctx.as_of, level=2)
                ids = {cid for cid, code in ind.items() if code == industry}
                if not ids:
                    raise ParamError(f"no company is classified in {industry} by {ctx.as_of}")
            else:
                ids = {cid for cid, c in comps.items() if c.security_code in codes}
                missing = sorted(set(codes) - {comps[i].security_code for i in ids})
                if missing:
                    raise ParamError(f"not in the company list: {', '.join(missing)}")
            label = {cid: comps[cid].security_code for cid in ids}
            holders = latest_holders(s, ctx.as_of, ids)
            # the holders' names, as shown (persons under pseudonyms)
            from ...models import OwnershipObservation
            names = {}
            for o in s.query(OwnershipObservation).filter(OwnershipObservation.company_id.in_(list(ids)),
                                                          OwnershipObservation.rank.isnot(None)):
                from ...network_measures import _norm
                key = f"E{o.entity_id}" if getattr(o, "entity_id", None) else _norm(o.shareholder_name)
                if key not in names:
                    names[key] = ctx.mask("ownership_observations", {"shareholder_name": o.shareholder_name,
                                                                      "shareholder_nature": getattr(o, "shareholder_nature", None),
                                                                      "shareholder_type": o.shareholder_type},
                                          "shareholder_name")[0]
            shared = {}
            for cid, hs in holders.items():
                for h in hs:
                    shared.setdefault(h, set()).add(cid)
            common = {h: cids for h, cids in shared.items() if len(cids) > 1}
            matrix = []
            for h in sorted(common, key=lambda h: (-len(common[h]), names.get(h, h))):
                for cid in sorted(common[h], key=lambda c: label[c]):
                    matrix.append({"holder": names.get(h, h), "company": label[cid],
                                   "stake": round(holders[cid][h] / 100.0, 6), "tip": f"{holders[cid][h]:.2f}%"})
            pairs = []
            cl = sorted(holders, key=lambda c: label[c])
            for i, a in enumerate(cl):
                for b in cl[i + 1:]:
                    both = set(holders[a]) & set(holders[b])
                    if both:
                        pairs.append({"company_a": label[a], "company_b": label[b], "shared_holders": len(both),
                                      "overlap": round(sum(min(holders[a][h], holders[b][h]) for h in both), 4)})
            pairs.sort(key=lambda r: (-r["overlap"], r["company_a"], r["company_b"]))
            by_year = []
            for y in range(y0, y1 + 1):
                cut = min(ctx.as_of, f"{y + 1}-12-31")
                rev = {}
                for f, pub in (s.query(FinancialFact, Disclosure.announcement_date)
                               .outerjoin(Disclosure, Disclosure.id == FinancialFact.disclosure_id)
                               .filter(FinancialFact.metric == "revenue", FinancialFact.reporting_period == f"{y}-12-31",
                                       FinancialFact.company_id.in_(list(ids)))):
                    if (pub or "9999")[:10] <= cut and f.value and f.value > 0:
                        rev[f.company_id] = max(rev.get(f.company_id, 0.0), f.value)
                tot = sum(rev.values())
                hy = latest_holders(s, cut, ids)
                v = mhhi_delta({c: x / tot for c, x in rev.items()}, hy) if tot else None
                by_year.append({"year": y, "companies_with_revenue": len(rev),
                                "companies_with_holders": sum(1 for c in rev if hy.get(c)),
                                "mhhi_delta": round(v, 2) if v is not None else None})
            tables = {
                "holdings": {"title": "Stakes of the holders shared by two or more companies (latest top-10 tables)",
                             "columns": ["holder", "company", "stake", "tip"], "rows": matrix,
                             "chart": {"type": "heatmap", "row": "holder", "col": "company", "value": "stake",
                                       "tip": "tip", "row_label": "holder"}},
                "pairs": {"title": "Pairs of companies sharing top-10 holders (overlap: sum of the smaller stakes, %)",
                          "columns": ["company_a", "company_b", "shared_holders", "overlap"], "rows": pairs},
                "mhhi_by_year": {"title": "Modified Herfindahl increment (HHI points; a lower bound)",
                                 "columns": ["year", "companies_with_revenue", "companies_with_holders", "mhhi_delta"],
                                 "rows": by_year,
                                 "chart": {"type": "bars", "x": "year", "y": "mhhi_delta", "x_label": "year",
                                           "y_label": "MHHI delta (HHI points)"}},
            }
            summary = [{"label": "Companies", "value": f"{len(ids):,}"},
                       {"label": "Holders shared", "value": f"{len(common):,}"},
                       {"label": "Pairs linked", "value": f"{len(pairs):,}"}]
            notes = [
                "An observed association between documented holdings; not evidence of coordination.",
                "Stakes are from each company's latest top-10 table published by the date; nominee accounts are "
                "left out.",
                "The MHHI increment uses revenue shares within the companies shown and treats control as "
                "proportional to stake; top-10 tables omit smaller holders, so it is a lower bound.",
                "Natural persons appear under pseudonyms.",
            ]
            p = {"industry": industry or None, "codes": sorted(label.values()), "start": y0, "end": y1,
                 "as_of": ctx.as_of, "title": f"Common ownership {industry or 'of the companies named'}, "
                                               f"as of {ctx.as_of}"}
            snap = series_snapshot(self.id, p, ctx.policy(), tables, [], notes, self.evidence, summary)
            return Built(snap, _figures(snap))


def _figures(snap):
    from ...charts.spec import ChartSpec, Series, Point
    rows = snap["tables"]["mhhi_by_year"]["rows"]
    spec = ChartSpec("bar", "Common-ownership increment (MHHI delta)",
                     [Series("MHHI delta", [Point(str(r["year"]), r["mhhi_delta"]) for r in rows])],
                     y_label="HHI points", subtitle="O'Brien and Salop; top-10 stakes; a lower bound",
                     caption="Observed association; not evidence of coordination.")
    return [("mhhi_by_year", spec)]
