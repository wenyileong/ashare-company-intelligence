"""Market-wide announcement catalogue (v2.0.3; general splitter in v2.0.4).

The live runs of v2.0.2 showed four problems with CNINFO's announcement
search when the stock field is left empty (findings 3, 6, 13 and 14), which
v2.0.3 addressed: one query per window (the ``column`` parameter is
ignored), paging that stops when nothing new arrives (one query returns at
most 3,000 results), resume by day, and errors recorded per day.

The first live whole-market run under v2.0.3 (findings 20 to 34) left twelve
days short of CNINFO's total, for four reasons: the board codes ``sz`` and
``sh`` cover whole exchanges (they include ChiNext and STAR), some category
and board combinations still exceed 3,000 on the April deadline days, some
announcements are on neither the Shanghai nor the Shenzhen board (probably
Beijing), and some rows are repeated for several securities. v2.0.4
replaces the fixed split with a general one:

* **Rows, not IDs.** A row is an announcement for one security (ID and
  security code). The completeness check compares rows with CNINFO's total,
  which counts rows; announcements listed for several securities are counted
  separately and are no longer mistaken for a shortfall.
* **A general splitter.** A query over 3,000 is split along the next useful
  dimension: board (disjoint codes first, whole exchanges as a fallback,
  Beijing included), category, industry (``trade``), then batches of
  companies (``stock``, halved again if still over the limit). Each
  dimension is checked live: a filter that CNINFO ignores (every part
  reports the whole) or rejects (every part is empty) is not used again in
  the run, and a split whose parts do not reach the parent's total is
  recorded as "partition incomplete" with the amount.
* **Both sort orders.** A query with 3,001 to 6,000 results is first read
  newest-first and oldest-first; if CNINFO applies the limit to each order
  separately this reaches every row without splitting. Whether it does is
  detected on first use.
* **Gaps by board.** A gap is attributed to boards from CNINFO's board
  totals and the security codes of the rows received. Only a gap within the
  enabled boards makes a day SHORTFALL; a gap outside them (for example
  Beijing when it is off) is recorded but the day is DONE.
* **Early stop.** A query that cannot be read in full (over the limit, with
  no dimension left) stops after five pages that bring nothing new.
* **Strategy version.** Each day records the strategy that produced it;
  re-cataloguing skips shortfall days whose gap recurred under the current
  strategy, since repeating the same queries cannot help (finding 26).
* **Recent totals.** CNINFO's totals can grow after the fact (finding 28):
  finished days of the last 30 days are rechecked at the start of a run and
  fetched again if their total has grown.

``probe_paging`` (v2.0.3) checks the 3,000-result limit; ``probe_filters``
(v2.0.4) checks the board codes, the industry and company filters, the sort
orders and repeated rows on one day, with a verdict for each.
"""
from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass, replace
from datetime import date, timedelta
from pathlib import Path
from typing import Callable

from .models import SessionLocal, Company, CatalogueDay, init_db
from .timeutil import utcnow

PAGE_SIZE = 30
QUERY_LIMIT = 3000               # results one CNINFO query returns (100 pages of 30), confirmed live
MARKET_COLUMN = "szse"           # ignored by CNINFO when the stock field is empty; any value works
PROGRESS_EVERY = 20              # pages
EARLY_STOP_PAGES = 5             # a capped query stops after this many pages with nothing new
BATCH_SIZE = 150                 # companies per query when splitting by company
RECHECK_DAYS = 30                # finished days whose totals are rechecked at the start of a run
STRATEGY = 2                     # v2.0.4; v2.0.3 days have no strategy recorded

