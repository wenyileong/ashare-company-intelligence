"""Whole-market operations (v1.9): resumable jobs, high-water marks,
incremental daily updates, scheduling and storage management.

Jobs
    A job has one item per unit of work (a company, or a day for market-wide
    catalogues). Items are committed one at a time, so a job interrupted at
    any point (crash, power cut, cancel) resumes where it stopped; every
    handler writes with upserts, so a repeated item never duplicates rows.
    Failed items are retried on the next run, up to three attempts, and
    listed for attention.

High-water marks
    Each source keeps the last date it has covered (per company or market
    wide), so an incremental run fetches only what is new.

Daily update
    Announcements are catalogued market-wide by day (one paged query per
    exchange and day, rather than one per company), documents are downloaded
    only for the kinds the extractors read, prices are fetched from each
    company's last stored date, and the extractors run for the companies
    that received new documents.
"""
from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
import sys
import time
from datetime import date, timedelta
from pathlib import Path

import httpx

from .timeutil import utcnow
from .models import Base, SessionLocal, init_db, Company, Disclosure, MarketBar, Job, JobItem, HighWaterMark

MAX_ATTEMPTS = 3


# --- high-water marks ---------------------------------------------------------------

def get_mark(source: str, scope: str, kind: str) -> str | None:
    s = SessionLocal()
    try:
        m = s.query(HighWaterMark).filter_by(source=source, scope=scope, kind=kind).one_or_none()
        return m.value if m else None
    finally:
        s.close()


def set_mark(source: str, scope: str, kind: str, value: str) -> None:
    s = SessionLocal()
    try:
        m = s.query(HighWaterMark).filter_by(source=source, scope=scope, kind=kind).one_or_none()
        if m is None:
            m = HighWaterMark(source=source, scope=scope, kind=kind, value=value)
            s.add(m)
        elif value > m.value:
            m.value = value
        m.updated_at = utcnow()
        s.commit()
    finally:
        s.close()


def marks() -> list[dict]:
    init_db()
    s = SessionLocal()
    try:
        return [{"source": m.source, "scope": m.scope, "kind": m.kind, "value": m.value,
                 "updated": m.updated_at.isoformat(timespec="seconds") if m.updated_at else None}
                for m in s.query(HighWaterMark).order_by(HighWaterMark.source, HighWaterMark.scope)]
    finally:
        s.close()


# --- handlers ------------------------------------------------------------------------

def _day_range(start: str, end: str) -> list[str]:
    d0, d1 = date.fromisoformat(start), date.fromisoformat(end)
    return [(d0 + timedelta(days=i)).isoformat() for i in range((d1 - d0).days + 1)]


DOWNLOAD_KINDS_DEFAULT = ("annual_report", "interim_report", "quarterly_report", "sustainability_report",
                          "regulatory_enquiry", "earnings_forecast_or_flash")


def _wants_document(title: str, kind: str, policy: tuple[str, ...]) -> bool:
    """Download documents for the kinds the extractors read (titles decide)."""
    if kind in policy:
        return True
    from .corporate_actions import classify_action_title
    from .regulatory import classify_event_title
    from .management import classify_management_title
    from .security_master import classify_listing_title
    from .control import classify_pledge_title
    from .transactions import classify_transaction_title
    return bool(classify_action_title(title) or classify_event_title(title) or classify_management_title(title)
                or classify_listing_title(title) or classify_pledge_title(title) or classify_transaction_title(title))


