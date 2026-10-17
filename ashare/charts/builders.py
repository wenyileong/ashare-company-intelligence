"""Chart builders: database views -> ChartSpec (v1.5)."""
from __future__ import annotations

import json
from collections import Counter

from .spec import ChartSpec, Series, Point

METRIC_LABELS = {"revenue": "Revenue", "net_profit": "Net profit", "net_profit_parent": "Net profit (parent)",
                 "operating_profit": "Operating profit", "total_assets": "Total assets",
                 "total_liabilities": "Total liabilities", "equity": "Equity", "operating_cash_flow": "Operating cash flow",
                 "rd_expense": "R&D expense", "cash": "Cash"}


def _company_name(code: str) -> str:
    from ..models import SessionLocal, Company
    s = SessionLocal()
    try:
        c = s.query(Company).filter_by(security_code=str(code).zfill(6)).first()
        return f"{c.security_code} {c.short_name_cn or c.legal_name_cn or ''}".strip() if c else str(code)
    finally:
        s.close()


def financial_chart(code: str, metrics: list[str] | None = None, period_type: str | None = "FY",
                    as_of: str | None = None, vintage: str = "latest") -> ChartSpec:
    from ..intelligence import financial_series
    metrics = metrics or ["revenue", "net_profit_parent"]
    series, sources = [], set()
    for m in metrics:
        pts = []
        for r in financial_series(code, m, as_of=as_of, period_type=period_type, vintage=vintage):
            pts.append(Point(r["period"], r["value"], meta={
                "published": r.get("published"), "source": r.get("source_title"), "method": r.get("method"),
                "confidence_class": r.get("confidence_class"), "review": r.get("review"), "fact_id": r.get("fact_id"),
                "table": "financial_facts", "row_id": r.get("fact_id")},
                confidence=r.get("confidence_class"), restated=bool(r.get("restated")), review=r.get("review")))
            if r.get("source_title"):
                sources.add(r["source_title"])
        series.append(Series(METRIC_LABELS.get(m, m), pts))
    caption = f"Source: {len(sources)} report(s) via CNINFO; {vintage} vintage" + (f"; as of {as_of}" if as_of else "")
    return ChartSpec("line", f"{_company_name(code)}: {', '.join(METRIC_LABELS.get(m, m) for m in metrics)}",
                     series, x_type="time", unit="CNY", y_label="CNY", as_of=as_of,
                     subtitle="Filled = high confidence, hollow = medium, dashed = low, diamond = restated, "
                              "square = reviewed",
                     caption=caption)


def segment_chart(code: str, dimension: str = "PRODUCT", period: str | None = None,
                  as_of: str | None = None) -> ChartSpec:
    from ..segments import segments
    v = segments(code, period=period, dimension=dimension, as_of=as_of)
    d = (v.get("dimensions") or {}).get(dimension.upper()) or {}
    pts = [Point(s["name"], s["revenue"], meta={"share": None if s.get("share") is None else f"{s['share']:.1%}",
                                                 "page": s.get("page"), "method": s.get("method"),
                                                 "table": "segment_observations", "row_id": s.get("id")})
           for s in d.get("segments", [])]
    spec = ChartSpec("hbar", f"{_company_name(code)}: revenue by {dimension.lower()} ({v.get('period') or 'n/a'})",
                     [Series("Revenue", pts)], unit="CNY",
                     caption=f"Source: annual/interim report segment tables; period {v.get('period')}")
    spec.height = max(160, 90 + 30 * len(pts))
    return spec


def history_chart(code: str, items: list[str] | None = None) -> ChartSpec:
    """R&D, workforce or patent items over time, each point with its source page."""
    from ..models import SessionLocal, Company, HumanCapitalObservation, Disclosure
    from ..human_capital import ITEMS
    from ..review import reviewed_rows
    items = items or ["rd_investment"]
    s = SessionLocal()
    try:
        c = s.query(Company).filter_by(security_code=str(code).zfill(6)).first()
        rows = [] if not c else reviewed_rows(s, "human_capital_observations", s.query(HumanCapitalObservation).filter(
            HumanCapitalObservation.company_id == c.id, HumanCapitalObservation.item.in_(items)).all())
        pub = {d.id: d.announcement_date for d in s.query(Disclosure).filter(
            Disclosure.id.in_({r.disclosure_id for r in rows if r.disclosure_id}))} if rows else {}
    finally:
        s.close()
    units = {ITEMS[i][1] for i in items if i in ITEMS}
    if len(units) > 1:
        raise ValueError(f"items have different units ({', '.join(sorted(units))}); chart one unit at a time")
    unit = "RATIO" if units == {"RATIO"} else ("CNY" if units == {"CNY"} else None)
    series = []
    for it in items:
        pts = [Point(r.reporting_period, r.value, meta={"published": pub.get(r.disclosure_id), "page": r.source_page,
                                                         "method": r.extraction_method,
                                                         "table": "human_capital_observations", "row_id": r.id})
               for r in sorted((r for r in rows if r.item == it), key=lambda r: r.reporting_period)]
        series.append(Series(ITEMS.get(it, (None, None, it))[2], pts))
    return ChartSpec("line", f"{_company_name(code)}: {', '.join(items)}", series, x_type="time", unit=unit,
                     caption="Source: annual report R&D and employee sections")


