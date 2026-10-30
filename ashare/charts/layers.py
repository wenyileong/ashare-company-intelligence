"""The layered view (v2.1, visualisation V1): the five NVF layers as columns, companies as rows.

Each cell lists what the snapshot holds for one company in one layer: its observations, regulatory events and
sector, and its shareholders and controller. The marker's outline shows the evidential status of the link behind it
(solid: a documented fact; dashed, dotted: an association or an estimate), so the status is never shown by colour
alone. A layer with no data for a company is drawn as a dashed cell saying so; nothing is interpolated.

The positions are decided here, from the snapshot, and painted by the Tk and SVG renderers alike (``layout.scene``),
so the desktop and the exported figure agree. The snapshot itself decides nothing that is drawn here differently.
"""
from __future__ import annotations

from .layout import FG, MUTED, GRID, text_width
from .spec import ChartSpec, Point, Series

STATUS_DASH = {"DOCUMENTED_FACT": None, "OBSERVED_ASSOCIATION": (5, 3), "ESTIMATED_RELATIONSHIP": (2, 2),
               "THEORETICAL_PROPOSITION": (8, 3)}
KIND_SHAPE = {"observation": "circle", "regulatory_event": "square", "sector": "square", "shareholder": "square",
              "controller": "square"}       # a diamond marks a restated figure, as in the other charts
SHORT = {"revenue": "Revenue", "net_profit_parent": "Net profit", "rd_expense": "R&D expense", "capex": "Capex",
         "rd_investment": "R&D investment", "rd_staff": "R&D staff", "rd_ratio": "R&D / revenue", "close": "Close"}
LANE_LABEL_W = 150
ROW_ITEM_H = 16


def _fit(text: str, width: float, size: int = 10) -> str:
    if text_width(text, size) <= width:
        return text
    while len(text) > 2 and text_width(text + "…", size) > width:
        text = text[:-1]
    return text + "…"


def _value_text(n: dict) -> str:
    from .layout import fmt_value
    if n.get("low") is not None and n.get("high") is not None:
        if n["low"] == n["high"]:
            return fmt_value(n["low"], n.get("unit"))
        return f"{fmt_value(n['low'], n.get('unit'))} to {fmt_value(n['high'], n.get('unit'))}"
    if n.get("value") is not None:
        return fmt_value(n["value"], n.get("unit"))
    return ""


def _short(n: dict) -> str:
    """The cell's text: what, which year, how much (the full label is in the tooltip)."""
    if n["kind"] != "observation":
        return n["label"]
    what = SHORT.get(n.get("metric") or "", n["label"])
    if n.get("source_kind"):
        what += " (guidance)" if n["source_kind"] == "MANAGEMENT_GUIDANCE" else " (forecast)"
    return f"{what} {str(n.get('period') or '')[:4]}"


def layers_chart(snap: dict, year: str | None = None, width: int = 1100, row_items: int = 6) -> ChartSpec:
    """A ChartSpec of kind ``layers`` from a snapshot; ``year`` keeps one fiscal year's observations."""
    p = snap["parameters"]
    nodes = {n["id"]: n for n in snap["nodes"]}
    status_of: dict[str, str] = {}
    company_of: dict[str, set] = {}
    for e in snap["edges"]:
        for end, other in ((e["target"], e["source"]), (e["source"], e["target"])):
            status_of.setdefault(end, e["evidence_status"])
            if other.startswith("company:"):
                company_of.setdefault(end, set()).add(other.split(":", 1)[1])
    cells: dict[tuple, list] = {}
    for n in snap["nodes"]:
        if n["kind"] in ("company", "data_gap"):
            continue
        if year and n["kind"] == "observation" and str(n.get("period") or "")[:4] != str(year):
            continue
        codes = [n["company_code"]] if n.get("company_code") else sorted(company_of.get(n["id"], ()))
        for code in codes:
            cells.setdefault((code, n["layer"]), []).append(n)
    lanes = list(p["companies"])
    rows_needed = max([1] + [min(len(v), row_items + 1) for v in cells.values()])
    row_h = max(46, 12 + rows_needed * ROW_ITEM_H)
    height = 96 + row_h * len(lanes) + 40
    plotted = []
    graph_nodes = []
    for (code, layer), items in sorted(cells.items()):
        items.sort(key=lambda n: (n["kind"] != "observation", n.get("metric") or "", n.get("period") or "",
                                  n["label"]))
        for k, n in enumerate(items):
            graph_nodes.append({"id": n["id"], "lane": code, "layer": layer, "slot": k, "label": n["label"],
                                "text": _short(n),
                                "kind": n["kind"], "status": status_of.get(n["id"], "DOCUMENTED_FACT"),
                                "value_text": _value_text(n), "masked": n.get("masked", False),
                                "restated": n.get("restated", False), "flags": n.get("flags") or [],
                                "meta": {"node": n["id"], "company": code,
                                         "published": (n.get("dates") or {}).get("published_date"),
                                         "page": (n.get("provenance") or {}).get("page"),
                                         "document": (n.get("provenance") or {}).get("disclosure_id")}})
            if n["kind"] == "observation" and k < row_items:
                prov, d = n.get("provenance") or {}, n.get("dates") or {}
                plotted.append({"company": code, "layer": layer, "id": n["id"], "metric": n.get("metric"),
                                "period": n.get("period"), "value": n.get("value"), "low": n.get("low"),
                                "high": n.get("high"), "unit": n.get("unit"),
                                "published": d.get("published_date"), "disclosure_id": prov.get("disclosure_id"),
                                "page": prov.get("page"), "status": status_of.get(n["id"], "DOCUMENTED_FACT")})
    title = "NVF layers" + (f", fiscal {year}" if year else "")
    gaps = [c["layer"] for c in snap["coverage"] if c["status"] == "GAP"]
    subtitle = (f"{len(lanes)} compan{'y' if len(lanes) == 1 else 'ies'}; as published by {p['as_of']}; "
                f"expectations: {'management guidance (a proxy)' if p['expectations'] == 'MANAGEMENT_GUIDANCE' else 'analyst forecasts'}")
    caption = ("Solid outline: documented fact. Dashed cell: no data in that layer"
               + (f" ({', '.join(gaps)} empty for every company)" if gaps else "") + ". Source: " + snap["software"]
               + ", snapshot schema " + str(snap["schema_version"]) + ".")
    labels = {n["id"].split(":", 1)[1]: n["label"] for n in snap["nodes"] if n["kind"] == "company"}
    spec = ChartSpec("layers", title, [Series("observations", [Point(r["id"], r["value"]) for r in plotted])],
                     subtitle=subtitle, caption=caption, width=width, height=height, as_of=p["as_of"],
                     graph={"layers": snap["layers"], "lanes": lanes, "lane_labels": labels, "nodes": graph_nodes,
                            "edges": [], "row_items": row_items, "row_h": row_h, "observations": plotted})
    return spec