def catalogue_market_day(day: str, kind: str = "all", download: bool = True,
                         policy: tuple[str, ...] = DOWNLOAD_KINDS_DEFAULT) -> dict:
    """All announcements of one day, both exchanges, matched to known companies."""
    from .disclosures import CNInfoDisclosureAdapter, store_downloaded, classify_title, clean_title
    from .disclosures import persist_announcement
    adapter = CNInfoDisclosureAdapter()
    s = SessionLocal()
    res = {"day": day, "announcements": 0, "matched": 0, "inserted": 0, "downloaded": 0, "unknown_codes": 0,
           "requests": 0}
    try:
        by_code = {c.security_code: c for c in s.query(Company)}
        for column in ("szse", "sse"):
            for page_no, data, raw in adapter.query_market_pages(day, day, column=column, kind=kind):
                res["requests"] += 1
                from .storage import store_raw
                from .config import CNINFO_QUERY_URL
                store_raw("CNINFO", CNINFO_QUERY_URL, raw, {"content_type": "application/json", "scope": "market",
                                                            "column": column, "day": day, "kind": kind,
                                                            "page_num": page_no})
                for item in data.get("announcements") or []:
                    res["announcements"] += 1
                    code = str(item.get("secCode") or "").zfill(6)
                    c = by_code.get(code)
                    if c is None:
                        res["unknown_codes"] += 1
                        continue
                    res["matched"] += 1
                    row, created = persist_announcement(s, c, item)
                    res["inserted"] += created
                    title = clean_title(item.get("announcementTitle")) or ""
                    if download and row.document_url and not (row.local_path and Path(row.local_path).exists()) \
                            and _wants_document(title, classify_title(title), policy):
                        store_downloaded(adapter, c, row)
                        res["downloaded"] += 1
                        res["requests"] += 1
                    s.commit()
        return res
    finally:
        s.close()
        adapter.close()


def _handle_catalogue_day(item_key: str, params: dict) -> dict:
    r = catalogue_market_day(item_key, params.get("kind", "all"), params.get("download", True),
                             tuple(params.get("policy") or DOWNLOAD_KINDS_DEFAULT))
    set_mark("CNINFO", "*", "announcements", item_key)
    return r


def _handle_catalogue_company(item_key: str, params: dict) -> dict:
    from .disclosure_pipeline import catalogue_disclosures
    since = params["since"]
    if params.get("incremental"):
        mark = get_mark("CNINFO", item_key, f"announcements:{params.get('kind', 'reports')}")
        if mark:
            since = max(since, (date.fromisoformat(mark) + timedelta(days=1)).isoformat())
    until = params.get("until") or date.today().isoformat()
    if since > until:
        return {"skipped": "up to date"}
    r = catalogue_disclosures(since, until, params.get("kind", "reports"), item_key, params.get("download", False))
    if r.get("errors"):
        raise RuntimeError(r["errors"][0]["error"])
    set_mark("CNINFO", item_key, f"announcements:{params.get('kind', 'reports')}", until)
    return {k: r[k] for k in ("inserted", "updated", "downloaded")}


def _handle_market(item_key: str, params: dict) -> dict:
    from .market import acquire_market_data
    start = params.get("start") or "2015-01-01"
    s = SessionLocal()
    try:
        c = s.query(Company).filter_by(security_code=item_key).first()
        last = s.query(MarketBar.trade_date).filter(MarketBar.company_id == c.id, MarketBar.adjustment == params.get(
            "adjust", "none")).order_by(MarketBar.trade_date.desc()).first() if c else None
    finally:
        s.close()
    if params.get("incremental") and last:
        start = max(start, (date.fromisoformat(last[0]) + timedelta(days=1)).isoformat())
    end = params.get("end") or date.today().isoformat()
    if start > end:
        return {"skipped": "up to date"}
    r = acquire_market_data(item_key, start, end, "eastmoney", params.get("adjust", "none"))
    if r["errors"]:
        raise RuntimeError(str(r["errors"][0]))
    set_mark("EASTMONEY_PUBLIC", item_key, "daily_bars", end)
    return {"inserted": r["bars_inserted"], "updated": r["bars_updated"]}


EXTRACTORS = ("financials", "corporate_actions", "regulatory", "management", "segments", "subsidiaries",
              "human_capital", "esg", "listing", "top_holders", "control", "pledges", "transactions")


