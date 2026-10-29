"""v1.2 business, product, regional and sales-channel segments.

Source: the 营业收入构成 table (and the 主营业务分行业/分产品/分地区情况
table with cost and gross margin) in the management discussion of annual
and interim reports, or an authorised CSV. Parsing is heuristic and every
row keeps its page and raw text.

Derived measures: overseas revenue share (regional dimension), revenue
concentration (Herfindahl-Hirschman index of segment shares) and segment
history across periods. A segment sum that does not match reported revenue
is flagged by validation rather than corrected.
"""
from __future__ import annotations

import csv
import re
from collections import defaultdict
from pathlib import Path

from .evaluation import calibrated_confidence  # noqa: F401
from .parsers import PARSERS, dual_run, record_confidence, extraction_note, tally_dual
from .timeutil import utcnow
from .models import SessionLocal, Company, Disclosure, SegmentObservation, init_db
from .places import region_class
from .ownership import normalise_date

DIMENSIONS = {"分行业": "INDUSTRY", "分产品": "PRODUCT", "分地区": "REGION", "分销售模式": "SALES_MODEL",
              "分渠道": "SALES_MODEL", "分销售渠道": "SALES_MODEL", "分部": "REPORTABLE_SEGMENT",
              "分业务": "INDUSTRY", "分板块": "INDUSTRY"}
DIMENSION_CODES = ("INDUSTRY", "PRODUCT", "REGION", "SALES_MODEL", "REPORTABLE_SEGMENT")

_NUM = r"-?\d[\d,]*(?:\.\d+)?"
_TOTAL = re.compile(r"^(营业收入合计|合计|总计|营业收入|主营业务收入合计|主营业务合计)$")


def _num(s: str) -> float | None:
    try:
        return float(s.replace(",", ""))
    except (TypeError, ValueError):
        return None


from .units import first_declared


def _unit(text: str) -> tuple[str, float]:
    return first_declared(text) or ("CNY", 1.0)


_SEG_PAGE = re.compile(r"(营业收入构成|主营业务分行业|主营业务分产品|主营业务分地区|分行业情况|分产品情况|分地区情况)")
# v2.0.8 (finding 83): where a segment table ends. The cost-analysis and output tables that follow have the same
# 分行业/分产品 row heads, and their rows are not revenue segments.
_SEG_END = re.compile(r"(成本分析表|成本构成|营业成本构成|产销量|销售量|生产量|主要销售客户|前五名|主要供应商|"
                      r"^第[一二三四五六七八九十]+节|^[一二三四五六七八九十]+、)")


