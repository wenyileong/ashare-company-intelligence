"""The market map (v2.3.0, plan Part D): every listed company as known on a date, linked by a shared actual
controller, shared top-10 holders and shared directors or officers, grouped by CSRC section or board.

Zoomed out, the page shows the groups and the links between them; zoomed in, or with 'Show companies', the companies.
A holder among the top ten of very many companies (a state fund, a securities finance company) would link almost
everything, so holders in more than ``max_holder_companies`` tables are left out and listed in the notes.
Network observations are not independent: a regression on these links needs clustered or network-robust errors.
"""
from __future__ import annotations

from collections import defaultdict

from ..data import Context, ParamError, check_date
from ..graph import Graph, graph_snapshot
from ..registry import register
from ..view import View, Built
from . import _checks, _groups

RELATION_SETS = {"all": ("SAME_CONTROLLER", "SHARES_HOLDER_WITH", "SHARES_DIRECTOR_WITH"),
                 "controller": ("SAME_CONTROLLER",), "holders": ("SHARES_HOLDER_WITH",),
                 "board": ("SHARES_DIRECTOR_WITH",)}


@register
class MarketMapView(View):
    id = "market_map"
    family = "relational"
    title = "Market map"
    intro = ("Every listed company as known on a date, linked by a shared actual controller, shared top-10 holders "
             "and shared directors or officers, grouped by CSRC section or board.")
    evidence = "DOCUMENTED_FACT"
    params = [
        {"key": "as_of", "label": "As known on", "kind": "date", "default": "", "flag": "--as-of",
         "hint": "Blank: today.", "required": False},
        {"key": "relations", "label": "Links", "kind": "choice:all,controller,holders,board", "default": "all",
         "flag": "--relations", "hint": "", "required": False},
        {"key": "min_weight", "label": "Fewest shared holders or persons", "kind": "text", "default": "1",
         "flag": "--min-weight", "hint": "A link needs at least this many in common.", "required": False},
        {"key": "max_holder_companies", "label": "Leave out holders in more tables than", "kind": "text",
         "default": "50", "flag": "--max-holder-companies", "hint": "", "required": False},
        {"key": "group_by", "label": "Groups", "kind": "choice:auto,board,csrc", "default": "auto",
         "flag": "--group-by", "hint": "", "required": False},
        {"key": "codes", "label": "Only these companies", "kind": "text", "default": "", "flag": "--codes",
         "hint": "Blank: the whole market.", "required": False},
        {"key": "out", "label": "Folder", "kind": "folder", "default": "visualise/market_map", "flag": "--out",
         "hint": "", "required": False},
    ]
    requires = [_checks.holders(), _checks.control(), _checks.roster(), _checks.industry()]

    def build(self, params: dict) -> Built:
        from ...models import Company, ControlObservation
        from ...control import controller_key
        from ...network_measures import latest_holders, interlock_network
        from ...util import parse_codes
        rel = params.get("relations") or "all"
        if rel not in RELATION_SETS:
            raise ParamError("links must be all, controller, holders or board")
        try:
            min_w = max(1, int(params.get("min_weight") or 1))
            cap = max(2, int(params.get("max_holder_companies") or 50))
        except ValueError:
            raise ParamError("the weights must be whole numbers")
        wanted = set(parse_codes(params.get("codes") or "")[0])
        with Context(check_date(params.get("as_of"), "As known on"), bool(params.get("include_licensed")),
                     params.get("key")) as ctx:
            s = ctx.s
            comps = {c.id: c for c in s.query(Company)}
            listed = _groups.listed_on(s, comps, ctx.as_of)
            if wanted:
                listed = {cid for cid in listed if comps[cid].security_code in wanted}
            group, basis = _groups.groups(s, comps, ctx.as_of, params.get("group_by") or "auto")
            g = Graph()
            links: dict[tuple, dict] = defaultdict(lambda: defaultdict(int))
            on = RELATION_SETS[rel]
            dropped_holders = []
            if "SAME_CONTROLLER" in on:
                latest: dict[int, tuple] = {}
                for o in s.query(ControlObservation):
                    p = ctx.published(o.disclosure_id)
                    if o.company_id in listed and o.actual_controller and ctx.known(p, o.observation_date):
                        if o.company_id not in latest or (o.observation_date, o.id) > latest[o.company_id][0]:
                            latest[o.company_id] = ((o.observation_date, o.id), controller_key(o.actual_controller))
                by_ctl = defaultdict(list)
                for cid, (_, k) in latest.items():
                    by_ctl[k].append(cid)
                for k, cids in by_ctl.items():
                    if 1 < len(cids) <= 400:
                        for i, a in enumerate(sorted(cids)):
                            for b in sorted(cids)[i + 1:]:
                                links[("SAME_CONTROLLER", a, b)]["n"] = 1
            if "SHARES_HOLDER_WITH" in on:
                holders = latest_holders(s, ctx.as_of, listed)
                by_h = defaultdict(set)
                for cid, hs in holders.items():
                    for h in hs:
                        by_h[h].add(cid)
                for h, cids in by_h.items():
                    if len(cids) > cap:
                        dropped_holders.append((len(cids), h))
                        continue
                    cl = sorted(cids)
                    for i, a in enumerate(cl):
                        for b in cl[i + 1:]:
                            links[("SHARES_HOLDER_WITH", a, b)]["n"] += 1
            if "SHARES_DIRECTOR_WITH" in on:
                net = interlock_network(s, ctx.as_of)
                for a, others in net.items():
                    if a not in listed:
                        continue
                    for b in others:
                        if b in listed and a < b:
                            links[("SHARES_DIRECTOR_WITH", a, b)]["n"] += 1
            used = set()
            for (relation, a, b), v in links.items():
                if v["n"] >= min_w:
                    used |= {a, b}
            for cid in sorted(listed):
                c = comps[cid]
                g.node(f"company:{c.security_code}", "company", ctx.label(c), code=c.security_code,
                       group=group.get(cid), ring="market")
            for (relation, a, b), v in sorted(links.items()):
                if v["n"] < min_w:
                    continue
                g.edge(f"company:{comps[a].security_code}", f"company:{comps[b].security_code}", relation,
                       {"kind": "derived", "method": "network_measures"}, {"observed_date": ctx.as_of},
                       value=v["n"], label=f"{v['n']} in common" if relation != "SAME_CONTROLLER" else None)
            deg = g.degree()
            for nid, n in g.nodes.items():
                n["degree"] = deg.get(nid, 0)
            by_rel = defaultdict(int)
            for e in g.edges.values():
                by_rel[e["relation"]] += 1
            summary = [{"label": "Companies listed", "value": f"{len(listed):,}"},
                       {"label": "Companies with a link", "value": f"{len(used):,}"}] + \
                      [{"label": f"Links: {k.lower().replace('_', ' ')}", "value": f"{v:,}"}
                       for k, v in sorted(by_rel.items())]
            dropped_holders.sort(reverse=True)
            notes = [
                "Links are documented facts: a controller read from a report, a top-10 table, a roster; each as "
                f"known on {ctx.as_of}.",
                f"Groups: {'CSRC sections' if basis == 'csrc' else 'boards (import the CSRC classification for sections)'}.",
                "Nominee accounts (Stock Connect) are left out of shared holders.",
                (f"Holders in more than {cap} top-10 tables are left out ({len(dropped_holders)}), since they would "
                 "link almost every company." if dropped_holders else "No holder was left out for breadth."),
                "Network observations are not independent: use clustered or network-robust standard errors.",
            ]
            p = {"as_of": ctx.as_of, "relations": rel, "min_weight": min_w, "max_holder_companies": cap,
                 "group_basis": basis, "codes": sorted(wanted), "aggregate_above": 800,
                 "title": f"Market map, as known on {ctx.as_of}"}
            snap = graph_snapshot(self.id, p, ctx.policy(), g, [], notes, self.evidence, summary)
            leaks = ctx.leaks(" ".join(n["label"] for n in snap["nodes"]))
            if leaks:
                raise ValueError("a person's name is shown unmasked; the map is not written")
            return Built(snap, [("market_map_groups", _figure(snap))])


def _figure(snap):
    from collections import Counter
    from ...charts.spec import ChartSpec, Series, Point
    linked = Counter(n.get("group") or "unknown" for n in snap["nodes"] if n.get("degree"))
    total = Counter(n.get("group") or "unknown" for n in snap["nodes"])
    groups = sorted(total, key=lambda k: -total[k])[:30]
    spec = ChartSpec("hbar", "Listed companies with a link, by group",
                     [Series("with a link", [Point(g, linked.get(g, 0)) for g in groups]),
                      Series("listed", [Point(g, total[g]) for g in groups])],
                     y_label="companies", subtitle=f"As known on {snap['parameters']['as_of']}",
                     caption="Links: a shared actual controller, top-10 holder or director or officer.")
    spec.height = max(260, 40 + 22 * len(groups))
    return spec
