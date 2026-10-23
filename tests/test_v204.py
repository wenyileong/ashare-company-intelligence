"""v2.0.4: a complete catalogue on the busiest days (findings 22 to 30).

The mock CNINFO below behaves as the live service did in the v2.0.3 run:
one query returns at most 3,000 results; ``sz`` and ``sh`` cover whole
exchanges (ChiNext and STAR included); some announcements are uncategorised
or on the Beijing board; an announcement can be listed for several
securities. The filters whose live behaviour is unknown (disjoint board
codes, industry, several companies at once, sort order) can each be switched
on or off, so that the engine is tested both where CNINFO supports them and
where it does not."""
from datetime import date

import httpx
import pytest

from ashare.http import set_default_transport
from ashare.market_catalogue import ALL_CATEGORIES, CSRC_SECTIONS

SZ_MAIN = [f"{i:06d}" for i in range(1, 121)]
CHINEXT = [f"{300000 + i}" for i in range(1, 61)]
SSE_MAIN = [f"{600000 + i}" for i in range(0, 120)]
STAR = [f"{688000 + i}" for i in range(1, 41)]
CODES = SZ_MAIN + CHINEXT + SSE_MAIN + STAR
BSE = [f"{920000 + i}" for i in range(1, 30)]


def board(code):
    if code.startswith("688"):
        return "STAR"
    if code.startswith("6"):
        return "SSE_MAIN"
    if code.startswith("3"):
        return "CHINEXT"
    if code.startswith("92"):
        return "BSE"
    return "SZSE_MAIN"


PLATE = {"sz": {"SZSE_MAIN", "CHINEXT"}, "sh": {"SSE_MAIN", "STAR"}, "szmb": {"SZSE_MAIN"}, "szcy": {"CHINEXT"},
         "shmb": {"SSE_MAIN"}, "shkcp": {"STAR"}, "bj": {"BSE"}}


def _ms(day):
    return int((date.fromisoformat(day) - date(1970, 1, 1)).total_seconds() * 1000) + 8 * 3600 * 1000


def trade_of(code):
    return CSRC_SECTIONS[2] if int(code[-2:]) % 3 else CSRC_SECTIONS[int(code[-2:]) % len(CSRC_SECTIONS)]


def items_for(day, n, rcjy_share=0.0, uncategorised=0, bse_uncategorised=0, multi=0, codes=CODES):
    """``n`` announcements for listed companies; a share of them in 日常经营 (rcjy); some
    uncategorised; some uncategorised Beijing announcements; ``multi`` announcements listed
    for a second security of another company."""
    out = []
    for i in range(n):
        code = codes[i % len(codes)]
        if i < int(n * rcjy_share):
            cat = "category_rcjy_szsh"
        elif i >= n - uncategorised:
            cat = None
        else:
            cat = ALL_CATEGORIES[i % len(ALL_CATEGORIES)]
        out.append({"announcementId": f"{day}-{i}", "announcementTitle": f"公告{i}", "secCode": code,
                    "adjunctUrl": f"finalpage/{day}/{i}.PDF", "announcementTime": _ms(day), "_cat": cat,
                    "_trade": trade_of(code)})
    for i in range(bse_uncategorised):
        out.append({"announcementId": f"{day}-bj{i}", "secCode": BSE[i % len(BSE)], "announcementTime": _ms(day),
                    "adjunctUrl": f"finalpage/{day}/bj{i}.PDF", "_cat": None, "_trade": CSRC_SECTIONS[2]})
    for i in range(multi):            # the same announcement, listed again for another company
        src = out[i]
        other = codes[(codes.index(src["secCode"]) + 1) % len(codes)]
        out.append(dict(src, secCode=other, _trade=trade_of(other)))
    return out


