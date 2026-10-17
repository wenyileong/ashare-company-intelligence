"""Chart specification (v1.5, build plan section 18.11).

A chart is described once, as data; renderers draw it. ``layout.scene``
turns a specification into drawing primitives in pixel coordinates, and the
SVG and Tk renderers paint those primitives, so the application and the
HTML reports always agree.
"""
from __future__ import annotations

from dataclasses import dataclass, field

# Okabe-Ito palette (colour-blind safe), without the low-contrast yellow.
PALETTE = ("#0072B2", "#D55E00", "#009E73", "#CC79A7", "#E69F00", "#56B4E9", "#000000")


@dataclass
class Point:
    x: object                      # ISO date string, category label or number
    y: float | None                # None = missing (drawn as a gap, never interpolated)
    meta: dict = field(default_factory=dict)   # provenance shown in the tooltip
    confidence: str | None = None  # HIGH / MEDIUM / LOW / UNVALIDATED -> marker style
    restated: bool = False         # drawn with a distinct (diamond) marker
    review: str | None = None      # ACCEPTED / CORRECTED -> square marker


@dataclass
class Series:
    name: str
    points: list[Point]
    colour: str | None = None
    unit: str | None = None
    band: list | None = None        # v1.7: (low, high) per point, drawn as a shaded band (line charts)


@dataclass
class ChartSpec:
    kind: str                       # line, bar, hbar; v1.7: scatter, hist, box, heatmap, stacked; v1.8: chain, tree, network
    title: str
    series: list[Series]
    x_type: str = "category"        # 'time' (ISO dates), 'category' or 'number'
    y_label: str = ""
    unit: str | None = None         # CNY, RATIO, PERSON … (drives number format)
    subtitle: str = ""
    caption: str = ""               # sources and as-of date; printed under the chart
    as_of: str | None = None        # drawn as a vertical rule on time axes
    width: int = 760
    height: int = 360
    # v1.7
    x_label: str = ""
    markers: list = field(default_factory=list)   # [{"x": date, "label": str, "group": str}] on time axes
    highlight: object = None        # scatter: label of the point to emphasise; hist/box: a value to mark
    fit: bool = False               # scatter: least-squares line
    bins: int = 20                  # hist
    percent: bool = False           # stacked: shares instead of amounts
    # v1.8: diagrams. {"nodes": [{"id", "label", "group", "meta"}], "edges": [{"from", "to", "label", "weight"}]}
    graph: dict | None = None

    def data_rows(self) -> list[dict]:
        """Exactly the plotted data, for CSV export."""
        if self.graph:
            nodes = {n["id"]: n for n in self.graph.get("nodes", [])}
            return [{"from": nodes.get(e["from"], {}).get("label", e["from"]),
                     "to": nodes.get(e["to"], {}).get("label", e["to"]), "label": e.get("label"),
                     "weight": e.get("weight")} for e in self.graph.get("edges", [])]
        rows = []
        for s in self.series:
            for p in s.points:
                row = {"series": s.name, "x": p.x, "y": p.y, "confidence": p.confidence,
                       "restated": p.restated, "review": p.review}
                for k, v in (p.meta or {}).items():
                    row[k] = v
                rows.append(row)
        return rows
