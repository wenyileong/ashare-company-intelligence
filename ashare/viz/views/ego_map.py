"""The ego map (v2.2, plan section B5): one company at the centre, as known on a date.

Around it: the actual controller and the control chain; the top-10 holders; subsidiaries and associates; directors
and officers (always under pseudonyms); the regulators that acted on it; its CSRC sector. At depth 2, the other
listed companies the same holders hold and the same persons serve (board interlocks).

Every link is a documented fact, dated by the document that states it. It absorbs the control-chain, group-tree
and interlock charts of v1.8.
"""
from __future__ import annotations

import hashlib
from datetime import date, timedelta

from ..data import Context, ParamError, check_date
from ..graph import Graph, graph_snapshot
from ..registry import register
from ..view import View, Built
from . import _checks

RELATION_SETS = {"all": None, "control": ("CONTROLS", "PARENT_OF"), "ownership": ("HOLDS",),
                 "group": ("SUBSIDIARY_OF",), "board": ("SERVES_ON",), "regulators": ("ACTS_ON",)}
ROLE_WINDOW_DAYS = 450        # a director or officer counts at a date if seen in a roster within this many days
MAX_SUBSIDIARIES = 40
MAX_SECOND = 60


def _nid(prefix: str, text: str) -> str:
    return prefix + ":" + hashlib.sha1(text.encode("utf-8")).hexdigest()[:12]


UNNAMED = "Authority not named"      # v2.3.0 (finding 140)