# CNINFO's announcement categories for listed A-shares (the codes used by its own search page).
ALL_CATEGORIES = (
    "category_ndbg_szsh", "category_bndbg_szsh", "category_yjdbg_szsh", "category_sjdbg_szsh",
    "category_yjygjxz_szsh", "category_qyfpxzcs_szsh", "category_dshgg_szsh", "category_jshgg_szsh",
    "category_gddh_szsh", "category_rcjy_szsh", "category_gszl_szsh", "category_zj_szsh",
    "category_sf_szsh", "category_zf_szsh", "category_gqjl_szsh", "category_pg_szsh",
    "category_jj_szsh", "category_gszq_szsh", "category_kzzq_szsh", "category_qtrz_szsh",
    "category_gqbd_szsh", "category_bcgz_szsh", "category_cqdq_szsh", "category_fxts_szsh",
    "category_tbclts_szsh", "category_tszlq_szsh",
)
# Board codes, with the program's board names. "disjoint" codes are tried first; v2.0.3 showed
# that sz and sh cover whole exchanges (finding 22), so they are the fallback.
BOARD_SCHEMES = {
    "disjoint": (("szmb", ("SZSE_MAIN",)), ("szcy", ("CHINEXT",)), ("shmb", ("SSE_MAIN",)),
                 ("shkcp", ("STAR",)), ("bj", ("BSE",))),
    "exchange": (("sz", ("SZSE_MAIN", "CHINEXT")), ("sh", ("SSE_MAIN", "STAR")), ("bj", ("BSE",))),
}
PLATES = tuple(code for code, _ in BOARD_SCHEMES["disjoint"])      # kept for compatibility
BOARD_OF_PLATE = {code: boards for scheme in BOARD_SCHEMES.values() for code, boards in scheme}
# CSRC industry sections (上市公司行业分类指引, 2012), as CNINFO's industry filter names them.
CSRC_SECTIONS = (
    "农、林、牧、渔业", "采矿业", "制造业", "电力、热力、燃气及水生产和供应业", "建筑业", "批发和零售业",
    "交通运输、仓储和邮政业", "住宿和餐饮业", "信息传输、软件和信息技术服务业", "金融业", "房地产业",
    "租赁和商务服务业", "科学研究和技术服务业", "水利、环境和公共设施管理业", "居民服务、修理和其他服务业",
    "教育", "卫生和社会工作", "文化、体育和娱乐业", "综合",
)
DIMENSIONS = ("board_disjoint", "board_exchange", "category", "trade", "stock")
CORE_BOARDS = {"SSE_MAIN", "STAR", "SZSE_MAIN", "CHINEXT"}

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


def _row_key(item: dict):
    """A row: one announcement for one security (CNINFO lists an announcement once per security)."""
    k = _ann_id(item)
    return (k, str(item.get("secCode") or "").zfill(6)) if k else None


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


def _board_of_code(code: str) -> str | None:
    from .universe import infer_exchange, infer_board
    ex = infer_exchange(code, optional=("BSE",))
    return infer_board(ex, code, optional=("BSE",)) if ex else None


def _enabled_boards() -> set[str]:
    from .universe import enabled_optional_boards
    return CORE_BOARDS | ({"BSE"} if "BSE" in enabled_optional_boards() else set())


@dataclass(frozen=True)
class Spec:
    """One CNINFO search: a date window and optional filters."""
    a: str
    b: str
    category: str = ""
    plate: str = ""
    trade: str = ""
    stock: str = ""                 # "code,orgId;code,orgId;..." (several companies at once)
    sort: str = ""                  # "", "desc" or "asc" (by time)

    def label(self) -> str:
        parts = [self.a if self.a == self.b else f"{self.a}~{self.b}"]
        cat = self.category.rstrip(";")
        if cat and ";" not in cat:
            parts.append(cat.split("_")[1] if cat.count("_") >= 2 else cat)
        if self.plate:
            parts.append(self.plate)
        if self.trade:
            parts.append(self.trade)
        if self.stock:
            parts.append(f"{self.stock.count(';') + 1} companies")
        if self.sort:
            parts.append(self.sort)
        return " ".join(parts[:1]) + (" " + "/".join(parts[1:]) if parts[1:] else "")


