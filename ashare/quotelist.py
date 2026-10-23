"""The public Eastmoney quote list (v2.0.3, finding 4).

In the v2.0.2 live runs every request to the quote list
(``push2.eastmoney.com/api/qt/clist/get``) failed with HTTP 502, while the
same provider's daily-bar service worked. With no listing dates, every
point-in-time panel came out empty.

This module

* tries several **request variants** (the host names Eastmoney's own pages
  use, http as well as https, the Referer and Origin a browser would send,
  and a smaller page size), keeps the program's honest user agent in every
  one, and remembers the variant that worked;
* provides ``diagnose()``, which tries each variant once and reports what
  each returned, so the cause can be seen rather than guessed;
* makes the listing-date download **resumable**: every page fetched is kept
  in a per-day file in the market data folder, so a run that fails at page 40
  carries on at page 41, and a partial list is still applied (listing dates
  for the companies it holds; "not in the quote list" only from a complete
  list).

v2.0.6 (findings 50 and 57): the live list stopped at page 10 of 56 on every
run, so only about 1,000 companies received listing dates. The probable cause
is that Eastmoney serves at most the first 1,000 rows of one query. The list
is therefore also read **in parts**: one board at a time, each in both code
orders, which covers up to 2,000 companies a board. A page that fails is
retried after a pause; the error is reported; once a query has stopped at the
same page after its retries, that row limit is remembered for the day, so the
parts do not wait for it again. The quote list is paced at no more than one
request every two seconds.

v2.0.7 (findings 58, 59 and 66): the live list then refused even page 1, so the
cause is a refusal rather than a row limit. Three refused attempts in a row
(the request, again after 30 seconds and again after two minutes; any success
resets the count) now stop the whole reading, instead of every board pausing
in turn (49 minutes). The note lists every board read, with its error.
"""
from __future__ import annotations

import json
import math
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx

from .config import USER_AGENT, MARKET_RPS, market_raw_dir
from .http import RateLimitedClient, Cancelled, check_cancel

FS = "m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23"        # SZSE main, ChiNext, SSE main, STAR
# v2.0.6: the boards one at a time (code, fs filter, name)
BOARD_FS = (("szmb", "m:0+t:6", "Shenzhen main board"), ("szcy", "m:0+t:80", "ChiNext"),
            ("shmb", "m:1+t:2", "Shanghai main board"), ("shkcp", "m:1+t:23", "STAR Market"))
ORDERS = (1, 0)                 # po=1: codes descending; po=0: ascending
RETRY_WAITS = (30, 120)         # seconds before the second and third attempt at a failed page
QUOTE_RPS = min(MARKET_RPS, 0.5)
UT = "bd1d9ddb04089700cf9c27f6f7426281"
PATH = "/api/qt/clist/get"
BROWSER_HEADERS = {"Referer": "https://quote.eastmoney.com/center/gridlist.html",
                   "Origin": "https://quote.eastmoney.com",
                   "Accept": "application/json, text/javascript, */*; q=0.01"}

# name, base URL, extra headers, page size
VARIANTS = [
    ("push2", "https://push2.eastmoney.com", {}, 100),
    ("push2+referer", "https://push2.eastmoney.com", BROWSER_HEADERS, 100),
    ("82.push2+referer", "https://82.push2.eastmoney.com", BROWSER_HEADERS, 100),
    ("push2delay+referer", "https://push2delay.eastmoney.com", BROWSER_HEADERS, 100),
    ("push2+referer+pz20", "https://push2.eastmoney.com", BROWSER_HEADERS, 20),
    ("http-push2+referer", "http://push2.eastmoney.com", BROWSER_HEADERS, 100),
]
COMPLETE_MIN = 3000            # fewer rows than this cannot be the whole A-share list


def _variant_file() -> Path:
    return market_raw_dir() / "quote_list_variant.json"


def _cache_dir() -> Path:
    return market_raw_dir() / "quote_list_pages"


def _china_today() -> str:
    return (datetime.now(timezone.utc) + timedelta(hours=8)).date().isoformat()


def _ordered_variants():
    """Variants with the one that worked last time first."""
    try:
        last = json.loads(_variant_file().read_text(encoding="utf-8")).get("name")
    except Exception:
        last = None
    return sorted(VARIANTS, key=lambda v: v[0] != last)


def _remember(name: str) -> None:
    try:
        _variant_file().parent.mkdir(parents=True, exist_ok=True)
        _variant_file().write_text(json.dumps({"name": name, "at": _china_today()}), encoding="utf-8")
    except OSError:
        pass


