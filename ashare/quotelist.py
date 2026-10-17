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
"""
from __future__ import annotations

import json
import math
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx

from .config import USER_AGENT, MARKET_RPS, market_raw_dir
from .http import RateLimitedClient, Cancelled

FS = "m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23"        # SZSE main, ChiNext, SSE main, STAR
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
        self.client = RateLimitedClient(USER_AGENT, MARKET_RPS, retries=retries)
        self.variants = _ordered_variants()
        self.errors: list[str] = []
        self.variant = None

    def _get(self, variant, pn, pz):
        name, base, headers, _ = variant
        params = {"pn": pn, "pz": pz, "po": 1, "np": 1, "fltt": 2, "invt": 2, "fid": "f12", "fs": FS,
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

    def page(self, pn: int, pz: int | None = None):
        """(total, rows, page size) for page ``pn``; tries the variants in turn."""
        order = [self.variant] if self.variant else []
        order += [v for v in self.variants if v is not self.variant]
        for v in order:
            size = pz or v[3]
            try:
                total, rows = self._get(v, pn, size)
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
    """Try page 1 of every variant once (about six requests) and report each result."""
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
    finally:
        client.close()
    if working:
        _remember(working)
        verdict = (f"The quote list answers with variant '{working}'; it is remembered and used first from now on. "
                   "Run 'Update the company list' again to fetch listing dates.")
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


def fetch_pages(fields: str, kind: str, progress=None, max_pages: int = 400) -> dict:
    """Every page of the quote list for ``fields``, resuming from today's cache.

    Returns ``{"rows": [...], "total": n, "complete": bool, "pages": k,
    "variant": name, "errors": [...]}``. Pages already fetched today are not
    fetched again; a failure stops the run but keeps what was fetched."""
    path = _cache_path(kind)
    cache = {"pages": {}, "total": None, "page_size": None}
    try:
        cache.update(json.loads(path.read_text(encoding="utf-8")))
    except Exception:
        pass
    pager = _Pager(fields)
    error = None
    try:
        pn = 1
        while pn <= max_pages:
            if str(pn) in cache["pages"]:
                pn += 1
                if cache["total"] is not None and (pn - 1) * cache["page_size"] >= cache["total"]:
                    break
                continue
            try:
                total, rows, size = pager.page(pn, cache["page_size"])
            except QuoteListError as exc:
                error = str(exc)
                break
            cache["total"], cache["page_size"] = total, size
            cache["pages"][str(pn)] = rows
            try:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
            except OSError:
                pass
            if progress and pn % 10 == 0:
                progress(f"  quote list: page {pn} of {math.ceil(total / size) if size else '?'}")
            if not rows or pn * size >= total:
                break
            pn += 1
    finally:
        pager.close()
    rows = [r for k in sorted(cache["pages"], key=int) for r in cache["pages"][k]]
    total = cache["total"] or 0
    size = cache["page_size"] or 100
    expected_pages = math.ceil(total / size) if total else None
    complete = bool(expected_pages) and all(str(p) in cache["pages"] for p in range(1, expected_pages + 1)) \
        and len({str(r.get("f12")) for r in rows}) >= COMPLETE_MIN
    return {"rows": rows, "total": total, "complete": complete, "pages": len(cache["pages"]),
            "expected_pages": expected_pages, "variant": pager.variant[0] if pager.variant else None,
            "error": error, "errors": pager.errors}


class ListingInfo(dict):
    """code -> {name, listing_date}, with how complete the list is."""
    complete = False
    total = 0
    note = None


def listing_info(progress=None) -> ListingInfo:
    r = fetch_pages("f12,f14,f26", "listing", progress=progress)
    out = ListingInfo()
    for row in r["rows"]:
        code = str(row.get("f12") or "").zfill(6)
        raw = str(row.get("f26") or "").strip()
        ld = f"{raw[:4]}-{raw[4:6]}-{raw[6:8]}" if len(raw) == 8 and raw.isdigit() and raw != "00000000" else None
        out[code] = {"name": row.get("f14"), "listing_date": ld}
    out.complete, out.total = r["complete"], r["total"]
    if not r["complete"]:
        if not r["rows"]:
            out.note = ("the quote list refused every request (" + (r["error"] or "no answer") + "); run "
                        "'Diagnose the quote list' (ashare-cli diagnose-quote-list) to see why")
        else:
            out.note = (f"quote list incomplete: {r['pages']} of {r['expected_pages'] or '?'} pages fetched "
                        f"({len(out)} companies); their listing dates were applied. Run 'Update the company list' "
                        "again to fetch the rest (pages already fetched today are kept)")
    return out