@register
class EgoMapView(View):
    id = "ego_map"
    family = "relational"
    title = "Ego map"
    intro = ("One company at the centre: its controller and control chain, top-10 holders, subsidiaries, directors "
             "and officers, the regulators that acted on it and its sector, as known on a date. Depth 2 adds the "
             "other companies the same holders hold and the same persons serve.")
    evidence = "DOCUMENTED_FACT"
    params = [
        {"key": "code", "label": "Security code", "kind": "code", "default": "600519", "flag": "--code",
         "hint": "Six digits, e.g. 600519.", "required": True},
        {"key": "as_of", "label": "As published by", "kind": "date", "default": "", "flag": "--as-of",
         "hint": "Only what was published by this date (blank: today).", "required": False},
        {"key": "depth", "label": "Depth", "kind": "choice:1,2", "default": "1", "flag": "--depth",
         "hint": "1: the company's own relations; 2: also the other companies its holders hold and its directors "
                 "serve.", "required": False},
        {"key": "relations", "label": "Relations", "kind": "choice:all,control,ownership,group,board,regulators",
         "default": "all", "flag": "--relations", "hint": "", "required": False},
        {"key": "out", "label": "Folder", "kind": "folder", "default": "visualise/ego_map", "flag": "--out",
         "hint": "", "required": False},
    ]
    requires = [_checks.control(), _checks.holders(), _checks.subsidiaries(), _checks.roster(),
                _checks.regulatory()]

    def build(self, params: dict) -> Built:
        code = str(params.get("code") or "").strip()
        if not code:
            raise ParamError("give a security code")
        depth = int(params.get("depth") or 1)
        if depth not in (1, 2):
            raise ParamError("depth must be 1 or 2")
        rel_key = params.get("relations") or "all"
        if rel_key not in RELATION_SETS:
            raise ParamError(f"relations must be one of {', '.join(RELATION_SETS)}")
        wanted = RELATION_SETS[rel_key]
        with Context(check_date(params.get("as_of"), "As published by"), bool(params.get("include_licensed")),
                     params.get("key")) as ctx:
            c = ctx.company(code)
            g = Graph()
            centre = f"company:{c.security_code}"
            g.node(centre, "company", ctx.label(c), code=c.security_code, centre=True, ring="centre")
            cov = []

            def on(rel):
                return wanted is None or rel in wanted
            if on("CONTROLS") or on("PARENT_OF"):
                cov.append(self._control(ctx, g, c, centre))
            if on("HOLDS"):
                cov.append(self._holders(ctx, g, c, centre, depth))
            if on("SUBSIDIARY_OF"):
                cov.append(self._subsidiaries(ctx, g, c, centre))
            if on("SERVES_ON"):
                cov.append(self._board(ctx, g, c, centre, depth))
            if on("ACTS_ON"):
                cov.append(self._regulators(ctx, g, c, centre))
            self._sector(ctx, g, c, centre)
            ids = self._identifiers(ctx, g)                           # v2.3.0 (B7)
            if ids is not None:
                cov.append(ids)
            deg = g.degree()
            for nid, n in g.nodes.items():
                n["degree"] = deg.get(nid, 0)
            # the chain, where one reaching the company was read, gives the steps; otherwise the direct controller
            # link (one step)
            top = []
            for rels in (("PARENT_OF",), ("CONTROLS",)):
                up = g.distances(centre, rels, directed=True)
                top = [n for n in up if n != centre and g.nodes[n]["kind"] in ("entity", "person")]
                if top:
                    break
            summary = [{"label": "Nodes", "value": str(len(g.nodes))}, {"label": "Links", "value": str(len(g.edges))},
                       {"label": "Steps to the ultimate controller",
                        "value": str(max(up[n] for n in top)) if top else "not known"}]
            notes = [
                "Every link is a documented fact: a report or announcement states it. A link is not evidence that "
                "one party caused anything.",
                "Natural persons are shown under the same pseudonyms as in pseudonymised releases.",
                "Top-10 tables list ten holders only; smaller holders are not shown.",
                f"Directors and officers count at the date if a roster published by then lists them within "
                f"{ROLE_WINDOW_DAYS} days before it.",
            ]
            p = {"code": c.security_code, "as_of": ctx.as_of, "depth": depth, "relations": rel_key,
                 "include_licensed": ctx.include_licensed, "title": f"{ctx.label(c)}: relations as of {ctx.as_of}"}
            snap = graph_snapshot(self.id, p, ctx.policy(), g, cov, notes, self.evidence, summary)
            from ..publish import dumps
            leaks = ctx.leaks(dumps(snap))
            if leaks:
                raise ValueError(f"a person's name is shown unmasked ({len(leaks)}); the map is not written")
            from ...charts.network import ego_spec
            return Built(snap, [("ego_map", ego_spec(snap))])

    # --- the parts ----------------------------------------------------------------------------------------------

    def _identifiers(self, ctx, g):
        """v2.3.0 (B7): accepted LEIs on the entity nodes, and the share of entities with one."""
        from ...models import Entity, EntityAlias
        from ...models_v23 import EntityIdentifier
        lei = {}
        for i, e in (ctx.s.query(EntityIdentifier, Entity).join(Entity, Entity.id == EntityIdentifier.entity_id)
                     .filter(EntityIdentifier.scheme == "LEI", EntityIdentifier.status == "ACCEPTED")):
            lei[e.name] = i.value
            for a in ctx.s.query(EntityAlias).filter(EntityAlias.entity_id == e.id):
                lei.setdefault(a.alias, i.value)
        if not lei:
            return None
        ents = [n for n in g.nodes.values() if n["kind"] in ("entity", "company") and not n.get("masked")]
        n_with = 0
        for n in ents:
            if n["label"] in lei:
                n["lei"] = lei[n["label"]]
                n_with += 1
        parents = self._gleif_parents(ctx, g)
        note = f"{n_with} of {len(ents)} organisations with a Legal Entity Identifier (GLEIF)"
        if parents:
            note += f"; {parents} parent link(s) from the GLEIF register"
        return {"item": "identifiers", "status": "FOUND" if n_with else "NONE", "note": note}

    def _gleif_parents(self, ctx, g) -> int:
        """v2.4.0: the direct and ultimate parents GLEIF records for the organisations on the map, as their own
        relation (never merged into the control chain read from reports). Only links observed by the map's date."""
        from ...models_v23 import ExternalRelationship
        by_lei = {n["lei"]: nid for nid, n in g.nodes.items() if n.get("lei")}
        if not by_lei:
            return 0
        by_label = {n["label"]: nid for nid, n in g.nodes.items() if n["kind"] in ("entity", "company")}
        added = 0
        for r in ctx.s.query(ExternalRelationship).filter(ExternalRelationship.child_lei.in_(list(by_lei)),
                                                          ExternalRelationship.source == "GLEIF"):
            if r.observed_date and r.observed_date > ctx.as_of:
                continue
            child = by_lei[r.child_lei]
            parent = by_lei.get(r.parent_lei) or by_label.get(r.parent_name or "")
            if parent is None:
                parent = f"lei:{r.parent_lei}"
                g.node(parent, "entity", r.parent_name or r.parent_lei, lei=r.parent_lei, ring="control")
            if parent == child:
                continue
            kind = "ultimate parent" if r.relation == "ULTIMATE_PARENT" else "direct parent"
            g.edge(parent, child, "GLEIF_PARENT", basis={"source": "GLEIF", "relation": r.relation},
                   dates={"observed_date": r.observed_date}, label=kind)
            added += 1
        return added

    def _entity(self, ctx, g, table, row, col, natural_hint=False):
        shown, masked = ctx.mask(table, row, col)
        kind = "person" if masked else "entity"
        nid = _nid(kind, shown)
        n = g.node(nid, kind, shown)
        n["masked"] = n["masked"] or masked
        return nid

    def _control(self, ctx, g, c, centre):
        from ...models import ControlObservation, ControlEdge
        rows = [(o, ctx.published(o.disclosure_id)) for o in
                ctx.s.query(ControlObservation).filter(ControlObservation.company_id == c.id)]
        rows = [(o, p) for o, p in rows if ctx.known(p, o.observation_date)]
        if not rows:
            return {"item": "control", "status": "NONE", "note": "no controller read from a report published by then"}
        o, pub = max(rows, key=lambda x: (x[0].observation_date or "", x[0].id))
        dates = {"published_date": pub, "observed_date": o.observation_date}
        basis = {"kind": "page", "disclosure_id": o.disclosure_id, "page": o.source_page, "method": o.extraction_method}
        if o.actual_controller:
            row = {"actual_controller": o.actual_controller, "controller_nature": o.controller_nature}
            nid = self._entity(ctx, g, "control_observations", row, "actual_controller")
            g.nodes[nid]["ring"] = "control"
            g.nodes[nid]["group"] = o.ownership_type
            g.edge(nid, centre, "CONTROLS", basis, dates, label="actual controller")
        chain = [e for e in ctx.s.query(ControlEdge).filter(ControlEdge.company_id == c.id)
                 if (e.observation_date or "") <= ctx.as_of]
        if chain:
            latest = max(e.observation_date or "" for e in chain)
            for e in [e for e in chain if (e.observation_date or "") == latest]:
                a = self._entity(ctx, g, "control_edges", {"parent_name": e.parent_name}, "parent_name")
                child_is_company = e.child_name in (c.legal_name_cn, c.short_name_cn)
                b = centre if child_is_company else self._entity(ctx, g, "control_edges",
                                                                 {"child_name": e.child_name}, "child_name")
                for x in (a, b):
                    if x != centre:
                        g.nodes[x].setdefault("ring", "control")
                g.edge(a, b, "PARENT_OF", {"kind": "chain", "source": e.source, "method": e.basis},
                       {"observed_date": e.observation_date}, value=e.pct,
                       label=f"{e.pct:.2f}%" if e.pct is not None else None)
        status = "FOUND" if o.actual_controller else ("NO_CONTROLLER" if o.no_actual_controller else "NOT_NAMED")
        return {"item": "control", "status": status, "note": f"report of {o.observation_date}"}

    def _latest_holders(self, ctx, company_id):
        from ...models import OwnershipObservation
        rows = [(o, ctx.published(o.disclosure_id)) for o in
                ctx.s.query(OwnershipObservation).filter(OwnershipObservation.company_id == company_id,
                                                         OwnershipObservation.rank.isnot(None))]
        rows = [(o, p) for o, p in rows if ctx.known(p, o.observation_date)
                and ctx.licence_ok("ownership_observations", {"source": o.source})]
        if not rows:
            return [], None
        d = max(o.observation_date or "" for o, _ in rows)
        return sorted([(o, p) for o, p in rows if (o.observation_date or "") == d], key=lambda x: x[0].rank or 99), d

    def _holders(self, ctx, g, c, centre, depth):
        from ...models import Company
        cur, d = self._latest_holders(ctx, c.id)
        if not cur:
            return {"item": "holders", "status": "NONE", "note": "no top-10 table read from a report published by then"}
        holder_ids = []
        for o, pub in cur:
            row = {"shareholder_name": o.shareholder_name, "shareholder_nature": o.shareholder_nature,
                   "shareholder_type": o.shareholder_type}
            nid = self._entity(ctx, g, "ownership_observations", row, "shareholder_name")
            g.nodes[nid].setdefault("ring", "holders")
            if o.entity_id is None:
                if "UNRESOLVED" not in g.nodes[nid]["flags"]:
                    g.nodes[nid]["flags"].append("UNRESOLVED")
            g.edge(nid, centre, "HOLDS", {"kind": "page", "disclosure_id": o.disclosure_id, "page": o.source_page,
                                          "method": o.extraction_method},
                   {"published_date": pub, "observed_date": o.observation_date}, value=o.ownership_pct,
                   label=f"{o.ownership_pct:.2f}%" if o.ownership_pct is not None else None)
            if not g.nodes[nid]["masked"]:
                holder_ids.append((nid, o.shareholder_name))
        if depth == 2 and holder_ids:
            from ...models import OwnershipObservation
            names = {name: nid for nid, name in holder_ids}
            others = (ctx.s.query(OwnershipObservation.company_id).filter(
                OwnershipObservation.shareholder_name.in_(list(names)), OwnershipObservation.company_id != c.id,
                OwnershipObservation.rank.isnot(None)).distinct().all())
            added = 0
            for (cid,) in sorted(others):
                if added >= MAX_SECOND:
                    break
                rows, _ = self._latest_holders(ctx, cid)
                hits = [(o, p) for o, p in rows if o.shareholder_name in names]
                if not hits:
                    continue
                oc = ctx.s.get(Company, cid)
                onid = f"company:{oc.security_code}"
                g.node(onid, "company", ctx.label(oc), code=oc.security_code, ring="second")
                for o, pub in hits:
                    g.edge(names[o.shareholder_name], onid, "HOLDS",
                           {"kind": "page", "disclosure_id": o.disclosure_id, "page": o.source_page,
                            "method": o.extraction_method},
                           {"published_date": pub, "observed_date": o.observation_date}, value=o.ownership_pct,
                           label=f"{o.ownership_pct:.2f}%" if o.ownership_pct is not None else None)
                added += 1
        return {"item": "holders", "status": "FOUND", "note": f"top-10 table of {d}"}

    def _subsidiaries(self, ctx, g, c, centre):
        from ...models import SubsidiaryObservation
        rows = [(o, ctx.published(o.disclosure_id)) for o in
                ctx.s.query(SubsidiaryObservation).filter(SubsidiaryObservation.company_id == c.id)]
        rows = [(o, p) for o, p in rows if ctx.known(p, o.observation_date)]
        if not rows:
            return {"item": "subsidiaries", "status": "NONE", "note": "no subsidiary list read by then"}
        d = max(o.observation_date or "" for o, _ in rows)
        cur = sorted([(o, p) for o, p in rows if (o.observation_date or "") == d],
                     key=lambda x: (-(x[0].total_pct or 0), x[0].entity_name or ""))
        for o, pub in cur[:MAX_SUBSIDIARIES]:
            nid = _nid("entity", o.entity_name or "")
            g.node(nid, "entity", o.entity_name or "", ring="group", group=o.jurisdiction_class)
            g.edge(nid, centre, "SUBSIDIARY_OF", {"kind": "page", "disclosure_id": o.disclosure_id,
                                                  "page": o.source_page, "method": o.extraction_method},
                   {"published_date": pub, "observed_date": o.observation_date}, value=o.total_pct,
                   label=(o.relationship or "") + (f" {o.total_pct:.0f}%" if o.total_pct is not None else ""))
        more = len(cur) - MAX_SUBSIDIARIES
        return {"item": "subsidiaries", "status": "FOUND",
                "note": f"list of {d}" + (f"; the {MAX_SUBSIDIARIES} largest stakes shown, {more} more in the "
                                          "database" if more > 0 else "")}

    def _roles_at(self, ctx, company_id=None, person_ids=None):
        from ...models import PersonRole
        lo = (date.fromisoformat(ctx.as_of) - timedelta(days=ROLE_WINDOW_DAYS)).isoformat()
        q = ctx.s.query(PersonRole)
        if company_id is not None:
            q = q.filter(PersonRole.company_id == company_id)
        if person_ids is not None:
            q = q.filter(PersonRole.person_id.in_(list(person_ids)))
        return [r for r in q if (r.first_date or "9999") <= ctx.as_of and (r.last_date or r.first_date or "") >= lo]

    def _board(self, ctx, g, c, centre, depth):
        from ...models import Person, Company
        roles = self._roles_at(ctx, company_id=c.id)
        if not roles:
            return {"item": "board", "status": "NONE", "note": "no roster read by then"}
        persons = {}
        for r in roles:
            p = ctx.s.get(Person, r.person_id)
            if p is None:
                continue
            shown = ctx.person(p.name)
            nid = _nid("person", shown)
            g.node(nid, "person", shown, ring="board")
            g.nodes[nid]["masked"] = True
            persons[r.person_id] = nid
            g.edge(nid, centre, "SERVES_ON", {"kind": "roster", "method": "roster"},
                   {"observed_date": r.last_date or r.first_date}, label=r.role)
        if depth == 2 and persons:
            added = 0
            for r in sorted(self._roles_at(ctx, person_ids=persons), key=lambda r: (r.company_id, r.id)):
                if r.company_id == c.id:
                    continue
                oc = ctx.s.get(Company, r.company_id)
                onid = f"company:{oc.security_code}"
                if onid not in g.nodes:
                    if added >= MAX_SECOND:
                        continue
                    added += 1
                g.node(onid, "company", ctx.label(oc), code=oc.security_code, ring="second")
                g.edge(persons[r.person_id], onid, "SERVES_ON", {"kind": "roster", "method": "roster"},
                       {"observed_date": r.last_date or r.first_date}, label=r.role)
        return {"item": "board", "status": "FOUND", "note": f"{len(persons)} person(s) in office"}

    def _regulators(self, ctx, g, c, centre):
        from ...models import RegulatoryEvent
        # v2.3.0 (finding 140): an event that names no authority (often one read from a title) is drawn under one
        # node, "Authority not named", instead of being dropped; the note counts what was shown and left out
        allev = list(ctx.s.query(RegulatoryEvent).filter(RegulatoryEvent.company_id == c.id))
        evs = [e for e in allev if ctx.known(e.announcement_date, e.event_date)]
        later = len(allev) - len(evs)
        if not evs:
            return {"item": "regulators", "status": "NONE",
                    "note": "no regulatory event published by then" + (f" ({later} published later)" if later else "")}
        by = {}
        for e in evs:
            by.setdefault(e.authority_name or e.authority or UNNAMED, []).append(e)
        unnamed = len(by.get(UNNAMED, []))
        for name, es in sorted(by.items()):
            nid = _nid("authority", name)
            node = g.node(nid, "authority", name, ring="regulators", group=es[0].authority)
            if name == UNNAMED and "UNNAMED" not in node["flags"]:
                node["flags"].append("UNNAMED")
            last = max(es, key=lambda e: (e.announcement_date or e.event_date or "", e.id))
            g.edge(nid, centre, "ACTS_ON", {"kind": "page", "disclosure_id": last.disclosure_id,
                                            "page": last.source_page, "method": last.extraction_method},
                   {"published_date": last.announcement_date, "observed_date": last.event_date}, value=len(es),
                   label=f"{len(es)} event(s); latest {last.legal_classification or last.event_type}")
        named = len(by) - (1 if unnamed else 0)
        note = f"{len(evs)} event(s) from {named} named authorit{'y' if named == 1 else 'ies'}"
        if unnamed:
            note += f"; {unnamed} naming no authority"
        if later:
            note += f"; {later} published after the date, left out"
        return {"item": "regulators", "status": "FOUND", "note": note}

    def _sector(self, ctx, g, c, centre):
        from ...models import IndustryClassification
        rows = [r for r in ctx.s.query(IndustryClassification).filter(IndustryClassification.company_id == c.id,
                                                                      IndustryClassification.scheme == "CSRC_2012")
                if (r.effective_date or "") <= ctx.as_of]
        if not rows:
            return
        r = max(rows, key=lambda r: (r.effective_date or "", r.id))
        code = r.level2_code or r.level1_code
        if not code:
            return
        nid = f"sector:{code}"
        g.node(nid, "sector", f"{code} {r.level2_name or r.level1_name or ''}".strip(), ring="sector")
        g.edge(centre, nid, "IN_SECTOR", {"kind": "classification", "source": r.source, "method": "CSRC_2012"},
               {"observed_date": r.effective_date})
