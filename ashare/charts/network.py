"""Diagrams (v1.8): control chains, group-structure trees and interlock networks."""
from __future__ import annotations

import math

from .layout import FG, MUTED, GRID, text_width
from .spec import ChartSpec, PALETTE

GROUP_COLOURS = {"listed": "#0072B2", "government": "#009E73", "person": "#CC79A7", "company": "#56B4E9",
                 "OFFSHORE": "#D55E00", "HONG_KONG": "#E69F00", "MACAU": "#E69F00", "TAIWAN": "#E69F00",
                 "FOREIGN": "#CC79A7", "MAINLAND": "#56B4E9", "UNKNOWN": "#8c959f"}


def _box(out, x, y, w, h, label, group, meta=None, tip=None):
    col = GROUP_COLOURS.get(group, PALETTE[0])
    out.append({"type": "rect", "x": x, "y": y, "w": w, "h": h, "fill": "#ffffff", "stroke": col,
                "tip": tip or label, "meta": meta or {}})
    out.append({"type": "rect", "x": x, "y": y, "w": 5, "h": h, "fill": col, "stroke": None})
    size = 11 if text_width(label, 11) < w - 16 else 9
    text = label
    while text_width(text, size) > w - 14 and len(text) > 4:
        text = text[:-2]
    if text != label:
        text = text[:-1] + "…"
    out.append({"type": "text", "x": x + w / 2 + 2, "y": y + h / 2 + 4, "text": text, "anchor": "middle",
                "size": size, "colour": FG, "weight": "bold" if group == "listed" else "normal"})


def _arrow(out, x1, y1, x2, y2, label=None, dash=None):
    out.append({"type": "line", "x1": x1, "y1": y1, "x2": x2, "y2": y2, "stroke": "#57606a", "width": 1.5, "dash": dash})
    ang = math.atan2(y2 - y1, x2 - x1)
    for da in (2.6, -2.6):
        out.append({"type": "line", "x1": x2, "y1": y2, "x2": x2 + 8 * math.cos(ang + da), "y2": y2 + 8 * math.sin(ang + da),
                    "stroke": "#57606a", "width": 1.5, "dash": None})
    if label:
        out.append({"type": "text", "x": (x1 + x2) / 2 + 8, "y": (y1 + y2) / 2 + 4, "text": label, "anchor": "start",
                    "size": 10, "colour": FG, "weight": "bold"})


def chain(spec: ChartSpec) -> list[dict]:
    """Nodes listed from the ultimate controller (top) to the listed company (bottom)."""
    out: list[dict] = []
    g = spec.graph
    nodes = g["nodes"]
    if not nodes:
        return out
    top = 60 + (14 if spec.subtitle else 0)
    gap = (spec.height - top - 40) / max(len(nodes), 1)
    h = min(36, gap * 0.55)
    w = min(420, spec.width - 120)
    x = (spec.width - w) / 2
    pos = {}
    for i, n in enumerate(nodes):
        y = top + gap * i
        pos[n["id"]] = (x, y)
        _box(out, x, y, w, h, n["label"], n.get("group"), n.get("meta"), n.get("tip"))
    for e in g["edges"]:
        if e["from"] in pos and e["to"] in pos:
            (x1, y1), (x2, y2) = pos[e["from"]], pos[e["to"]]
            _arrow(out, x1 + w / 2, y1 + h, x2 + w / 2, y2, e.get("label"), (4, 3) if e.get("label") is None else None)
    out.append({"type": "text", "x": x + w + 12, "y": top + 12, "text": "arrow: holds", "anchor": "start", "size": 10,
                "colour": MUTED, "weight": "normal"})
    return out