def _handle_extract(item_key: str, params: dict) -> dict:
    out = {}
    steps = params.get("steps") or EXTRACTORS
    for step in steps:
        if step == "financials":
            from .financials import extract_financials
            r = extract_financials(item_key, "all")
        elif step == "corporate_actions":
            from .corporate_actions import extract_corporate_actions
            r = extract_corporate_actions(item_key)
        elif step == "regulatory":
            from .regulatory import extract_regulatory_events
            r = extract_regulatory_events(item_key)
        elif step == "management":
            from .management import extract_management_events, extract_rosters
            r = {"events": extract_management_events(item_key), "rosters": extract_rosters(item_key)}
        elif step == "segments":
            from .segments import extract_segments
            r = extract_segments(item_key)
        elif step == "subsidiaries":
            from .group import extract_subsidiaries
            r = extract_subsidiaries(item_key)
        elif step == "human_capital":
            from .human_capital import extract_human_capital
            r = extract_human_capital(item_key)
        elif step == "esg":
            from .esg import extract_esg
            r = extract_esg(item_key)
        elif step == "listing":
            from .security_master import extract_listing_events
            r = extract_listing_events(item_key)
        elif step == "top_holders":
            from .control import extract_top_holders
            r = extract_top_holders(item_key)
        elif step == "control":
            from .control import extract_control
            r = extract_control(item_key)
        elif step == "pledges":
            from .control import extract_pledges
            r = extract_pledges(item_key)
        elif step == "transactions":
            from .transactions import extract_transactions
            r = extract_transactions(item_key)
        else:
            raise ValueError(f"unknown extraction step {step}")
        out[step] = {k: v for k, v in (r.items() if isinstance(r, dict) else []) if not isinstance(v, (list, dict))}
    return out


HANDLERS = {"catalogue_day": _handle_catalogue_day, "catalogue": _handle_catalogue_company, "market": _handle_market,
            "extract": _handle_extract}


# --- jobs ----------------------------------------------------------------------------

def create_job(kind: str, params: dict, items: list[str] | None = None) -> int:
    if kind not in HANDLERS:
        raise ValueError(f"job kind must be one of {', '.join(HANDLERS)}")
    init_db()
    s = SessionLocal()
    try:
        if items is None:
            if kind == "catalogue_day":
                items = _day_range(params["since"], params.get("until") or date.today().isoformat())
            else:
                q = s.query(Company)
                if params.get("codes"):
                    q = q.filter(Company.security_code.in_([c.zfill(6) for c in params["codes"]]))
                items = [c.security_code for c in q.order_by(Company.security_code)]
        job = Job(kind=kind, params=json.dumps(params, ensure_ascii=False), status="QUEUED", total=len(items))
        s.add(job)
        s.flush()
        for k in dict.fromkeys(items):
            s.add(JobItem(job_id=job.id, item_key=k))
        s.commit()
        return job.id
    finally:
        s.close()


def request_cancel(job_id: int) -> None:
    s = SessionLocal()
    try:
        j = s.get(Job, job_id)
        if j and j.status in ("QUEUED", "RUNNING"):
            j.cancel_requested = 1
            s.commit()
    finally:
        s.close()


def _transient(exc) -> bool:
    return isinstance(exc, (httpx.TransportError, httpx.HTTPStatusError, TimeoutError, ConnectionError))