class MarketQuery:
    """Sends CNINFO searches and pages them, keying rows by announcement and security."""

    def __init__(self, adapter, store_raw: bool = True):
        self.adapter, self.store_raw = adapter, store_raw
        self.requests = 0

    def page(self, spec: Spec, page_num: int) -> dict:
        from .config import CNINFO_QUERY_URL
        payload = {"pageNum": str(page_num), "pageSize": str(PAGE_SIZE), "tabName": "fulltext",
                   "column": MARKET_COLUMN, "stock": spec.stock, "searchkey": "", "secid": "", "plate": spec.plate,
                   "category": spec.category, "trade": spec.trade, "seDate": f"{spec.a}~{spec.b}",
                   "sortName": "time" if spec.sort else "", "sortType": spec.sort, "isHLtitle": "true"}
        response = self.adapter.http.post(CNINFO_QUERY_URL, data=payload, headers={
            "Referer": "https://www.cninfo.com.cn/new/commonUrl?url=disclosure/list/notice",
            "Origin": "https://www.cninfo.com.cn", "X-Requested-With": "XMLHttpRequest",
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8"})
        self.requests += 1
        data = response.json() or {}
        if self.store_raw:
            from .storage import store_raw
            store_raw("CNINFO", CNINFO_QUERY_URL, response.content,
                      {"content_type": "application/json", "scope": "market", "window": f"{spec.a}~{spec.b}",
                       "category": spec.category, "plate": spec.plate, "trade": spec.trade,
                       "stock": spec.stock[:200], "sort": spec.sort, "page_num": page_num})
        return data

    def first(self, spec: Spec):
        data = self.page(spec, 1)
        return int(data.get("totalAnnouncement") or 0), data

    def rest(self, spec: Spec, first_data: dict, total: int, label: str = "", progress=None,
             on_items: Callable | None = None, known: dict | None = None, early_stop: bool = False) -> dict:
        """Continue a query from its first page; returns {row key: item}.

        ``known``: rows already collected for the day; with ``early_stop``,
        paging stops after EARLY_STOP_PAGES pages that bring nothing new to it."""
        seen: dict = {}
        last_page = max(1, math.ceil(total / PAGE_SIZE)) if total else 1
        page_num, data, idle = 1, first_data, 0
        stop = "end"
        while True:
            items = data.get("announcements") or []
            new = {}
            for it in items:
                k = _row_key(it)
                if k and k not in seen:
                    new[k] = it
            seen.update(new)
            fresh = [k for k in new if known is None or k not in known]     # judged before on_items records them
            if on_items and new:
                on_items(list(new.values()))
            if progress and page_num % PROGRESS_EVERY == 0:
                _say(progress, f"    {label}: page {page_num} of {min(last_page, QUERY_LIMIT // PAGE_SIZE)} "
                               f"({len(seen):,} of {total:,})")
            if not items:
                break
            if not new and page_num > 1:
                stop = "repeat"          # CNINFO is repeating earlier results: nothing more to get
                break
            if early_stop and known is not None:
                idle = 0 if fresh else idle + 1
                if idle >= EARLY_STOP_PAGES:
                    stop = "idle"
                    break
            if total and len(seen) >= total:
                break
            if not data.get("hasMore"):
                break
            if page_num >= last_page + 1:
                stop = "past_total"
                break
            page_num += 1
            data = self.page(spec, page_num)
        self.last_stop = stop
        return seen


def _china_today() -> str:
    from datetime import datetime, timezone
    return (datetime.now(timezone.utc) + timedelta(hours=8)).date().isoformat()


def _record(session, kind, day, status, expected=None, stored=None, window=None, method=None, queries=None,
            error=None, **detail):
    # Today (China time) is still receiving announcements: never treat it as finished.
    if status in DONE_STATES and day >= _china_today():
        status = "OPEN"
    row = session.query(CatalogueDay).filter_by(kind=kind, day=day).one_or_none()
    if row is None:
        row = CatalogueDay(kind=kind, day=day)
        session.add(row)
    row.status, row.expected, row.stored, row.window = status, expected, stored, window
    row.method, row.queries, row.error, row.updated_at = method, queries, error, utcnow()
    row.rows_multi = detail.get("rows_multi")
    row.gap_in_scope = detail.get("gap_in_scope")
    row.gap_out_scope = detail.get("gap_out_scope")
    row.partition = (detail.get("partition") or None) and str(detail["partition"])[:250]
    row.window_expected = detail.get("window_expected")
    row.strategy = STRATEGY if status != "FAILED" else detail.get("strategy")


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
                 "method": r.method, "queries": r.queries, "error": r.error, "rows_multi": r.rows_multi,
                 "gap_in_scope": r.gap_in_scope, "gap_out_scope": r.gap_out_scope, "partition": r.partition,
                 "strategy": r.strategy, "window_expected": r.window_expected}
                for r in q.order_by(CatalogueDay.day)]
    finally:
        s.close()


