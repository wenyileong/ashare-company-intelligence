"""A desktop chart as an interactive page (v2.3.0, plan section B4.5).

The Tk chart windows draw a fixed picture. 'Open interactive' writes the same data as an offline page with the
zoomable chart runtime (``viz/viewer/chart_runtime.js``): wheel and pinch zoom, pan, box zoom, reset, typed ranges and
the exact value under the pointer. Diagrams (chains, trees, networks, layers) are not charts of values and are left as
they are.
"""
from __future__ import annotations

import html
import json
import re
from pathlib import Path

from .spec import ChartSpec, PALETTE

SUPPORTED = ("line", "bar", "hbar", "scatter", "stacked", "hist")


def _num(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def config(spec: ChartSpec) -> dict:
    """A Chart.js configuration with the spec's data, unchanged (missing values stay gaps)."""
    if spec.kind not in SUPPORTED:
        raise ValueError(f"a {spec.kind} chart has no interactive page")
    numeric_x = spec.kind == "scatter" or spec.x_type == "number"
    datasets, labels = [], []
    if not numeric_x:
        for s in spec.series:
            for p in s.points:
                if p.x not in labels:
                    labels.append(p.x)
    for i, s in enumerate(spec.series):
        colour = s.colour or PALETTE[i % len(PALETTE)]
        if numeric_x:
            data = [{"x": _num(p.x), "y": p.y, "r": {"label": str(p.meta.get("label") or p.x),
                                                     **{k: v for k, v in p.meta.items() if k in ("disclosure_id",
                                                                                                 "page")}}}
                    for p in s.points if _num(p.x) is not None]
        else:
            by = {p.x: p.y for p in s.points}
            data = [by.get(x) for x in labels]
        datasets.append({"label": s.name, "data": data, "borderColor": colour, "backgroundColor": colour,
                         "spanGaps": False, "pointRadius": 2 if spec.kind != "scatter" else 3})
    kind = {"line": "line", "bar": "bar", "hbar": "bar", "stacked": "bar", "hist": "bar", "scatter": "scatter"}[spec.kind]
    scales = {"x": {"title": {"display": bool(spec.x_label), "text": spec.x_label}},
              "y": {"title": {"display": bool(spec.y_label), "text": spec.y_label}}}
    if numeric_x:
        scales["x"]["type"] = "linear"
    if spec.kind == "stacked":
        scales["x"]["stacked"] = scales["y"]["stacked"] = True
    cfg = {"type": kind, "data": {"datasets": datasets}, "options": {"animation": False, "scales": scales}}
    if not numeric_x:
        cfg["data"]["labels"] = [str(x) for x in labels]
    if spec.kind == "hbar":
        cfg["options"]["indexAxis"] = "y"
    return cfg


def page(spec: ChartSpec) -> str:
    from ..viz.viewer import HERE, _script_safe
    from ..viz.pages import interactive_scripts
    cfg = config(spec)
    money = (spec.unit or "").upper() == "CNY"
    libs = _script_safe((HERE / "vendor" / "chart.umd.js").read_text(encoding="utf-8")) + "\n" + interactive_scripts()
    css = (HERE / "views.css").read_text(encoding="utf-8")
    data = json.dumps(cfg, ensure_ascii=False, default=str).replace("</", "<\\/")
    title = html.escape(spec.title)
    sub = html.escape(" · ".join(x for x in (spec.subtitle, spec.caption) if x))
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><title>{title}</title>
<meta name="viewport" content="width=device-width, initial-scale=1"><style>{css}</style></head>
<body><div class="panel"><h1>{title}</h1><div class="muted">{sub}</div><div id="chart"></div></div>
<script>{libs}</script>
<script id="cfg" type="application/json">{data}</script>
<script>
(function () {{
  var cfg = JSON.parse(document.getElementById("cfg").textContent), holder = document.getElementById("chart");
  if (window.AshareInteractive) window.AshareInteractive.make(holder, cfg, {{money: {str(money).lower()}}});
  else {{ var c = document.createElement("canvas"); holder.appendChild(c); new Chart(c, cfg); }}
  window.__interactive = {{charts: window.AshareInteractive ? window.AshareInteractive.charts.length : 0}};
}})();
</script></body></html>"""


def write_page(spec: ChartSpec, folder: str | Path) -> Path:
    slug = re.sub(r"[^\w\-]+", "_", spec.title, flags=re.UNICODE).strip("_")[:60] or "chart"
    out = Path(folder)
    out.mkdir(parents=True, exist_ok=True)
    p = out / f"{slug}.html"
    p.write_text(page(spec), encoding="utf-8")
    return p
