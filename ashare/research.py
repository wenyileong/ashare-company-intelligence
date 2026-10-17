"""v1.0 research tools: search, document inspection, audit trail, reproducible
queries and dataset releases."""
from __future__ import annotations

import csv
import hashlib
import json
import platform
import re
import sqlite3
from pathlib import Path

from . import __version__
from .config import db_path
from .timeutil import utcnow
from .models import (
    SessionLocal, Company, Security, Disclosure, DocumentPage, ResearchQuery, Base, init_db, engine,
)


def _sha256_file(path: Path) -> str | None:
    try:
        h = hashlib.sha256()
        with open(path, "rb") as fh:
            for chunk in iter(lambda: fh.read(1 << 20), b""):
                h.update(chunk)
        return h.hexdigest()
    except OSError:
        return None


# ---------------------------------------------------------------------------
# Disclosure and full-text search
# ---------------------------------------------------------------------------

def search_disclosures(query: str | None = None, security_code: str | None = None, since: str | None = None,
                       until: str | None = None, kind: str | None = None, limit: int = 200):
    """Title search over catalogued announcements (substring; all words must match)."""
    init_db()
    session = SessionLocal()
    try:
        q = session.query(Disclosure, Company.security_code).join(Company, Disclosure.company_id == Company.id)
        for word in (query or "").split():
            q = q.filter(Disclosure.title_cn.contains(word))
        if security_code:
            q = q.filter(Company.security_code == str(security_code).zfill(6))
        if since:
            q = q.filter(Disclosure.announcement_date >= since)
        if until:
            q = q.filter(Disclosure.announcement_date <= until)
        if kind:
            q = q.filter(Disclosure.kind == kind)
        return [{"disclosure_id": d.id, "code": code, "date": d.announcement_date, "kind": d.kind,
                 "title": d.title_cn, "downloaded": bool(d.local_path), "url": d.document_url}
                for d, code in q.order_by(Disclosure.announcement_date.desc()).limit(limit).all()]
    finally:
        session.close()


def _fts_available(conn) -> bool:
    from .models import is_sqlite
    if not is_sqlite():
        return False          # other back ends use the plain substring search
    try:
        conn.exec_driver_sql("CREATE VIRTUAL TABLE IF NOT EXISTS document_fts USING fts5("
                             "text, content='document_pages', content_rowid='id', tokenize='trigram')")
        return True
    except Exception:
        return False


def index_documents(security_code: str | None = None, reindex: bool = False) -> dict:
    """Extract page text from downloaded documents into ``document_pages``.

    Where SQLite provides FTS5 with the trigram tokenizer, a full-text index
    is maintained; Chinese has no word boundaries, so trigram (substring)
    matching is used. Queries shorter than three characters fall back to a
    plain substring scan.
    """
    from .corporate_actions import _document_pages
    init_db()
    session = SessionLocal()
    totals = {"documents": 0, "pages": 0, "skipped": 0, "errors": []}
    try:
        q = session.query(Disclosure).join(Company, Disclosure.company_id == Company.id).filter(Disclosure.local_path.isnot(None))
        if security_code:
            q = q.filter(Company.security_code == str(security_code).zfill(6))
        for d in q.all():
            existing = session.query(DocumentPage).filter_by(disclosure_id=d.id).count()
            if existing and not reindex:
                totals["skipped"] += 1
                continue
            path = Path(d.local_path)
            if not path.exists():
                totals["errors"].append({"disclosure_id": d.id, "error": "file missing"})
                continue
            try:
                pages = _document_pages(path)
            except Exception as exc:
                totals["errors"].append({"disclosure_id": d.id, "error": repr(exc)})
                continue
            session.query(DocumentPage).filter_by(disclosure_id=d.id).delete()
            for i, text in enumerate(pages, start=1):
                session.add(DocumentPage(disclosure_id=d.id, company_id=d.company_id, page=i, text=text,
                                         document_sha256=d.sha256))
            totals["documents"] += 1
            totals["pages"] += len(pages)
        session.commit()
    finally:
        session.close()
    with engine().begin() as conn:
        totals["full_text_index"] = _fts_available(conn)
        if totals["full_text_index"]:
            conn.exec_driver_sql("INSERT INTO document_fts(document_fts) VALUES('rebuild')")
    return totals


