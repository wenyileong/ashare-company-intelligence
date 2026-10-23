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

v2.0.6 (findings 37 to 56, from the first live runs of the engine):

* **Splits before sorting.** CNINFO's time order is honoured but unstable
  (rows move between pages), so a query over the limit is split first, and
  read in both orders only as a last pass.
* **Finer splits.** Below industry: manufacturing by its CSRC divisions (if
  CNINFO accepts them), then batches of companies sent with their own
  exchange (``column``), then, as a last resort, single companies seen in the
  query (at most ``SINGLE_MAX`` requests). Every split is checked against its
  parent's total, as before.
* **Short queries under the limit** are split too: a window by day, a day by
  board, since smaller queries move fewer rows between pages.
* **Paging** stops after ``EARLY_STOP_PAGES`` pages with nothing new to the
  query (not at the first repeated page) and never goes past page 100.
* **No repeats.** Within a day, a query already read (or counted) is reused.
* **Sorting** is turned off only when the first pages of the two orders match,
  for that kind of query; a failed request is an error like any other.
* **Strategy 3**, so that days short under strategy 2 are fetched again.
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
BATCH_SIZE = 10                  # companies per query when splitting by company (v2.0.7: the size confirmed live;
                                 # CNINFO did not apply a batch of 150, finding 61)
RECHECK_DAYS = 30                # finished days whose totals are rechecked at the start of a run
STRATEGY = 3                     # v2.0.6 (2 = v2.0.4; v2.0.3 days have no strategy recorded)
STOCK_MAX_MEMBERS = 2500         # companies a company split may cover (one board)
SINGLE_MAX = 1500                # single-company queries allowed for one leaf over the limit (v2.0.6)
MAX_PAGES = QUERY_LIMIT // PAGE_SIZE     # pages beyond 100 repeat earlier results

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
# CSRC manufacturing divisions (C13 to C43, 上市公司行业分类指引, 2012), for a manufacturing query still over the
# limit (finding 45). Whether CNINFO's industry field accepts them is checked as the run goes, like every filter.
CSRC_MANUFACTURING = (
    "农副食品加工业", "食品制造业", "酒、饮料和精制茶制造业", "烟草制品业", "纺织业", "纺织服装、服饰业",
    "皮革、毛皮、羽毛及其制品和制鞋业", "木材加工和木、竹、藤、棕、草制品业", "家具制造业", "造纸和纸制品业",
    "印刷和记录媒介复制业", "文教、工美、体育和娱乐用品制造业", "石油加工、炼焦和核燃料加工业",
    "化学原料和化学制品制造业", "医药制造业", "化学纤维制造业", "橡胶和塑料制品业", "非金属矿物制品业",
    "黑色金属冶炼和压延加工业", "有色金属冶炼和压延加工业", "金属制品业", "通用设备制造业", "专用设备制造业",
    "汽车制造业", "铁路、船舶、航空航天和其他运输设备制造业", "电气机械和器材制造业",
    "计算机、通信和其他电子设备制造业", "仪器仪表制造业", "其他制造业", "废弃资源综合利用业",
    "金属制品、机械和设备修理业",
)
DIMENSIONS = ("board_disjoint", "board_exchange", "category", "trade", "trade_division", "stock")
# The exchange (``column``) a company query is sent with, by board (as the per-company search sends it).
COLUMN_OF_BOARD = {"SSE_MAIN": "sse", "STAR": "sse", "SSE_B": "sse", "SZSE_MAIN": "szse", "CHINEXT": "szse",
                   "SZSE_B": "szse", "BSE": "bj"}
PLATE_OF_BOARD = {"SSE_MAIN": "sh", "STAR": "shkcp", "SZSE_MAIN": "sz", "CHINEXT": "szcy", "BSE": "bj",
                  "SSE_B": "sh", "SZSE_B": "sz"}
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
    column: str = ""                # v2.0.6: the exchange, sent with company queries ("" = MARKET_COLUMN)

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
                   "column": spec.column or MARKET_COLUMN, "stock": spec.stock, "searchkey": "", "secid": "", "plate": spec.plate,
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
        page_num, data, idle, stale = 1, first_data, 0, 0
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
            # v2.0.6 (finding 38): rows move between pages, so one page of repeats is not the end; several are.
            stale = 0 if new else stale + 1
            if stale >= EARLY_STOP_PAGES:
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
            if page_num >= MAX_PAGES:
                stop = "limit"           # pages beyond 100 repeat earlier results
                break
            page_num += 1
            data = self.page(spec, page_num)
        self.last_stop = stop
        return seen


