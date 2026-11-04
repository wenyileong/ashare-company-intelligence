"""The offline interactive pages of the Visualise section (v2.2, plan section B4.5).

One HTML file per view, with the snapshot and the libraries inside it, so that it opens from disk with no server
and no network, like the topology viewer (whose libraries it shares: ``viewer/vendor``, licences in
``vendor/LICENSES.txt``). Graph views use the 2D force layout (no WebGL needed); chart views use Chart.js, and draw
heatmaps as coloured tables.
"""
from __future__ import annotations

from pathlib import Path

from .viewer import HERE, _script_safe

PAGES = {"graph": ("relmap.html", "relmap.js", ("force-graph.min.js",)),
         "series": ("chart.html", "chart.js", ("chart.umd.js",))}


def render_page(snap: dict) -> str:
    from .publish import dumps
    page_name, app_name, libs = PAGES[snap["kind"]]
    page = (HERE / page_name).read_text(encoding="utf-8")
    page = page.replace("/*STYLES*/", (HERE / "views.css").read_text(encoding="utf-8"))
    page = page.replace("/*LIBS*/", "\n".join(_script_safe((HERE / "vendor" / lib).read_text(encoding="utf-8"))
                                               for lib in libs))
    page = page.replace("/*SNAPSHOT*/", dumps(snap).replace("</", "<\\/"))
    page = page.replace("/*APP*/", _script_safe((HERE / app_name).read_text(encoding="utf-8")))
    return page


def write_page(snap: dict, path: str | Path) -> Path:
    p = Path(path)
    p.write_text(render_page(snap), encoding="utf-8")
    return p
