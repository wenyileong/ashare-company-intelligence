"""Market-wide announcement catalogue (v2.0.3).

The live runs of v2.0.2 showed four problems with CNINFO's announcement
search when the stock field is left empty (findings 3, 6, 13 and 14):

* the ``column`` parameter is ignored: SSE and SZSE queries return the same
  whole-market results, so querying both doubled every run;
* one query appears to return at most 100 pages of 30 (3,000 results); later
  pages repeat earlier content while CNINFO still reports more to come, so a
  day with more than 3,000 announcements was truncated *and* paged on to the
  program's limit of 2,000 pages;
* every run restarted at its start date;
* an error inside a split month abandoned the rest of the month.

This module replaces the v2.0.2 loop:

* **One query per window** (column ``szse``; the exchange of each
  announcement comes from its security code).
* **Paging stops** as soon as a page brings no new announcement, once every
  announcement CNINFO reported has arrived, or after the last page CNINFO's
  total implies.
* **Splitting**: a window over the limit is halved down to single days; a
  single day over the limit is split by announcement category, and a
  category still over the limit by exchange board.
* **Shortfalls**: for every day, the distinct announcements received are
  compared with CNINFO's total; a gap is recorded as SHORTFALL and reported.
* **Resume**: every finished day is recorded in ``catalogue_days``; a rerun
  queries only days that are not yet finished (or failed), unless asked to
  refresh.
* **Errors per day**: a failure is recorded against the days of the window
  that failed; the run carries on with the next window and lists the failed
  days at the end. Three failed windows in a row stop the run.
* **Progress** within a query every 20 pages.

``probe_paging`` checks the 3,000-result limit directly (finding 6): it reads
pages 100, 101 and 150 of a busy day and compares the announcement IDs.
"""
from __future__ import annotations

import math
from datetime import date, timedelta
from pathlib import Path
from typing import Callable

from .models import SessionLocal, Company, CatalogueDay, init_db
from .timeutil import utcnow

PAGE_SIZE = 30
QUERY_LIMIT = 3000               # results one CNINFO query returns reliably (100 pages of 30)
MARKET_COLUMN = "szse"           # ignored by CNINFO when the stock field is empty; any value works
PROGRESS_EVERY = 20              # pages

# CNINFO's announcement categories for listed A-shares (the codes used by its
# own search page). A day over the limit is split into these; an
# announcement filed under no category, or under several, is caught by the
# day-level comparison with CNINFO's total.
ALL_CATEGORIES = (
    "category_ndbg_szsh", "category_bndbg_szsh", "category_yjdbg_szsh", "category_sjdbg_szsh",
    "category_yjygjxz_szsh", "category_qyfpxzcs_szsh", "category_dshgg_szsh", "category_jshgg_szsh",
    "category_gddh_szsh", "category_rcjy_szsh", "category_gszl_szsh", "category_zj_szsh",
    "category_sf_szsh", "category_zf_szsh", "category_gqjl_szsh", "category_pg_szsh",
    "category_jj_szsh", "category_gszq_szsh", "category_kzzq_szsh", "category_qtrz_szsh",
    "category_gqbd_szsh", "category_bcgz_szsh", "category_cqdq_szsh", "category_fxts_szsh",
    "category_tbclts_szsh", "category_tszlq_szsh",
)
# Last-resort split of one category on one day (if the board filter works
# with an empty stock field; if it does not, the shortfall is reported).
PLATES = ("sz", "szcy", "sh", "shkcp")

DONE_STATES = ("DONE", "SHORTFALL")


class StopRun(Exception):
    """Too many consecutive failures; the run stops (finished days are kept)."""


def _say(progress, text):
    if progress:
        progress(text)


def _days(a: str, b: str) -> list[str]:
    d0, d1 = date.fromisoformat(a), date.fromisoformat(b)
    return [(d0 + timedelta(days=i)).isoformat() for i in range((d1 - d0).days + 1)]


def _months(since: str, until: str):
    d0, d1 = date.fromisoformat(since), date.fromisoformat(until)
    while d0 <= d1:
        nxt = date(d0.year + (d0.month == 12), d0.month % 12 + 1, 1)
        end = min(nxt - timedelta(days=1), d1)
        yield d0.isoformat(), end.isoformat()
        d0 = end + timedelta(days=1)


def _runs(days: list[str]):
    """Consecutive runs of days, as (first, last) pairs."""
    out, start, prev = [], None, None
    for d in days:
        dd = date.fromisoformat(d)
        if start is None:
            start = prev = dd
        elif dd == prev + timedelta(days=1):
            prev = dd
        else:
            out.append((start.isoformat(), prev.isoformat()))
            start = prev = dd
    if start is not None:
        out.append((start.isoformat(), prev.isoformat()))
    return out