def layers(spec: ChartSpec) -> list[dict]:
    g = spec.graph
    out: list[dict] = []
    W = spec.width
    top = 60 + (14 if spec.subtitle else 0)
    L, R = LANE_LABEL_W, W - 16
    cols = g["layers"]
    colw = (R - L) / max(len(cols), 1)
    row_h, row_items = g["row_h"], g["row_items"]
    header_h = 30
    # column headers: a colour bar (the layer) and its name
    for i, c in enumerate(cols):
        x = L + i * colw
        out.append({"type": "rect", "x": x + 2, "y": top, "w": colw - 4, "h": 4, "fill": c["colour"], "stroke": None})
        out.append({"type": "text", "x": x + 6, "y": top + 20, "text": _fit(c["label"], colw - 10, 11),
                    "anchor": "start", "size": 11, "colour": FG, "weight": "bold"})
    by_cell: dict[tuple, list] = {}
    for n in g["nodes"]:
        by_cell.setdefault((n["lane"], n["layer"]), []).append(n)
    y0 = top + header_h
    for r, code in enumerate(g["lanes"]):
        y = y0 + r * row_h
        out.append({"type": "line", "x1": 16, "y1": y, "x2": R, "y2": y, "stroke": GRID, "width": 1, "dash": None})
        out.append({"type": "text", "x": 16, "y": y + 16, "text": _fit(g["lane_labels"].get(code, code), L - 24, 11),
                    "anchor": "start", "size": 11, "colour": FG, "weight": "bold"})
        for i, c in enumerate(cols):
            x = L + i * colw
            items = by_cell.get((code, c["id"]), [])
            if not items:
                out.append({"type": "rect", "x": x + 4, "y": y + 6, "w": colw - 8, "h": 22, "fill": "#fafbfc",
                            "stroke": None})
                for (x1, y1, x2, y2) in ((x + 4, y + 6, x + colw - 4, y + 6), (x + 4, y + 28, x + colw - 4, y + 28),
                                         (x + 4, y + 6, x + 4, y + 28), (x + colw - 4, y + 6, x + colw - 4, y + 28)):
                    out.append({"type": "line", "x1": x1, "y1": y1, "x2": x2, "y2": y2, "stroke": "#c6cdd6",
                                "width": 1, "dash": (4, 3)})
                out.append({"type": "text", "x": x + 10, "y": y + 21, "text": "No data", "anchor": "start", "size": 10,
                            "colour": MUTED, "weight": "normal"})
                continue
            for k, n in enumerate(items[:row_items]):
                cy = y + 14 + k * ROW_ITEM_H
                shape = "diamond" if n["restated"] else KIND_SHAPE.get(n["kind"], "circle")
                tip = n["label"] + (f": {n['value_text']}" if n["value_text"] else "") + \
                    (f" (published {n['meta']['published']})" if n["meta"].get("published") else "") + \
                    (f"; page {n['meta']['page']}" if n["meta"].get("page") else "") + \
                    ("; pseudonym" if n["masked"] else "") + \
                    (f"; findings: {', '.join(n['flags'])}" if n["flags"] else "")
                out.append({"type": "marker", "shape": shape, "cx": x + 12, "cy": cy, "r": 4,
                            "fill": "#ffffff" if n["status"] != "DOCUMENTED_FACT" else c["colour"],
                            "stroke": c["colour"], "dash": STATUS_DASH.get(n["status"]), "tip": tip,
                            "meta": n["meta"]})
                text = n["text"] + (f"  {n['value_text']}" if n["value_text"] else "")
                out.append({"type": "text", "x": x + 21, "y": cy + 4, "text": _fit(text, colw - 30, 10),
                            "anchor": "start", "size": 10, "colour": FG, "weight": "normal"})
            if len(items) > row_items:
                cy = y + 14 + row_items * ROW_ITEM_H
                out.append({"type": "text", "x": x + 21, "y": cy + 4, "text": f"+ {len(items) - row_items} more",
                            "anchor": "start", "size": 10, "colour": MUTED, "weight": "normal"})
    yb = y0 + len(g["lanes"]) * row_h
    out.append({"type": "line", "x1": 16, "y1": yb, "x2": R, "y2": yb, "stroke": GRID, "width": 1, "dash": None})
    return out
