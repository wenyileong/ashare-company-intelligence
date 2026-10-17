"""Turn a ChartSpec into drawing primitives (pixel coordinates, origin top-left).

Primitives are plain dicts::

    {"type": "line", "x1", "y1", "x2", "y2", "stroke", "width", "dash"}
    {"type": "polyline", "points": [(x, y), ...], "stroke", "width"}
    {"type": "rect", "x", "y", "w", "h", "fill", "stroke"}
    {"type": "marker", "shape": circle|diamond|square, "cx", "cy", "r", "fill", "stroke", "dash"}
    {"type": "text", "x", "y", "text", "anchor": start|middle|end, "size", "colour", "weight"}

Markers and bars carry ``tip`` (tooltip text) and ``meta`` (provenance).
"""
from __future__ import annotations

import math
from datetime import date

from .spec import ChartSpec, PALETTE

FG, MUTED, GRID, AXIS = "#1f2328", "#57606a", "#e6e8eb", "#8c959f"
MARGIN = {"left": 70, "right": 120, "top": 48, "bottom": 54}
MAX_MARKERS = 400


def text_width(text: str, size: float = 11) -> float:
    return sum(size if ord(ch) > 0x2E80 else size * 0.58 for ch in str(text))


def fmt_value(v: float | None, unit: str | None = None) -> str:
    if v is None:
        return "n/a"
    if unit in ("RATIO", "PCT"):
        return f"{v * 100:.1f}%"
    a = abs(v)
    if a >= 1e9:
        return f"{v / 1e9:,.2f}bn"
    if a >= 1e6:
        return f"{v / 1e6:,.1f}m"
    if a >= 1e4:
        return f"{v / 1e3:,.0f}k"
    if a >= 100 or float(v).is_integer():
        return f"{v:,.0f}"
    return f"{v:,.2f}"


def nice_ticks(lo: float, hi: float, n: int = 5) -> list[float]:
    if lo == hi:
        lo, hi = (lo - 1, hi + 1) if lo == 0 else (lo * 0.9, hi * 1.1)
        if lo > hi:
            lo, hi = hi, lo
    span = hi - lo
    raw = span / max(n, 1)
    mag = 10 ** math.floor(math.log10(raw))
    step = next(m * mag for m in (1, 2, 2.5, 5, 10) if m * mag >= raw)
    start = math.floor(lo / step) * step
    ticks = []
    t = start
    while t <= hi + step * 0.5:
        ticks.append(round(t, 10))
        t += step
    return ticks


def _ordinal(x) -> float:
    if isinstance(x, (int, float)):
        return float(x)
    s = str(x)[:10]
    try:
        return float(date.fromisoformat(s).toordinal())
    except ValueError:
        return float("nan")


def _time_ticks(lo: float, hi: float) -> list[tuple[float, str]]:
    d0, d1 = date.fromordinal(int(lo)), date.fromordinal(int(math.ceil(hi)))
    years = d1.year - d0.year
    ticks = []
    if years >= 2:
        step = max(1, math.ceil(years / 8))
        for y in range(d0.year, d1.year + 2, step):
            o = date(y, 1, 1).toordinal()
            if lo <= o <= hi:
                ticks.append((o, str(y)))
        if len(ticks) < 2:
            ticks = [(lo, d0.isoformat()), (hi, d1.isoformat())]
    else:
        y, m = d0.year, d0.month
        while True:
            o = date(y, m, 1).toordinal()
            if o > hi:
                break
            if o >= lo:
                ticks.append((o, f"{y}-{m:02d}"))
            m += 3 if years >= 1 else 1
            if m > 12:
                y, m = y + 1, m - 12
        if not ticks:
            ticks = [(lo, d0.isoformat()), (hi, d1.isoformat())]
    return ticks


def _marker_style(p, colour):
    shape = "diamond" if p.restated else ("square" if p.review in ("ACCEPTED", "CORRECTED") else "circle")
    conf = (p.confidence or "").upper()
    if conf == "HIGH" or p.review in ("ACCEPTED", "CORRECTED"):
        return shape, colour, colour, None
    if conf == "LOW":
        return shape, "#ffffff", colour, (2, 2)
    return shape, "#ffffff", colour, None  # MEDIUM / UNVALIDATED: hollow