class _Collector:
    """Collects every row of one unit (a day, or a window of quiet days)."""

    def __init__(self, q: MarketQuery, kind_category: str, persist, progress, caps: dict, companies):
        self.q, self.kind_category, self.persist, self.progress = q, kind_category, persist, progress
        self.caps, self.companies = caps, companies
        self.rows: dict = {}
        self.notes: list[str] = []
        self.board_totals: dict[str, int] | None = None
        self.board_scheme: str | None = None
        self.methods: list[str] = []

    # -- fetching -------------------------------------------------------------------------------
    def _take(self, items):
        new = []
        for it in items:
            k = _row_key(it)
            if k and k not in self.rows:
                self.rows[k] = it
                new.append(it)
        if new:
            self.persist(new)

    def fetch(self, spec: Spec, total: int, data: dict, early: bool = False) -> set:
        """Read a query. ``early``: stop after EARLY_STOP_PAGES pages with nothing new to the unit; used only
        for a last pass after a split, when the parts have already brought in what they can reach."""
        got = self.q.rest(spec, data, total, spec.label(), self.progress, self._take,
                          known=self.rows if early else None, early_stop=early)
        return set(got)

    def sort_harvest(self, spec: Spec, total: int, early: bool = False) -> set:
        """Read a query newest-first and oldest-first. Returns the rows found; detects whether the
        sort order is honoured (if oldest-first starts with the same rows, it is not)."""
        if self.caps.get("sort") is False:
            return set()
        try:
            dt, ddata = self.q.first(replace(spec, sort="desc"))
            got = self.fetch(replace(spec, sort="desc"), dt, ddata, early=early and dt > QUERY_LIMIT)
            at, adata = self.q.first(replace(spec, sort="asc"))
        except Exception:                       # an unsupported sort value: never use it again
            self.caps["sort"] = False
            return set()
        first_desc = {_row_key(i) for i in (ddata.get("announcements") or [])}
        first_asc = {_row_key(i) for i in (adata.get("announcements") or [])}
        if first_asc and first_asc == first_desc and total > PAGE_SIZE:
            self.caps["sort"] = False           # the order is ignored: oldest-first is the same query
            return got
        got |= self.fetch(replace(spec, sort="asc"), at, adata, early=early and at > QUERY_LIMIT)
        if "sort" not in self.caps and len(got) > min(total, QUERY_LIMIT):
            self.caps["sort"] = True
        self.methods.append("SORT_BOTH")
        return got

    # -- splitting ------------------------------------------------------------------------------
    def children(self, dim: str, spec: Spec) -> list[Spec]:
        if self.caps.get(dim) is False:
            return []
        if dim.startswith("board_"):
            scheme = dim.split("_", 1)[1]
            if spec.plate or spec.stock:
                return []
            if self.caps.get("board_scheme") and self.caps["board_scheme"] != scheme:
                return []                       # the other scheme is already confirmed
            return [replace(spec, plate=code) for code, _ in BOARD_SCHEMES[scheme]]
        if dim == "category":
            if spec.stock:
                return []
            cats = _split_categories(spec.category or self.kind_category)
            if spec.category and ";" not in spec.category.rstrip(";"):
                return []
            return [replace(spec, category=c) for c in cats]
        if dim == "trade":
            if spec.trade or spec.stock:
                return []
            return [replace(spec, trade=t) for t in CSRC_SECTIONS]
        if dim == "stock":
            if spec.stock:
                parts = spec.stock.split(";")
                if len(parts) < 2:
                    return []
                mid = len(parts) // 2
                return [replace(spec, stock=";".join(parts[:mid])), replace(spec, stock=";".join(parts[mid:]))]
            boards = set(BOARD_OF_PLATE.get(spec.plate, ())) if spec.plate else None
            members = [c for c in self.companies if c[2] and (boards is None or c[3] in boards)]
            if not members:
                return []
            members.sort()
            batches = [members[i:i + BATCH_SIZE] for i in range(0, len(members), BATCH_SIZE)]
            return [replace(spec, stock=";".join(f"{code},{org}" for code, _, org, _ in b)) for b in batches]
        return []

    def collect(self, spec: Spec, total: int, data: dict, dims: tuple, top: bool = False) -> set:
        """Every row of ``spec``; returns the rows found for it."""
        if total <= QUERY_LIMIT:
            got = self.fetch(spec, total, data)
            if len(got) < total and total > PAGE_SIZE:
                got |= self.sort_harvest(spec, total)      # rows moving between pages: read both orders
            return got
        got: set = set()
        if total <= 2 * QUERY_LIMIT and self.caps.get("sort") is not False:
            got |= self.sort_harvest(spec, total)
            if len(got) >= total:
                return got
        evaluated = []
        for dim in dims:
            kids = self.children(dim, spec)
            if not kids:
                continue
            totals = [(k,) + tuple(self.q.first(k)) for k in kids]
            tsum = sum(t for _, t, _ in totals)
            if len(kids) > 1 and all(t == total for _, t, _ in totals):
                self.caps[dim] = False                    # the filter is ignored
                self.notes.append(f"{dim}: filter ignored by CNINFO")
                continue
            if tsum == 0:
                # Every part empty. For a board, industry or company filter that means CNINFO rejects it, and it
                # is not used again; a category split can legitimately be empty (uncategorised rows), so it is
                # only skipped here.
                if dim != "category":
                    self.caps[dim] = False
                    self.notes.append(f"{dim}: filter returns nothing")
                continue
            if dim.startswith("board_") and top:
                self.board_totals = {k.plate: t for k, t, _ in totals}
                self.board_scheme = dim.split("_", 1)[1]
                if tsum == total:
                    self.caps["board_scheme"] = self.board_scheme
            evaluated.append((dim, totals, tsum))
            if tsum >= total and not dim == "category":   # categories overlap: their sum proves nothing
                break
        # Use the dimensions in order of coverage until the rows reach the total.
        evaluated.sort(key=lambda e: (-(min(e[2], total)), DIMENSIONS.index(e[0])))
        for dim, totals, tsum in evaluated:
            if len(got) >= total:
                break
            if tsum < total:
                self.notes.append(f"{spec.label()}: {dim} parts reach {tsum:,} of {total:,}")
            self.methods.append(dim.upper())
            rest = tuple(d for d in dims if d != dim and not (d.startswith("board_") and dim.startswith("board_")))
            if dim == "stock":
                rest = rest + ("stock",)                  # a company batch over the limit is halved again
            names = {"category": "category", "trade": "industry", "stock": "company batch"}
            unit = names.get(dim, "board")
            for i, (kid, t, kdata) in enumerate(totals, 1):
                if t:
                    got |= self.collect(kid, t, kdata, rest)
                if len(totals) >= 5 and i % 5 == 0 and i < len(totals):
                    _say(self.progress, f"    {spec.label()}: {unit} {i} of {len(totals)} done "
                                        f"({len(got):,} of {total:,} so far)")
        if len(got) < total:
            # The parts did not reach everything: read what the query itself holds. After a split the first
            # pages mostly repeat rows already found, so this pass stops when idle; with no split it reads all.
            split = bool(evaluated)
            got |= self.fetch(spec, total, data, early=split)
            if self.caps.get("sort") is not False:
                got |= self.sort_harvest(spec, total, early=split)
            if len(got) < total:
                self.notes.append(f"{spec.label()}: {total - len(got):,} of {total:,} unreachable")
        return got

    # -- gaps -----------------------------------------------------------------------------------
    def gaps(self, spec: Spec, total: int, rows: set) -> tuple[int, int]:
        """(gap within the enabled boards, gap outside them) for ``spec``."""
        gap = max(0, total - len(rows))
        if not gap:
            return 0, 0
        totals = self.board_totals
        scheme = self.board_scheme
        if totals is None:
            scheme = self.caps.get("board_scheme") or "exchange"
            if self.caps.get(f"board_{scheme}") is False:
                scheme = "exchange" if scheme == "disjoint" else "disjoint"
            if self.caps.get(f"board_{scheme}") is False:
                return gap, 0
            try:
                totals = {code: self.q.first(replace(spec, plate=code))[0] for code, _ in BOARD_SCHEMES[scheme]}
            except Exception:
                return gap, 0
            if all(t == total for t in totals.values()) or not any(totals.values()):
                return gap, 0                     # board filter unusable: the whole gap counts
        # Conservative: only a gap proven to lie on a board outside the enabled ones counts as outside;
        # everything else (including rows CNINFO's board totals do not account for) counts as inside.
        by_board = Counter(_board_of_code(k[1]) for k in rows)
        enabled = _enabled_boards()
        gap_out = 0
        for code, boards in BOARD_SCHEMES[scheme]:
            if set(boards) <= enabled:
                continue
            t = totals.get(code, 0)
            gap_out += max(0, t - sum(by_board.get(b, 0) for b in boards))
        gap_out = min(gap_out, gap)
        return gap - gap_out, gap_out


