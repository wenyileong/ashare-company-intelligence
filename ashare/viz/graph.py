"""The relational model of the Visualise section (v2.2, plan section B4.4).

Nodes are companies, legal entities, natural persons (always under pseudonyms), authorities, sectors and groups;
edges are documented relations (control, holdings, subsidiaries, board seats, regulatory actions …), each with the
document and page that state it and its dates. A name that cannot be resolved stays its own node, flagged
``UNRESOLVED``, and is never merged by guesswork.

Measures are computed in pure Python (no new dependency for the Windows build): degree, connected components,
distance from a node, and the two-sided to one-sided projection.
"""
from __future__ import annotations

from collections import defaultdict, deque

GRAPH_SCHEMA_VERSION = 2
NODE_KINDS = ("company", "entity", "person", "authority", "sector", "group")
RELATIONS = {
    "CONTROLS": "is the actual controller of",
    "HOLDS": "holds shares in (top-10 table)",
    "PARENT_OF": "holds a stake in (control chain)",
    "SUBSIDIARY_OF": "is a subsidiary or associate of",
    "SERVES_ON": "serves on the board or management of",
    "ACTS_ON": "took a regulatory action concerning",
    "IN_SECTOR": "is classified in",
    "SHARES_HOLDER_WITH": "shares a top-10 holder with",
    "SHARES_DIRECTOR_WITH": "shares a director or officer with",
    "SAME_CONTROLLER": "has the same actual controller as",          # v2.3.0 (market map)
    "GLEIF_PARENT": "is the direct or ultimate parent of (GLEIF register)",     # v2.4.0
}


class Graph:
    def __init__(self):
        self.nodes: dict[str, dict] = {}
        self.edges: dict[str, dict] = {}

    def node(self, nid: str, kind: str, label: str, **extra) -> dict:
        if kind not in NODE_KINDS:
            raise ValueError(f"unknown node kind {kind!r}")
        n = self.nodes.get(nid)
        if n is None:
            n = {"id": nid, "kind": kind, "label": label, "flags": [], "masked": False}
            self.nodes[nid] = n
        for k, v in extra.items():
            if v is not None:
                n[k] = v
        return n

    def edge(self, source: str, target: str, relation: str, basis: dict | None = None, dates: dict | None = None,
             value=None, label: str | None = None, status: str = "DOCUMENTED_FACT") -> dict:
        if relation not in RELATIONS:
            raise ValueError(f"unknown relation {relation!r}")
        eid = f"e:{relation}:{source}>{target}"
        e = {"id": eid, "source": source, "target": target, "relation": relation, "evidence_status": status,
             "basis": basis or {}, "dates": dates or {}, "value": value, "label": label}
        old = self.edges.get(eid)
        # the latest observation of a pair is the one shown
        if old is None or (e["dates"].get("observed_date") or "") >= (old["dates"].get("observed_date") or ""):
            self.edges[eid] = e
        return self.edges[eid]

    # --- measures --------------------------------------------------------------------------------------------------

    def _adjacent(self, directed: bool = False) -> dict[str, set]:
        adj = defaultdict(set)
        for e in self.edges.values():
            adj[e["source"]].add(e["target"])
            if not directed:
                adj[e["target"]].add(e["source"])
        return adj

    def degree(self) -> dict[str, int]:
        adj = self._adjacent()
        return {n: len(adj.get(n, ())) for n in self.nodes}

    def components(self) -> list[set]:
        adj, seen, out = self._adjacent(), set(), []
        for n in sorted(self.nodes):
            if n in seen:
                continue
            comp, queue = set(), deque([n])
            seen.add(n)
            while queue:
                x = queue.popleft()
                comp.add(x)
                for y in adj.get(x, ()):
                    if y not in seen:
                        seen.add(y)
                        queue.append(y)
            out.append(comp)
        return out

    def distances(self, start: str, relations: tuple[str, ...] | None = None, directed: bool = False) -> dict[str, int]:
        """Steps from ``start`` to every node reached (optionally over some relations, optionally following the
        edges' direction backwards, as up a control chain)."""
        adj = defaultdict(set)
        for e in self.edges.values():
            if relations and e["relation"] not in relations:
                continue
            if directed:
                adj[e["target"]].add(e["source"])
            else:
                adj[e["source"]].add(e["target"])
                adj[e["target"]].add(e["source"])
        dist, queue = {start: 0}, deque([start])
        while queue:
            x = queue.popleft()
            for y in adj.get(x, ()):
                if y not in dist:
                    dist[y] = dist[x] + 1
                    queue.append(y)
        return dist

    def to_dict(self) -> dict:
        return {"nodes": [self.nodes[k] for k in sorted(self.nodes)],
                "edges": [self.edges[k] for k in sorted(self.edges)]}


def project(pairs: list[tuple[str, str]]) -> dict[tuple[str, str], set]:
    """Two-sided to one-sided: from (holder, company) pairs, the pairs of companies that share holders, with the
    holders they share."""
    by_holder = defaultdict(set)
    for holder, company in pairs:
        by_holder[holder].add(company)
    out: dict[tuple[str, str], set] = defaultdict(set)
    for holder, companies in by_holder.items():
        cs = sorted(companies)
        for i in range(len(cs)):
            for j in range(i + 1, len(cs)):
                out[(cs[i], cs[j])].add(holder)
    return dict(out)


def graph_snapshot(view_id: str, params: dict, policy: dict, graph: Graph, coverage: list[dict], notes: list[str],
                   evidence: str, summary: list[dict] | None = None) -> dict:
    from .. import __version__
    from .definitions import CURRENT
    g = graph.to_dict()
    return {"schema_version": GRAPH_SCHEMA_VERSION, "kind": "graph", "view": view_id,
            "software": f"ashare {__version__}", "definitions": CURRENT, "parameters": params, "policy": policy,
            "evidence": evidence, "relations": RELATIONS, "coverage": coverage, "nodes": g["nodes"],
            "edges": g["edges"], "summary": summary or [], "notes": notes}