class LiveCNInfo:
    """``stock``: "yes" (batches and single companies work), "no" (several at once return nothing; single
    companies work), "ignore" (several at once are ignored), "never" (no company filter works). v2.0.6:
    ``exchange="ignore"`` makes ``sz``/``sh`` ignored; ``column_strict`` makes a company query return nothing
    unless it is sent with the company's own exchange; ``division`` ("yes"/"no") whether manufacturing
    divisions are accepted as an industry."""
    def __init__(self, items, disjoint="yes", trade="yes", stock="yes", sort="yes", unstable=False, bj="yes",
                 exchange="yes", column_strict=False, division="no"):
        self.items, self.bj = items, bj
        self.disjoint, self.trade, self.stock, self.sort, self.unstable = disjoint, trade, stock, sort, unstable
        self.exchange, self.column_strict, self.division = exchange, column_strict, division
        self.calls = []

    def __call__(self, request):
        if "hisAnnouncement/query" not in str(request.url):
            return httpx.Response(404)
        body = dict(httpx.QueryParams(request.content.decode()))
        self.calls.append(body)
        a, b = body["seDate"].split("~")
        cats = [c for c in body.get("category", "").split(";") if c]
        plate, trade, stock = body.get("plate", ""), body.get("trade", ""), body.get("stock", "")
        sel = [it for it in self.items
               if a <= date.fromtimestamp((it["announcementTime"] - 8 * 3600 * 1000) / 1000).isoformat() <= b
               and (not cats or it["_cat"] in cats)]
        if plate:
            if (plate in ("szmb", "shmb") and self.disjoint == "zero") or (plate == "bj" and self.bj == "no"):
                sel = []
            elif plate in ("sz", "sh") and self.exchange == "ignore":
                pass
            elif not (plate in ("szmb", "shmb") and self.disjoint == "ignore"):
                sel = [it for it in sel if board(it["secCode"]) in PLATE[plate]]
        if trade and self.trade == "yes":
            if trade in CSRC_SECTIONS:
                sel = [it for it in sel if it["_trade"] == trade]
            elif self.division == "yes":
                sel = [it for it in sel if it["_trade"] == CSRC_SECTIONS[2] and it.get("_division") == trade]
            else:
                sel = []
        if stock:
            codes = {p.split(",")[0] for p in stock.split(";")}
            column = body.get("column", "")
            if self.stock == "never" or (len(codes) > 1 and self.stock == "no"):
                sel = []
            elif self.column_strict and any(("sse" if c.startswith("6") else "szse") != column for c in codes):
                sel = []
            elif not (len(codes) > 1 and self.stock == "ignore"):
                sel = [it for it in sel if it["secCode"] in codes]
        order = body.get("sortType", "")
        if order and self.sort == "yes":
            sel = list(reversed(sel)) if order == "desc" else list(sel)
        page = min(int(body["pageNum"]), 100)
        lo = (page - 1) * 30
        if self.unstable and not (order and self.sort == "yes"):
            lo += (page - 1) // 20        # rows move between pages: one row is skipped every 20 pages
        chunk = sel[lo: lo + 30]
        return httpx.Response(200, json={"announcements": [{k: v for k, v in it.items() if not k.startswith("_")}
                                                             for it in chunk] or None,
                                         "totalAnnouncement": len(sel),
                                         "hasMore": page * 30 < len(sel) or len(sel) > 3000})


@pytest.fixture
def universe(db):
    from ashare.storage import upsert_ashares
    upsert_ashares([{"code": c, "exchange": "SSE" if c.startswith("6") else "SZSE", "short_name_cn": f"简{c}",
                     "org_id": f"o{c}"} for c in CODES])
    return CODES


def _run(server, *args, **kw):
    from ashare.market_catalogue import catalogue
    set_default_transport(httpx.MockTransport(server))
    try:
        return catalogue(*args, **kw)
    finally:
        set_default_transport(None)


def _stored():
    from ashare.models import SessionLocal, Disclosure, Company
    s = SessionLocal()
    try:
        return {(d.announcement_id, c.security_code) for d, c in
                s.query(Disclosure, Company).join(Company, Disclosure.company_id == Company.id)}
    finally:
        s.close()


DAY = "2026-04-29"


def _april29():
    # 12,000 rows, 45% in 日常经营: about 2,700 per exchange-wide board and over 3,000 on Shenzhen
    # (the main board and ChiNext together), plus uncategorised and Beijing announcements and rows
    # listed for two securities.
    return items_for(DAY, 12000, rcjy_share=0.45, uncategorised=150, bse_uncategorised=120, multi=40)


def _expected_in_scope(items):
    return {(it["announcementId"], it["secCode"]) for it in items if board(it["secCode"]) != "BSE"}