def search_documents(query: str, security_code: str | None = None, limit: int = 50) -> list[dict]:
    """Full-text search of indexed document pages, with a snippet per hit."""
    init_db()
    phrase = query.strip()
    if not phrase:
        return []
    params = {"lim": limit}
    where = ""
    if security_code:
        where = " AND c.security_code = :code"
        params["code"] = str(security_code).zfill(6)
    with engine().connect() as conn:
        use_fts = len(phrase) >= 3 and _fts_available(conn)
        if use_fts:
            params["q"] = '"' + phrase.replace('"', '""') + '"'
            sql = ("SELECT p.id, p.disclosure_id, p.page, p.text, c.security_code, d.announcement_date, d.title_cn "
                   "FROM document_fts f JOIN document_pages p ON p.id = f.rowid "
                   "JOIN disclosures d ON d.id = p.disclosure_id JOIN companies c ON c.id = p.company_id "
                   "WHERE document_fts MATCH :q" + where + " ORDER BY d.announcement_date DESC LIMIT :lim")
        else:
            params["q"] = f"%{phrase}%"
            sql = ("SELECT p.id, p.disclosure_id, p.page, p.text, c.security_code, d.announcement_date, d.title_cn "
                   "FROM document_pages p JOIN disclosures d ON d.id = p.disclosure_id "
                   "JOIN companies c ON c.id = p.company_id WHERE p.text LIKE :q" + where +
                   " ORDER BY d.announcement_date DESC LIMIT :lim")
        from sqlalchemy import text as sqltext
        rows = conn.execute(sqltext(sql), params).all()
    out = []
    for pid, did, page, text, code, date, title in rows:
        flat = re.sub(r"\s+", " ", text or "")
        i = flat.find(phrase)
        snippet = flat[max(0, i - 60): i + len(phrase) + 60] if i >= 0 else flat[:120]
        out.append({"code": code, "date": date, "title": title, "disclosure_id": did, "page": page, "snippet": snippet})
    return out


def inspect_document(disclosure_id: int, page: int | None = None, verify: bool = True) -> dict:
    """Metadata, integrity check and page text of a source document."""
    from .corporate_actions import _document_pages
    init_db()
    session = SessionLocal()
    try:
        d = session.get(Disclosure, disclosure_id)
        if not d:
            return {"error": "disclosure not found"}
        info = {"disclosure_id": d.id, "title": d.title_cn, "date": d.announcement_date,
                "announcement_id": d.announcement_id, "url": d.document_url, "local_path": d.local_path,
                "stored_sha256": d.sha256}
        if d.local_path and verify:
            actual = _sha256_file(Path(d.local_path))
            info["integrity"] = ("FILE_MISSING" if actual is None else
                                 "VERIFIED" if actual == d.sha256 else "HASH_MISMATCH")
        if page:
            stored = session.query(DocumentPage).filter_by(disclosure_id=d.id, page=page).first()
            if stored:
                info["page_text"] = stored.text
            elif d.local_path and Path(d.local_path).exists():
                pages = _document_pages(Path(d.local_path))
                info["page_text"] = pages[page - 1] if 0 < page <= len(pages) else None
        return info
    finally:
        session.close()


# ---------------------------------------------------------------------------
# Audit trail
# ---------------------------------------------------------------------------

TRACEABLE = {"financial_facts", "corporate_actions", "regulatory_events", "ownership_observations",
             "capital_structure_observations", "market_bars",
             # v1.5: the enrichment tables are traceable too (and reviewable)
             "segment_observations", "subsidiary_observations", "human_capital_observations",
             "esg_observations", "management_observations"}


