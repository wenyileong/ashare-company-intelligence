"""Additional chart layouts (v1.7): scatter with fit, histogram, box plot,
coverage heatmap and stacked bars. Same primitives as ``layout``."""
from __future__ import annotations

import math
import statistics

from .layout import FG, MUTED, GRID, AXIS, MARGIN, nice_ticks, fmt_value, text_width
from .spec import ChartSpec, PALETTE


def _axes(out, L, R, T, B, ylo, yhi, unit, xticks=None, xunit=None, xlo=None, xhi=None):
    yt = nice_ticks(ylo, yhi)
    y0, y1 = yt[0], yt[-1]
    sy = lambda v: B - (v - y0) / (y1 - y0) * (B - T) if y1 != y0 else (B + T) / 2  # noqa: E731
    for t in yt:
        out.append({"type": "line", "x1": L, "y1": sy(t), "x2": R, "y2": sy(t), "stroke": GRID, "width": 1, "dash": None})
        out.append({"type": "text", "x": L - 6, "y": sy(t) + 4, "text": fmt_value(t, unit), "anchor": "end",
                    "size": 10, "colour": MUTED, "weight": "normal"})
    out.append({"type": "line", "x1": L, "y1": B, "x2": R, "y2": B, "stroke": AXIS, "width": 1, "dash": None})
    sx = None
    if xlo is not None:
        xt = nice_ticks(xlo, xhi)
        x0, x1 = xt[0], xt[-1]
        sx = lambda v: L + (v - x0) / (x1 - x0) * (R - L) if x1 != x0 else (L + R) / 2  # noqa: E731
        for t in xt:
            out.append({"type": "line", "x1": sx(t), "y1": B, "x2": sx(t), "y2": B + 4, "stroke": AXIS, "width": 1,
                        "dash": None})
            out.append({"type": "text", "x": sx(t), "y": B + 17, "text": fmt_value(t, xunit), "anchor": "middle",
                        "size": 10, "colour": MUTED, "weight": "normal"})
    return sy, sx


def _frame(spec):
    top = MARGIN["top"] + (14 if spec.subtitle else 0) + (12 if spec.y_label else 0)
    return MARGIN["left"], spec.width - 40, top, spec.height - MARGIN["bottom"]


def _labels(out, spec, L, R, B, T):
    if spec.x_label:
        out.append({"type": "text", "x": (L + R) / 2, "y": B + 34, "text": spec.x_label, "anchor": "middle",
                    "size": 10, "colour": MUTED, "weight": "normal"})
    if spec.y_label:
        out.append({"type": "text", "x": L, "y": T - 8, "text": spec.y_label, "anchor": "start", "size": 10,
                    "colour": MUTED, "weight": "normal"})


def ols(xs, ys):
    n = len(xs)
    if n < 3:
        return None
    mx, my = sum(xs) / n, sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    if sxx == 0:
        return None
    b = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sxx
    a = my - b * mx
    ss_res = sum((y - a - b * x) ** 2 for x, y in zip(xs, ys))
    ss_tot = sum((y - my) ** 2 for y in ys)
    return {"a": a, "b": b, "r2": 1 - ss_res / ss_tot if ss_tot else None, "n": n}


def scatter(spec: ChartSpec, colours: dict) -> list[dict]:
    out: list[dict] = []
    L, R, T, B = _frame(spec)
    pts = [(s, p) for s in spec.series for p in s.points if p.y is not None and isinstance(p.x, (int, float))]
    if not pts:
        return out
    xs, ys = [p.x for _, p in pts], [p.y for _, p in pts]
    sy, sx = _axes(out, L, R, T, B, min(ys), max(ys), spec.unit, xlo=min(xs), xhi=max(xs),
                   xunit=(spec.series[0].unit if spec.series else None))
    _labels(out, spec, L, R, B, T)
    big = len(pts) > 2000
    for s, p in pts:
        hi = spec.highlight is not None and (p.meta or {}).get("label") == spec.highlight
        col = colours[s.name]
        out.append({"type": "marker", "shape": "circle", "cx": sx(p.x), "cy": sy(p.y), "r": 6 if hi else (2 if big else 3.5),
                    "fill": "#D55E00" if hi else col, "stroke": "#000000" if hi else col, "dash": None,
                    "tip": "\n".join([str((p.meta or {}).get("label", "")), f"x: {fmt_value(p.x)}",
                                      f"y: {fmt_value(p.y, spec.unit)}"] +
                                     [f"{k}: {v}" for k, v in (p.meta or {}).items() if k not in ("label",)]),
                    "meta": p.meta})
        if hi:
            out.append({"type": "text", "x": sx(p.x) + 9, "y": sy(p.y) - 6, "text": str(spec.highlight),
                        "anchor": "start", "size": 11, "colour": FG, "weight": "bold"})
    if spec.fit:
        f = ols(xs, ys)
        if f:
            x0, x1 = min(xs), max(xs)
            out.append({"type": "line", "x1": sx(x0), "y1": sy(f["a"] + f["b"] * x0), "x2": sx(x1),
                        "y2": sy(f["a"] + f["b"] * x1), "stroke": FG, "width": 1.5, "dash": (6, 3)})
            sign = "−" if f["b"] < 0 else "+"
            out.append({"type": "text", "x": R, "y": T + 4, "text": f"y = {f['a']:.3g} {sign} {abs(f['b']):.3g}x   "
                        f"R² = {f['r2']:.2f}   n = {f['n']}" if f["r2"] is not None else "", "anchor": "end",
                        "size": 10, "colour": FG, "weight": "normal"})
    return out