def test_acceptance_day_complete_when_every_filter_works(universe):
    from ashare.market_catalogue import day_status
    items = _april29()
    server = LiveCNInfo(items)
    r = _run(server, DAY, DAY, "all")
    st = day_status("all")[0]
    assert st["status"] == "DONE" and st["gap_in_scope"] == 0 and st["gap_out_scope"] == 0
    assert st["expected"] == len(items) and st["stored"] == len(items) and st["rows_multi"] == 40
    assert _expected_in_scope(items) <= _stored()                         # every row for a listed company
    assert r["rows_multi"] == 40 and not r["days_shortfall"]
    assert r["unmatched_by_reason"] and sum(r["unmatched_by_reason"].values()) == r["unmatched"] == 120
    assert r["filters"].get("board_scheme") == "disjoint"
    assert len(server.calls) < 1500


def test_complete_without_disjoint_boards_industry_or_sort(universe):
    """Only whole-exchange boards, categories and company batches work: still complete."""
    from ashare.market_catalogue import day_status
    items = _april29()
    server = LiveCNInfo(items, disjoint="zero", trade="ignore", sort="ignore")
    r = _run(server, DAY, DAY, "all")
    st = day_status("all")[0]
    assert st["status"] == "DONE" and st["gap_in_scope"] == 0, st
    assert _expected_in_scope(items) <= _stored()
    assert r["filters"].get("trade") is False
    assert "STOCK" in st["method"] and "SORT_BOTH" not in st["method"]     # v2.0.6: splits before sorting


def test_complete_with_industry_only(universe):
    from ashare.market_catalogue import day_status
    # Without company batches or sort order, uncategorised rows beyond 3,000 within one industry and board
    # cannot be reached, so this day has none.
    items = items_for(DAY, 12000, rcjy_share=0.45, bse_uncategorised=120, multi=40)
    r = _run(LiveCNInfo(items, disjoint="zero", stock="no", sort="ignore"), DAY, DAY, "all")
    st = day_status("all")[0]
    assert st["status"] == "DONE" and st["gap_in_scope"] == 0, st
    assert "TRADE" in st["method"]


def test_unreachable_rows_are_recorded_not_lost_silently(universe):
    """No filter beyond category and whole-exchange board works: the gap is recorded per board."""
    from ashare.market_catalogue import day_status
    items = _april29()
    r = _run(LiveCNInfo(items, disjoint="zero", trade="ignore", stock="never", sort="ignore"), DAY, DAY, "all")
    st = day_status("all")[0]
    assert st["status"] == "SHORTFALL" and st["gap_in_scope"] > 0
    assert st["stored"] + st["gap_in_scope"] + st["gap_out_scope"] == st["expected"]
    assert "unreachable" in (st["partition"] or "") or "reach" in (st["partition"] or "")
    assert r["days_shortfall"][0]["gap_in_scope"] == st["gap_in_scope"]


def test_both_sort_orders_reach_up_to_6000(universe):
    from ashare.market_catalogue import day_status
    day = "2026-04-22"
    items = items_for(day, 5200, uncategorised=0)
    server = LiveCNInfo(items, disjoint="zero", trade="ignore", stock="no", sort="yes")
    r = _run(server, day, day, "reports")             # a kind with fewer categories: the day stays over 3,000
    st = day_status("reports")[0]
    assert r["filters"].get("sort") is True or st["status"] == "DONE"


def test_sort_both_on_a_single_category_day(universe):
    """A single-category kind over 3,000 with no filter but the sort order: complete via both orders."""
    from ashare.market_catalogue import day_status
    day = "2026-04-23"
    items = items_for(day, 4500, rcjy_share=0.0)
    for it in items:
        it["_cat"] = "category_ndbg_szsh"
    server = LiveCNInfo(items, disjoint="ignore", exchange="ignore", trade="ignore", stock="never", sort="yes")
    r = _run(server, day, day, "annual")
    st = day_status("annual")[0]
    assert st["status"] == "DONE" and st["stored"] == 4500 and "SORT_BOTH" in st["method"]
    assert any(k.startswith("sort[") and v is True for k, v in r["filters"].items())