def _companies_for_split(session) -> list[tuple]:
    out = []
    for c in session.query(Company):
        out.append((c.security_code, c.short_name_cn, c.org_id, c.board))
    return out


def recheck_recent(kind: str, until: str | None = None, adapter=None, progress=None, horizon: int = RECHECK_DAYS,
                   q: MarketQuery | None = None) -> list[str]:
    """Finished days of the last ``horizon`` days whose CNINFO total has grown since (finding 28)."""
    from .disclosures import CNInfoDisclosureAdapter
    init_db()
    category = _category_for(kind)
    today = date.fromisoformat(until or _china_today())
    start = (today - timedelta(days=horizon)).isoformat()
    s = SessionLocal()
    try:
        rows = [r for r in s.query(CatalogueDay).filter(CatalogueDay.kind == kind, CatalogueDay.day >= start,
                                                        CatalogueDay.day <= today.isoformat(),
                                                        CatalogueDay.status == "DONE")]
    finally:
        s.close()
    windows: dict[str, tuple[int, list[str]]] = {}
    for r in rows:
        known = r.window_expected if r.window_expected is not None else (r.expected if r.window and
                                                                         r.window == f"{r.day}~{r.day}" else None)
        if known is None or not r.window:
            continue
        windows.setdefault(r.window, (known, []))[1].append(r.day)
    if not windows:
        return []
    own = q is None and adapter is None
    adapter = adapter or (None if q else CNInfoDisclosureAdapter())
    q = q or MarketQuery(adapter, store_raw=False)
    grown = []
    try:
        for win, (known, days) in sorted(windows.items()):
            a, b = win.split("~")
            total, _ = q.first(Spec(a, b, category))
            if total > known:
                grown.extend(days)
                _say(progress, f"  {win}: CNINFO now reports {total:,} (was {known:,}); fetching again")
    finally:
        if own and adapter is not None:
            adapter.close()
    return sorted(grown)