def trace(table: str, row_id: int, verify: bool = True) -> dict:
    """Provenance chain for one observation (build plan, section 6):
    company -> security -> observation -> source -> document -> page/tag ->
    raw value -> normalised value -> method -> validation."""
    if table not in TRACEABLE:
        raise ValueError(f"table must be one of {sorted(TRACEABLE)}")
    init_db()
    session = SessionLocal()
    try:
        model = next(m.class_ for m in Base.registry.mappers if m.class_.__tablename__ == table)
        row = session.get(model, row_id)
        if not row:
            return {"error": "row not found"}
        company = session.get(Company, row.company_id) if getattr(row, "company_id", None) else None
        security = (session.query(Security).filter_by(company_id=company.id).first() if company else None)
        disclosure = session.get(Disclosure, row.disclosure_id) if getattr(row, "disclosure_id", None) else None
        chain = {
            "company": {"code": company.security_code, "name": company.legal_name_cn, "exchange": company.exchange,
                        "board": company.board} if company else None,
            "security": {"code": security.security_code, "type": security.security_type,
                         "currency": security.currency} if security else None,
            "observation": {"table": table, "id": row.id},
            "source": getattr(row, "source", None) or (disclosure.source if disclosure else None),
        }
        doc = {}
        if disclosure:
            doc = {"disclosure_id": disclosure.id, "title": disclosure.title_cn,
                   "published": disclosure.announcement_date, "announcement_id": disclosure.announcement_id,
                   "url": disclosure.document_url, "local_path": disclosure.local_path,
                   "sha256": disclosure.sha256, "retrieved_at": str(disclosure.retrieved_at)}
            if verify and disclosure.local_path:
                actual = _sha256_file(Path(disclosure.local_path))
                doc["integrity"] = ("FILE_MISSING" if actual is None else
                                    "VERIFIED" if actual == disclosure.sha256 else "HASH_MISMATCH")
        elif getattr(row, "source_document", None):
            doc = {"source_document": row.source_document}
        if getattr(row, "document_hash", None):
            doc["document_hash"] = row.document_hash
        if table == "market_bars" and row.raw_json:
            raw = json.loads(row.raw_json)
            doc = {"raw_payload": raw.get("raw_path"), "raw_sha256": raw.get("raw_sha256")}
            if verify and raw.get("raw_path"):
                actual = _sha256_file(Path(raw["raw_path"]))
                doc["integrity"] = ("FILE_MISSING" if actual is None else
                                    "VERIFIED" if actual == raw.get("raw_sha256") else "HASH_MISMATCH")
        chain["document"] = doc or None
        chain["location"] = {k: getattr(row, k) for k in ("source_page", "source_xbrl_tag", "source_label", "source_context")
                             if hasattr(row, k) and getattr(row, k) is not None} or None
        raw_value = getattr(row, "raw_value", None) or getattr(row, "raw_text", None)
        chain["raw_value"] = raw_value
        norm = {}
        for k in ("metric", "reporting_period", "period_type", "value", "unit", "currency", "action_type", "status",
                  "ratio", "cash_amount", "share_delta", "event_type", "legal_classification", "fine_amount_total",
                  "shares", "ownership_pct", "total_shares", "tradable_shares", "trade_date", "close", "adjustment",
                  "dimension", "segment_name", "revenue", "gross_margin", "entity_name", "total_pct", "item",
                  "person_name", "role", "remuneration", "observation_date"):
            if hasattr(row, k) and getattr(row, k) is not None:
                norm[k] = getattr(row, k)
        if getattr(row, "normalised_value", None):
            norm["normalised_json"] = json.loads(row.normalised_value)
        chain["normalised_value"] = norm
        chain["extraction_method"] = getattr(row, "extraction_method", None)
        if getattr(row, "extraction_note", None):
            chain["extraction_note"] = json.loads(row.extraction_note)
        from .review import REVIEWABLE, CorrectionIndex
        if table in REVIEWABLE:
            idx = CorrectionIndex(session, table)
            c = idx.get(row)
            if c is not None:
                chain["review"] = {"action": c.action, "field": c.field, "original": c.original_value,
                                   "corrected": c.corrected_value, "reason": c.reason, "reviewer": c.reviewer,
                                   "at": c.created_at.isoformat(timespec="seconds")}
        chain["confidence"] = getattr(row, "confidence", None)
        from .crossvalidation import confidence_class
        chain["validation"] = {"status": getattr(row, "validation_status", None),
                               "confidence_class": confidence_class(getattr(row, "confidence", None),
                                                                    getattr(row, "validation_status", None))}
        from .models import ValidationFlag
        flags = [f for f in session.query(ValidationFlag).filter(ValidationFlag.table_name == table)
                 if row.id in json.loads(f.row_ids)]
        chain["validation"]["flags"] = [{"rule": f.rule, "severity": f.severity, "details": json.loads(f.details or "{}")}
                                        for f in flags]
        if chain["location"] and chain["location"].get("source_page") and disclosure:
            insp = inspect_document(disclosure.id, chain["location"]["source_page"], verify=False)
            text = insp.get("page_text") or ""
            probe = (raw_value or "")[:12]
            i = text.find(probe) if probe else -1
            chain["page_excerpt"] = re.sub(r"\s+", " ", text[max(0, i - 80): i + 160] if i >= 0 else text[:240])
        return chain
    finally:
        session.close()