def test_beijing_only_gap_leaves_the_day_done(universe):
    """Uncategorised Beijing announcements beyond reach are outside the enabled boards."""
    from ashare.market_catalogue import day_status
    day = "2026-04-21"
    items = items_for(day, 2000, bse_uncategorised=3400)
    r = _run(LiveCNInfo(items, trade="ignore", stock="no", sort="ignore"), day, day, "all")
    st = day_status("all")[0]
    assert st["status"] == "DONE" and st["gap_in_scope"] == 0 and st["gap_out_scope"] == 400
    assert r["days_gap_outside"] and not r["days_shortfall"]


def test_gap_not_proven_outside_counts_inside(universe):
    """If CNINFO's Beijing code does not work, unreached Beijing rows cannot be proven to lie outside the
    enabled boards, so they count as a gap within them (conservative)."""
    from ashare.market_catalogue import day_status
    items = _april29()
    _run(LiveCNInfo(items, disjoint="zero", bj="no", trade="ignore", sort="ignore"), DAY, DAY, "all")
    st = day_status("all")[0]
    assert st["status"] == "SHORTFALL" and st["gap_in_scope"] == 120 and st["gap_out_scope"] == 0
    assert _expected_in_scope(items) <= _stored()               # every listed company's row still arrived


def test_rows_for_several_securities_are_not_a_shortfall(universe):
    from ashare.market_catalogue import day_status
    day = "2026-01-27"
    items = items_for(day, 1600, multi=12)
    r = _run(LiveCNInfo(items), day, day, "all")
    st = day_status("all")[0]
    assert st["status"] == "DONE" and st["stored"] == 1612 and st["rows_multi"] == 12
    assert _expected_in_scope(items) <= _stored()


def test_unstable_ordering_is_recovered_by_reading_both_orders(universe):
    from ashare.market_catalogue import day_status
    day = "2026-01-09"
    items = items_for(day, 2950)
    r = _run(LiveCNInfo(items, unstable=True), day, day, "all")
    st = day_status("all")[0]
    assert st["status"] == "DONE" and st["stored"] == 2950 and "SORT_BOTH" in st["method"]


def test_unstable_ordering_without_sort_is_recovered_by_boards(universe):
    """v2.0.6 (finding 39): a short day under the limit is read again board by board."""
    from ashare.market_catalogue import day_status
    day = "2026-01-09"
    items = items_for(day, 2950)
    _run(LiveCNInfo(items, unstable=True, sort="ignore"), day, day, "all")
    st = day_status("all")[0]
    assert st["status"] == "DONE" and st["stored"] == 2950 and "BOARDS" in st["method"]


def test_unstable_ordering_without_sort_or_boards_is_a_recorded_gap(universe):
    from ashare.market_catalogue import day_status
    day = "2026-01-09"
    items = items_for(day, 2950)
    _run(LiveCNInfo(items, unstable=True, sort="ignore", disjoint="zero"), day, day, "all")
    st = day_status("all")[0]
    assert st["status"] == "SHORTFALL" and st["gap_in_scope"] > 0


def test_early_stop_on_a_capped_query(universe):
    """A capped query that brings nothing new stops after five pages rather than reading all 100."""
    items = _april29()
    server = LiveCNInfo(items, disjoint="zero", trade="ignore", stock="no", sort="ignore")
    _run(server, DAY, DAY, "all")
    whole_day_pages = [c for c in server.calls if c["seDate"] == f"{DAY}~{DAY}" and not c.get("category")
                       and not c.get("plate") and not c.get("stock") and int(c["pageNum"]) > 1]
    assert len(whole_day_pages) < 20


def test_recent_totals_are_rechecked(universe):
    from ashare.market_catalogue import _china_today, day_status
    from datetime import timedelta
    day = (date.fromisoformat(_china_today()) - timedelta(days=3)).isoformat()
    items = items_for(day, 100)
    server = LiveCNInfo(items)
    _run(server, day, day, "all")
    assert day_status("all", day, day)[0]["stored"] == 100
    server.items = items + items_for(day, 105)[100:]          # five announcements appear later
    r = _run(server, day, day, "all")
    assert r["days_rechecked"] == [day] and day_status("all", day, day)[0]["stored"] == 105
    server.calls.clear()
    r = _run(server, day, day, "all")                          # unchanged now: one recheck query, no refetch
    assert r["days_rechecked"] == [] and len(server.calls) == 1