def parse_segment_pages(pages: list[str]) -> list[dict]:
    """Parse revenue-composition and segment-margin tables.

    Composition table rows: name, amount, share%, prior amount, prior share%, yoy%.
    Margin table rows (header mentions 毛利率): name, revenue, cost, margin%,
    revenue yoy%, cost yoy%, margin change.

    v2.0.8 (finding 83): a table continued on the next page keeps its dimension, unit and kind (v2.0.7 started
    each page afresh and skipped a page without a heading, losing the rows after a page break); "其中：" breakdown
    rows are not segments, and "小计" rows are subtotals. Each row records the kind of table it came from:
    the composition table lists every segment, the margin table only those above 10% of revenue.
    """
    rows = []
    mode = dimension = None       # mode: 'composition' or 'margin'
    unit, mult = "CNY", 1.0
    active = False
    for pno, page in enumerate(pages, start=1):
        if _SEG_PAGE.search(page):
            if not active:
                unit, mult = _unit(page)
            active = True
        elif not active:
            continue
        for raw_line in page.splitlines():
            line = raw_line.replace("　", " ").strip()
            if not line:
                continue
            if _SEG_END.search(line) and not _SEG_PAGE.search(line):
                active, mode, dimension = False, None, None
                continue
            if _SEG_PAGE.search(line):
                active = True
            if not active:
                continue
            declared = first_declared(line)
            if declared:
                unit, mult = declared
            if re.search(r"营业收入构成", line):
                mode, dimension = "composition", None
            if "毛利率" in line:
                mode = "margin"
            head = re.match(r"^(分行业|分产品|分地区|分销售模式|分渠道|分销售渠道|分部|分业务|分板块)", line)
            if head:
                dimension = DIMENSIONS[head.group(1)]
                line = line[len(head.group(1)):].strip()
                if not line:
                    continue
            toks = line.split()
            k = 0
            while k < len(toks) and not re.fullmatch(r"-?\d[\d,]*(?:\.\d+)?%?|[-－—]", toks[k]):
                k += 1
            if k == 0 or k == len(toks) or len(toks) - k > 9:
                continue
            if not all(re.fullmatch(r"-?\d[\d,]*(?:\.\d+)?%?|[-－—]", t) for t in toks[k:]):
                continue
            name = "".join(toks[:k])
            if re.search(r"\d{4}年|单位|项目|金额|比重|同比|营业成本|毛利率", name):
                continue
            if re.match(r"^其中\s*[:：]?", name):          # a breakdown of the row above, not a segment
                continue
            subtotal = name in ("小计", "合计小计")
            if dimension is None and not _TOTAL.match(name):
                continue
            values = [(t.endswith("%"), _num(t.rstrip("%"))) for t in toks[k:] if t not in ("-", "－", "—")]
            plain = [v for is_pct, v in values if not is_pct and v is not None]
            pct = [v for is_pct, v in values if is_pct and v is not None]
            rec = {"dimension": dimension or "TOTAL", "segment_name": name, "page": pno, "raw": line, "unit": unit,
                   "is_total": bool(_TOTAL.match(name)) or subtotal}
            if mode == "margin":
                if len(plain) < 2:
                    continue
                rec.update(revenue=plain[0] * mult, cost=plain[1] * mult,
                           gross_margin=pct[0] / 100 if pct else None,
                           revenue_yoy=pct[1] / 100 if len(pct) > 1 else None)
                rec["table"] = "margin"
            else:
                if not plain:
                    continue
                rec.update(revenue=plain[0] * mult, revenue_share=pct[0] / 100 if pct else None,
                           revenue_prior=plain[1] * mult if len(plain) > 1 else None,
                           revenue_yoy=pct[-1] / 100 if len(pct) >= 3 else None)
                rec["table"] = "composition"
            rec["table_kind"] = rec["table"]
            if rec["dimension"] == "REGION":
                rec["region_class"] = region_class(name)
            rows.append(rec)
    return rows


def _merge(rows: list[dict]) -> list[dict]:
    """Combine composition and margin rows for the same dimension and segment."""
    merged: dict[tuple, dict] = {}
    for r in rows:
        key = (r["dimension"], r["segment_name"])
        if key not in merged:
            merged[key] = dict(r)
        else:
            cur = merged[key]
            for k in ("revenue_share", "revenue_prior", "cost", "gross_margin", "revenue_yoy", "region_class"):
                if cur.get(k) is None and r.get(k) is not None:
                    cur[k] = r[k]
            if cur.get("revenue") is None:
                cur["revenue"] = r.get("revenue")
            if r.get("table_kind") == "composition":
                cur["table_kind"] = "composition"
    return list(merged.values())


def _period_of(d: Disclosure) -> str | None:
    m = re.search(r"(20\d{2})\s*年", d.title_cn or "")
    if not m:
        return None
    return f"{m.group(1)}-06-30" if "半年" in (d.title_cn or "") else f"{m.group(1)}-12-31"