def _ann_id(item: dict) -> str | None:
    v = item.get("announcementId") or item.get("announcementID")
    if v:
        return str(v)
    adj = item.get("adjunctUrl")
    return f"adj:{adj}" if adj else None


def _item_day(item: dict) -> str | None:
    from .disclosures import announcement_date
    return announcement_date(item.get("announcementTime"))


def _category_for(kind: str) -> str:
    from .disclosures import REPORT_CATEGORIES
    if kind not in REPORT_CATEGORIES:
        raise ValueError(f"Unknown disclosure kind: {kind}")
    return REPORT_CATEGORIES[kind]


def _split_categories(category: str) -> list[str]:
    """Categories to split a query into: the kind's own list, or every category for kind 'all'."""
    parts = [c for c in category.split(";") if c]
    if len(parts) > 1:
        return [c + ";" for c in parts]
    if not parts:
        return [c + ";" for c in ALL_CATEGORIES]
    return []


class MarketQuery:
    """Pages one exchange-wide query to the end, de-duplicating by announcement ID."""

    def __init__(self, adapter, store_raw: bool = True):
        self.adapter, self.store_raw = adapter, store_raw
        self.requests = 0

    def page(self, a, b, category, plate, page_num):
        from .config import CNINFO_QUERY_URL
        payload = {"pageNum": str(page_num), "pageSize": str(PAGE_SIZE), "tabName": "fulltext",
                   "column": MARKET_COLUMN, "stock": "", "searchkey": "", "secid": "", "plate": plate,
                   "category": category, "trade": "", "seDate": f"{a}~{b}", "sortName": "", "sortType": "",
                   "isHLtitle": "true"}
        response = self.adapter.http.post(CNINFO_QUERY_URL, data=payload, headers={
            "Referer": "https://www.cninfo.com.cn/new/commonUrl?url=disclosure/list/notice",
            "Origin": "https://www.cninfo.com.cn", "X-Requested-With": "XMLHttpRequest",
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8"})
        self.requests += 1
        data = response.json() or {}
        if self.store_raw:
            from .storage import store_raw
            store_raw("CNINFO", CNINFO_QUERY_URL, response.content,
                      {"content_type": "application/json", "scope": "market", "window": f"{a}~{b}",
                       "category": category, "plate": plate, "page_num": page_num})
        return data

    def first(self, a, b, category="", plate=""):
        data = self.page(a, b, category, plate, 1)
        return int(data.get("totalAnnouncement") or 0), data

    def rest(self, a, b, category, plate, first_data, total, label="", progress=None,
             on_items: Callable | None = None) -> dict:
        """Continue a query from its first page; returns {id: item}."""
        seen: dict[str, dict] = {}
        last_page = max(1, math.ceil(total / PAGE_SIZE)) if total else 1
        page_num, data = 1, first_data
        stop = "end"
        while True:
            items = data.get("announcements") or []
            new = {}
            for it in items:
                k = _ann_id(it)
                if k and k not in seen:
                    new[k] = it
            seen.update(new)
            if on_items and new:
                on_items(list(new.values()))
            if progress and page_num % PROGRESS_EVERY == 0:
                _say(progress, f"    {label}: page {page_num} of {last_page} ({len(seen):,} of {total:,})")
            if not items:
                break
            if not new and page_num > 1:
                stop = "repeat"          # CNINFO is repeating earlier results: nothing more to get
                break
            if total and len(seen) >= total:
                break
            if not data.get("hasMore"):
                break
            if page_num >= last_page + 1:
                stop = "past_total"
                break
            page_num += 1
            data = self.page(a, b, category, plate, page_num)
        self.last_stop = stop
        return seen


def _china_today() -> str:
    from datetime import datetime, timezone
    return (datetime.now(timezone.utc) + timedelta(hours=8)).date().isoformat()


def _record(session, kind, day, status, expected=None, stored=None, window=None, method=None, queries=None,
            error=None):
    # Today (China time) is still receiving announcements: never treat it as finished.
    if status in DONE_STATES and day >= _china_today():
        status = "OPEN"
    row = session.query(CatalogueDay).filter_by(kind=kind, day=day).one_or_none()
    if row is None:
        row = CatalogueDay(kind=kind, day=day)
        session.add(row)
    row.status, row.expected, row.stored, row.window = status, expected, stored, window
    row.method, row.queries, row.error, row.updated_at = method, queries, error, utcnow()


def day_status(kind: str, since: str | None = None, until: str | None = None) -> list[dict]:
    init_db()
    s = SessionLocal()
    try:
        q = s.query(CatalogueDay).filter_by(kind=kind)
        if since:
            q = q.filter(CatalogueDay.day >= since)
        if until:
            q = q.filter(CatalogueDay.day <= until)
        return [{"day": r.day, "status": r.status, "expected": r.expected, "stored": r.stored, "window": r.window,
                 "method": r.method, "queries": r.queries, "error": r.error} for r in q.order_by(CatalogueDay.day)]
    finally:
        s.close()


def catalogue(since: str, until: str, kind: str = "all", download_documents: bool = False,
              refresh: bool = False, retry_shortfalls: bool = False, days: list[str] | None = None,
              progress: Callable[[str], None] | None = None, adapter=None, max_failures: int = 3) -> dict:
    """Catalogue every company's announcements, resuming by day."""
    from .disclosures import CNInfoDisclosureAdapter, persist_announcement
    init_db()
    category = _category_for(kind)
    own = adapter is None
    adapter = adapter or CNInfoDisclosureAdapter()
    session = SessionLocal()
    q = MarketQuery(adapter)
    tot = {"mode": "market", "kind": kind, "queries": 0, "announcements": 0, "inserted": 0, "updated": 0,
           "unmatched": 0, "downloaded": 0, "days_done": 0, "days_skipped": 0, "days_shortfall": [],
           "days_failed": [], "errors": []}
    new_rows: list[int] = []
    try:
        companies = {c.security_code: c for c in session.query(Company)}
        if not companies:
            return {**tot, "note": "the company list is empty; run update-universe first"}
        wanted = sorted(set(days)) if days else _days(since, until)
        if not refresh:
            done = {r.day for r in session.query(CatalogueDay).filter(
                CatalogueDay.kind == kind, CatalogueDay.day.in_(wanted),
                CatalogueDay.status.in_(("DONE",) if retry_shortfalls else DONE_STATES))}
        else:
            done = set()
        pending = [d for d in wanted if d not in done]
        tot["days_skipped"] = len(wanted) - len(pending)
        _say(progress, f"Market-wide catalogue, kind={kind}: {len(pending)} day(s) to fetch"
                       + (f", {tot['days_skipped']} already finished (skipped)" if tot["days_skipped"] else "")
                       + ". One query per window; busy days are split until CNINFO returns every announcement.")
        if download_documents:
            from .disclosure_pipeline import _wanted
        state = {"consecutive": 0}

        def persist(items):
            for it in items:
                tot["announcements"] += 1
                code = str(it.get("secCode") or "").zfill(6)
                company = companies.get(code)
                if company is None:
                    tot["unmatched"] += 1
                    continue
                row, created = persist_announcement(session, company, it)
                if row is None:
                    continue
                tot["inserted"] += created
                tot["updated"] += not created
                if download_documents and row.document_url and _wanted(row) and \
                        not (row.local_path and Path(row.local_path).exists()):
                    session.flush()
                    new_rows.append(row.id)
            session.commit()

        def run_query(a, b, cat, plate, label, total, first_data):
            """Page a query that is within the limit; returns the IDs by day."""
            got = q.rest(a, b, cat, plate, first_data, total, label, progress, persist)
            by_day: dict[str, set] = {}
            for k, it in got.items():
                by_day.setdefault(_item_day(it) or a, set()).add(k)
            return got, by_day

        finished: set[str] = set()

        def plate_split(d, cat, name):
            ids = set()
            for plate in PLATES:
                pt, pdata = q.first(d, d, cat, plate)
                if pt:
                    got, _ = run_query(d, d, cat, plate, f"{d} {name}/{plate}", pt, pdata)
                    ids |= set(got)
            return ids

        def single_day(d, total, first_data, win):
            """A single day over the limit: split by category, then a category over the limit by board."""
            cats = _split_categories(category)
            ids: set[str] = set()
            method = "CATEGORY_SPLIT"
            if not cats:                     # a kind with one category: split it by board
                ids |= plate_split(d, category, kind)
                method = "PLATE_SPLIT"
            for ci, cat in enumerate(cats, 1):
                if ci > 1 and ci % 5 == 1:
                    _say(progress, f"    {d}: category {ci - 1} of {len(cats)} done "
                                   f"({len(ids):,} of {total:,} so far)")
                ct, cdata = q.first(d, d, cat, "")
                if ct == 0:
                    continue
                name = cat.rstrip(";").split("_")[1] if cat.count("_") >= 2 else cat
                if ct > QUERY_LIMIT:
                    ids |= plate_split(d, cat, name)
                    method = "CATEGORY_AND_PLATE_SPLIT"
                else:
                    got, _ = run_query(d, d, cat, "", f"{d} {name}", ct, cdata)
                    ids |= set(got)
            if len(ids) < total and cats:
                # Some announcements are under no category (or a category not in the list): a last pass over
                # the whole day by board picks up what each board's first 3,000 results hold.
                _say(progress, f"    {d}: {total - len(ids):,} announcements outside the categories; "
                               "trying the whole day by board")
                before = len(ids)
                ids |= plate_split(d, category, "remainder")
                if len(ids) > before:
                    method += "+BOARD_REMAINDER"
            status = "DONE" if len(ids) >= total else "SHORTFALL"
            _record(session, kind, d, status, total, len(ids), win, method, q.requests)
            session.commit()
            finished.add(d)
            if status == "SHORTFALL":
                tot["days_shortfall"].append({"day": d, "expected": total, "stored": len(ids)})
                _say(progress, f"  {d}: SHORTFALL, {len(ids):,} of {total:,} announcements received after splitting")
            else:
                _say(progress, f"  {d}: {total:,} announcements after splitting ({method.lower()}), complete")
            tot["days_done"] += 1

        def window(a, b):
            try:
                total, data = q.first(a, b, category, "")
                if total > QUERY_LIMIT and a != b:
                    da, db = date.fromisoformat(a), date.fromisoformat(b)
                    mid = da + (db - da) // 2
                    window(a, mid.isoformat())
                    window((mid + timedelta(days=1)).isoformat(), b)
                    return
                if total > QUERY_LIMIT:
                    _say(progress, f"  {a}: {total:,} announcements, more than one query returns; splitting")
                    single_day(a, total, data, f"{a}~{b}")
                else:
                    _say(progress, f"  {a} to {b}: {total:,} announcements" if a != b else f"  {a}: {total:,} announcements")
                    got, by_day = run_query(a, b, category, "", f"{a}~{b}", total, data)
                    complete = len(got) >= total
                    for d in _days(a, b):
                        n = len(by_day.get(d, ()))
                        if a == b:
                            _record(session, kind, d, "DONE" if complete else "SHORTFALL", total, n,
                                    f"{a}~{b}", "DAY", q.requests)
                        else:
                            _record(session, kind, d, "DONE" if complete else "SHORTFALL", None, n,
                                    f"{a}~{b}", "WINDOW", q.requests)
                        tot["days_done"] += 1
                        finished.add(d)
                    session.commit()
                    if not complete:
                        tot["days_shortfall"].append({"day": f"{a}~{b}", "expected": total, "stored": len(got)})
                        _say(progress, f"  {a} to {b}: SHORTFALL, {len(got):,} of {total:,} received")
                state["consecutive"] = 0
            except StopRun:
                raise
            except Exception as exc:
                from .http import Cancelled
                if isinstance(exc, Cancelled):
                    raise
                session.rollback()
                failed = [d for d in _days(a, b) if d not in finished]
                for d in failed:
                    _record(session, kind, d, "FAILED", window=f"{a}~{b}", error=repr(exc))
                session.commit()
                tot["days_failed"].extend(failed)
                tot["errors"].append({"window": f"{a}~{b}", "error": repr(exc)})
                _say(progress, f"  {a} to {b}: error {exc!r}; recorded as failed, run again to retry these days")
                state["consecutive"] += 1
                if state["consecutive"] >= max_failures:
                    raise StopRun(exc)

        try:
            for ma, mb in _months(min(wanted), max(wanted)) if wanted else []:
                month_days = [d for d in pending if ma <= d <= mb]
                for a, b in _runs(month_days):
                    window(a, b)
        except StopRun as stop:
            from .errors import friendly_error
            tot["stopped_early"] = True
            _say(progress, f"{max_failures} windows in a row failed, so the run stopped here.\n"
                 + friendly_error(stop.args[0]))
        tot["queries"] = q.requests
        tot["days_failed"] = sorted(set(tot["days_failed"]))
        _say(progress, f"Catalogue done: {tot['announcements']:,} announcements in {q.requests:,} queries; "
                       f"{tot['inserted']:,} new, {tot['updated']:,} already known; {tot['days_done']} day(s) "
                       f"finished, {len(tot['days_shortfall'])} with a shortfall, {len(tot['days_failed'])} failed.")
        if tot["days_failed"]:
            _say(progress, "Failed days (run the same action again to retry only these): "
                 + ", ".join(tot["days_failed"]))
        if download_documents and new_rows:
            from .disclosure_pipeline import download_pending
            tot.update(download_pending(new_rows, progress=progress, adapter=adapter))
        return tot
    finally:
        session.close()
        if own:
            adapter.close()


def busy_days(kind: str = "all", since: str | None = None, until: str | None = None,
              threshold: int = 2500) -> list[str]:
    """Days to re-catalogue: recorded shortfalls, and days catalogued before
    v2.0.3 whose stored announcements reach ``threshold`` (a sign that the
    3,000-result limit may have cut them short)."""
    from sqlalchemy import func
    from .models import Disclosure
    init_db()
    s = SessionLocal()
    try:
        out = {r.day for r in s.query(CatalogueDay).filter(CatalogueDay.kind == kind,
                                                            CatalogueDay.status.in_(("SHORTFALL", "FAILED")))}
        recorded = {r.day for r in s.query(CatalogueDay).filter(CatalogueDay.kind == kind,
                                                                 CatalogueDay.status == "DONE")}
        q = s.query(Disclosure.announcement_date, func.count(Disclosure.id)).group_by(Disclosure.announcement_date)
        for d, n in q:
            if d and n >= threshold and d not in recorded:
                out.add(d)
        days = sorted(d for d in out if (not since or d >= since) and (not until or d <= until))
        return days
    finally:
        s.close()


def recatalogue_busy_days(kind: str = "all", since: str | None = None, until: str | None = None,
                          threshold: int = 2500, progress=None, adapter=None) -> dict:
    days = busy_days(kind, since, until, threshold)
    if not days:
        _say(progress, "No busy days to re-catalogue: no recorded shortfalls or failures, and no earlier day "
                       f"with {threshold:,} or more stored announcements.")
        return {"days": [], "note": "nothing to do"}
    _say(progress, f"Re-cataloguing {len(days)} day(s): {', '.join(days)}")
    r = catalogue(days[0], days[-1], kind, days=days, refresh=True, progress=progress, adapter=adapter)
    r["days"] = days
    return r


def probe_paging(day: str = "2026-04-24", adapter=None) -> dict:
    """Finding 6: does CNINFO stop at 100 pages (3,000 results) for one query?

    Reads pages 1, 100, 101 and 150 of an exchange-wide, all-category query
    for ``day`` and compares the announcement IDs."""
    from .disclosures import CNInfoDisclosureAdapter
    own = adapter is None
    adapter = adapter or CNInfoDisclosureAdapter()
    q = MarketQuery(adapter, store_raw=False)
    try:
        ids, info = {}, {}
        total = 0
        for p in (1, 100, 101, 150):
            data = q.page(day, day, "", "", p)
            if p == 1:
                total = int(data.get("totalAnnouncement") or 0)
            items = data.get("announcements") or []
            ids[p] = [_ann_id(i) for i in items if _ann_id(i)]
            info[p] = {"items": len(items), "has_more": bool(data.get("hasMore"))}
        out = {"day": day, "total": total, "pages": info}
        if total <= QUERY_LIMIT:
            out["verdict"] = "INCONCLUSIVE"
            out["explanation"] = (f"{day} has {total:,} announcements, within one query's limit; probe a busier day "
                                  "(for example 2026-04-24 or 2026-04-30).")
            return out
        s100, s101, s150 = set(ids[100]), set(ids[101]), set(ids[150])
        if (not s101 or s101 <= s100 or s101 == set(ids[1])) and (not s150 or s150 <= s100 | s101):
            out["verdict"] = "LIMIT_CONFIRMED"
            out["explanation"] = ("Pages after 100 bring no new announcements: one query returns at most 3,000. "
                                  "v2.0.3 splits such days by category and records any shortfall.")
        elif s101 - s100 and s150 - (s100 | s101):
            out["verdict"] = "NO_LIMIT"
            out["explanation"] = ("Pages 101 and 150 bring new announcements: CNINFO pages past 3,000. Splitting is "
                                  "still safe, only slower than necessary.")
        else:
            out["verdict"] = "UNCLEAR"
            out["explanation"] = "The pages overlap partly; keep the report and send it with a bug report."
        out["overlap_101_with_100"] = len(s101 & s100)
        out["new_on_101"] = len(s101 - s100)
        out["new_on_150"] = len(s150 - (s100 | s101))
        out["requests"] = q.requests
        return out
    finally:
        if own:
            adapter.close()