def tree(spec: ChartSpec) -> list[dict]:
    """Root on the left, children in a column grouped by group (e.g. jurisdiction)."""
    out: list[dict] = []
    g = spec.graph
    root = g["nodes"][0]
    kids = sorted(g["nodes"][1:], key=lambda n: (str(n.get("group")), n["label"]))
    top = 56 + (14 if spec.subtitle else 0)
    rw, rh = 190, 40
    ry = top + (spec.height - top - 30) / 2 - rh / 2
    _box(out, 20, ry, rw, rh, root["label"], "listed", root.get("meta"))
    if not kids:
        return out
    step = (spec.height - top - 30) / len(kids)
    h = max(12, min(26, step * 0.75))
    cx, cw = 300, spec.width - 300 - 20
    edges = {e["to"]: e for e in g["edges"]}
    groups_seen = []
    for i, n in enumerate(kids):
        y = top + step * i
        _box(out, cx, y, cw, h, n["label"] + (f"  {edges[n['id']]['label']}" if n["id"] in edges and edges[n["id"]].get("label") else ""),
             n.get("group"), n.get("meta"), n.get("tip"))
        out.append({"type": "line", "x1": 20 + rw, "y1": ry + rh / 2, "x2": cx, "y2": y + h / 2, "stroke": GRID,
                    "width": 1, "dash": None})
        if n.get("group") not in groups_seen:
            groups_seen.append(n.get("group"))
    for k, gname in enumerate(groups_seen):   # legend with text labels
        out.append({"type": "rect", "x": 20, "y": spec.height - 40 - 14 * k, "w": 10, "h": 10,
                    "fill": GROUP_COLOURS.get(gname, PALETTE[0]), "stroke": None})
        out.append({"type": "text", "x": 34, "y": spec.height - 31 - 14 * k, "text": str(gname).replace("_", " ").title(),
                    "anchor": "start", "size": 10, "colour": FG, "weight": "normal"})
    return out


def network(spec: ChartSpec) -> list[dict]:
    """Nodes on a circle; edge width by weight; labels on nodes."""
    out: list[dict] = []
    g = spec.graph
    nodes = g["nodes"]
    if not nodes:
        return out
    cx, cy = spec.width / 2, (spec.height + 40) / 2
    r = min(spec.width, spec.height - 80) / 2 - 60
    pos = {}
    for i, n in enumerate(nodes):
        a = 2 * math.pi * i / len(nodes) - math.pi / 2
        pos[n["id"]] = (cx + r * math.cos(a), cy + r * math.sin(a))
    wmax = max([e.get("weight") or 1 for e in g["edges"]] or [1])
    for e in g["edges"]:
        if e["from"] in pos and e["to"] in pos:
            (x1, y1), (x2, y2) = pos[e["from"]], pos[e["to"]]
            out.append({"type": "line", "x1": x1, "y1": y1, "x2": x2, "y2": y2, "stroke": "#8c959f",
                        "width": 1 + 3 * (e.get("weight") or 1) / wmax, "dash": None})
            if e.get("label"):
                out.append({"type": "marker", "shape": "square", "cx": (x1 + x2) / 2, "cy": (y1 + y2) / 2, "r": 3,
                            "fill": "#ffffff", "stroke": "#8c959f", "dash": None, "tip": e["label"], "meta": {}})
    for n in nodes:
        x, y = pos[n["id"]]
        col = GROUP_COLOURS.get(n.get("group"), PALETTE[0])
        out.append({"type": "marker", "shape": "circle", "cx": x, "cy": y, "r": 7, "fill": col, "stroke": col,
                    "dash": None, "tip": n.get("tip") or n["label"], "meta": n.get("meta") or {}})
        anchor = "start" if x >= cx else "end"
        out.append({"type": "text", "x": x + (11 if x >= cx else -11), "y": y + 4, "text": n["label"], "anchor": anchor,
                    "size": 10, "colour": FG, "weight": "normal"})
    return out


# --- v2.2: the ego map -------------------------------------------------------------------------------------------

#: the arc of the circle (degrees, clockwise from the right, y downwards) each kind of relation is drawn in
EGO_ARCS = {"control": (235, 305), "sector": (310, 335), "holders": (340, 400), "group": (45, 135),
            "regulators": (140, 170), "board": (175, 230)}
KIND_COLOURS = {"company": "#0072B2", "entity": "#56B4E9", "person": "#CC79A7", "authority": "#D55E00",
                "sector": "#009E73", "group": "#E69F00"}
SHAPES = {"company": "square", "entity": "circle", "person": "diamond", "authority": "triangle", "sector": "square",
          "group": "circle"}