def catalogue(since: str, until: str, kind: str = "all", download_documents: bool = False,
              refresh: bool = False, retry_shortfalls: bool = False, days: list[str] | None = None,
              progress: Callable[[str], None] | None = None, adapter=None, max_failures: int = 3,
              recheck: bool = True) -> dict:
    """Catalogue every company's announcements, resuming by day."""
    from .disclosures import CNInfoDisclosureAdapter, persist_announcement
    from .universe import rejection_reason
    init_db()
    category = _category_for(kind)
    own = adapter is None
    adapter = adapter or CNInfoDisclosureAdapter()
    session = SessionLocal()
    q = MarketQuery(adapter)
    tot = {"mode": "market", "kind": kind, "queries": 0, "announcements": 0, "inserted": 0, "updated": 0,
           "unmatched": 0, "rows_multi": 0, "downloaded": 0, "days_done": 0, "days_skipped": 0,
           "days_shortfall": [], "days_gap_outside": [], "days_failed": [], "days_rechecked": [], "errors": []}
    unmatched_reasons: Counter = Counter()
    new_rows: list[int] = []
    caps: dict = {}
    try:
        companies = {c.security_code: c for c in session.query(Company)}
        if not companies:
            return {**tot, "note": "the company list is empty; run update-universe first"}
        split_companies = _companies_for_split(session)
        wanted = sorted(set(days)) if days else _days(since, until)
        if not refresh:
            done = {r.day for r in session.query(CatalogueDay).filter(
                CatalogueDay.kind == kind, CatalogueDay.day.in_(wanted),
                CatalogueDay.status.in_(("DONE",) if retry_shortfalls else DONE_STATES))}
            if recheck and wanted and wanted[-1] >= (date.fromisoformat(_china_today())
                                                     - timedelta(days=RECHECK_DAYS)).isoformat():
                try:
                    grown = [d for d in recheck_recent(kind, min(wanted[-1], _china_today()), q=q,
                                                       progress=progress) if d in done]
                except Exception as exc:          # a failed recheck never stops the run
                    grown = []
                    _say(progress, f"  (recent totals not rechecked: {exc!r})")
                done -= set(grown)
                tot["days_rechecked"] = grown
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
                    unmatched_reasons[rejection_reason(code) if code.strip("0") else "no security code"] += 1
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

        finished: set[str] = set()

        def finish_unit(col: _Collector, spec: Spec, total: int, rows: set, method: str):
            a, b = spec.a, spec.b
            gap_in, gap_out = col.gaps(spec, total, rows)
            ids = {k[0] for k in rows}
            multi = len(rows) - len(ids)
            tot["rows_multi"] += multi
            complete = gap_in == 0
            status = "DONE" if complete else "SHORTFALL"
            note = "; ".join(col.notes) if col.notes else None
            by_day: dict[str, int] = Counter(_item_day(col.rows[k]) or a for k in rows if k in col.rows)
            for d in _days(a, b):
                if a == b:
                    _record(session, kind, d, status, total, len(rows), f"{a}~{b}", method, q.requests,
                            rows_multi=multi, gap_in_scope=gap_in, gap_out_scope=gap_out, partition=note,
                            window_expected=total)
                else:
                    _record(session, kind, d, status, None, by_day.get(d, 0), f"{a}~{b}", method, q.requests,
                            gap_in_scope=gap_in, gap_out_scope=gap_out, partition=note, window_expected=total)
                tot["days_done"] += 1
                finished.add(d)
            session.commit()
            span = a if a == b else f"{a}~{b}"
            if not complete:
                tot["days_shortfall"].append({"day": span, "expected": total, "stored": len(rows),
                                              "gap_in_scope": gap_in, "gap_out_scope": gap_out})
                _say(progress, f"  {span}: SHORTFALL, {len(rows):,} of {total:,} rows received; "
                               f"{gap_in:,} missing within the enabled boards"
                               + (f", {gap_out:,} outside them" if gap_out else ""))
            elif gap_out:
                tot["days_gap_outside"].append({"day": span, "expected": total, "stored": len(rows),
                                                "gap_out_scope": gap_out})
                _say(progress, f"  {span}: complete within the enabled boards ({len(rows):,} of {total:,} rows; "
                               f"{gap_out:,} outside the enabled boards not reached)")
            elif total > QUERY_LIMIT:
                _say(progress, f"  {span}: {total:,} rows after splitting ({method.lower()}), complete")

        def window(a, b):
            try:
                spec = Spec(a, b, category)
                total, data = q.first(spec)
                if total > QUERY_LIMIT and a != b:
                    da, db = date.fromisoformat(a), date.fromisoformat(b)
                    mid = da + (db - da) // 2
                    window(a, mid.isoformat())
                    window((mid + timedelta(days=1)).isoformat(), b)
                    return
                col = _Collector(q, category, persist, progress, caps, split_companies)
                if total > QUERY_LIMIT:
                    _say(progress, f"  {a}: {total:,} announcements, more than one query returns; splitting")
                    rows = col.collect(spec, total, data, DIMENSIONS, top=True)
                    method = "+".join(dict.fromkeys(col.methods)) or "SPLIT"
                else:
                    _say(progress, f"  {a} to {b}: {total:,} announcements" if a != b else f"  {a}: {total:,} announcements")
                    rows = col.collect(spec, total, data, ())
                    method = ("DAY" if a == b else "WINDOW") + ("+SORT_BOTH" if "SORT_BOTH" in col.methods else "")
                finish_unit(col, spec, total, rows, method)
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
        tot["unmatched_by_reason"] = dict(unmatched_reasons.most_common())
        tot["filters"] = {k: v for k, v in caps.items()}
        _say(progress, f"Catalogue done: {tot['announcements']:,} rows in {q.requests:,} queries; "
                       f"{tot['inserted']:,} new, {tot['updated']:,} already known, {tot['unmatched']:,} for "
                       f"securities outside the company list; {tot['days_done']} day(s) finished, "
                       f"{len(tot['days_shortfall'])} with a gap within the enabled boards, "
                       f"{len(tot['days_failed'])} failed.")
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
              threshold: int = 2500, include_current: bool = False) -> list[str]:
    """Days to re-catalogue: FAILED days; SHORTFALL days produced by an earlier strategy (or by the
    current one, with ``include_current``); and days catalogued before v2.0.3 whose stored
    announcements reach ``threshold``."""
    from sqlalchemy import func
    from .models import Disclosure
    init_db()
    s = SessionLocal()
    try:
        out = set()
        for r in s.query(CatalogueDay).filter(CatalogueDay.kind == kind,
                                              CatalogueDay.status.in_(("SHORTFALL", "FAILED"))):
            if r.status == "FAILED" or include_current or (r.strategy or 0) < STRATEGY:
                out.add(r.day)
        recorded = {r.day for r in s.query(CatalogueDay).filter(CatalogueDay.kind == kind)}
        q = s.query(Disclosure.announcement_date, func.count(Disclosure.id)).group_by(Disclosure.announcement_date)
        for d, n in q:
            if d and n >= threshold and d not in recorded:
                out.add(d)
        return sorted(d for d in out if (not since or d >= since) and (not until or d <= until))
    finally:
        s.close()


