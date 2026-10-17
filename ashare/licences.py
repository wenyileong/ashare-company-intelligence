"""Licence classes for every source of data (v2.0).

Each row in the database comes from a source (the ``source`` column, or the
extraction method for tables without one). Each source belongs to one
licence class:

PUBLIC_DISCLOSURE  statutory disclosures and exchange pages (CNINFO, SSE, SZSE,
                   BSE) and values extracted from them;
PUBLIC_FEED        free public market feeds (Eastmoney). Not exchange-
                   authoritative; the provider's terms of use apply to
                   redistribution;
DERIVED            values the program computes from other rows (adjustment
                   factors, calendars, histories);
MANUAL             the researcher's own review corrections and hand coding;
LICENSED           vendor data imported under a licence (ESG ratings, Shenwan
                   industries, index files, unknown CSV imports).

A CSV import is treated as LICENSED unless its source label is tagged
otherwise with ``set-licence``: the program cannot know where an imported
file came from, and the cautious default keeps vendor data out of releases.
Releases exclude LICENSED rows by default (``ashare.release``).
"""
from __future__ import annotations

import re

CLASSES = ("PUBLIC_DISCLOSURE", "PUBLIC_FEED", "DERIVED", "MANUAL", "LICENSED")

DESCRIPTIONS = {
    "PUBLIC_DISCLOSURE": "Statutory disclosure or exchange page, and values extracted from it",
    "PUBLIC_FEED": "Free public market feed; provider terms apply to redistribution",
    "DERIVED": "Computed by the program from other rows",
    "MANUAL": "Researcher's own review or hand coding",
    "LICENSED": "Vendor data imported under a licence (excluded from releases by default)",
}

_RULES = (
    (r"^(CNINFO|SSE|SZSE|BSE|EXCHANGE|PDF|XBRL|ANNUAL_REPORT|DISCLOSURE)", "PUBLIC_DISCLOSURE"),
    (r"^(EASTMONEY|SINA|TENCENT|PUBLIC_FEED)", "PUBLIC_FEED"),
    (r"^(DERIVED|OWN$|COMPUTED|CALENDAR)", "DERIVED"),
    (r"^(MANUAL|HAND|REVIEW)", "MANUAL"),
)

# Tables whose content is licensed whatever the label says.
TABLE_LICENCE = {"esg_ratings": "LICENSED"}
# Tables with no source column: the licence follows the extraction method.
METHOD_TABLES = {"financial_facts"}
# Tables that hold only the program's own bookkeeping.
INTERNAL_TABLES = {"jobs", "job_items", "high_water_marks", "parser_calibration", "research_queries",
                   "review_items", "validation_flags", "sources", "raw_records", "document_pages",
                   "companies", "securities", "persons", "person_roles", "entities", "entity_aliases",
                   "capital_reconciliations"}


def _overrides(session=None) -> dict[str, str]:
    from .models import SessionLocal, Source
    s = session or SessionLocal()
    try:
        return {r.name.upper(): r.licence for r in s.query(Source).filter(Source.licence.isnot(None))}
    finally:
        if session is None:
            s.close()


def classify_source(label: str | None, overrides: dict | None = None) -> str:
    """The licence class of a source label."""
    lab = (label or "").strip().upper()
    if overrides and lab in overrides:
        return overrides[lab]
    for pat, cls in _RULES:
        if re.match(pat, lab):
            return cls
    return "LICENSED"          # CSV_IMPORT and any unknown label


def row_licence(table: str, row: dict, overrides: dict | None = None) -> str:
    """The licence class of one row of *table*. A label tagged with
    ``set-licence`` takes precedence over every default rule."""
    label = str(row.get("source") or row.get("source_label") or "").strip().upper()
    if overrides and label in overrides:
        return overrides[label]
    if table in TABLE_LICENCE:
        return TABLE_LICENCE[table]
    if table == "industry_classifications":
        scheme = str(row.get("scheme") or "").upper()
        if scheme.startswith("SW"):
            return "LICENSED"                       # Shenwan: commercial
        if scheme.startswith(("CSRC", "CNINFO")):
            return "PUBLIC_DISCLOSURE"              # published by the CSRC / CNINFO
    if table in INTERNAL_TABLES:
        return "DERIVED"
    if "source" in row and row["source"] is not None:
        return classify_source(row["source"], overrides)
    if table in METHOD_TABLES:
        m = str(row.get("extraction_method") or "").upper()
        if "IMPORT" in m or "CSV" in m:
            return classify_source(row.get("source_label") or "CSV_IMPORT", overrides)
        return "MANUAL" if "MANUAL" in m else "PUBLIC_DISCLOSURE"
    return "PUBLIC_DISCLOSURE"


def set_licence(source: str, licence: str) -> dict:
    """Tag a source label with a licence class (stored in ``sources``)."""
    licence = licence.upper()
    if licence not in CLASSES:
        raise ValueError(f"licence must be one of {CLASSES}")
    from .models import SessionLocal, Source, init_db
    init_db()
    s = SessionLocal()
    try:
        row = s.query(Source).filter_by(name=source).first()
        if row is None:
            row = Source(name=source, access_type="import")
            s.add(row)
        row.licence = licence
        s.commit()
        return {"source": source, "licence": licence}
    finally:
        s.close()


def licence_summary() -> list[dict]:
    """Rows per table and licence class, with the source labels seen."""
    from sqlalchemy import select
    from .models import Base, SessionLocal, init_db
    from . import transactions  # noqa: F401
    init_db()
    s = SessionLocal()
    out = []
    try:
        ov = _overrides(s)
        for name, t in sorted(Base.metadata.tables.items()):
            if name in INTERNAL_TABLES:
                continue
            cols = [c for c in ("source", "extraction_method", "scheme", "source_label") if c in t.c]
            counts: dict[tuple, int] = {}
            stmt = select(*[t.c[c] for c in cols]) if cols else select(t.c[list(t.c.keys())[0]])
            for r in s.execute(stmt):
                row = dict(zip(cols, r)) if cols else {}
                key = (row_licence(name, row, ov), row.get("source") or row.get("extraction_method") or "")
                counts[key] = counts.get(key, 0) + 1
            for (lic, src), n in sorted(counts.items()):
                out.append({"table": name, "licence": lic, "source": src, "rows": n})
        return out
    finally:
        s.close()