class QuoteListError(RuntimeError):
    pass


class _Pager:
    """Fetches pages of the quote list, switching variant when one fails."""

    def __init__(self, fields: str, retries: int = 2):
        self.fields = fields
        self.client = RateLimitedClient(USER_AGENT, QUOTE_RPS, retries=retries)
        self.variants = _ordered_variants()
        self.errors: list[str] = []
        self.variant = None

    def _get(self, variant, pn, pz, fs: str = FS, po: int = 1):
        name, base, headers, _ = variant
        params = {"pn": pn, "pz": pz, "po": po, "np": 1, "fltt": 2, "invt": 2, "fid": "f12", "fs": fs,
                  "fields": self.fields, "ut": UT}
        r = self.client.get(base + PATH, params=params, headers=headers)
        payload = r.json()
        data = (payload or {}).get("data")
        if data is None:
            raise QuoteListError(f"answer without data (rc={(payload or {}).get('rc')})")
        rows = data.get("diff") or []
        if isinstance(rows, dict):
            rows = list(rows.values())
        return int(data.get("total") or 0), rows

    def page(self, pn: int, pz: int | None = None, fs: str = FS, po: int = 1):
        """(total, rows, page size) for page ``pn``; tries the variants in turn."""
        order = [self.variant] if self.variant else []
        order += [v for v in self.variants if v is not self.variant]
        for v in order:
            size = pz or v[3]
            try:
                total, rows = self._get(v, pn, size, fs, po)
                if self.variant is not v:
                    self.variant = v
                    _remember(v[0])
                return total, rows, size
            except Cancelled:
                raise
            except (httpx.HTTPError, OSError, ValueError, QuoteListError) as exc:
                self.errors.append(f"{v[0]} page {pn}: {_describe(exc)}")
        raise QuoteListError("every variant failed: " + "; ".join(self.errors[-len(order):]))

    def close(self):
        self.client.close()


def _describe(exc) -> str:
    if isinstance(exc, httpx.HTTPStatusError):
        return f"HTTP {exc.response.status_code}"
    return f"{type(exc).__name__}: {exc}"


def diagnose() -> dict:
    """Try page 1 of every variant once (about six requests), then page 11 with the variant that answered (two
    requests), and report each result."""
    client = RateLimitedClient(USER_AGENT, MARKET_RPS, retries=1)
    pager = _Pager("f12,f14,f26")
    pager.client.close()
    pager.client = client
    results = []
    working = None
    try:
        for v in VARIANTS:
            entry = {"variant": v[0], "url": v[1] + PATH}
            try:
                total, rows = pager._get(v, 1, v[3])
                entry.update(ok=True, total=total, rows=len(rows),
                             sample=", ".join(f"{r.get('f12')} {r.get('f14')} {r.get('f26')}" for r in rows[:2]))
                working = working or v[0]
            except Cancelled:
                raise
            except Exception as exc:
                entry.update(ok=False, error=_describe(exc))
            results.append(entry)
        # v2.0.6 (finding 57): does the list stop after the first 1,000 rows of one query? Page 11 of the whole
        # list, and page 11 of the Shanghai main board, with the variant that answered (two requests).
        deep = []
        if working:
            v = next(x for x in VARIANTS if x[0] == working)
            for label, fs in (("whole list", FS), ("Shanghai main board", BOARD_FS[2][1])):
                entry = {"variant": f"{working}, page 11 of the {label}", "url": v[1] + PATH, "deep": True}
                try:
                    total, rows = pager._get(v, 11, 100, fs, 1)
                    entry.update(ok=bool(rows), total=total, rows=len(rows),
                                 sample=", ".join(f"{r.get('f12')} {r.get('f14')}" for r in rows[:2]),
                                 **({} if rows else {"error": "no rows"}))
                except Cancelled:
                    raise
                except Exception as exc:
                    entry.update(ok=False, error=_describe(exc))
                deep.append(entry)
            results += deep
    finally:
        client.close()
    if working:
        _remember(working)
        verdict = (f"The quote list answers with variant '{working}'; it is remembered and used first from now on. "
                   "Run 'Update the company list' again to fetch listing dates.")
        whole = deep[0] if deep else None
        listed = next((e.get("total") or 0 for e in results if e.get("ok") and not e.get("deep")), 0)
        if whole is not None and not whole.get("ok") and listed > 1000:
            verdict += (" Page 11 is refused although the list holds more than 1,000 rows, so one query probably returns at "
                        "most 1,000 rows; the program then reads the list board by board, in both code orders.")
        elif whole is not None and not whole.get("ok"):
            verdict += (" Page 11 was refused (" + (whole.get("error") or "no rows") + "); the program reads the "
                        "list board by board when the whole list stops part-way.")
    elif all("HTTP 5" in (r.get("error") or "") for r in results):
        verdict = ("Every variant was refused by Eastmoney's servers (HTTP 5xx). The service may be refusing "
                   "automated requests from this network, or be down. Try again later or from another network; "
                   "until then, panels can use report evidence for year-by-year universes "
                   "(build-panel --universe-basis report-evidence), or import listing dates "
                   "(import-listing-events-csv).")
    else:
        verdict = ("No variant answered. Check the internet connection and any proxy or firewall (see the errors); "
                   "the Self-test's network checks help.")
    return {"results": results, "working": working, "verdict": verdict}