def test_recatalogue_holds_days_whose_gap_recurred(universe):
    from ashare.market_catalogue import recatalogue_busy_days, day_status
    items = _april29()
    server = LiveCNInfo(items, disjoint="zero", trade="ignore", stock="never", sort="ignore")
    _run(server, DAY, DAY, "all")
    assert day_status("all")[0]["status"] == "SHORTFALL"
    set_default_transport(httpx.MockTransport(server))
    try:
        lines = []
        server.calls.clear()
        r = recatalogue_busy_days("all", progress=lines.append)
        assert r["days"] == [] and r["held"] == [DAY] and not server.calls
        assert any("cannot close a gap" in x for x in lines)
        server.stock = "yes"                                   # a method that works: --include-current
        r = recatalogue_busy_days("all", include_current=True)
    finally:
        set_default_transport(None)
    assert day_status("all")[0]["status"] == "DONE"


def test_v203_shortfalls_are_recatalogued(universe):
    """Days short under v2.0.3 (no strategy recorded) are fetched again with the new method."""
    from ashare.models import SessionLocal, CatalogueDay
    from ashare.market_catalogue import recatalogue_busy_days, day_status
    s = SessionLocal()
    s.add(CatalogueDay(kind="all", day=DAY, status="SHORTFALL", expected=1, stored=0))
    s.commit()
    s.close()
    set_default_transport(httpx.MockTransport(LiveCNInfo(_april29())))
    try:
        r = recatalogue_busy_days("all")
    finally:
        set_default_transport(None)
    assert r["days"] == [DAY] and day_status("all")[0]["status"] == "DONE"


def test_exit_codes_and_desktop_wording(universe, tmp_path, monkeypatch):
    from typer.testing import CliRunner
    from ashare.cli import app
    items = _april29()
    set_default_transport(httpx.MockTransport(LiveCNInfo(items, disjoint="zero", trade="ignore", stock="never",
                                                         sort="ignore")))
    try:
        res = CliRunner().invoke(app, ["catalogue-disclosures", "--since", DAY, "--until", DAY, "--kind", "all"])
        assert res.exit_code == 3 and "Finished with gaps" in res.output
        pytest.importorskip("tkinter")
        from ashare.gui import run_command
        monkeypatch.chdir(tmp_path)
        code, out = run_command(["catalogue-disclosures", "--since", DAY, "--until", DAY, "--kind", "all",
                                 "--refresh"])
        assert code == 3
    finally:
        set_default_transport(None)
    set_default_transport(httpx.MockTransport(LiveCNInfo(items)))
    try:
        res = CliRunner().invoke(app, ["catalogue-disclosures", "--since", DAY, "--until", DAY, "--kind", "all",
                                       "--refresh"])
        assert res.exit_code == 0, res.output
    finally:
        set_default_transport(None)


def test_probe_filters_verdicts(universe):
    from ashare.market_catalogue import probe_filters
    items = _april29() + items_for("2026-01-10", 300, multi=5)
    set_default_transport(httpx.MockTransport(LiveCNInfo(items)))
    try:
        r = {t["test"]: t["verdict"] for t in probe_filters(DAY)["tests"]}
    finally:
        set_default_transport(None)
    assert r == {"boards_disjoint": "PARTITION", "boards_exchange": "PARTITION", "industry": "PARTITION",
                 "manufacturing_divisions": "REJECTED", "company_batches": "WORKS", "sort_orders": "HONOURED",
                 "repeated_rows": "ROWS_PER_SECURITY"}
    set_default_transport(httpx.MockTransport(LiveCNInfo(items, disjoint="zero", trade="ignore", stock="no",
                                                         sort="ignore", unstable=True)))
    try:
        r = {t["test"]: t["verdict"] for t in probe_filters(DAY)["tests"]}
    finally:
        set_default_transport(None)
    assert r["boards_disjoint"] in ("PARTIAL", "REJECTED") and r["industry"] == "IGNORED"
    assert r["company_batches"] == "SINGLES_ONLY" and r["sort_orders"] == "IGNORED"
    assert r["manufacturing_divisions"] == "IGNORED"


def test_migration_adds_catalogue_detail_columns(db):
    from sqlalchemy import inspect
    from ashare.models import engine
    cols = {c["name"] for c in inspect(engine()).get_columns("catalogue_days")}
    assert {"rows_multi", "gap_in_scope", "gap_out_scope", "partition", "strategy", "window_expected"} <= cols