def histogram(spec: ChartSpec, colours: dict) -> list[dict]:
    out: list[dict] = []
    L, R, T, B = _frame(spec)
    vals = [p.y for s in spec.series[:1] for p in s.points if p.y is not None]
    if not vals:
        return out
    lo, hi = min(vals), max(vals)
    if lo == hi:
        lo, hi = lo - 0.5, hi + 0.5
    k = max(1, spec.bins)
    width = (hi - lo) / k
    counts = [0] * k
    for v in vals:
        counts[min(k - 1, int((v - lo) / width))] += 1
    sy, sx = _axes(out, L, R, T, B, 0, max(counts), "COUNT", xlo=lo, xhi=hi, xunit=spec.unit)
    _labels(out, spec, L, R, B, T)
    col = colours[spec.series[0].name]
    for i, n in enumerate(counts):
        a, b = lo + i * width, lo + (i + 1) * width
        out.append({"type": "rect", "x": sx(a), "y": sy(n), "w": max(sx(b) - sx(a) - 1, 1), "h": sy(0) - sy(n),
                    "fill": col, "stroke": None, "tip": f"{fmt_value(a, spec.unit)} to {fmt_value(b, spec.unit)}: {n}",
                    "meta": {"from": a, "to": b, "count": n}})
    _mark_value(out, spec, sx, T, B)
    med = statistics.median(vals)
    out.append({"type": "text", "x": R, "y": T + 4, "text": f"n = {len(vals)}   median = {fmt_value(med, spec.unit)}",
                "anchor": "end", "size": 10, "colour": FG, "weight": "normal"})
    return out


def _mark_value(out, spec, sx, T, B):
    if isinstance(spec.highlight, (int, float)):
        x = sx(spec.highlight)
        out.append({"type": "line", "x1": x, "y1": T, "x2": x, "y2": B, "stroke": "#D55E00", "width": 2, "dash": None})
        out.append({"type": "text", "x": x + 4, "y": T + 18, "text": f"company: {fmt_value(spec.highlight, spec.unit)}",
                    "anchor": "start", "size": 10, "colour": "#D55E00", "weight": "bold"})


def five(vals):
    v = sorted(vals)
    n = len(v)

    def q(p):
        i = p * (n - 1)
        lo, hi = math.floor(i), math.ceil(i)
        return v[lo] + (v[hi] - v[lo]) * (i - lo)
    return {"min": v[0], "q1": q(0.25), "median": q(0.5), "q3": q(0.75), "max": v[-1], "n": n}


def boxplot(spec: ChartSpec, colours: dict) -> list[dict]:
    out: list[dict] = []
    L, R, T, B = _frame(spec)
    groups: dict = {}
    for p in spec.series[0].points:
        if p.y is not None:
            groups.setdefault(p.x, []).append(p.y)
    if not groups:
        return out
    cats = list(groups)
    allv = [v for vs in groups.values() for v in vs]
    sy, _ = _axes(out, L, R, T, B, min(allv), max(allv), spec.unit)
    _labels(out, spec, L, R, B, T)
    band = (R - L) / len(cats)
    col = colours[spec.series[0].name]
    for i, c in enumerate(cats):
        st = five(groups[c])
        cx = L + band * (i + 0.5)
        w = min(40, band * 0.5)
        tip = (f"{c}: n = {st['n']}\nmedian {fmt_value(st['median'], spec.unit)}\nQ1 {fmt_value(st['q1'], spec.unit)}"
               f"  Q3 {fmt_value(st['q3'], spec.unit)}\nmin {fmt_value(st['min'], spec.unit)}  max "
               f"{fmt_value(st['max'], spec.unit)}")
        out.append({"type": "line", "x1": cx, "y1": sy(st["min"]), "x2": cx, "y2": sy(st["max"]), "stroke": col,
                    "width": 1, "dash": None})
        out.append({"type": "rect", "x": cx - w / 2, "y": sy(st["q3"]), "w": w, "h": max(sy(st["q1"]) - sy(st["q3"]), 1),
                    "fill": "#ffffff", "stroke": col, "tip": tip, "meta": {"category": c, **st}})
        out.append({"type": "line", "x1": cx - w / 2, "y1": sy(st["median"]), "x2": cx + w / 2, "y2": sy(st["median"]),
                    "stroke": col, "width": 2.5, "dash": None})
        if i % max(1, math.ceil(len(cats) / 12)) == 0:
            out.append({"type": "text", "x": cx, "y": B + 17, "text": str(c), "anchor": "middle", "size": 10,
                        "colour": MUTED, "weight": "normal"})
    if isinstance(spec.highlight, (int, float)):
        y = sy(spec.highlight)
        out.append({"type": "line", "x1": L, "y1": y, "x2": R, "y2": y, "stroke": "#D55E00", "width": 1.5, "dash": (4, 3)})
    return out