def flags_chart(code: str | None = None) -> ChartSpec:
    from ..crossvalidation import show_flags
    counts = Counter(f.rule for f in show_flags(code))
    pts = [Point(rule, float(n)) for rule, n in counts.most_common()]
    spec = ChartSpec("hbar", "Validation findings by rule" + (f" ({code})" if code else ""),
                     [Series("Findings", pts)], unit="COUNT", caption="Source: validation_flags (latest run)")
    spec.height = max(160, 90 + 26 * len(pts))
    return spec


BUILDERS = {"financials": financial_chart, "segments": segment_chart, "history": history_chart, "flags": flags_chart}


def export_chart(spec: ChartSpec, base: str) -> list[str]:
    """Write <base>.svg, <base>.csv (exactly the plotted data) and, if
    matplotlib is installed, <base>.png."""
    import csv
    from pathlib import Path
    from .svg import render_svg
    from . import mpl
    base_path = Path(base)
    base_path.parent.mkdir(parents=True, exist_ok=True)
    files = []
    svg = base_path.with_suffix(".svg")
    svg.write_text(render_svg(spec), encoding="utf-8")
    files.append(str(svg))
    rows = spec.data_rows()
    cols = []
    for r in rows:
        for k in r:
            if k not in cols:
                cols.append(k)
    out = base_path.with_suffix(".csv")
    with out.open("w", encoding="utf-8-sig", newline="") as fh:
        fh.write(f"# {spec.title}\n# {spec.caption}\n")
        w = csv.DictWriter(fh, fieldnames=cols or ["series", "x", "y"])
        w.writeheader()
        for r in rows:
            w.writerow({k: (json.dumps(v, ensure_ascii=False) if isinstance(v, (dict, list)) else v)
                        for k, v in r.items()})
    files.append(str(out))
    if mpl.available():
        try:
            files.append(mpl.render_png(spec, str(base_path.with_suffix(".png"))))
        except NotImplementedError:
            pass
    return files


# --- v1.7 ---------------------------------------------------------------------------------

def price_chart(code: str, start: str | None = None, end: str | None = None, adjusted: str = "backward",
                events: tuple[str, ...] = ("corporate_actions", "regulatory", "management", "listing")) -> ChartSpec:
    """Close (own-adjusted by default) with corporate, regulatory, management and listing events."""
    from ..valuation import adjusted_closes
    from ..models import (SessionLocal, Company, CorporateAction, RegulatoryEvent, ManagementEvent, ListingEvent)
    rows = adjusted_closes(code, "backward" if adjusted == "backward" else "forward") if adjusted != "none" else \
        [{"date": r["date"], "adjusted": r["close"]} for r in adjusted_closes(code, "forward")]
    rows = [r for r in rows if (not start or r["date"] >= start) and (not end or r["date"] <= end)]
    pts = [Point(r["date"], r["adjusted"], {"close": r.get("close")}) for r in rows]
    markers = []
    if rows:
        lo, hi = rows[0]["date"], rows[-1]["date"]
        s = SessionLocal()
        try:
            c = s.query(Company).filter_by(security_code=str(code).zfill(6)).first()
            if c:
                if "corporate_actions" in events:
                    for a in s.query(CorporateAction).filter_by(company_id=c.id):
                        d = a.ex_date or a.announcement_date
                        if d and lo <= d <= hi:
                            markers.append({"x": d, "group": "corporate action", "label": f"{a.action_type} ({a.status})",
                                            "meta": {"table": "corporate_actions", "row_id": a.id}})
                if "regulatory" in events:
                    for e in s.query(RegulatoryEvent).filter_by(company_id=c.id):
                        d = e.event_date or e.announcement_date
                        if d and lo <= d <= hi:
                            markers.append({"x": d, "group": "regulatory", "label": f"{e.event_type} {e.status or ''}",
                                            "meta": {"table": "regulatory_events", "row_id": e.id}})
                if "management" in events:
                    for e in s.query(ManagementEvent).filter_by(company_id=c.id):
                        d = e.event_date or e.announcement_date
                        if d and lo <= d <= hi:
                            markers.append({"x": d, "group": "management",
                                            "label": f"{e.event_type} {e.person_name or ''} {e.role or ''}"})
                if "listing" in events:
                    for e in s.query(ListingEvent).filter_by(company_id=c.id):
                        if e.event_date and lo <= e.event_date <= hi:
                            markers.append({"x": e.event_date, "group": "listing",
                                            "label": f"{e.event_type} {e.new_value or ''}"})
        finally:
            s.close()
    label = {"backward": "adjusted close (own factors, backward)", "forward": "adjusted close (own factors, forward)",
             "none": "close (unadjusted)"}[adjusted]
    return ChartSpec("line", f"{_company_name(code)}: {label}", [Series("Close", pts)], x_type="time", unit="CNY",
                     markers=markers, subtitle=f"{len(markers)} event(s) marked on the axis; hover for details",
                     caption="Prices: market_bars; adjustment factors from recorded corporate actions")