def extract_segments(security_code: str | None = None, again: bool = False, progress=None) -> dict:
    """Segments from annual and interim reports.

    v2.0.8: only the pages of the segment tables are read (:mod:`ashare.reportreader`), with progress and resume
    (:mod:`ashare.extractstate`); rows an earlier parser read from a document, and the current one does not
    (cost-analysis rows, rows cut at a page break), are removed."""
    from .extractstate import run
    init_db()
    session = SessionLocal()
    totals = {"reports": 0, "segments": 0, "inserted": 0, "updated": 0, "errors": []}
    try:
        q = session.query(Disclosure, Company).join(Company, Disclosure.company_id == Company.id).filter(
            Disclosure.kind.in_(("annual_report", "interim_report")), Disclosure.local_path.isnot(None))
        if security_code:
            q = q.filter(Company.security_code == str(security_code).zfill(6))

        def handle(d, c, reader):
            path = Path(d.local_path)
            period = _period_of(d)
            if not period:
                return None
            rows, info = dual_run("segments", path, {"title": d.title_cn}, reader=reader, sections=["segments"])
            tally_dual(totals, info, d.id)
            keep = {(r["dimension"], r["segment_name"]) for r in rows}
            for old in session.query(SegmentObservation).filter_by(company_id=c.id, disclosure_id=d.id):
                if (old.dimension, old.segment_name) not in keep:
                    session.delete(old)
                    totals["removed"] = totals.get("removed", 0) + 1
            if not rows:
                return "EMPTY"
            totals["reports"] += 1
            for r in rows:
                totals["segments"] += 1
                row = session.query(SegmentObservation).filter_by(
                    company_id=c.id, reporting_period=period, dimension=r["dimension"],
                    segment_name=r["segment_name"], source=d.source or "CNINFO", disclosure_id=d.id).one_or_none()
                if row is None:
                    row = SegmentObservation(company_id=c.id, reporting_period=period, dimension=r["dimension"],
                                             segment_name=r["segment_name"], source=d.source or "CNINFO",
                                             disclosure_id=d.id, extraction_method="PDF_TABLE_HEURISTIC")
                    session.add(row)
                    totals["inserted"] += 1
                else:
                    totals["updated"] += 1
                for k in ("revenue", "revenue_share", "revenue_prior", "revenue_yoy", "cost", "gross_margin",
                          "region_class", "is_total", "unit", "table_kind"):
                    setattr(row, k, r.get(k))
                row.source_document = d.local_path or d.document_url
                row.source_page, row.raw_value = r["page"], r["raw"]
                row.extraction_method = PARSERS[r["_variant"]].method
                row.confidence = record_confidence(r, 0.55)
                row.extraction_note = extraction_note(r)
                row.retrieved_at = utcnow()
            return "READ"

        rows = q.order_by(Company.security_code, Disclosure.announcement_date, Disclosure.id).all()
        return run("segments", rows, handle, totals, again, progress, session)
    finally:
        session.close()


def import_segments_csv(path: str, source: str = "CSV_IMPORT") -> dict:
    """Columns: security_code, reporting_period, dimension (INDUSTRY, PRODUCT,
    REGION, SALES_MODEL, REPORTABLE_SEGMENT, or 分行业 …), segment_name,
    revenue, cost, gross_margin (fraction or %), assets, revenue_prior."""
    init_db()
    session = SessionLocal()
    inserted = updated = 0
    errors = []
    try:
        with Path(path).open("r", encoding="utf-8-sig", newline="") as fh:
            rows = list(csv.DictReader(fh))
        for i, r in enumerate(rows, 1):
            try:
                c = session.query(Company).filter_by(security_code=str(r.get("security_code") or "").strip().zfill(6)).first()
                if not c:
                    raise ValueError("company not found")
                period = normalise_date(r.get("reporting_period"))
                dim_raw = (r.get("dimension") or "").strip()
                dim = DIMENSIONS.get(dim_raw, dim_raw.upper())
                if dim not in DIMENSION_CODES:
                    raise ValueError(f"unknown dimension {dim_raw!r}")
                name = (r.get("segment_name") or "").strip()
                if not period or not name:
                    raise ValueError("reporting_period and segment_name are required")
                row = session.query(SegmentObservation).filter_by(
                    company_id=c.id, reporting_period=period, dimension=dim, segment_name=name, source=source,
                    disclosure_id=None).one_or_none()
                if row is None:
                    row = SegmentObservation(company_id=c.id, reporting_period=period, dimension=dim,
                                             segment_name=name, source=source, extraction_method="CSV_IMPORT")
                    session.add(row)
                    inserted += 1
                else:
                    updated += 1

                def num(k):
                    v = (r.get(k) or "").replace(",", "").strip()
                    if not v:
                        return None
                    return float(v.rstrip("%")) / 100 if v.endswith("%") else float(v)
                row.revenue, row.cost, row.assets, row.revenue_prior = num("revenue"), num("cost"), num("assets"), num("revenue_prior")
                gm = num("gross_margin")
                row.gross_margin = gm / 100 if gm is not None and gm > 1 else gm
                row.is_total = bool(_TOTAL.match(name))
                row.region_class = region_class(name) if dim == "REGION" else None
                row.unit = "CNY"
                row.source_document = r.get("source_document")
                row.confidence = float(r["confidence"]) if r.get("confidence") else None
                session.flush()
            except Exception as exc:
                errors.append({"row": i, "error": str(exc)})
        session.commit()
        return {"inserted": inserted, "updated": updated, "errors": errors}
    finally:
        session.close()