def _cache_path(kind: str) -> Path:
    return _cache_dir() / f"{kind}_{_china_today()}.json"


def _wait(seconds: float) -> None:
    """Sleep, ending early if the user presses Stop."""
    end = time.monotonic() + seconds
    while True:
        check_cancel()
        left = end - time.monotonic()
        if left <= 0:
            return
        time.sleep(min(1.0, left))


MAX_REFUSALS = 3                # v2.0.7: refused attempts in a row that stop the reading


class Refused(QuoteListError):
    """The quote list refused MAX_REFUSALS attempts in a row."""


class _Refusals:
    """Counts refused attempts in a row across the whole reading (any success resets it), and pauses before a
    second and third attempt (RETRY_WAITS). v2.0.7: the reading stops after three refused attempts in a row,
    instead of pausing again for every board (finding 58)."""

    def __init__(self, offline: bool):
        self.offline, self.n, self.errors = offline, 0, []

    def before(self) -> None:
        if self.n and not self.offline:
            _wait(RETRY_WAITS[min(self.n, len(RETRY_WAITS)) - 1])

    def ok(self) -> None:
        self.n = 0

    def failed(self, what: str) -> None:
        self.n += 1
        self.errors.append(what)
        if self.n >= MAX_REFUSALS:
            raise Refused("; ".join(self.errors[-MAX_REFUSALS:]))


def _attempt(pager: _Pager, ref: _Refusals, pn: int, pz, fs: str, po: int, label: str):
    ref.before()
    try:
        out = pager.page(pn, pz, fs, po)
    except Refused:
        raise
    except QuoteListError as exc:
        ref.failed(f"{label.strip(' ()') or 'whole list'} page {pn}: {exc}")
        raise
    ref.ok()
    return out


def _read_query(pager: _Pager, part: dict, fs: str, po: int, save, ref: _Refusals, progress=None,
                label: str = "", max_pages: int = 400, row_cap: int | None = None, late_tries: int = 2) -> str | None:
    """Read one query into ``part`` ({"pages", "total", "page_size", "error"}), resuming from its cached pages.
    Returns the error that stopped it, or None. A first page is tried until the reading is refused (Refused is
    raised); a later page at most ``late_tries`` times. With ``row_cap``, pages beyond the cap are not requested."""
    pn = 1
    tries = 0
    while pn <= max_pages:
        size = part.get("page_size")
        if str(pn) in part["pages"]:
            if part.get("total") is not None and size and pn * size >= part["total"]:
                return None
            pn += 1
            continue
        if row_cap is not None and size and (pn - 1) * size >= row_cap:
            part["error"] = f"page {pn}: beyond the {row_cap:,} rows one query returns"
            save()
            return part["error"]
        try:
            total, rows, size = _attempt(pager, ref, pn, size, fs, po, label)
        except Refused as exc:
            part["error"] = f"page {pn}: {str(exc).split('; ')[-1].split(': ', 1)[-1]}"
            part["failed_page"] = pn
            save()
            raise
        except QuoteListError as exc:
            tries += 1
            if pn == 1 or tries < late_tries:
                continue                      # try the same page again (after a pause)
            part["error"] = f"page {pn}: {exc}"
            part["failed_page"] = pn
            save()
            return part["error"]
        tries = 0
        part["total"], part["page_size"] = total, size
        part["pages"][str(pn)] = rows
        part["error"] = None
        part.pop("failed_page", None)
        save()
        if progress and pn % 10 == 0:
            progress(f"  quote list{label}: page {pn} of {math.ceil(total / size) if size else '?'}")
        if not rows or pn * size >= total:
            return None
        pn += 1
    return None