def _tip(series_name, p, unit) -> str:
    lines = [f"{series_name}: {fmt_value(p.y, unit)}", f"{p.x}"]
    for k in ("published", "source", "page", "method", "confidence_class", "review", "note"):
        v = (p.meta or {}).get(k)
        if v not in (None, ""):
            lines.append(f"{k.replace('_', ' ')}: {v}")
    if p.restated:
        lines.append("restated in a later report")
    return "\n".join(lines)


def scene(spec: ChartSpec) -> list[dict]:
    W, H = spec.width, spec.height
    prims: list[dict] = [{"type": "rect", "x": 0, "y": 0, "w": W, "h": H, "fill": "#ffffff", "stroke": None}]
    prims.append({"type": "text", "x": 16, "y": 22, "text": spec.title, "anchor": "start", "size": 14,
                  "colour": FG, "weight": "bold"})
    if spec.subtitle:
        prims.append({"type": "text", "x": 16, "y": 38, "text": spec.subtitle, "anchor": "start", "size": 11,
                      "colour": MUTED, "weight": "normal"})
    colours = {s.name: s.colour or PALETTE[i % len(PALETTE)] for i, s in enumerate(spec.series)}
    if spec.graph is not None:                    # v1.8 diagrams
        from .network import DIAGRAMS
        prims += DIAGRAMS[spec.kind](spec)
        if spec.caption:
            prims.append({"type": "text", "x": 16, "y": H - 8, "text": spec.caption, "anchor": "start", "size": 10,
                          "colour": MUTED, "weight": "normal"})
        return prims
    values = [p.y for s in spec.series for p in s.points if p.y is not None]
    if not values:
        prims.append({"type": "text", "x": W / 2, "y": H / 2, "text": "No data to plot", "anchor": "middle",
                      "size": 12, "colour": MUTED, "weight": "normal"})
        return prims
    from .more import LAYOUTS
    if spec.kind == "hbar":
        prims += _hbar(spec, colours, values)
    elif spec.kind in LAYOUTS:
        prims += LAYOUTS[spec.kind](spec, colours)
    else:
        prims += _xy(spec, colours, values)
    if spec.caption:
        prims.append({"type": "text", "x": 16, "y": H - 8, "text": spec.caption, "anchor": "start", "size": 10,
                      "colour": MUTED, "weight": "normal"})
    return prims


