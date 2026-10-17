"""Tk renderer: paints the same primitives on a Tkinter canvas, with
provenance tooltips on hover and an optional click callback."""
from __future__ import annotations

from .layout import scene
from .spec import ChartSpec

FONT = "Segoe UI"


def _font(p):
    return (FONT, -int(p["size"] * 1.0), "bold" if p.get("weight") == "bold" else "normal")


def render_tk(canvas, spec: ChartSpec, on_click=None) -> list[dict]:
    """Draw ``spec`` on ``canvas`` (cleared first). Returns the primitives drawn."""
    canvas.delete("all")
    canvas.configure(width=spec.width, height=spec.height, background="#ffffff")
    prims = scene(spec)
    hot = []   # (x0, y0, x1, y1, primitive) for tooltips
    for p in prims:
        t = p["type"]
        if t == "rect":
            canvas.create_rectangle(p["x"], p["y"], p["x"] + p["w"], p["y"] + p["h"], fill=p.get("fill") or "",
                                    outline=p.get("stroke") or "")
            if p.get("tip"):
                hot.append((p["x"], p["y"], p["x"] + p["w"], p["y"] + p["h"], p))
        elif t == "line":
            canvas.create_line(p["x1"], p["y1"], p["x2"], p["y2"], fill=p["stroke"], width=p["width"],
                               dash=p.get("dash") or "")
        elif t == "polyline":
            flat = [c for xy in p["points"] for c in xy]
            canvas.create_line(*flat, fill=p["stroke"], width=p["width"], joinstyle="round")
        elif t == "polygon":
            flat = [c for xy in p["points"] for c in xy]
            canvas.create_polygon(*flat, fill=p.get("fill") or "", outline=p.get("stroke") or "")
        elif t == "marker":
            cx, cy, r = p["cx"], p["cy"], p["r"]
            kw = dict(fill=p["fill"], outline=p["stroke"], width=1.5, dash=p.get("dash") or "")
            if p["shape"] == "diamond":
                canvas.create_polygon(cx, cy - r - 1, cx + r + 1, cy, cx, cy + r + 1, cx - r - 1, cy, **kw)
            elif p["shape"] == "square":
                canvas.create_rectangle(cx - r, cy - r, cx + r, cy + r, **kw)
            else:
                canvas.create_oval(cx - r, cy - r, cx + r, cy + r, **kw)
            hot.append((cx - r - 3, cy - r - 3, cx + r + 3, cy + r + 3, p))
        elif t == "text":
            anchor = {"start": "w", "middle": "center", "end": "e"}[p.get("anchor", "start")]
            canvas.create_text(p["x"], p["y"] - p["size"] * 0.35, text=p["text"], fill=p["colour"], font=_font(p),
                               anchor=anchor)
    tip = {"id": None, "box": None}

    def hide(_e=None):
        for k in ("id", "box"):
            if tip[k]:
                canvas.delete(tip[k])
                tip[k] = None

    def find(x, y):
        for x0, y0, x1, y1, p in reversed(hot):
            if x0 <= x <= x1 and y0 <= y <= y1:
                return p
        return None

    def motion(e):
        hide()
        p = find(e.x, e.y)
        if not p:
            return
        tx = e.x + 14 if e.x < spec.width - 260 else e.x - 260
        tip["id"] = canvas.create_text(tx + 6, e.y + 6, text=p["tip"], anchor="nw", font=(FONT, -11),
                                       fill="#1f2328")
        x0, y0, x1, y1 = canvas.bbox(tip["id"])
        tip["box"] = canvas.create_rectangle(x0 - 6, y0 - 4, x1 + 6, y1 + 4, fill="#fffbe6", outline="#d0b000")
        canvas.tag_raise(tip["id"])

    def click(e):
        p = find(e.x, e.y)
        if p and on_click:
            on_click(p.get("meta") or {})

    canvas.bind("<Motion>", motion)
    canvas.bind("<Leave>", hide)
    canvas.bind("<Button-1>", click)
    return prims