def _cap_path() -> Path:
    return _cache_dir() / f"row_cap_{_china_today()}.json"


def _known_cap():
    try:
        return int(json.loads(_cap_path().read_text(encoding="utf-8"))["row_cap"])
    except Exception:
        return None


def _remember_cap(cap: int) -> None:
    try:
        _cap_path().parent.mkdir(parents=True, exist_ok=True)
        _cap_path().write_text(json.dumps({"row_cap": cap}), encoding="utf-8")
    except OSError:
        pass


def _contiguous(part: dict) -> int:
    n = 0
    while str(n + 1) in part.get("pages", {}):
        n += 1
    return n


def _rows(part: dict) -> list[dict]:
    return [r for k in sorted(part.get("pages", {}), key=int) for r in part["pages"][k]]


def _part_complete(part: dict) -> bool:
    total, size = part.get("total"), part.get("page_size")
    if not total or not size:
        return part.get("total") == 0
    return all(str(p) in part["pages"] for p in range(1, math.ceil(total / size) + 1))


def fetch_pages(fields: str, kind: str, progress=None, max_pages: int = 400, use_cache: bool = True,
                min_rows: int = COMPLETE_MIN) -> dict:
    """Every page of the quote list for ``fields``, resuming from today's cache.

    Returns ``{"rows": [...], "total": n, "complete": bool, "pages": k, "expected_pages": m,
    "variant": name, "error": str|None, "errors": [...], "parts": {...}}``. Pages already fetched
    today are not fetched again; a failure stops that query but keeps what was fetched.

    v2.0.6: when the whole list stops part-way, it is read one board at a time in both code orders
    (see the module notes), and the rows are merged by code."""
    path = _cache_path(kind)
    cache = {"pages": {}, "total": None, "page_size": None, "parts": {}, "row_cap": None}
    if use_cache:
        try:
            cache.update(json.loads(path.read_text(encoding="utf-8")))
        except Exception:
            pass
    cache.setdefault("parts", {})
    if cache.get("row_cap") is None:
        cache["row_cap"] = _known_cap()          # confirmed earlier today, perhaps by another download

    def save():
        if not use_cache:
            return
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
        except OSError:
            pass

    pager = _Pager(fields)
    ref = _Refusals(pager.client.offline)
    error, refused = None, None
    parts_used = False
    try:
        cap = cache.get("row_cap")
        # A limit confirmed earlier today is tried once more: if the page beyond it now answers, it is dropped.
        error = _read_query(pager, cache, FS, 1, save, ref, progress, "", max_pages,
                            late_tries=1 if cap is not None else 2)
        size = cache.get("page_size")
        if cap is not None and size and _contiguous(cache) * size > cap:
            cache["row_cap"] = None
            try:
                _cap_path().unlink()
            except OSError:
                pass
            save()
        if not _part_complete(cache) and cache["pages"]:
            # The whole list stopped part-way. A stop at a page after earlier pages answered may be the number of
            # rows one query returns; it is confirmed when a board stops at the same number of rows, and is then
            # remembered for today. If the boards are refused too, the reading stops after three refused
            # attempts in a row.
            size = cache.get("page_size")
            candidate = _contiguous(cache) * size if size else None
            parts_used = True
            for code, fs, name in BOARD_FS:
                codes: set = set()
                btotal = None
                for po in ORDERS:
                    if btotal is not None and len(codes) >= btotal:
                        break
                    part = cache["parts"].setdefault(f"{code}:{po}", {"pages": {}, "total": None,
                                                                       "page_size": None, "error": None})
                    label = f" ({name}, {'descending' if po else 'ascending'})"
                    err = _read_query(pager, part, fs, po, save, ref, progress, label, max_pages,
                                      row_cap=cache.get("row_cap"), late_tries=1)
                    if err and part.get("failed_page"):
                        before = (part["failed_page"] - 1) * (part.get("page_size") or 0)
                        if candidate and before == candidate:
                            cache["row_cap"] = candidate            # the same limit: confirmed, no waiting
                            _remember_cap(candidate)
                            ref.ok()                                # explained by the limit, not a refusal
                            save()
                        else:                                       # a different stop: try that page again
                            _read_query(pager, part, fs, po, save, ref, progress, label, max_pages,
                                        row_cap=cache.get("row_cap"), late_tries=MAX_REFUSALS)
                    btotal = part.get("total") if part.get("total") is not None else btotal
                    codes |= {str(r.get("f12")) for r in _rows(part)}
    except Refused as exc:
        refused = str(exc)
        save()
    finally:
        pager.close()
    merged: dict = {}
    for r in _rows(cache):
        merged[str(r.get("f12"))] = r
    board_info = {}
    for code, fs, name in BOARD_FS:
        codes, btotal, berr = set(), None, None
        for po in ORDERS:
            part = cache["parts"].get(f"{code}:{po}")
            if not part:
                continue
            for r in _rows(part):
                merged.setdefault(str(r.get("f12")), r)
                codes.add(str(r.get("f12")))
            btotal = part.get("total") if part.get("total") is not None else btotal
            berr = berr or part.get("error")
        attempted = any(f"{code}:{po}" in cache["parts"] for po in ORDERS)
        if btotal is not None or codes or attempted:      # v2.0.7: also a board refused at its first page
            board_info[code] = {"name": name, "total": btotal, "rows": len(codes),
                                "complete": btotal is not None and len(codes) >= btotal,
                                "error": None if btotal is not None and len(codes) >= btotal else berr}
    rows = list(merged.values())
    total = cache["total"] or 0
    size = cache["page_size"] or 100
    expected_pages = math.ceil(total / size) if total else None
    whole_complete = _part_complete(cache) and bool(expected_pages)
    boards_complete = len(board_info) == len(BOARD_FS) and all(b["complete"] for b in board_info.values())
    complete = (whole_complete or boards_complete) and len({str(r.get("f12")) for r in rows}) >= min_rows
    return {"rows": rows, "total": total, "complete": complete, "pages": len(cache["pages"]),
            "expected_pages": expected_pages, "variant": pager.variant[0] if pager.variant else None,
            "error": error, "errors": pager.errors, "parts": board_info, "parts_used": parts_used,
            "row_cap": cache.get("row_cap"), "refused": refused}