def run_job(job_id: int, progress=None, sleep=time.sleep) -> dict:
    """Run (or resume) a job. ``progress(done, total, item_key, status)`` is called after each item."""
    init_db()
    s = SessionLocal()
    try:
        job = s.get(Job, job_id)
        if job is None:
            raise ValueError(f"no job {job_id}")
        if job.status == "DONE":
            return job_summary(job_id)
        params = json.loads(job.params or "{}")
        job.status, job.started_at, job.cancel_requested = "RUNNING", job.started_at or utcnow(), 0
        s.commit()
        handler = HANDLERS[job.kind]
        items = [i for i in s.query(JobItem).filter(JobItem.job_id == job_id).order_by(JobItem.id)
                 if i.status == "PENDING" or (i.status == "FAILED" and i.attempts < MAX_ATTEMPTS)]
        for item in items:
            s.refresh(job)
            if job.cancel_requested:
                job.status = "CANCELLED"
                s.commit()
                break
            item.attempts += 1
            try:
                result = handler(item.item_key, params)
                item.status, item.result, item.last_error = "DONE", json.dumps(result, ensure_ascii=False,
                                                                               default=str), None
            except Exception as exc:  # noqa: BLE001 - every failure is recorded on the item
                item.status, item.last_error = "FAILED", f"{type(exc).__name__}: {exc}"[:1000]
                job.last_error = item.last_error
                if _transient(exc) and item.attempts < MAX_ATTEMPTS:
                    sleep(min(2 ** item.attempts, 30))
            item.updated_at = utcnow()
            job.done = s.query(JobItem).filter_by(job_id=job_id, status="DONE").count()
            job.failed = s.query(JobItem).filter_by(job_id=job_id, status="FAILED").count()
            s.commit()
            if progress:
                progress(job.done, job.total, item.item_key, item.status)
        if job.status == "RUNNING":
            retryable = s.query(JobItem).filter(JobItem.job_id == job_id, JobItem.status == "FAILED",
                                                JobItem.attempts < MAX_ATTEMPTS).count()
            job.status = "DONE" if not job.failed else ("PARTIAL" if not retryable else "QUEUED")
            job.finished_at = utcnow()
            s.commit()
        return job_summary(job_id)
    finally:
        s.close()


def job_summary(job_id: int) -> dict:
    s = SessionLocal()
    try:
        j = s.get(Job, job_id)
        failed = [{"item": i.item_key, "attempts": i.attempts, "error": i.last_error}
                  for i in s.query(JobItem).filter_by(job_id=job_id, status="FAILED").limit(20)]
        return {"id": j.id, "kind": j.kind, "status": j.status, "total": j.total, "done": j.done, "failed": j.failed,
                "params": json.loads(j.params or "{}"), "failed_items": failed}
    finally:
        s.close()


def list_jobs(limit: int = 20) -> list[dict]:
    init_db()
    s = SessionLocal()
    try:
        return [{"id": j.id, "kind": j.kind, "status": j.status, "done": j.done, "failed": j.failed, "total": j.total,
                 "created": j.created_at.isoformat(timespec="minutes") if j.created_at else None,
                 "error": (j.last_error or "")[:80]}
                for j in s.query(Job).order_by(Job.id.desc()).limit(limit)]
    finally:
        s.close()


def daily_update(until: str | None = None, prices: bool = True, extract: bool = True, progress=None) -> dict:
    """Incremental update: announcements since the market-wide mark, new prices, extraction."""
    init_db()
    until = until or date.today().isoformat()
    mark = get_mark("CNINFO", "*", "announcements")
    since = (date.fromisoformat(mark) + timedelta(days=1)).isoformat() if mark else \
        (date.fromisoformat(until) - timedelta(days=1)).isoformat()
    out = {"since": since, "until": until}
    if since <= until:
        j = create_job("catalogue_day", {"since": since, "until": until, "kind": "all", "download": True})
        out["catalogue"] = run_job(j, progress)
    if prices:
        out["prices"] = update_prices(until, progress)
    if extract:
        s = SessionLocal()
        try:
            codes = sorted({c.security_code for d, c in s.query(Disclosure, Company).join(
                Company, Disclosure.company_id == Company.id).filter(Disclosure.announcement_date >= since,
                                                                     Disclosure.local_path.isnot(None))})
        finally:
            s.close()
        if codes:
            j = create_job("extract", {}, codes)
            out["extract"] = run_job(j, progress)
    return out