def segment_mix_chart(code: str, dimension: str = "PRODUCT", percent: bool = True) -> ChartSpec:
    from ..segments import segment_history
    hist = segment_history(code, dimension)
    periods = sorted({k for row in hist for k in row if k != "segment" and k.endswith("12-31")})
    series = [Series(row["segment"], [Point(p[:4], row.get(p)) for p in periods]) for row in hist]
    return ChartSpec("stacked", f"{_company_name(code)}: revenue mix by {dimension.lower()}", series, unit="CNY",
                     percent=percent, caption="Source: annual report segment tables (fiscal years)")


def workforce_chart(code: str, kind: str = "composition") -> ChartSpec:
    from ..human_capital import human_capital_history, ITEMS
    items = [k for k, v in ITEMS.items() if v[0] == ("WORKFORCE" if kind == "composition" else "EDUCATION")
             and k.startswith("staff_" if kind == "composition" else "edu_") and not k.endswith("_total")]
    hist = human_capital_history(code, tuple(items))
    periods = sorted({k for row in hist for k in row if k != "item" and k.endswith("12-31")})
    series = [Series(ITEMS[row["item"]][2], [Point(p[:4], row.get(p)) for p in periods]) for row in hist]
    return ChartSpec("stacked", f"{_company_name(code)}: workforce by {'function' if kind == 'composition' else 'education'}",
                     series, unit="PERSON", percent=True, caption="Source: annual report 员工情况")


