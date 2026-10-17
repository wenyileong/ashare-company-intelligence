"""Announcement catalogue: one company at a time, or the whole market (v2.0.1).

Whole market (no security code)
    v2.0 queried CNINFO once per company, which for ~5,600 companies is at
    least 5,600 requests before any downloads, and printed nothing until the
    end, so a whole-market run looked stuck. v2.0.1 queries each exchange as
    a whole for the requested categories, in date windows small enough that
    CNINFO returns every result (a window with too many results is split),
    and matches announcements to companies by security code. Reports for
    January to October take a few hundred requests instead of several
    thousand.

    Downloads, if asked for, run as a second phase after the catalogue, with
    a size and time estimate first and a progress line as they go. Both
    phases commit as they go, so a stopped run loses nothing and running it
    again carries on (existing records are updated, downloaded files are
    skipped).
"""
from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path
from typing import Callable

from .models import SessionLocal, Company, Disclosure, init_db
from .disclosures import (CNInfoDisclosureAdapter, persist_disclosures, persist_announcement, store_downloaded,
                          REPORT_CATEGORIES, CNINFO_QUERY_URL)

# Results CNINFO returns for one query before paging stops being reliable.
# Typical document sizes (MB) for the download estimate.
TYPICAL_MB = {"annual_report": 6.0, "interim_report": 3.5, "quarterly_report": 0.8, "sustainability_report": 3.0}


def _say(progress: Callable[[str], None] | None, text: str) -> None:
    if progress:
        progress(text)


def catalogue_disclosures(since: str, until: str, kind: str = "reports", security_code: str | None = None,
                          download_documents: bool = False, max_pages: int = 10000,
                          progress: Callable[[str], None] | None = None, mode: str = "auto",
                          refresh: bool = False, retry_shortfalls: bool = False) -> dict:
    """Catalogue announcements. ``mode``: 'auto' (market-wide without a code,
    per company with one), 'market' or 'company'."""
    init_db()
    if kind not in REPORT_CATEGORIES:
        raise ValueError(f"Unknown disclosure kind: {kind}")
    if mode == "market" or (mode == "auto" and not security_code):
        return catalogue_market(since, until, kind, download_documents, progress=progress, refresh=refresh,
                                retry_shortfalls=retry_shortfalls)
    return catalogue_by_company(since, until, kind, security_code, download_documents, max_pages, progress)


def catalogue_by_company(since, until, kind="reports", security_code=None, download_documents=False,
                         max_pages=10000, progress=None) -> dict:
    session = SessionLocal()
    adapter = CNInfoDisclosureAdapter()
    totals = {"mode": "company", "companies": 0, "inserted": 0, "updated": 0, "downloaded": 0, "raw_pages": 0,
              "errors": []}
    try:
        query = session.query(Company)
        if security_code:
            query = query.filter(Company.security_code == security_code.zfill(6))
        companies = query.order_by(Company.security_code).all()
        n = len(companies)
        if n > 1:
            _say(progress, f"{n} companies, one query each (at least {n} requests, about {n // 60 + 1} minutes "
                           "at one per second, plus downloads).")
        for i, company in enumerate(companies, 1):
            totals["companies"] += 1
            try:
                pages = adapter.query_pages(company, since, until, kind=kind, max_pages=max_pages)
                result = persist_disclosures(company, pages, kind, download_documents=download_documents)
                for key in ("inserted", "updated", "downloaded", "raw_pages"):
                    totals[key] += result[key]
                if n > 1 and (result["inserted"] or result["downloaded"] or i % 50 == 0 or i == n):
                    _say(progress, f"[{i}/{n}] {company.security_code} {company.short_name_cn or ''}: "
                                   f"{result['inserted']} new, {result['downloaded']} downloaded "
                                   f"(total {totals['inserted']} new)")
            except Exception as exc:
                totals["errors"].append({"code": company.security_code, "error": repr(exc)})
                _say(progress, f"[{i}/{n}] {company.security_code}: error {exc!r}")
                import httpx
                recent = totals["errors"][-5:]
                if (len(recent) == 5 and isinstance(exc, (httpx.TransportError, httpx.HTTPStatusError))
                        and [e["code"] for e in recent] == [c.security_code for c in companies[i - 5:i]]):
                    from .errors import friendly_error
                    _say(progress, "Five companies in a row failed, so the run stopped here.\n" + friendly_error(exc))
                    totals["stopped_early"] = True
                    break
        return totals
    finally:
        adapter.close()
        session.close()


def catalogue_market(since: str, until: str, kind: str = "reports", download_documents: bool = False,
                     progress: Callable[[str], None] | None = None, adapter=None, refresh: bool = False,
                     retry_shortfalls: bool = False) -> dict:
    """Catalogue every company's announcements with market-wide queries
    (v2.0.3: one query per window, resumable by day; see market_catalogue)."""
    from .market_catalogue import catalogue
    return catalogue(since, until, kind, download_documents, refresh=refresh, retry_shortfalls=retry_shortfalls,
                     progress=progress, adapter=adapter)


def _wanted(row) -> bool:
    """Documents the extractors read: full reports (not summaries or English
    versions) and the announcement types that have an extractor."""
    from .ops import _wants_document, DOWNLOAD_KINDS_DEFAULT
    return _wants_document(row.title_cn or "", row.kind or "", DOWNLOAD_KINDS_DEFAULT)


def download_estimate(rows) -> dict:
    mb = sum(TYPICAL_MB.get(r.kind or "", 1.0) for r in rows)
    n = len(rows)
    return {"documents": n, "approx_gb": round(mb / 1024, 1), "approx_hours": round(n * 1.5 / 3600, 1)}


def download_pending(ids: list[int] | None = None, kinds: tuple[str, ...] | None = None,
                     progress: Callable[[str], None] | None = None, adapter=None) -> dict:
    """Download catalogued documents not yet on disk (given ids, or all of some kinds)."""
    own = adapter is None
    adapter = adapter or CNInfoDisclosureAdapter()
    session = SessionLocal()
    done = failed = 0
    try:
        q = session.query(Disclosure).filter(Disclosure.document_url.isnot(None))
        if ids is not None:
            if not ids:
                return {"downloaded": 0, "download_failed": 0}
            q = q.filter(Disclosure.id.in_(ids))
        if kinds:
            q = q.filter(Disclosure.kind.in_(kinds))
        rows = [r for r in q.order_by(Disclosure.announcement_date.desc())
                if not (r.local_path and Path(r.local_path).exists())]
        est = download_estimate(rows)
        _say(progress, f"Downloading {est['documents']} documents: roughly {est['approx_gb']} GB and "
                       f"{est['approx_hours']} hours at the polite rate. You can stop at any time; running the "
                       "same action again skips files already downloaded.")
        companies = {c.id: c for c in session.query(Company)}
        n = len(rows)
        for i, row in enumerate(rows, 1):
            try:
                store_downloaded(adapter, companies[row.company_id], row)
                session.commit()
                done += 1
            except Exception as exc:
                session.rollback()
                failed += 1
                _say(progress, f"  [{i}/{n}] {row.sec_code} {row.title_cn}: download failed ({exc!r})")
            if i % 25 == 0 or i == n:
                _say(progress, f"  [{i}/{n}] downloaded {done}" + (f", {failed} failed" if failed else ""))
        return {"downloaded": done, "download_failed": failed}
    finally:
        session.close()
        if own:
            adapter.close()