def current_strategy_shortfalls(kind: str = "all", since: str | None = None, until: str | None = None) -> list[str]:
    init_db()
    s = SessionLocal()
    try:
        return sorted(r.day for r in s.query(CatalogueDay).filter(
            CatalogueDay.kind == kind, CatalogueDay.status == "SHORTFALL", CatalogueDay.strategy >= STRATEGY)
            if (not since or r.day >= since) and (not until or r.day <= until))
    finally:
        s.close()


def recatalogue_busy_days(kind: str = "all", since: str | None = None, until: str | None = None,
                          threshold: int = 2500, progress=None, adapter=None, include_current: bool = False) -> dict:
    days = busy_days(kind, since, until, threshold, include_current)
    held = [] if include_current else current_strategy_shortfalls(kind, since, until)
    if held:
        _say(progress, f"Not fetched again: {len(held)} day(s) whose gap recurred under the current method "
                       f"({', '.join(held[:10])}{' ...' if len(held) > 10 else ''}). Repeating the same queries "
                       "cannot close a gap caused by a limit of CNINFO's search; see 'Which days are catalogued' "
                       "for the cause recorded against each day.")
    if not days:
        _say(progress, "No busy days to re-catalogue: no failures, no shortfalls from an earlier version, and no "
                       f"earlier day with {threshold:,} or more stored announcements.")
        return {"days": [], "held": held, "note": "nothing to do"}
    _say(progress, f"Re-cataloguing {len(days)} day(s): {', '.join(days)}")
    r = catalogue(days[0], days[-1], kind, days=days, refresh=True, progress=progress, adapter=adapter,
                  recheck=False)
    r["days"] = days
    r["held"] = held
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
            data = q.page(Spec(day, day), p)
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
                                  "Busy days are split so that every announcement arrives, and any gap is recorded.")
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