def _published(session, row) -> str:
    if row.disclosure_id:
        d = session.get(Disclosure, row.disclosure_id)
        return (d.announcement_date if d else None) or row.reporting_period
    return row.reporting_period


def segments(security_code: str, period: str | None = None, dimension: str | None = None,
             as_of: str | None = None) -> dict:
    """Segments for one period (default: latest known at ``as_of``), with
    shares, overseas exposure and concentration per dimension."""
    init_db()
    session = SessionLocal()
    try:
        c = session.query(Company).filter_by(security_code=str(security_code).zfill(6)).first()
        if not c:
            return {"error": "company not found"}
        from .review import reviewed_rows
        rows = reviewed_rows(session, "segment_observations",
                             [r for r in session.query(SegmentObservation).filter_by(company_id=c.id)
                              if not as_of or _published(session, r) <= as_of])
        if dimension:
            rows = [r for r in rows if r.dimension == dimension.upper()]
        if not rows:
            return {"code": c.security_code, "period": period, "dimensions": {}}
        period = period or max(r.reporting_period for r in rows)
        rows = [r for r in rows if r.reporting_period == period]
        # one source per (dimension, name): prefer the latest-published document
        best = {}
        for r in rows:
            k = (r.dimension, r.segment_name)
            if k not in best or _published(session, r) > _published(session, best[k]):
                best[k] = r
        dims = defaultdict(list)
        for r in best.values():
            dims[r.dimension].append(r)
        overall = next((r for r in dims.pop("TOTAL", []) if r.is_total and r.revenue), None)
        out = {}
        for dim, rs in dims.items():
            items = [r for r in rs if not r.is_total]
            total_row = next((r for r in rs if r.is_total), None) or overall
            seg_sum = sum(r.revenue or 0 for r in items)
            base = (total_row.revenue if total_row and total_row.revenue else None) or seg_sum or None
            shares = [(r.revenue or 0) / base for r in items] if base else []
            hhi = sum(s * s for s in shares) if shares else None
            overseas = None
            if dim == "REGION" and base:
                ov = sum(r.revenue or 0 for r in items if r.region_class == "OVERSEAS")
                unknown = sum(r.revenue or 0 for r in items if r.region_class == "UNKNOWN")
                overseas = {"overseas_share": ov / base, "unclassified_share": unknown / base}
            out[dim] = {
                "segments": [{"id": r.id, "name": r.segment_name, "revenue": r.revenue,
                              "share": (r.revenue or 0) / base if base else r.revenue_share,
                              "yoy": r.revenue_yoy, "gross_margin": r.gross_margin, "region": r.region_class,
                              "method": r.extraction_method, "page": r.source_page}
                             for r in sorted(items, key=lambda r: -(r.revenue or 0))],
                "total_reported": total_row.revenue if total_row else None, "segment_sum": seg_sum,
                "hhi": hhi, "effective_segments": (1 / hhi) if hhi else None, "regional": overseas,
            }
        return {"code": c.security_code, "period": period, "as_of": as_of, "dimensions": out,
                "note": "HHI = sum of squared revenue shares (1 = a single segment); effective segments = 1/HHI."}
    finally:
        session.close()


def segment_history(security_code: str, dimension: str = "PRODUCT") -> list[dict]:
    """Each segment's revenue across periods (FY and H1 shown separately)."""
    init_db()
    session = SessionLocal()
    try:
        c = session.query(Company).filter_by(security_code=str(security_code).zfill(6)).first()
        if not c:
            return []
        rows = session.query(SegmentObservation).filter_by(company_id=c.id, dimension=dimension.upper()).all()
        hist = defaultdict(dict)
        for r in rows:
            if not r.is_total:
                hist[r.segment_name][r.reporting_period] = r.revenue
        periods = sorted({r.reporting_period for r in rows})
        return [{"segment": name, **{p: vals.get(p) for p in periods}} for name, vals in sorted(hist.items())]
    finally:
        session.close()
