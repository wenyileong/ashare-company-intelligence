"""Optional matplotlib renderer for publication figures and PNG export.

matplotlib is not part of the Windows build; this module is used only when
it is installed (``pip install matplotlib``) in a source installation.
"""
from __future__ import annotations

from .layout import _ordinal, fmt_value
from .spec import ChartSpec, PALETTE


def available() -> bool:
    try:
        import matplotlib  # noqa: F401
        return True
    except Exception:
        return False


SUPPORTED = ("line", "bar", "hbar", "scatter", "hist")
CJK_FONTS = ["Microsoft YaHei", "SimHei", "PingFang SC", "Noto Sans CJK SC", "Source Han Sans SC",
             "WenQuanYi Zen Hei", "Arial Unicode MS", "DejaVu Sans"]


def render_png(spec: ChartSpec, path: str, dpi: int = 200) -> str:
    if spec.kind not in SUPPORTED or spec.graph is not None:
        raise NotImplementedError(f"the matplotlib renderer does not draw '{spec.kind}' charts; use the SVG")
    import warnings
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    matplotlib.rcParams["font.sans-serif"] = CJK_FONTS
    matplotlib.rcParams["axes.unicode_minus"] = False
    warnings.filterwarnings("ignore", message="Glyph .* missing from font")
    from datetime import date
    fig, ax = plt.subplots(figsize=(spec.width / 100, spec.height / 100))
    for i, s in enumerate(spec.series):
        col = s.colour or PALETTE[i % len(PALETTE)]
        if spec.kind == "scatter":
            ax.scatter([p.x for p in s.points if p.y is not None], [p.y for p in s.points if p.y is not None],
                       s=12, color=col)
            continue
        if spec.kind == "hist":
            ax.hist([p.y for p in s.points if p.y is not None], bins=spec.bins, color=col)
            continue
        if spec.kind == "hbar":
            pts = [p for p in s.points if p.y is not None]
            ax.barh([str(p.x) for p in pts][::-1], [p.y for p in pts][::-1], color=col)
            continue
        if spec.x_type == "time":
            xs = [date.fromordinal(int(_ordinal(p.x))) for p in s.points]
        else:
            xs = [str(p.x) for p in s.points]
        ys = [p.y if p.y is not None else float("nan") for p in s.points]
        if spec.kind == "bar":
            ax.bar(xs, ys, color=col, label=s.name)
        else:
            ax.plot(xs, ys, color=col, marker="o", label=s.name)
    ax.set_title(spec.title, loc="left", fontsize=11)
    ax.yaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda v, _: fmt_value(v, spec.unit)))
    if len(spec.series) > 1:
        ax.legend(frameon=False)
    if spec.caption:
        fig.text(0.01, 0.01, spec.caption, fontsize=7, color="#57606a")
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    fig.tight_layout()
    fig.savefig(path, dpi=dpi)
    plt.close(fig)
    return path
