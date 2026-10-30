"""The offline topology viewer: one HTML file with the snapshot and the libraries inside (v2.1, renderer R2).

The page is the NVF Topology Tester v0.1's (``viewer/index.html``, ``app.js`` and ``styles.css``), adapted to read
the snapshot instead of building its graph. The libraries are bundled at pinned versions (``viewer/vendor``, licences
in ``vendor/LICENSES.txt``), so the file opens from disk with no server and no network (finding P3)."""
from __future__ import annotations

from pathlib import Path

HERE = Path(__file__).resolve().parent / "viewer"
LIBRARIES = ("3d-force-graph.min.js", "force-graph.min.js", "chart.umd.js")


def _script_safe(text: str) -> str:
    """Text that cannot end the <script> element it is placed in."""
    return text.replace("</", "<\\/").replace("<!--", "<\\!--")


def render_viewer(snap: dict) -> str:
    from .snapshot import dumps
    page = (HERE / "index.html").read_text(encoding="utf-8")
    page = page.replace("/*STYLES*/", (HERE / "styles.css").read_text(encoding="utf-8"))
    for lib in LIBRARIES:
        page = page.replace(f"/*LIB:{lib}*/", _script_safe((HERE / "vendor" / lib).read_text(encoding="utf-8")))
    # the snapshot's JSON is data inside a script element: only "</" needs care, and JSON allows "<\/"
    page = page.replace("/*SNAPSHOT*/", dumps(snap).replace("</", "<\\/"))
    page = page.replace("/*APP*/", _script_safe((HERE / "app.js").read_text(encoding="utf-8")))
    return page


def write_viewer(snap: dict, path: str | Path) -> Path:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(render_viewer(snap), encoding="utf-8")
    return p


def check_libraries() -> list[str]:
    """Libraries missing from the installed program (the viewer then says so in the page)."""
    return [lib for lib in LIBRARIES if not (HERE / "vendor" / lib).exists()]