def heatmap(spec: ChartSpec, colours: dict) -> list[dict]:
    """Points: x = column label, y = value in [0, 1], meta['row'] = row label."""
    out: list[dict] = []
    rows, cols, cells = [], [], {}
    for p in spec.series[0].points:
        r = (p.meta or {}).get("row")
        if r not in rows:
            rows.append(r)
        if p.x not in cols:
            cols.append(p.x)
        cells[(r, p.x)] = p
    if not rows:
        return out
    label_w = min(200, max(text_width(str(r), 10) for r in rows) + 10)
    L, R = 16 + label_w, spec.width - 20
    T, B = MARGIN["top"] + (14 if spec.subtitle else 0), spec.height - 40
    cw, ch = (R - L) / len(cols), (B - T) / len(rows)
    for i, r in enumerate(rows):
        out.append({"type": "text", "x": L - 6, "y": T + ch * (i + 0.5) + 4, "text": str(r), "anchor": "end",
                    "size": 10, "colour": FG, "weight": "normal"})
        for j, c in enumerate(cols):
            p = cells.get((r, c))
            v = p.y if p else None
            if v is None:
                fill = "#ffffff"
            else:   # white -> blue (#0072B2), sequential and colour-blind safe
                t = max(0.0, min(1.0, v))
                fill = "#%02x%02x%02x" % (round(255 - (255 - 0x00) * t), round(255 - (255 - 0x72) * t),
                                          round(255 - (255 - 0xB2) * t))
            out.append({"type": "rect", "x": L + cw * j, "y": T + ch * i, "w": max(cw - 1, 1), "h": max(ch - 1, 1),
                        "fill": fill, "stroke": GRID, "tip": f"{r} · {c}: " + ("missing" if v is None else f"{v:.0%}"),
                        "meta": {"row": r, "column": c, "value": v}})
    every = max(1, math.ceil(len(cols) / max(1, (R - L) // 40)))
    for j, c in enumerate(cols):
        if j % every == 0:
            out.append({"type": "text", "x": L + cw * (j + 0.5), "y": B + 14, "text": str(c), "anchor": "middle",
                        "size": 10, "colour": MUTED, "weight": "normal"})
    return out


def stacked(spec: ChartSpec, colours: dict) -> list[dict]:
    out: list[dict] = []
    L, T, B = MARGIN["left"], MARGIN["top"] + (14 if spec.subtitle else 0), spec.height - MARGIN["bottom"]
    R = spec.width - MARGIN["right"]
    cats = []
    for s in spec.series:
        for p in s.points:
            if p.x not in cats:
                cats.append(p.x)
    totals = {c: sum((p.y or 0) for s in spec.series for p in s.points if p.x == c and (p.y or 0) > 0) for c in cats}
    top = 1.0 if spec.percent else max(totals.values() or [1])
    sy, _ = _axes(out, L, R, T, B, 0, top, "RATIO" if spec.percent else spec.unit)
    band = (R - L) / max(len(cats), 1)
    for i, c in enumerate(cats):
        base = 0.0
        cx = L + band * i + band * 0.15
        for s in spec.series:
            p = next((p for p in s.points if p.x == c), None)
            if not p or not p.y or p.y <= 0:
                continue
            v = p.y / totals[c] if spec.percent and totals[c] else p.y
            out.append({"type": "rect", "x": cx, "y": sy(base + v), "w": band * 0.7, "h": sy(base) - sy(base + v),
                        "fill": colours[s.name], "stroke": "#ffffff",
                        "tip": f"{c} · {s.name}: {fmt_value(p.y, spec.unit)}" + (f" ({v:.1%})" if spec.percent else ""),
                        "meta": p.meta})
            base += v
        out.append({"type": "text", "x": cx + band * 0.35, "y": B + 17, "text": str(c), "anchor": "middle", "size": 10,
                    "colour": MUTED, "weight": "normal"})
    for k, s in enumerate(spec.series):     # legend on the right (with text, not colour alone)
        y = T + 14 * k
        out.append({"type": "rect", "x": R + 10, "y": y - 8, "w": 10, "h": 10, "fill": colours[s.name], "stroke": None})
        out.append({"type": "text", "x": R + 24, "y": y + 1, "text": s.name, "anchor": "start", "size": 10,
                    "colour": FG, "weight": "normal"})
    return out


LAYOUTS = {"scatter": scatter, "hist": histogram, "box": boxplot, "heatmap": heatmap, "stacked": stacked}