def ego_spec(snap: dict) -> ChartSpec:
    """The chart specification of an ego-map snapshot (publication figure)."""
    nodes = [{"id": n["id"], "label": n["label"], "group": n["kind"], "ring": n.get("ring") or "second",
              "centre": bool(n.get("centre"))} for n in snap["nodes"]]
    edges = [{"from": e["source"], "to": e["target"], "label": e.get("label"), "relation": e["relation"]}
             for e in snap["edges"]]
    p = snap.get("parameters", {})
    spec = ChartSpec("ego", p.get("title") or "Ego map", [], graph={"nodes": nodes, "edges": edges},
                     subtitle="Controller above, holders right, group below, board left; second-step companies "
                              "on the outer ring",
                     caption=f"Documented relations published by {p.get('as_of')}; persons under pseudonyms; "
                             "top-10 tables list ten holders only.")
    spec.height = 620
    return spec


def _short(text: str, n: int = 14) -> str:
    return text if len(text) <= n else text[: n - 1] + "…"


def ego(spec: ChartSpec) -> list[dict]:
    out: list[dict] = []
    g = spec.graph
    nodes = g["nodes"]
    if not nodes:
        return out
    cx, cy = spec.width / 2, (spec.height + 40) / 2
    r1 = min(spec.width, spec.height - 90) / 2 * 0.55
    r2 = r1 * 1.65
    pos: dict[str, tuple[float, float]] = {}
    angle: dict[str, float] = {}
    by_ring: dict[str, list] = {}
    for n in nodes:
        if n.get("centre"):
            pos[n["id"]] = (cx, cy)
        else:
            by_ring.setdefault(n["ring"], []).append(n)
    for ring, (a0, a1) in EGO_ARCS.items():
        members = sorted(by_ring.get(ring, []), key=lambda n: n["label"])
        for i, n in enumerate(members):
            a = a0 + (a1 - a0) * (i + 0.5) / len(members)
            angle[n["id"]] = a
            pos[n["id"]] = (cx + r1 * math.cos(math.radians(a)), cy + r1 * math.sin(math.radians(a)))
    second = sorted(by_ring.get("second", []), key=lambda n: n["label"])
    near: dict[str, list] = {}
    for e in g["edges"]:
        for a, b in ((e["from"], e["to"]), (e["to"], e["from"])):
            if a in angle:
                near.setdefault(b, []).append(angle[a])
    placed = sorted(second, key=lambda n: (sum(near.get(n["id"], [0])) / max(len(near.get(n["id"], [0])), 1),
                                           n["label"]))
    for i, n in enumerate(placed):
        a = 360 * (i + 0.5) / max(len(placed), 1) if not near.get(n["id"]) else \
            sum(near[n["id"]]) / len(near[n["id"]]) + (i % 3 - 1) * 6
        pos[n["id"]] = (cx + r2 * math.cos(math.radians(a)), cy + r2 * math.sin(math.radians(a)))
    for e in g["edges"]:
        if e["from"] in pos and e["to"] in pos:
            (x1, y1), (x2, y2) = pos[e["from"]], pos[e["to"]]
            dash = (4, 3) if e.get("relation") in ("SERVES_ON", "ACTS_ON") else None
            out.append({"type": "line", "x1": x1, "y1": y1, "x2": x2, "y2": y2, "stroke": GRID if dash else "#8c959f",
                        "width": 1, "dash": dash})
    for n in nodes:
        if n["id"] not in pos:
            continue
        x, y = pos[n["id"]]
        col = KIND_COLOURS.get(n["group"], PALETTE[0])
        out.append({"type": "marker", "shape": SHAPES.get(n["group"], "circle"), "cx": x, "cy": y,
                    "r": 9 if n.get("centre") else 5, "fill": col, "stroke": "#000000" if n.get("centre") else col,
                    "dash": None, "tip": n["label"], "meta": {}})
        right = x >= cx
        out.append({"type": "text", "x": x + (8 if right else -8), "y": y + 4,
                    "text": n["label"] if n.get("centre") else _short(n["label"]),
                    "anchor": "start" if right else "end", "size": 11 if n.get("centre") else 9, "colour": FG,
                    "weight": "bold" if n.get("centre") else "normal"})
    return out


from .layers import layers  # noqa: E402  (v2.1: the NVF layered view)

DIAGRAMS = {"chain": chain, "tree": tree, "network": network, "layers": layers, "ego": ego}
