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
                          refresh: bool = False, retry_shortfalls: bool = False,
                          refresh_days: int | None = None) -> dict:
    """Catalogue announcements. ``mode``: 'auto' (market-wide without a code,
    per company with one), 'market' or 'company'."""
    init_db()
    if kind not in REPORT_CATEGORIES:
        raise ValueError(f"Unknown disclosure kind: {kind}")
    if mode == "market" or (mode == "auto" and not security_code):
        return catalogue_market(since, until, kind, download_documents, progress=progress, refresh=refresh,
                                retry_shortfalls=retry_shortfalls, refresh_days=refresh_days)
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
                     retry_shortfalls: bool = False, refresh_days: int | None = None) -> dict:
    """Catalogue every company's announcements with market-wide queries
    (v2.0.3: one query per window, resumable by day; see market_catalogue)."""
    from .market_catalogue import catalogue
    return catalogue(since, until, kind, download_documents, refresh=refresh, retry_shortfalls=retry_shortfalls,
                     progress=progress, adapter=adapter, refresh_days=refresh_days)


def _wanted(row) -> bool:
    """Documents the extractors read: full reports (not summaries or English
    versions) and the announcement types that have an extractor."""
    from .ops import _wants_document, DOWNLOAD_KINDS_DEFAULT
    return _wants_document(row.title_cn or "", row.kind or "", DOWNLOAD_KINDS_DEFAULT)


#: v2.1.2 (finding 119): seconds a document when no download has been timed yet. v2.1 assumed 1.5 s; the author's
#: downloads took about 5.6 s.
DEFAULT_SECONDS = 5.0


def _rates_file() -> Path:
    from .config import db_path
    return db_path().resolve().parent / "download_rates.json"


def _read_rates() -> dict:
    import json
    try:
        r = json.loads(_rates_file().read_text(encoding="utf-8"))
        return r if isinstance(r, dict) else {}
    except Exception:
        return {}


def _record_rates(seconds: float, n: int, mb_by_kind: dict) -> None:
    """Keep the measured rate (seconds a document) and mean size by kind for the next estimate."""
    import json
    if n <= 0:
        return
    r = _read_rates()
    r["seconds_per_document"] = round(seconds / n, 2)
    sizes = r.get("mb_by_kind") if isinstance(r.get("mb_by_kind"), dict) else {}
    for kind, (mb, k) in mb_by_kind.items():
        if k:
            sizes[kind] = round(mb / k, 2)
    r["mb_by_kind"] = sizes
    try:
        _rates_file().write_text(json.dumps(r, indent=2), encoding="utf-8")
    except Exception:
        pass


def download_estimate(rows) -> dict:
    """Size and time of a download. v2.1.2: from the rate and sizes measured in earlier downloads, when known."""
    rates = _read_rates()
    sizes = rates.get("mb_by_kind") if isinstance(rates.get("mb_by_kind"), dict) else {}
    try:
        per = float(rates.get("seconds_per_document") or DEFAULT_SECONDS)
    except (TypeError, ValueError):
        per = DEFAULT_SECONDS
    mb = 0.0
    for r in rows:
        k = r.kind or ""
        try:
            mb += float(sizes.get(k) or TYPICAL_MB.get(k, 1.0))
        except (TypeError, ValueError):
            mb += TYPICAL_MB.get(k, 1.0)
    n = len(rows)
    return {"documents": n, "approx_gb": round(mb / 1024, 1), "approx_hours": round(n * per / 3600, 1),
            "seconds_each": per, "measured": "seconds_per_document" in rates}


def download_pending(ids: list[int] | None = None, kinds: tuple[str, ...] | None = None,
                     progress: Callable[[str], None] | None = None, adapter=None) -> dict:
    """Download catalogued documents not yet on disk (given ids, or all of some kinds).

    v2.1.2: the IDs are queried a few hundred at a time (finding 120: a ten-month refresh queued more than SQLite
    takes in one statement); progress gives seconds a document and the time left, and the measured rate is kept
    for the next estimate (finding 119)."""
    import time
    from .dbutil import in_chunks
    from .extractstate import Progress
    own = adapter is None
    adapter = adapter or CNInfoDisclosureAdapter()
    session = SessionLocal()
    done = failed = 0
    t0 = time.monotonic()
    sizes: dict = {}
    try:
        q = session.query(Disclosure).filter(Disclosure.document_url.isnot(None))
        if kinds:
            q = q.filter(Disclosure.kind.in_(kinds))
        if ids is not None:
            if not ids:
                return {"downloaded": 0, "download_failed": 0}
            found = in_chunks(q, Disclosure.id, sorted(set(ids)))
        else:
            found = q.all()
        found.sort(key=lambda r: (r.announcement_date or "", r.id), reverse=True)
        rows = [r for r in found if not (r.local_path and Path(r.local_path).exists())]
        est = download_estimate(rows)
        _say(progress, f"Downloading {est['documents']:,} documents: roughly {est['approx_gb']} GB and "
                       f"{est['approx_hours']} hours at {est['seconds_each']:.1f} s a document"
                       + (" (the rate of the last download)" if est["measured"] else "")
                       + ". You can stop at any time; running the same action again skips files already downloaded.")
        companies = {c.id: c for c in session.query(Company)}
        n = len(rows)
        prog = Progress(n, progress)
        try:
            for i, row in enumerate(rows, 1):
                try:
                    store_downloaded(adapter, companies[row.company_id], row)
                    session.commit()
                    done += 1
                    try:
                        mb = Path(row.local_path).stat().st_size / 1048576 if row.local_path else 0.0
                        tot_mb, k = sizes.get(row.kind or "", (0.0, 0))
                        sizes[row.kind or ""] = (tot_mb + mb, k + 1)
                    except OSError:
                        pass
                except Exception as exc:
                    session.rollback()
                    failed += 1
                    _say(progress, f"  [{i}/{n}] {row.sec_code} {row.title_cn}: download failed ({exc!r})")
                prog.step()
        finally:
            _record_rates(time.monotonic() - t0, done, sizes)
        return {"downloaded": done, "download_failed": failed}
    finally:
        session.close()
        if own:
            adapter.close()


def wanted_missing(since: str, until: str, kinds: tuple[str, ...] | None = None) -> list[int]:
    """IDs of documents dated ``since`` to ``until`` that the extractors read (``_wanted``) and that are not on disk.

    v2.1.2 (finding 121): the catalogue's download step chooses its documents from the database, not from a list
    held in memory, so a rerun downloads what an interrupted run left."""
    session = SessionLocal()
    try:
        out = []
        for row in (session.query(Disclosure)
                    .filter(Disclosure.document_url.isnot(None), Disclosure.announcement_date >= since,
                            Disclosure.announcement_date <= until,
                            *([Disclosure.kind.in_(kinds)] if kinds else []))
                    .yield_per(2000)):
            if row.local_path and Path(row.local_path).exists():
                continue
            if _wanted(row):
                out.append(row.id)
        return out
    finally:
        session.close()