def _xy(spec: ChartSpec, colours: dict, values: list[float]) -> list[dict]:
    W, H = spec.width, spec.height
    top = MARGIN["top"] + (14 if spec.subtitle else 0) + (12 if spec.y_label else 0)
    L, R, T, B = MARGIN["left"], W - MARGIN["right"], top, H - MARGIN["bottom"]
    out: list[dict] = []
    band_vals = [v for s in spec.series if s.band for b in s.band if b for v in b if v is not None]
    lo, hi = min(values + band_vals), max(values + band_vals)
    if spec.kind == "bar":
        lo, hi = min(lo, 0.0), max(hi, 0.0)
    yt = nice_ticks(lo, hi)
    y0, y1 = yt[0], yt[-1]
    sy = lambda v: B - (v - y0) / (y1 - y0) * (B - T) if y1 != y0 else (B + T) / 2  # noqa: E731
    for t in yt:
        out.append({"type": "line", "x1": L, "y1": sy(t), "x2": R, "y2": sy(t), "stroke": GRID, "width": 1,
                    "dash": None})
        out.append({"type": "text", "x": L - 6, "y": sy(t) + 4, "text": fmt_value(t, spec.unit), "anchor": "end",
                    "size": 10, "colour": MUTED, "weight": "normal"})
    if spec.y_label:
        out.append({"type": "text", "x": L, "y": T - 8, "text": spec.y_label, "anchor": "start", "size": 10,
                    "colour": MUTED, "weight": "normal"})
    # x scale
    if spec.x_type == "time":
        xs = [_ordinal(p.x) for s in spec.series for p in s.points]
        xs = [x for x in xs if not math.isnan(x)]
        xlo, xhi = min(xs), max(xs)
        if spec.as_of:
            a = _ordinal(spec.as_of)
            if not math.isnan(a):
                xhi = max(xhi, a)
        if xlo == xhi:
            xlo, xhi = xlo - 180, xhi + 180
        pad = (xhi - xlo) * 0.03
        xlo, xhi = xlo - pad, xhi + pad
        sx = lambda x: L + (_ordinal(x) - xlo) / (xhi - xlo) * (R - L)  # noqa: E731
        for o, label in _time_ticks(xlo, xhi):
            px = L + (o - xlo) / (xhi - xlo) * (R - L)
            out.append({"type": "line", "x1": px, "y1": B, "x2": px, "y2": B + 4, "stroke": AXIS, "width": 1,
                        "dash": None})
            out.append({"type": "text", "x": px, "y": B + 17, "text": label, "anchor": "middle", "size": 10,
                        "colour": MUTED, "weight": "normal"})
        band = 0
    else:
        cats = []
        for s in spec.series:
            for p in s.points:
                if p.x not in cats:
                    cats.append(p.x)
        n = max(len(cats), 1)
        band = (R - L) / n
        pos = {c: L + band * (i + 0.5) for i, c in enumerate(cats)}
        sx = lambda x: pos[x]  # noqa: E731
        every = max(1, math.ceil(n / max(1, (R - L) // 70)))
        for i, c in enumerate(cats):
            if i % every == 0:
                out.append({"type": "text", "x": pos[c], "y": B + 17, "text": str(c), "anchor": "middle", "size": 10,
                            "colour": MUTED, "weight": "normal"})
    out.append({"type": "line", "x1": L, "y1": B, "x2": R, "y2": B, "stroke": AXIS, "width": 1, "dash": None})
    if spec.markers and spec.x_type == "time":     # v1.7: events on the time axis
        groups = []
        for m in spec.markers:
            if m.get("group") not in groups:
                groups.append(m.get("group"))
        for m in spec.markers:
            o = _ordinal(m["x"])
            if math.isnan(o) or not (xlo <= o <= xhi):
                continue
            px = sx(m["x"])
            gi = groups.index(m.get("group"))
            col = PALETTE[(gi + 2) % len(PALETTE)]
            out.append({"type": "line", "x1": px, "y1": T, "x2": px, "y2": B, "stroke": "#d0d7de", "width": 1,
                        "dash": (2, 3)})
            out.append({"type": "marker", "shape": "diamond", "cx": px, "cy": B - 6, "r": 4, "fill": col,
                        "stroke": col, "dash": None, "tip": f"{m['x']}  {m.get('group') or ''}\n{m.get('label') or ''}",
                        "meta": m.get("meta") or {}})
    if spec.as_of and spec.x_type == "time":
        px = sx(spec.as_of)
        out.append({"type": "line", "x1": px, "y1": T, "x2": px, "y2": B, "stroke": FG, "width": 1, "dash": (4, 3)})
        out.append({"type": "text", "x": px + 4, "y": T + 10, "text": f"as of {spec.as_of}", "anchor": "start",
                    "size": 10, "colour": FG, "weight": "normal"})
    if spec.kind == "bar":
        k = len(spec.series)
        bw = band * 0.8 / max(k, 1)
        zero = sy(0.0)
        for i, s in enumerate(spec.series):
            for p in s.points:
                if p.y is None:
                    continue
                cx = sx(p.x) - band * 0.4 + bw * i
                top = min(sy(p.y), zero)
                out.append({"type": "rect", "x": cx, "y": top, "w": max(bw - 2, 1), "h": abs(sy(p.y) - zero),
                            "fill": colours[s.name], "stroke": None, "tip": _tip(s.name, p, spec.unit),
                            "meta": p.meta})
    else:
        end_labels: list[list] = []
        for s in spec.series:                      # shaded bands first, under the lines
            if s.band:
                upper = [(sx(p.x), sy(b[1])) for p, b in zip(s.points, s.band) if b and b[1] is not None]
                lower = [(sx(p.x), sy(b[0])) for p, b in zip(s.points, s.band) if b and b[0] is not None]
                if len(upper) > 1 and len(lower) > 1:
                    out.append({"type": "polygon", "points": upper + lower[::-1], "fill": "#cfe3f1", "stroke": None})
        for s in spec.series:
            col = colours[s.name]
            pts = sorted(s.points, key=lambda p: _ordinal(p.x) if spec.x_type == "time" else 0) \
                if spec.x_type == "time" else s.points
            run: list[tuple[float, float]] = []
            for p in pts:
                if p.y is None:          # a gap: end the current line
                    if len(run) > 1:
                        out.append({"type": "polyline", "points": run, "stroke": col, "width": 2})
                    run = []
                    continue
                run.append((sx(p.x), sy(p.y)))
            if len(run) > 1:
                out.append({"type": "polyline", "points": run, "stroke": col, "width": 2})
            drawn = [p for p in pts if p.y is not None]
            if len(drawn) <= MAX_MARKERS:
                for p in drawn:
                    shape, fill, stroke, dash = _marker_style(p, col)
                    out.append({"type": "marker", "shape": shape, "cx": sx(p.x), "cy": sy(p.y), "r": 4,
                                "fill": fill, "stroke": stroke, "dash": dash, "tip": _tip(s.name, p, spec.unit),
                                "meta": p.meta})
            if drawn:  # label at the end of the line (colour is never the only cue)
                last = drawn[-1]
                end_labels.append([sy(last.y) + 4, sx(last.x) + 8, s.name, col])
        # keep end labels at least 12 px apart
        end_labels.sort()
        for i in range(1, len(end_labels)):
            if end_labels[i][0] - end_labels[i - 1][0] < 12:
                end_labels[i][0] = end_labels[i - 1][0] + 12
        for y, x, name, col in end_labels:
            out.append({"type": "text", "x": x, "y": y, "text": name, "anchor": "start", "size": 10, "colour": col,
                        "weight": "bold"})
    return out


def _hbar(spec: ChartSpec, colours: dict, values: list[float]) -> list[dict]:
    W, H = spec.width, spec.height
    s = spec.series[0]
    pts = [p for p in s.points if p.y is not None]
    label_w = min(260, max(text_width(str(p.x), 11) for p in pts) + 12)
    L, R, T = 16 + label_w, W - 90, MARGIN["top"]
    B = H - MARGIN["bottom"] + 20
    lo, hi = min(min(values), 0.0), max(max(values), 0.0)
    xt = nice_ticks(lo, hi, 4)
    x0, x1 = xt[0], xt[-1]
    sx = lambda v: L + (v - x0) / (x1 - x0) * (R - L) if x1 != x0 else L  # noqa: E731
    out: list[dict] = []
    for t in xt:
        out.append({"type": "line", "x1": sx(t), "y1": T, "x2": sx(t), "y2": B, "stroke": GRID, "width": 1,
                    "dash": None})
        out.append({"type": "text", "x": sx(t), "y": B + 14, "text": fmt_value(t, spec.unit), "anchor": "middle",
                    "size": 10, "colour": MUTED, "weight": "normal"})
    n = max(len(s.points), 1)
    band = (B - T) / n
    col = colours[s.name]
    for i, p in enumerate(s.points):
        cy = T + band * i
        out.append({"type": "text", "x": L - 8, "y": cy + band / 2 + 4, "text": str(p.x), "anchor": "end",
                    "size": 11, "colour": FG, "weight": "normal"})
        if p.y is None:
            out.append({"type": "text", "x": L + 4, "y": cy + band / 2 + 4, "text": "not disclosed",
                        "anchor": "start", "size": 10, "colour": MUTED, "weight": "normal"})
            continue
        left, right = sorted((sx(0.0), sx(p.y)))
        fill = col if (p.confidence or "HIGH").upper() != "LOW" else "#ffffff"
        out.append({"type": "rect", "x": left, "y": cy + band * 0.15, "w": max(right - left, 1),
                    "h": band * 0.7, "fill": fill, "stroke": col, "tip": _tip(s.name, p, spec.unit), "meta": p.meta})
        out.append({"type": "text", "x": right + 6, "y": cy + band / 2 + 4, "text": fmt_value(p.y, spec.unit),
                    "anchor": "start", "size": 10, "colour": FG, "weight": "normal"})
    return out