def probe_filters(day: str = "2026-04-29", adapter=None, quiet_window: str = "2026-01-09~2026-01-12") -> dict:
    """v2.0.4: which of CNINFO's search filters work with the stock field empty.

    Tests on ``day``: the disjoint and exchange board codes (do the parts add
    up to the day's total?), the industry filter and company batches on the
    largest category and board, the two sort orders, and, on a quiet window,
    whether repeated announcement IDs carry different security codes."""
    from .disclosures import CNInfoDisclosureAdapter
    init_db()
    own = adapter is None
    adapter = adapter or CNInfoDisclosureAdapter()
    q = MarketQuery(adapter, store_raw=False)
    out: dict = {"day": day, "tests": []}

    def add(name, verdict, detail, **extra):
        out["tests"].append({"test": name, "verdict": verdict, "detail": detail, **extra})

    try:
        total, _ = q.first(Spec(day, day))
        out["total"] = total
        for scheme, plates in BOARD_SCHEMES.items():
            parts = {code: q.first(Spec(day, day, plate=code))[0] for code, _ in plates}
            s = sum(parts.values())
            if all(v == total for v in parts.values()):
                verdict = "IGNORED"
            elif s == total:
                verdict = "PARTITION"
            elif s == 0:
                verdict = "REJECTED"
            else:
                verdict = "PARTIAL"
            add(f"boards_{scheme}", verdict, f"parts add up to {s:,} of {total:,}", parts=parts)
        # the largest category on the largest exchange-wide board
        best = (0, "", "")
        for cat in ALL_CATEGORIES:
            for plate in ("sz", "sh"):
                t = q.first(Spec(day, day, cat + ";", plate))[0]
                if t > best[0]:
                    best = (t, cat + ";", plate)
            if best[0] > QUERY_LIMIT and cat.endswith("zj_szsh"):
                break
        ptotal, pcat, pplate = best
        out["largest"] = {"category": pcat, "plate": pplate, "total": ptotal}
        base = Spec(day, day, pcat, pplate)
        tparts = {t: q.first(replace(base, trade=t))[0] for t in CSRC_SECTIONS}
        ts = sum(tparts.values())
        add("industry", "IGNORED" if all(v == ptotal for v in tparts.values()) else
            "PARTITION" if ts == ptotal else "REJECTED" if ts == 0 else "PARTIAL",
            f"industries add up to {ts:,} of {ptotal:,}; largest part {max(tparts.values()):,}", parts=tparts)
        s = SessionLocal()
        try:
            comps = [(c.security_code, c.org_id) for c in s.query(Company).order_by(Company.security_code)
                     if c.org_id and c.board in set(BOARD_OF_PLATE.get(pplate, ()))][:6]
        finally:
            s.close()
        if len(comps) >= 2:
            singles = [q.first(replace(base, category="", plate="", stock=f"{c},{o}"))[0] for c, o in comps[:3]]
            together = q.first(replace(base, category="", plate="",
                                       stock=";".join(f"{c},{o}" for c, o in comps[:3])))[0]
            add("company_batches", "WORKS" if together == sum(singles) and together > 0 else
                "IGNORED" if together >= total else "NO_DATA" if sum(singles) == 0 else "FAILS",
                f"three companies together: {together:,}; one by one: {sum(singles):,}")
        else:
            add("company_batches", "NOT_TESTED", "no companies with an organisation ID on that board")
        d1 = q.page(replace(base, sort="desc"), 1).get("announcements") or []
        a1 = q.page(replace(base, sort="asc"), 1).get("announcements") or []
        kd, ka = {_row_key(i) for i in d1}, {_row_key(i) for i in a1}
        add("sort_orders", "IGNORED" if kd == ka else "HONOURED",
            f"first page newest-first and oldest-first share {len(kd & ka)} of {len(kd)} rows")
        a, b = quiet_window.split("~")
        qt, qdata = q.first(Spec(a, b))
        rows = q.rest(Spec(a, b), qdata, qt)
        ids = Counter(k[0] for k in rows)
        repeated = {i for i, n in ids.items() if n > 1}
        add("repeated_rows", "ROWS_PER_SECURITY" if repeated and len(rows) >= qt else
            "UNSTABLE_ORDER" if len(rows) < qt else "NONE",
            f"{quiet_window}: {len(rows):,} rows of {qt:,}; {len(repeated)} announcement(s) listed for several "
            "securities")
        out["requests"] = q.requests
        return out
    finally:
        if own:
            adapter.close()