def update_prices(until: str, progress=None) -> dict:
    """Today's bars for the whole market in one pass over the quote list; companies whose last
    bar is older than the previous weekday are backfilled one by one (a resumable job)."""
    from .market import fetch_eastmoney_snapshot, persist_snapshot
    out = {}
    try:
        snap = fetch_eastmoney_snapshot(until)
        out["snapshot"] = persist_snapshot(snap)
        if snap:
            set_mark("EASTMONEY_PUBLIC", "*", "daily_snapshot", until)
    except Exception as exc:  # the backfill below still runs
        out["snapshot_error"] = f"{type(exc).__name__}: {exc}"
    prev = date.fromisoformat(until) - timedelta(days=1)
    while prev.weekday() >= 5:
        prev -= timedelta(days=1)
    s = SessionLocal()
    try:
        from sqlalchemy import func
        last = dict(s.query(MarketBar.company_id, func.max(MarketBar.trade_date)).filter(
            MarketBar.adjustment == "none").group_by(MarketBar.company_id).all())
        stale = [c.security_code for c in s.query(Company) if (last.get(c.id) or "") < prev.isoformat()]
    finally:
        s.close()
    if stale:
        j = create_job("market", {"incremental": True, "end": until}, stale)
        out["backfill"] = run_job(j, progress)
    out["backfilled_companies"] = len(stale)
    return out


