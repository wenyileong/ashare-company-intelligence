"""Dataset explorer (v1.7): summaries and charts of a built panel."""
from __future__ import annotations

import csv
import math
import statistics

from .charts.spec import ChartSpec, Series, Point

ID_COLUMNS = ("code", "name", "period", "measure_date", "cutoff")


def _num(v):
    if v in (None, ""):
        return None
    try:
        x = float(v)
        return None if math.isnan(x) else x
    except (TypeError, ValueError):
        return v


def load_panel(path: str) -> list[dict]:
    with open(path, encoding="utf-8-sig", newline="") as fh:
        rows = list(csv.DictReader(fh))
    return [{k: (v if k in ID_COLUMNS or k.endswith("__published") else _num(v)) for k, v in r.items()} for r in rows]


def numeric_columns(rows: list[dict]) -> list[str]:
    cols = [c for c in (rows[0].keys() if rows else []) if c not in ID_COLUMNS and not c.endswith("__published")]
    return [c for c in cols if any(isinstance(r.get(c), float) for r in rows)
            and all(r.get(c) is None or isinstance(r.get(c), float) for r in rows)]


def summary(rows: list[dict]) -> list[dict]:
    out = []
    for c in numeric_columns(rows):
        vals = [r[c] for r in rows if r.get(c) is not None]
        if not vals:
            out.append({"variable": c, "n": 0, "missing": len(rows)})
            continue
        q = statistics.quantiles(vals, n=4) if len(vals) > 1 else [vals[0]] * 3
        out.append({"variable": c, "n": len(vals), "missing": len(rows) - len(vals),
                    "mean": statistics.fmean(vals), "sd": statistics.stdev(vals) if len(vals) > 1 else None,
                    "min": min(vals), "p25": q[0], "median": q[1], "p75": q[2], "max": max(vals)})
    return out


def correlations(rows: list[dict], cols: list[str] | None = None) -> list[dict]:
    """Pairwise Pearson correlations on complete pairs."""
    cols = cols or numeric_columns(rows)
    out = []
    for i, a in enumerate(cols):
        row = {"variable": a}
        for b in cols:
            pairs = [(r[a], r[b]) for r in rows if r.get(a) is not None and r.get(b) is not None]
            if len(pairs) < 3:
                row[b] = None
                continue
            xs, ys = zip(*pairs)
            try:
                row[b] = round(statistics.correlation(xs, ys), 3)
            except statistics.StatisticsError:
                row[b] = None
        out.append(row)
    return out


def chart_for(rows: list[dict], kind: str, x: str | None = None, y: str | None = None,
              highlight: str | None = None) -> ChartSpec:
    if kind == "hist":
        vals = [Point(r["code"], r.get(x), {"period": r["period"]}) for r in rows if isinstance(r.get(x), float)]
        return ChartSpec("hist", f"Distribution of {x}", [Series(x, vals)], x_label=x,
                         caption=f"{len(vals)} non-missing of {len(rows)} rows")
    if kind == "box":
        pts = [Point(str(r["period"])[:4] if len(str(r["period"])) >= 4 else r["period"], r.get(x))
               for r in rows if isinstance(r.get(x), float)]
        pts.sort(key=lambda p: p.x)
        return ChartSpec("box", f"{x} by year", [Series(x, pts)], y_label=x, caption="Box: quartiles; whiskers: "
                         "minimum and maximum")
    if kind == "scatter":
        pts = [Point(r[x], r[y], {"label": r["code"], "period": r["period"]}) for r in rows
               if isinstance(r.get(x), float) and isinstance(r.get(y), float)]
        return ChartSpec("scatter", f"{y} against {x}", [Series("observations", pts)], fit=True, x_label=x,
                         y_label=y, highlight=highlight, caption=f"{len(pts)} complete pairs; dashed: least squares")
    if kind == "coverage":
        cols = numeric_columns(rows) + [c for c in (rows[0].keys() if rows else [])
                                        if c not in ID_COLUMNS and not c.endswith("__published")
                                        and c not in numeric_columns(rows)]
        years = sorted({str(r["period"])[:4] for r in rows})
        pts = []
        for c in cols:
            for yy in years:
                rs = [r for r in rows if str(r["period"])[:4] == yy]
                share = sum(1 for r in rs if r.get(c) not in (None, "")) / len(rs) if rs else None
                pts.append(Point(yy, share, {"row": c}))
        spec = ChartSpec("heatmap", "Coverage: share of rows with a value", [Series("coverage", pts)],
                         caption="Darker = more complete; white = missing")
        spec.height = max(200, 80 + 18 * len(cols))
        return spec
    raise ValueError("kind must be hist, box, scatter or coverage")