def _china_today() -> str:
    from datetime import datetime, timezone
    return (datetime.now(timezone.utc) + timedelta(hours=8)).date().isoformat()


def _short_method(method: str | None, width: int = 60) -> str | None:
    """The method fits its column (String(60)); v2.0.6 methods can name many splits. Kept to whole parts."""
    if not method or len(method) <= width:
        return method
    head = method[:width - 4]
    return (head.rsplit("+", 1)[0] if "+" in head else head) + "+..."


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
    row.method, row.queries, row.error, row.updated_at = _short_method(method), queries, error, utcnow()
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


def units(rows: list[dict]) -> list[dict]:
    """v2.0.6 (finding 40): day records as units. The days of a window of quiet days, read as one query, share
    one total and one gap; they are shown as one row ("a~b (window)") with the window's total, the rows stored
    on its days added up, and the gap once. Other days are unchanged."""
    out, groups = [], {}
    for r in rows:
        w = r.get("window") or ""
        a, _, b = w.partition("~")
        if a and b and a != b and r.get("window_expected") is not None and r["status"] != "FAILED":
            key = (w, r["status"], r.get("method"))
            if key not in groups:
                groups[key] = dict(r, day=f"{w} (window)", expected=r["window_expected"], stored=0, days=0)
                out.append(groups[key])
            g = groups[key]
            g["stored"] += r.get("stored") or 0
            g["days"] += 1
        else:
            out.append(dict(r, days=1))
    return out


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
        self._firsts: dict = {}          # v2.0.6: counts already asked for in this unit
        self._done: dict = {}            # v2.0.6: queries already read in this unit, with their rows
        self.singles = 0                 # single-company queries used in this unit

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

    def first(self, spec: Spec):
        """CNINFO's count and first page for ``spec``, asked once per unit (finding 46)."""
        if spec not in self._firsts:
            self._firsts[spec] = self.q.first(spec)
        return self._firsts[spec]

    def fetch(self, spec: Spec, total: int, data: dict, early: bool = False) -> set:
        """Read a query. ``early``: stop after EARLY_STOP_PAGES pages with nothing new to the unit; used only
        for a last pass, when other readings have already brought in what they can reach."""
        got = self.q.rest(spec, data, total, spec.label(), self.progress, self._take,
                          known=self.rows if early else None, early_stop=early)
        return set(got)

    @staticmethod
    def _shape(spec: Spec) -> str:
        """The kind of query, for filters whose support may depend on it (sorting)."""
        return "+".join(n for n, v in (("plate", spec.plate), ("category", spec.category.rstrip(";").count(";") == 0
                                                                and spec.category), ("trade", spec.trade),
                                       ("stock", spec.stock)) if v) or "day"

    def sort_harvest(self, spec: Spec, total: int, early: bool = False) -> set:
        """Read a query newest-first and oldest-first; a supplement only, since the order is unstable
        (finding 37). Detects, per kind of query, whether the order is honoured (if the first pages of the
        two orders are the same, it is not). A request that fails after the client's retries leaves a recorded
        gap for this query but does not turn sorting off (finding 55)."""
        key = f"sort[{self._shape(spec)}]"
        if self.caps.get(key) is False:
            return set()
        try:
            dt, ddata = self.q.first(replace(spec, sort="desc"))
            at, adata = self.q.first(replace(spec, sort="asc"))
        except Exception as exc:             # after the client's retries: a gap for this query, not proof
            self.notes.append(f"{spec.label()}: sorted reading failed ({type(exc).__name__})")
            return set()
        first_desc = {_row_key(i) for i in (ddata.get("announcements") or [])}
        first_asc = {_row_key(i) for i in (adata.get("announcements") or [])}
        if first_asc and first_asc == first_desc and total > PAGE_SIZE:
            self.caps[key] = False              # the order is ignored for this kind of query
            return set()
        self.caps.setdefault(key, True)
        got = self.fetch(replace(spec, sort="desc"), dt, ddata, early=early)
        got |= self.fetch(replace(spec, sort="asc"), at, adata, early=early)
        self.methods.append("SORT_BOTH")
        return got

    # -- splitting ------------------------------------------------------------------------------
    def _members(self, spec: Spec) -> list[tuple]:
        """Companies (code, name, orgId, board) a company split of ``spec`` covers."""
        boards = set(BOARD_OF_PLATE.get(spec.plate, ())) if spec.plate else None
        return sorted(c for c in self.companies if c[2] and (boards is None or c[3] in boards))

    def _company_specs(self, spec: Spec, members: list[tuple], style: str, size: int) -> list[Spec]:
        """Queries for ``members`` in batches of ``size``, one exchange per batch, sent with the companies'
        own exchange. Style "A": no board code; style "B": the per-company search's board code."""
        out = []
        by_column: dict = {}
        for m in members:
            by_column.setdefault(COLUMN_OF_BOARD.get(m[3], MARKET_COLUMN), []).append(m)
        for column, ms in sorted(by_column.items()):
            for i in range(0, len(ms), size):
                part = ms[i:i + size]
                boards = {m[3] for m in part}
                plate = PLATE_OF_BOARD.get(next(iter(boards)), "") if style == "B" and len(boards) == 1 else ""
                out.append(replace(spec, plate=plate, column=column,
                                   stock=";".join(f"{code},{org}" for code, _, org, _ in part)))
        return out

    def children(self, dim: str, spec: Spec, style: str = "A") -> list[Spec]:
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
        if dim == "trade_division":
            if spec.trade != "制造业" or spec.stock:
                return []
            return [replace(spec, trade=t) for t in CSRC_MANUFACTURING]
        if dim == "stock":
            if spec.stock:
                parts = spec.stock.split(";")
                if len(parts) < 2:
                    return []
                mid = len(parts) // 2
                return [replace(spec, stock=";".join(parts[:mid])), replace(spec, stock=";".join(parts[mid:]))]
            members = self._members(spec)
            if not members or len(members) > STOCK_MAX_MEMBERS:
                return []                     # v2.0.7: within one board only (a few hundred queries at most)
            return self._company_specs(spec, members, style, BATCH_SIZE)
        return []

    def _evaluate(self, dim: str, spec: Spec, total: int):
        """(children with their counts, sum) for a split, or None if the split is unavailable. Checks the
        filter: one that CNINFO ignores or rejects is not used again in the run."""
        styles = ("A", "B") if dim == "stock" and not spec.stock and "stock_style" not in self.caps else \
            (self.caps.get("stock_style", "A"),)
        for style in styles:
            kids = self.children(dim, spec, style)
            if not kids:
                return None
            totals = [(k,) + tuple(self.first(k)) for k in kids]
            tsum = sum(t for _, t, _ in totals)
            big = max((t for _, t, _ in totals), default=0)
            if big > total + max(5, total // 100):
                # v2.0.7 (finding 62): a part larger than the whole means the filter was not applied
                self.caps[dim] = False
                self.notes.append(f"{dim}: filter not applied by CNINFO (a part of {big:,} for a query of {total:,})")
                return None
            if len(kids) > 1 and all(t == total for _, t, _ in totals):
                self.caps[dim] = False                    # the filter is ignored
                self.notes.append(f"{dim}: filter ignored by CNINFO")
                return None
            if tsum == 0:
                if dim == "stock" and style != styles[-1]:
                    continue                              # try the other way of sending companies
                # Every part empty. For a board, industry or company filter that means CNINFO rejects it, and it
                # is not used again; a category split can legitimately be empty (uncategorised rows), so it is
                # only skipped here.
                if dim != "category":
                    self.caps[dim] = False
                    self.notes.append(f"{dim}: filter returns nothing")
                return None
            if dim == "stock" and not spec.stock:
                self.caps["stock_style"] = style
            return totals, tsum
        return None

    def collect(self, spec: Spec, total: int, data: dict, dims: tuple, top: bool = False,
                small_split: bool = False) -> set:
        """Every row of ``spec``; returns the rows found for it. A query already read in this unit is not
        read again (finding 46)."""
        key = replace(spec, sort="")
        if key in self._done:
            return self._done[key]
        got = self._collect(spec, total, data, dims, top, small_split)
        self._done[key] = got
        return got

    def _collect(self, spec: Spec, total: int, data: dict, dims: tuple, top: bool, small_split: bool) -> set:
        if total <= QUERY_LIMIT:
            got = self.fetch(spec, total, data)
            if len(got) < total and small_split:
                got |= self._split_small(spec, total)     # finding 39: smaller queries move fewer rows
            if len(got) < total and total > PAGE_SIZE:
                got |= self.sort_harvest(spec, total, early=True)
            return got
        got: set = set()
        evaluated = []
        # v2.0.7: the costly splits (company batches, manufacturing divisions) are counted only if the others
        # leave rows missing; the rest are counted first and used in order of coverage, as before.
        lazy = ("trade_division", "stock")
        for dim in [d for d in dims if d not in lazy]:
            r = self._evaluate(dim, spec, total)
            if r is None:
                continue
            totals, tsum = r
            if dim.startswith("board_") and top:
                self.board_totals = {k.plate: t for k, t, _ in totals}
                self.board_scheme = dim.split("_", 1)[1]
                if tsum == total:
                    self.caps["board_scheme"] = self.board_scheme
            evaluated.append((dim, totals, tsum))
            if tsum >= total and not dim == "category":   # categories overlap: their sum proves nothing
                break
        evaluated.sort(key=lambda e: (-(min(e[2], total)), DIMENSIONS.index(e[0])))
        used = 0
        for dim in [d for d in dims if d in lazy] + [None]:
            # Use the dimensions counted so far, in order of coverage, until the rows reach the total.
            for dim_, totals, tsum in evaluated[used:]:
                used += 1
                if len(got) >= total:
                    break
                got |= self._use(spec, total, dim_, totals, tsum, dims)
            if dim is None or len(got) >= total:
                break
            r = self._evaluate(dim, spec, total)
            if r is not None:
                evaluated.append((dim, r[0], r[1]))
        if len(got) < total:
            # The parts did not reach everything: read what the query itself holds. After a split the first
            # pages mostly repeat rows already found, so this pass stops when idle; with no split it reads all.
            split = bool(evaluated)
            got |= self.fetch(spec, total, data, early=split)
            if len(got) < total:
                got |= self.sort_harvest(spec, total, early=split)
            if len(got) < total:
                got |= self._singles(spec, total, got)
            if len(got) < total:
                self.notes.append(f"{spec.label()}: {total - len(got):,} of {total:,} unreachable")
        return got

    def _use(self, spec: Spec, total: int, dim: str, totals, tsum: int, dims: tuple) -> set:
        """Collect the parts of a split of ``spec`` along ``dim``."""
        got: set = set()
        if tsum < total:
            self.notes.append(f"{spec.label()}: {dim} parts reach {tsum:,} of {total:,}")
        self.methods.append(dim.upper())
        rest = tuple(d for d in dims if d != dim and not (d.startswith("board_") and dim.startswith("board_")))
        if dim == "stock":
            rest = rest + ("stock",)                  # a company batch over the limit is halved again
        if dim == "trade_division":
            rest = tuple(d for d in rest if d != "trade")
        names = {"category": "category", "trade": "industry", "trade_division": "manufacturing division",
                 "stock": "company batch"}
        unit = names.get(dim, "board")
        for i, (kid, t, kdata) in enumerate(totals, 1):
            if t:
                got |= self.collect(kid, t, kdata, rest)
            if len(totals) >= 5 and i % 5 == 0 and i < len(totals):
                _say(self.progress, f"    {spec.label()}: {unit} {i} of {len(totals)} done "
                                    f"({len(got):,} of {total:,} so far)")
        return got

    def _split_small(self, spec: Spec, total: int) -> set:
        """A query under the limit that came back short: read it again in parts, by day, then by board."""
        got: set = set()
        if spec.a != spec.b:
            kids = [replace(spec, a=d, b=d) for d in _days(spec.a, spec.b)]
            method = "DAYS"
        elif not spec.plate and not spec.stock and self.caps.get("board_disjoint") is not False:
            kids = self.children("board_disjoint", spec)
            method = "BOARDS"
        else:
            return got
        if not kids:
            return got
        self.methods.append(method)
        for kid in kids:
            t, kdata = self.first(kid)
            if t:
                got |= self.collect(kid, t, kdata, (), small_split=True)
        return got

    def _singles(self, spec: Spec, total: int, got: set) -> set:
        """Last resort for a query over the limit (finding 45): one query per company seen in its rows, within
        SINGLE_MAX queries per unit. The companies seen have rows in this query, so if the first three return
        nothing in both ways of sending a company, company queries do not work and are not used again."""
        cat = spec.category.rstrip(";")
        if spec.stock or total <= QUERY_LIMIT or self.caps.get("single") is False or not spec.plate \
                or not cat or ";" in cat:
            return set()                          # only for a leaf within one board and one category
        seen = {k[1] for k in got}
        members = [m for m in self._members(spec) if m[0] in seen]
        if not members:
            return set()
        if self.singles + len(members) > SINGLE_MAX:
            self.notes.append(f"{spec.label()}: {len(members):,} single-company queries would exceed "
                              f"{SINGLE_MAX:,}; not tried")
            return set()
        styles = (self.caps["single_style"],) if "single_style" in self.caps else ("A", "B")
        kids = []
        for style in styles:
            trial = self._company_specs(spec, members, style, 1)
            if any(self.first(k)[0] for k in trial[:3]):
                self.caps["single_style"] = style
                kids = trial
                break
            self.singles += min(3, len(trial))
        if not kids:
            self.caps["single"] = False           # company queries return nothing: not used again
            self.notes.append("single companies: filter returns nothing")
            return set()
        _say(self.progress, f"    {spec.label()}: {total - len(got):,} still missing; reading {len(kids):,} "
                            "companies one at a time")
        self.methods.append("SINGLE_COMPANIES")
        out: set = set()
        for kid in kids:
            t, kdata = self.first(kid)
            self.singles += 1
            if t:
                out |= self.fetch(kid, t, kdata)
            if len(got | out) >= total:
                break
        return out

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
                totals = {code: self.first(replace(spec, plate=code))[0] for code, _ in BOARD_SCHEMES[scheme]}
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
           "days_shortfall": [], "days_gap_outside": [], "days_failed": [], "days_rechecked": [], "errors": [],
           "days_open": 0}
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
            session.commit()
            # v2.0.6: counted as finished only once recorded, so that a failed write leaves the days FAILED
            for d in _days(a, b):
                if d >= _china_today():
                    tot["days_open"] += 1        # finding 43: today is kept open, not finished
                else:
                    tot["days_done"] += 1
                finished.add(d)
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
                    rows = col.collect(spec, total, data, (), small_split=True)
                    method = ("DAY" if a == b else "WINDOW") + "".join(f"+{m}" for m in dict.fromkeys(col.methods))
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
                       f"securities outside the company list; {tot['days_done']} day(s) finished"
                       + ("; today kept open (it is fetched again next time)" if tot["days_open"] else "") + ", "
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
    whether repeated announcement IDs carry different security codes.

    v2.0.6 (finding 54): the company test uses companies that have
    announcements in the query (from its first page), sends them with their
    own exchange, with and without a board code, and tests one, two, three and
    up to ten companies, so that a failure shows where it starts. Manufacturing
    divisions are tested as an industry."""
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
        # v2.0.6 (finding 54): manufacturing divisions as an industry
        manu = replace(base, trade="制造业")
        mt = q.first(manu)[0]
        dparts = {t: q.first(replace(manu, trade=t))[0] for t in CSRC_MANUFACTURING}
        dsum = sum(dparts.values())
        add("manufacturing_divisions", "NOT_TESTED" if not mt else
            "IGNORED" if all(v == mt for v in dparts.values()) else
            "PARTITION" if dsum == mt else "REJECTED" if dsum == 0 else "PARTIAL",
            f"divisions add up to {dsum:,} of {mt:,} (manufacturing){'; largest part ' + format(max(dparts.values()), ',') if dsum else ''}",
            parts=dparts)
        # v2.0.6 (finding 54): company queries, with companies known to have announcements in this query, sent
        # with their own exchange; one, two and three companies, then a batch of up to ten.
        page1 = []
        for p in (1, 2, 3):                 # enough rows for 50 different companies
            page1 += q.page(base, p).get("announcements") or []
        s = SessionLocal()
        try:
            known = {c.security_code: c for c in s.query(Company)}
        finally:
            s.close()
        comps = []
        for it in page1:
            code = str(it.get("secCode") or "").zfill(6)
            c = known.get(code)
            org = it.get("orgId") or (c.org_id if c else None)
            board = c.board if c else _board_of_code(code)
            if org and board and code not in {x[0] for x in comps}:
                comps.append((code, None, org, board))
            if len(comps) >= 50:
                break
        if len(comps) >= 3:
            probe = _Collector(q, pcat, lambda items: None, None, {}, comps)
            result, works = {}, None
            for style in ("A", "B"):
                singles = [q.first(k)[0] for k in probe._company_specs(base, comps[:3], style, 1)]
                if any(singles):
                    two = sum(q.first(k)[0] for k in probe._company_specs(base, comps[:2], style, 2))
                    three = sum(q.first(k)[0] for k in probe._company_specs(base, comps[:3], style, 3))
                    one = singles + [q.first(k)[0] for k in probe._company_specs(base, comps[3:], style, 1)]
                    ten = comps[:10]
                    batch = sum(q.first(k)[0] for k in probe._company_specs(base, ten, style, len(ten)))
                    # v2.0.7 (finding 61): larger batches, to find the largest CNINFO applies
                    sizes = {}
                    for n in (25, 50):
                        if len(comps) >= n:
                            got = q.first(probe._company_specs(base, comps[:n], style, n)[0])[0]
                            sizes[n] = {"together": got, "one_by_one": sum(one[:n]),
                                        "applied": got == sum(one[:n])}
                    result = {"style": style, "singles": singles, "two": two, "three": three,
                              "batch": batch, "batch_singles": sum(one[:10]), "companies": len(ten),
                              "larger": sizes}
                    works = style
                    break
                result.setdefault("tried", []).append({"style": style, "singles": singles})
            if works is None:
                add("company_batches", "FAILS", "three companies with announcements in this query return nothing "
                    "one by one, with or without a board code", **result)
            else:
                r = result
                verdict = ("WORKS" if r["two"] == sum(r["singles"][:2]) and r["three"] == sum(r["singles"])
                           and r["batch"] == r["batch_singles"] else
                           "IGNORED" if r["batch"] >= ptotal else "SINGLES_ONLY" if r["two"] == 0 else "PARTIAL")
                style_text = "without a board code" if works == "A" else "with the board code"
                larger = "; ".join(f"{n} together {v['together']:,} (one by one {v['one_by_one']:,}"
                                   f"{', applied' if v['applied'] else ', NOT applied'})"
                                   for n, v in r["larger"].items())
                add("company_batches", verdict,
                    f"one by one {sum(r['singles']):,} ({', '.join(str(x) for x in r['singles'])}); two together "
                    f"{r['two']:,}; three together {r['three']:,}; {r['companies']} together {r['batch']:,} "
                    f"(one by one {r['batch_singles']:,})" + (f"; {larger}" if larger else "")
                    + f"; sent with the company's exchange, {style_text}; the catalogue sends {BATCH_SIZE} at a time",
                    **r)
        else:
            add("company_batches", "NOT_TESTED", "fewer than three companies with an organisation ID in the query")
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