# ---------------------------------------------------------------------------
# Reproducible queries
# ---------------------------------------------------------------------------

_WRITE = re.compile(r"\b(insert|update|delete|drop|alter|create|replace|attach|detach|pragma|vacuum|reindex)\b", re.I)


def database_fingerprint() -> str:
    """SHA-256 over table names and row counts plus the max id of each table:
    cheap to compute, and changes whenever data are added or removed."""
    init_db()
    h = hashlib.sha256()
    with engine().connect() as conn:
        for name in sorted(Base.metadata.tables):
            n = conn.exec_driver_sql(f"SELECT COUNT(*), MAX(id) FROM {name}").one()
            h.update(f"{name}:{n[0]}:{n[1]}|".encode())
    return h.hexdigest()


def run_query(sql: str, out: str | None = None, name: str | None = None, fmt: str = "csv") -> dict:
    """Run a read-only SQL query and log it for reproducibility.

    The database is opened read-only (SQLite ``mode=ro``), so a query cannot
    modify data whatever it contains. The query text, its hash, a database
    fingerprint, the row count and the output file's hash are recorded in
    ``research_queries``.
    """
    init_db()
    if _WRITE.search(sql):
        raise ValueError("only read-only SELECT/WITH queries are allowed")
    from .models import is_sqlite
    if is_sqlite():
        uri = Path(db_path()).resolve().as_uri() + "?mode=ro"
        conn = sqlite3.connect(uri, uri=True)
        try:
            cur = conn.execute(sql)
            cols = [c[0] for c in cur.description or []]
            rows = cur.fetchall()
        finally:
            conn.close()
    else:   # v1.9: other back ends run the query in a read-only transaction
        with engine().connect() as conn:
            conn.exec_driver_sql("SET TRANSACTION READ ONLY")
            res = conn.exec_driver_sql(sql)
            cols, rows = list(res.keys()), [tuple(r) for r in res.fetchall()]
            conn.rollback()
    out_path, out_hash = None, None
    if out:
        out_path = Path(out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        if fmt == "parquet":
            _write_parquet(out_path, cols, rows)
        else:
            with out_path.open("w", encoding="utf-8-sig", newline="") as fh:
                w = csv.writer(fh)
                w.writerow(cols)
                w.writerows(rows)
        out_hash = _sha256_file(out_path)
    fp = database_fingerprint()
    session = SessionLocal()
    try:
        log = ResearchQuery(kind="QUERY", name=name, query_text=sql,
                            query_sha256=hashlib.sha256(sql.encode()).hexdigest(),
                            database_sha256=fp, row_count=len(rows),
                            output_path=str(out_path) if out_path else None, output_sha256=out_hash,
                            software_version=__version__, run_at=utcnow())
        session.add(log)
        session.commit()
        log_id = log.id
    finally:
        session.close()
    return {"columns": cols, "rows": rows, "row_count": len(rows), "output": str(out_path) if out_path else None,
            "output_sha256": out_hash, "database_fingerprint": fp, "log_id": log_id}


def _write_parquet(path: Path, cols, rows):
    try:
        import pyarrow as pa
        import pyarrow.parquet as pq
    except ImportError as exc:
        raise RuntimeError("Parquet export needs the optional 'pyarrow' package "
                           "(pip install pyarrow); CSV and SQLite exports need nothing extra") from exc
    table = pa.table({c: [r[i] for r in rows] for i, c in enumerate(cols)})
    pq.write_table(table, path)


# ---------------------------------------------------------------------------
# Dataset release
# ---------------------------------------------------------------------------

def release_dataset(out_dir: str = "releases", name: str | None = None, security_code: str | None = None,
                    formats: tuple[str, ...] = ("csv", "sqlite"), **options) -> dict:
    """Write a versioned, self-describing dataset release.

    v2.0: delegates to :func:`ashare.release.build_release`, which excludes
    licensed data by default, can pseudonymise personal names, writes a
    data-quality report and a CITATION.cff, and builds the SQLite snapshot
    on any database back end.
    """
    from .release import build_release
    return build_release(out_dir, name, security_code, formats, **options)