def industry_distribution_chart(code: str, metric: str = "roe", scheme: str = "CSRC_2012", level: int = 2,
                                as_of: str | None = None) -> ChartSpec:
    from ..industry import industry_stats
    st = industry_stats(code, metric, scheme, level, None, "FY", as_of)
    vals = st.get("values") or {}
    unit = "RATIO" if metric in ("net_margin", "liabilities_to_assets", "rd_intensity", "roa", "roe") else "CNY"
    pct = st.get("company_percentile")
    return ChartSpec("hist", f"{metric} across {st.get('industry') or 'the industry'}",
                     [Series(metric, [Point(c, v) for c, v in vals.items()])], unit=unit,
                     highlight=st.get("company_value"), bins=min(20, max(5, len(vals) // 3 or 5)), x_label=metric,
                     subtitle=f"{len(vals)} companies" + (f"; {code} at the {pct:.0%} percentile" if pct is not None else ""),
                     caption=f"{scheme} level {level}; latest fiscal year per company" + (f"; as of {as_of}" if as_of else ""))


def peer_scatter_chart(code: str, x_metric: str = "rd_intensity", y_metric: str = "net_margin",
                       scheme: str = "CSRC_2012", level: int = 2, as_of: str | None = None) -> ChartSpec:
    from ..industry import industry_stats
    a = industry_stats(code, x_metric, scheme, level, None, "FY", as_of).get("values") or {}
    b = industry_stats(code, y_metric, scheme, level, None, "FY", as_of).get("values") or {}
    pts = [Point(a[c], b[c], {"label": c}) for c in a if c in b]
    unit = lambda m: "RATIO" if m in ("net_margin", "liabilities_to_assets", "rd_intensity", "roa", "roe") else "CNY"  # noqa: E731
    return ChartSpec("scatter", f"{y_metric} against {x_metric}: industry peers",
                     [Series("peers", pts, unit=unit(x_metric))], unit=unit(y_metric), highlight=str(code).zfill(6),
                     fit=True, x_label=x_metric, y_label=y_metric,
                     caption=f"{scheme} level {level}; latest fiscal year per company")


BUILDERS.update({"price": price_chart, "segment-mix": segment_mix_chart, "workforce": workforce_chart,
                 "industry": industry_distribution_chart, "peers": peer_scatter_chart})


# --- v1.8 diagrams -------------------------------------------------------------------------

def control_chart(code: str, as_of: str | None = None) -> ChartSpec:
    from ..control import control_at, classify_ownership
    r = control_at(code, as_of)
    ctl = r.get("control") or {}
    edges = r.get("chain") or []
    order, seen = [], set()
    children = {e["child"] for e in edges}
    parents = {e["parent"] for e in edges}
    top = [p for p in parents if p not in children] or list(parents)
    cur = top[0] if top else None
    while cur and cur not in seen:
        order.append(cur)
        seen.add(cur)
        nxt = next((e["child"] for e in edges if e["parent"] == cur), None)
        cur = nxt
    if not order:
        order = [r.get("name") or code]

    def group(name):
        if name == (r.get("name") or ""):
            return "listed"
        if any(k in name for k in ("国有资产", "国资委", "人民政府", "财政")):
            return "government"
        return "person" if classify_ownership(name)[0] == "PRIVATE" else "company"
    nodes = [{"id": n, "label": n, "group": group(n)} for n in order]
    gedges = [{"from": e["parent"], "to": e["child"], "label": f"{e['pct']:.2f}%" if e.get("pct") else None}
              for e in edges]
    sub = (f"Ownership type: {ctl.get('ownership_type')} · as reported {ctl.get('date')} (published {ctl.get('published')})"
           if ctl else "No control information")
    spec = ChartSpec("chain", f"{_company_name(code)}: control chain", [], subtitle=sub, graph={"nodes": nodes, "edges": gedges},
                     caption="Dashed: stake not disclosed in the text read; import the 方框图 percentages with "
                             "import-control-edges-csv")
    spec.height = max(220, 110 + 70 * len(nodes))
    return spec


def group_tree_chart(code: str, date: str | None = None) -> ChartSpec:
    from ..group import subsidiaries
    v = subsidiaries(code, date=date)
    ents = v.get("entities") or []
    nodes = [{"id": "root", "label": _company_name(code)}]
    edges = []
    for i, e in enumerate(ents):
        nid = f"e{i}"
        nodes.append({"id": nid, "label": e["name"], "group": e.get("jurisdiction") or "UNKNOWN",
                      "tip": f"{e['name']}\n{e.get('relationship')} {e.get('pct')}%\n{e.get('jurisdiction')}"})
        edges.append({"from": "root", "to": nid, "label": f"{e['pct']:.0f}%" if e.get("pct") is not None else None})
    spec = ChartSpec("tree", f"{_company_name(code)}: group structure ({v.get('date') or 'n/a'})", [],
                     graph={"nodes": nodes, "edges": edges}, subtitle="Grouped by jurisdiction; offshore entities in orange",
                     caption="Source: 企业集团的构成 and 主要控股参股公司分析")
    spec.height = max(240, 100 + 22 * len(ents))
    return spec


def interlock_chart(code: str | None = None, as_of: str | None = None) -> ChartSpec:
    from ..control import interlocks
    rows = interlocks(as_of, code)
    names = {}
    from ..models import SessionLocal, Company
    s = SessionLocal()
    try:
        for c in s.query(Company):
            names[c.security_code] = f"{c.security_code} {c.short_name_cn or ''}".strip()
    finally:
        s.close()
    ids = sorted({r["company_a"] for r in rows} | {r["company_b"] for r in rows})
    nodes = [{"id": i, "label": names.get(i, i), "group": "listed" if i == code else "company"} for i in ids]
    edges = [{"from": r["company_a"], "to": r["company_b"], "weight": r["count"],
              "label": ", ".join(r["shared_directors"])} for r in rows]
    return ChartSpec("network", "Board interlocks" + (f" of {names.get(code, code)}" if code else ""), [],
                     graph={"nodes": nodes, "edges": edges}, height=520,
                     subtitle=f"{len(edges)} link(s): companies sharing a director; hover a link for the names",
                     caption="Persons resolved by name, gender and birth year (see resolve-persons)")


BUILDERS.update({"control": control_chart, "group-tree": group_tree_chart, "interlocks": interlock_chart})