class ListingInfo(dict):
    """code -> {name, listing_date}, with how complete the list is."""
    complete = False
    total = 0
    note = None
    parts: dict = {}
    row_cap = None
    refused = None


def listing_info(progress=None) -> ListingInfo:
    r = fetch_pages("f12,f14,f26", "listing", progress=progress)
    out = ListingInfo()
    for row in r["rows"]:
        code = str(row.get("f12") or "").zfill(6)
        raw = str(row.get("f26") or "").strip()
        ld = f"{raw[:4]}-{raw[4:6]}-{raw[6:8]}" if len(raw) == 8 and raw.isdigit() and raw != "00000000" else None
        out[code] = {"name": row.get("f14"), "listing_date": ld}
    out.complete, out.total = r["complete"], r["total"]
    out.parts = r.get("parts", {})
    out.row_cap = r.get("row_cap")
    if r.get("parts_used") and r["complete"]:
        out.note = (f"quote list read board by board ({len(out):,} companies), because one query returns at most "
                    f"{r['row_cap']:,} rows" if r.get("row_cap") else
                    f"quote list read board by board ({len(out):,} companies)")
    out.refused = r.get("refused")
    if r.get("refused") and not r["complete"]:
        out.note = (f"the quote list refused {MAX_REFUSALS} attempts in a row, so it was not read further "
                    f"({len(out):,} companies fetched; {r['refused']}). Eastmoney may be refusing requests from "
                    "this network for a while: run 'Update the company list' again later, or import listing dates "
                    "(see the user guide)")
    elif not r["complete"]:
        if not r["rows"]:
            out.note = ("the quote list refused every request (" + (r["error"] or "no answer") + "); run "
                        "'Diagnose the quote list' (ashare-cli diagnose-quote-list) to see why")
        else:
            boards = "; ".join(f"{b['name']} {b['rows']:,} of {format(b['total'], ',') if b['total'] is not None else '?'}"
                               + (f" ({b['error']})" if b.get("error") else "")
                               for b in r.get("parts", {}).values())
            out.note = (f"quote list incomplete: {len(out):,} companies fetched"
                        + (f" (whole list: {r['error']})" if r.get("error") else "")
                        + (f"; by board: {boards}" if boards else "")
                        + ". Their listing dates were applied. Run 'Update the company list' again later to fetch "
                          "the rest (what was fetched today is kept), or 'Diagnose the quote list' to see why")
    return out