def estimate_daily_requests(announcements: int = 4000, page_size: int = 30, download_share: float = 0.2,
                            companies: int = 5300, rps: float = 1.0) -> dict:
    """Requests and minutes for a daily incremental run at the polite rate."""
    queries = 2 * max(1, -(-announcements // (2 * page_size)))
    downloads = round(announcements * download_share)
    prices = -(-companies // 100)          # the quote list returns 100 securities per request
    total = queries + downloads + prices
    return {"catalogue_queries": queries, "document_downloads": downloads, "price_requests": prices,
            "total_requests": total, "minutes_at_rate": round(total / rps / 60, 1)}


# --- scheduling ------------------------------------------------------------------------

TASK_NAME = "AShareScraper daily update"


def _cli_command() -> str:
    if getattr(sys, "frozen", False):
        exe = Path(sys.executable).with_name("ashare-cli.exe")
        return f'"{exe}" daily-update'
    return f'"{sys.executable}" -m ashare.app daily-update'


def schedule(enable: bool, at: str = "18:30", dry_run: bool = False) -> dict:
    """Create or remove a daily Windows Task Scheduler entry (opt-in). Elsewhere, print a cron line."""
    if platform.system() != "Windows":
        line = f"{at.split(':')[1]} {at.split(':')[0]} * * 1-5 cd '{Path.cwd()}' && {_cli_command()}"
        return {"platform": platform.system(), "note": "add this line with 'crontab -e'" if enable else
                "remove the line from 'crontab -e'", "cron": line}
    data_folder = os.environ.get("ASHARE_DB", "ashares.db")
    tr = f'cmd /c "cd /d \\"{Path(data_folder).resolve().parent}\\" && {_cli_command()}"'
    cmd = (["schtasks", "/Create", "/F", "/SC", "WEEKLY", "/D", "MON,TUE,WED,THU,FRI", "/TN", TASK_NAME, "/TR", tr,
            "/ST", at] if enable else ["schtasks", "/Delete", "/F", "/TN", TASK_NAME])
    if dry_run:
        return {"command": cmd}
    r = subprocess.run(cmd, capture_output=True, text=True)
    return {"command": cmd, "returncode": r.returncode, "output": (r.stdout or r.stderr).strip()}


# --- storage -------------------------------------------------------------------------------

def _size(path: Path) -> int:
    if not path.exists():
        return 0
    if path.is_file():
        return path.stat().st_size
    return sum(p.stat().st_size for p in path.rglob("*") if p.is_file())


def storage_stats() -> dict:
    from .config import db_path, raw_dir, disclosure_dir, market_raw_dir
    init_db()
    s = SessionLocal()
    try:
        by_kind = {}
        for d in s.query(Disclosure).filter(Disclosure.local_path.isnot(None)):
            p = Path(d.local_path)
            k = by_kind.setdefault(d.kind or "other", {"documents": 0, "bytes": 0, "missing": 0})
            if p.exists():
                k["documents"] += 1
                k["bytes"] += p.stat().st_size
            else:
                k["missing"] += 1
        pruned = s.query(Disclosure).filter(Disclosure.local_path.is_(None), Disclosure.sha256.isnot(None)).count()
    finally:
        s.close()
    mb = lambda b: round(b / 1e6, 1)  # noqa: E731
    return {"database_mb": mb(_size(db_path())), "documents_mb": mb(_size(disclosure_dir())),
            "raw_responses_mb": mb(_size(raw_dir())), "market_raw_mb": mb(_size(market_raw_dir())),
            "pruned_documents": pruned,
            "by_kind": {k: {**v, "mb": mb(v.pop("bytes"))} for k, v in sorted(by_kind.items())}}


def prune_documents(kinds: tuple[str, ...] = ("other_announcement",), older_than_days: int = 0,
                    dry_run: bool = True) -> dict:
    """Delete downloaded documents of the given kinds, keeping URL and hash so they can be fetched again.
    Periodic reports are never pruned by default."""
    from .config import disclosure_dir
    init_db()
    s = SessionLocal()
    cutoff = (date.today() - timedelta(days=older_than_days)).isoformat()
    out = {"documents": 0, "mb": 0.0, "dry_run": dry_run}
    root = disclosure_dir().resolve()
    try:
        for d in s.query(Disclosure).filter(Disclosure.local_path.isnot(None), Disclosure.kind.in_(kinds)):
            p = Path(d.local_path)
            if not p.exists() or (d.announcement_date or "") > cutoff:
                continue
            if root not in p.resolve().parents:
                continue      # never delete outside the documents folder
            out["documents"] += 1
            out["mb"] += p.stat().st_size / 1e6
            if not dry_run:
                p.unlink()
                d.local_path = None
        if not dry_run:
            s.commit()
        out["mb"] = round(out["mb"], 1)
        return out
    finally:
        s.close()


def refetch_document(disclosure_id: int) -> dict:
    """Download a pruned document again and check it against the stored hash."""
    import hashlib
    from .disclosures import CNInfoDisclosureAdapter, store_downloaded
    init_db()
    s = SessionLocal()
    adapter = CNInfoDisclosureAdapter()
    try:
        d = s.get(Disclosure, disclosure_id)
        if d is None or not d.document_url:
            raise ValueError("no such disclosure, or it has no document URL")
        old = d.sha256
        c = s.get(Company, d.company_id)
        store_downloaded(adapter, c, d)
        s.commit()
        return {"disclosure_id": d.id, "path": d.local_path, "hash_matches": old is None or old == d.sha256}
    finally:
        adapter.close()
        s.close()


# --- DuckDB / analytics export -------------------------------------------------------------

def export_duckdb(out: str = "ashares.duckdb", tables: list[str] | None = None) -> dict:
    """Copy tables into a DuckDB file (optional dependency) for fast analytics."""
    try:
        import duckdb
    except ImportError as exc:
        raise RuntimeError("DuckDB export needs the optional duckdb package (pip install duckdb)") from exc
    from .models import engine
    init_db()
    names = tables or sorted(Base.metadata.tables)
    con = duckdb.connect(out)
    n = 0
    try:
        with engine().connect() as conn:
            for t in names:
                rows = conn.exec_driver_sql(f"SELECT * FROM {t}").fetchall()
                cols = list(Base.metadata.tables[t].columns.keys())
                con.execute(f"DROP TABLE IF EXISTS {t}")
                con.execute(f"CREATE TABLE {t} ({', '.join(c + ' VARCHAR' for c in cols)})")
                if rows:
                    con.executemany(f"INSERT INTO {t} VALUES ({', '.join('?' for _ in cols)})",
                                    [[None if v is None else str(v) for v in r] for r in rows])
                n += 1
    finally:
        con.close()
    return {"file": out, "tables": n, "note": "columns are stored as text; cast in queries"}
