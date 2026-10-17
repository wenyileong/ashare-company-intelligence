"""SVG renderer: paints the primitives produced by ``layout.scene``."""
from __future__ import annotations

from html import escape

from .layout import scene
from .spec import ChartSpec

FONT = "system-ui, -apple-system, 'Segoe UI', 'Microsoft YaHei', 'PingFang SC', sans-serif"


def _n(v: float) -> str:
    return f"{v:.1f}".rstrip("0").rstrip(".")


def _dash(d) -> str:
    return f' stroke-dasharray="{d[0]},{d[1]}"' if d else ""


def _title(p) -> str:
    return f"<title>{escape(p['tip'])}</title>" if p.get("tip") else ""


def render_svg(spec: ChartSpec) -> str:
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{spec.width}" height="{spec.height}" '
           f'viewBox="0 0 {spec.width} {spec.height}" font-family="{FONT}" role="img" '
           f'aria-label="{escape(spec.title)}">']
    for p in scene(spec):
        t = p["type"]
        if t == "rect":
            fill = p.get("fill") or "none"
            stroke = f' stroke="{p["stroke"]}"' if p.get("stroke") else ""
            body = _title(p)
            out.append(f'<rect x="{_n(p["x"])}" y="{_n(p["y"])}" width="{_n(p["w"])}" height="{_n(p["h"])}" '
                       f'fill="{fill}"{stroke}>{body}</rect>' if body else
                       f'<rect x="{_n(p["x"])}" y="{_n(p["y"])}" width="{_n(p["w"])}" height="{_n(p["h"])}" '
                       f'fill="{fill}"{stroke}/>')
        elif t == "line":
            out.append(f'<line x1="{_n(p["x1"])}" y1="{_n(p["y1"])}" x2="{_n(p["x2"])}" y2="{_n(p["y2"])}" '
                       f'stroke="{p["stroke"]}" stroke-width="{p["width"]}"{_dash(p.get("dash"))}/>')
        elif t == "polyline":
            pts = " ".join(f"{_n(x)},{_n(y)}" for x, y in p["points"])
            out.append(f'<polyline points="{pts}" fill="none" stroke="{p["stroke"]}" stroke-width="{p["width"]}" '
                       f'stroke-linejoin="round"/>')
        elif t == "polygon":
            pts = " ".join(f"{_n(x)},{_n(y)}" for x, y in p["points"])
            out.append(f'<polygon points="{pts}" fill="{p.get("fill") or "none"}" stroke="{p.get("stroke") or "none"}"/>')
        elif t == "marker":
            cx, cy, r = p["cx"], p["cy"], p["r"]
            attrs = f'fill="{p["fill"]}" stroke="{p["stroke"]}" stroke-width="1.5"{_dash(p.get("dash"))}'
            if p["shape"] == "diamond":
                shape = (f'<polygon points="{_n(cx)},{_n(cy - r - 1)} {_n(cx + r + 1)},{_n(cy)} {_n(cx)},{_n(cy + r + 1)} '
                         f'{_n(cx - r - 1)},{_n(cy)}" {attrs}>')
                close = "</polygon>"
            elif p["shape"] == "square":
                shape = f'<rect x="{_n(cx - r)}" y="{_n(cy - r)}" width="{_n(2 * r)}" height="{_n(2 * r)}" {attrs}>'
                close = "</rect>"
            else:
                shape = f'<circle cx="{_n(cx)}" cy="{_n(cy)}" r="{_n(r)}" {attrs}>'
                close = "</circle>"
            out.append(shape + _title(p) + close)
        elif t == "text":
            anchor = p.get("anchor", "start")
            weight = ' font-weight="bold"' if p.get("weight") == "bold" else ""
            out.append(f'<text x="{_n(p["x"])}" y="{_n(p["y"])}" font-size="{p["size"]}" fill="{p["colour"]}" '
                       f'text-anchor="{anchor}"{weight}>{escape(str(p["text"]))}</text>')
    out.append("</svg>")
    return "\n".join(out)
