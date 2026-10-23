"""v2.0.7: the top-10 shareholder layouts and fail-safe pseudonymisation (findings 68 and 69), company
batches of ten (findings 61 and 62), the quote list's refusal rule (findings 58 and 66), and the exchanges'
stock lists as a source of listing dates."""
import json
from pathlib import Path

import httpx
import pytest

from ashare.http import set_default_transport

# --- top-10 shareholders (finding 68) ---------------------------------------------------------

# The Shenzhen layout: the nature after the name (here glued to it, as PDF text often gives it), then the
# percentage, the shares held, the change, restricted and unrestricted shares, and the pledge state.
LAYOUT_B = ["（二）前10名股东持股情况", "单位：股",
            "股东名称 股东性质 持股比例 报告期末持股数量 报告期内增减变动情况 持有有限售条件的股份数量 "
            "持有无限售条件的股份数量 质押、标记或冻结情况",
            "西安投资控股有限公司国有法人 26.80% 1,370,083,991 0 0 1,370,083,991 不适用 0",
            "陕西煤业化工集团有限责任公司 国有法人 16.76% 856,800,000 46 0 856,800,000 质押 100,000",
            "张三境内自然人 0.52% 26,600,000 -519 0 26,600,000 不适用 0",
            "上述股东关联关系或一致行动的说明 无"]
# The quarterly form: no change column.
LAYOUT_B_QUARTER = ["前10名股东持股情况", "股东名称 股东性质 持股比例(%) 持股数量 持有有限售条件的股份数量 质押、标记或冻结情况",
                    "西安投资控股有限公司 国有法人 26.80 1,370,083,991 0 不适用 0",
                    "李四 境内自然人 1.10 56,000,000 56,000,000 质押 1,000,000",
                    "前10名无限售条件股东持股情况"]


def test_top10_layout_with_nature_after_the_name():
    from ashare.control import parse_top10_pages
    rows = parse_top10_pages(["\n".join(LAYOUT_B)])
    assert [r["shareholder_name"] for r in rows] == ["西安投资控股有限公司", "陕西煤业化工集团有限责任公司", "张三"]
    a, b, c = rows
    assert (a["ownership_pct"], a["shares"], a["change_shares"], a["shareholder_type"]) == \
        (26.8, 1370083991, 0, "STATE_LEGAL_PERSON")
    assert (b["ownership_pct"], b["change_shares"], b["restricted_shares"]) == (16.76, 46, 0)
    assert b["pledged_shares"] == 100000
    assert (c["ownership_pct"], c["change_shares"], c["shareholder_type"]) == (0.52, -519, "DOMESTIC_NATURAL_PERSON")
    assert {r["layout"] for r in rows} == {"B"}


def test_top10_quarterly_layout_without_change_column():
    from ashare.control import parse_top10_pages
    a, b = parse_top10_pages(["\n".join(LAYOUT_B_QUARTER)])
    assert (a["ownership_pct"], a["shares"], a["change_shares"], a["restricted_shares"]) == (26.8, 1370083991, None, 0)
    assert (b["shareholder_name"], b["restricted_shares"], b["pledged_shares"]) == ("李四", 56000000, 1000000)


def test_top10_layout_from_the_row_when_the_header_is_missing():
    from ashare.control import parse_top10_pages
    lines = [x for x in LAYOUT_B if not x.startswith("股东名称")]
    rows = parse_top10_pages(["\n".join(lines)])
    assert [r["ownership_pct"] for r in rows] == [26.8, 16.76, 0.52]


def test_a_table_that_cannot_be_percentages_is_rejected():
    from ashare.control import parse_top10_pages
    bad = ["前十名股东持股情况", "甲公司 60.0 1,000 70.0 0 无 国有法人", "乙公司 0 2,000 50.0 0 无 国有法人"]
    assert parse_top10_pages(["\n".join(bad)]) == []


def test_split_nature():
    from ashare.control import split_nature
    assert split_nature("西安投资控股有限公司国有法人") == ("西安投资控股有限公司", "国有法人")
    assert split_nature("张三境内自然人") == ("张三", "境内自然人")
    assert split_nature("香港中央结算有限公司") == ("香港中央结算有限公司", None)


def test_reextraction_removes_misread_rows(company, tmp_path):
    from helpers import make_pdf, add_disclosure
    from ashare.models import SessionLocal, OwnershipObservation, Disclosure, ReviewItem
    from ashare.control import extract_top_holders
    pdf = make_pdf(tmp_path / "q.pdf", ["2026年第一季度报告"] + LAYOUT_B)
    add_disclosure(company, "2026年第一季度报告", "2026-04-29", pdf, ann_id="Q1")
    s = SessionLocal()
    d = s.query(Disclosure).filter_by(announcement_id="Q1").one()
    stale = OwnershipObservation(company_id=company.id, disclosure_id=d.id, observation_date="2026-03-31",
                                 shareholder_name="张三境内自然人", ownership_pct=-519.0, change_shares=0.52,
                                 source="CNINFO")
    s.add(stale)
    s.commit()
    s.add(ReviewItem(item_key="x1", kind="LOW_CONF", company_id=company.id, table_name="ownership_observations",
                     row_id=stale.id))
    s.commit()
    s.close()
    r = extract_top_holders("600519")
    s = SessionLocal()
    names = {o.shareholder_name: o for o in s.query(OwnershipObservation)}
    items = s.query(ReviewItem).count()
    s.close()
    assert "张三境内自然人" not in names and names["张三"].ownership_pct == 0.52
    assert r.get("removed") == 1 and items == 0


# --- pseudonymisation (finding 69) --------------------------------------------------------------

def test_fail_safe_natural_person_rule():
    from ashare.release import is_natural_person
    assert is_natural_person("张三境内自然人")                       # the nature glued on (finding 69)
    assert is_natural_person("JOHN SMITH") and is_natural_person("Mary-Jane O'Neill")   # Latin letters
    assert is_natural_person("司马相如欧阳")                          # an unusual name: masked unless shown otherwise
    assert not is_natural_person("西安投资控股有限公司国有法人")
    assert not is_natural_person("ABU DHABI INVESTMENT AUTHORITY") and not is_natural_person("NORGES BANK")
    assert not is_natural_person("全国社会保障基金理事会") and not is_natural_person("中央汇金资产管理有限责任公司")
    assert not is_natural_person("26.80") and not is_natural_person("")


def test_glued_name_is_masked_in_a_release(company, tmp_path):
    from ashare.models import SessionLocal, OwnershipObservation, Disclosure
    from ashare.release import build_release, pseudonym, load_key
    s = SessionLocal()
    d = Disclosure(company_id=company.id, announcement_id="A9", title_cn="关于股东张三减持股份的公告",
                   announcement_date="2026-04-29", source="CNINFO")
    s.add(d)
    s.flush()
    for rank, (name, nature) in enumerate([("张三境内自然人", None), ("JOHN SMITH", "其他"),
                                           ("西安投资控股有限公司", "国有法人")], 1):
        s.add(OwnershipObservation(company_id=company.id, disclosure_id=d.id, observation_date="2026-03-31",
                                   shareholder_name=name, shareholder_nature=nature, rank=rank, source="CNINFO"))
    s.commit()
    s.close()
    keyf = tmp_path / "k.key"
    r = build_release(str(tmp_path / "rel"), name="p", pseudonymise=True, key_file=str(keyf), quality=False)
    rel = Path(r["release"])
    everything = "".join(p.read_text(encoding="utf-8-sig") for p in (rel / "csv").glob("*.csv"))
    assert "张三" not in everything and "JOHN SMITH" not in everything
    assert "西安投资控股有限公司" in everything
    key = load_key(str(keyf))
    assert pseudonym("张三", key) in everything            # the same identifier as the bare name


# --- the quote list's refusal rule (findings 58, 59 and 66) -----------------------------------

FS_ALL = "m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23"


def _refusing_server(answer_pages=10, refuse_once=()):
    """The whole list answers its first ``answer_pages`` pages, then everything is refused (HTTP 502);
    ``refuse_once``: (fs, pn) pages refused once only."""
    calls, done = [], set()

    def handler(request):
        p = request.url.params
        pn, pz, fs = int(p["pn"]), int(p["pz"]), p["fs"]
        calls.append((fs, pn))
        if (fs, pn) in refuse_once and (fs, pn) not in done:
            done.add((fs, pn))
            return httpx.Response(502)
        if fs != FS_ALL or pn > answer_pages:
            return httpx.Response(502)
        rows = [{"f12": f"{600000 + i}", "f14": "x", "f26": 20100104} for i in range((pn - 1) * pz, pn * pz)]
        return httpx.Response(200, json={"rc": 0, "data": {"total": 5600, "diff": rows}})
    return handler, calls


def _recording(monkeypatch):
    from ashare import quotelist
    seen, real = [], quotelist._Pager.page

    def page(self, pn, pz=None, fs=quotelist.FS, po=1):
        seen.append((fs, pn))
        return real(self, pn, pz, fs, po)
    monkeypatch.setattr(quotelist._Pager, "page", page)
    return seen


def test_three_refused_attempts_stop_the_reading(db, monkeypatch):
    from ashare.quotelist import listing_info
    attempts = _recording(monkeypatch)
    handler, calls = _refusing_server()
    set_default_transport(httpx.MockTransport(handler))
    try:
        info = listing_info()
    finally:
        set_default_transport(None)
    late = [a for a in attempts if a[1] > 10 or a[0] != FS_ALL]
    # page 11 twice (with a pause), then the first board's page 1: three refused attempts, then nothing more
    assert [a[1] for a in late] == [11, 11, 1] and late[2][0] == "m:0+t:6"
    assert len(attempts) == 13 and not info.complete and len(info) == 1000
    assert info.refused and "refused 3 attempts in a row" in info.note and "Shenzhen main board" in info.refused


def test_a_refused_first_page_is_tried_three_times(db, monkeypatch):
    from ashare.quotelist import listing_info
    attempts = _recording(monkeypatch)
    handler, calls = _refusing_server(answer_pages=0)
    set_default_transport(httpx.MockTransport(handler))
    try:
        info = listing_info()
    finally:
        set_default_transport(None)
    assert attempts == [(FS_ALL, 1)] * 3 and info.refused and len(info) == 0


def test_one_refusal_then_an_answer_carries_on(db):
    from ashare.quotelist import listing_info
    handler, calls = _refusing_server(answer_pages=56, refuse_once={(FS_ALL, 11)})
    set_default_transport(httpx.MockTransport(handler))
    try:
        info = listing_info()
    finally:
        set_default_transport(None)
    assert info.complete and len(info) == 5600 and not info.refused and not info.parts


def test_pauses_before_the_second_and_third_attempt(monkeypatch):
    from ashare import quotelist
    waits = []
    monkeypatch.setattr(quotelist, "_wait", waits.append)
    ref = quotelist._Refusals(offline=False)
    ref.before()
    ref.failed("a")
    ref.before()
    ref.failed("b")
    ref.before()
    with pytest.raises(quotelist.Refused):
        ref.failed("c")
    assert waits == [30, 120]
    ref2 = quotelist._Refusals(offline=False)
    ref2.failed("a")
    ref2.ok()
    ref2.before()
    assert waits == [30, 120]                 # a success resets the count: no pause


def test_board_refused_at_its_first_page_is_named(db):
    from ashare.quotelist import fetch_pages
    handler, _ = _refusing_server()
    set_default_transport(httpx.MockTransport(handler))
    try:
        r = fetch_pages("f12,f14,f26", "listing")
    finally:
        set_default_transport(None)
    assert r["parts"]["szmb"]["rows"] == 0 and "page 1" in (r["parts"]["szmb"]["error"] or "")


# --- the exchanges' stock lists (findings 58 and 66) --------------------------------------------

def _xlsx(rows):
    """A minimal .xlsx: shared strings for text, numbers as numbers."""
    import io
    import zipfile
    from xml.sax.saxutils import escape
    strings, sheet_rows = [], []
    for ri, row in enumerate(rows, 1):
        cells = []
        for ci, v in enumerate(row):
            ref = f"{chr(65 + ci)}{ri}"
            if isinstance(v, (int, float)):
                cells.append(f'<c r="{ref}"><v>{v}</v></c>')
            else:
                strings.append(str(v))
                cells.append(f'<c r="{ref}" t="s"><v>{len(strings) - 1}</v></c>')
        sheet_rows.append(f'<row r="{ri}">{"".join(cells)}</row>')
    ns = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("xl/sharedStrings.xml", f'<sst xmlns="{ns}">' + "".join(f"<si><t>{escape(x)}</t></si>"
                                                                           for x in strings) + "</sst>")
        z.writestr("xl/worksheets/sheet1.xml", f'<worksheet xmlns="{ns}"><sheetData>{"".join(sheet_rows)}'
                                               "</sheetData></worksheet>")
    return buf.getvalue()


SZ_CODES = [f"{i:06d}" for i in range(1, 2101)]
SH_CODES = [f"{600000 + i}" for i in range(1100)]
STAR_CODES = [f"{688000 + i}" for i in range(1, 351)]


def _exchange_server(sse_ok=True, szse_ok=True, quote_calls=None):
    head = ["板块", "公司全称", "英文名称", "注册地址", "A股代码", "A股简称", "A股上市日期", "A股总股本"]
    rows = [head] + [["主板" if c < "300000" else "创业板", "x", "", "", int(c), f"深{c}", "2001-08-27", 100]
                     for c in SZ_CODES]
    rows[2][6] = 37130                       # an Excel day number (2001-08-27)
    xlsx = _xlsx(rows)

    def handler(request):
        url = str(request.url)
        if "query.sse.com.cn" in url:
            if not sse_ok:
                return httpx.Response(503)
            codes = STAR_CODES if request.url.params["STOCK_TYPE"] == "8" else SH_CODES
            assert request.headers.get("referer", "").startswith("https://www.sse.com.cn/")
            return httpx.Response(200, json={"result": [{"A_STOCK_CODE": c, "COMPANY_ABBR": f"沪{c}",
                                                         "LIST_DATE": "19991110"} for c in codes]})
        if "szse.cn/api/report/ShowReport" in url:
            if not szse_ok:
                return httpx.Response(404)
            return httpx.Response(200, content=xlsx)
        if "clist/get" in url:
            if quote_calls is not None:
                quote_calls.append(url)
            p = request.url.params
            pn, pz = int(p["pn"]), int(p["pz"])
            allc = SZ_CODES + SH_CODES + STAR_CODES
            diff = [{"f12": c, "f14": "q", "f26": 20100104} for c in allc[(pn - 1) * pz: pn * pz]]
            return httpx.Response(200, json={"rc": 0, "data": {"total": len(allc), "diff": diff}})
        return httpx.Response(404)
    return handler


def test_read_xlsx_and_dates():
    from ashare.exchange_lists import read_xlsx, normalise_listing_date
    rows = read_xlsx(_xlsx([["A股代码", "A股上市日期"], [1, "1991-04-03"], [600519, 37130]]))
    assert rows == [["A股代码", "A股上市日期"], ["1", "1991-04-03"], ["600519", "37130"]]
    assert normalise_listing_date("20010827") == normalise_listing_date("2001/08/27") == "2001-08-27"
    assert normalise_listing_date("37130") == "2001-08-27" and normalise_listing_date("-") is None


def test_exchange_lists_are_read(db):
    from ashare.exchange_lists import exchange_listing_info
    set_default_transport(httpx.MockTransport(_exchange_server()))
    try:
        info = exchange_listing_info()
    finally:
        set_default_transport(None)
    assert info.complete and len(info) == 2100 + 1100 + 350
    assert info["000001"]["listing_date"] == "2001-08-27" and info["600000"]["listing_date"] == "1999-11-10"
    assert info["000002"]["listing_date"] == "2001-08-27"            # from the Excel day number
    assert info.lists["szse_a"]["dated"] == 2100


def _universe_for_lists():
    from ashare.storage import upsert_ashares
    upsert_ashares([{"code": c, "exchange": "SSE" if c.startswith("6") else "SZSE", "short_name_cn": f"简{c}",
                     "org_id": f"o{c}"} for c in SZ_CODES + SH_CODES + STAR_CODES])


def test_exchange_lists_first_quote_list_not_needed(db):
    from ashare.pipeline import enrich_listing_status
    _universe_for_lists()
    quote = []
    set_default_transport(httpx.MockTransport(_exchange_server(quote_calls=quote)))
    try:
        st = enrich_listing_status()
    finally:
        set_default_transport(None)
    assert st["listing_dates_added"] == 3550 and st["listing_dates_by_source"]["exchanges"] == 3550
    assert quote == [] and st["exchange_lists_complete"] and st["LISTED"] == 3550


def test_quote_list_fills_what_a_failed_exchange_list_leaves(db):
    from ashare.pipeline import enrich_listing_status
    _universe_for_lists()
    quote = []
    set_default_transport(httpx.MockTransport(_exchange_server(szse_ok=False, quote_calls=quote)))
    try:
        st = enrich_listing_status()
    finally:
        set_default_transport(None)
    by = st["listing_dates_by_source"]
    assert by["exchanges"] == 1450 and by["quote_list"] == 2100 and quote
    assert "HTTP 404" in st["exchange_lists"] and not st["exchange_lists_complete"]


def test_update_universe_prints_the_sources(db, monkeypatch):
    from typer.testing import CliRunner
    from ashare.cli import app
    from ashare import pipeline
    _universe_for_lists()
    monkeypatch.setattr(pipeline, "update_universe", lambda source, listing_dates=True: {
        "observations": 1, "inserted": 0, "updated": 1, "rejected": 0, "errors": [],
        "status": pipeline.enrich_listing_status()})
    from ashare import cli
    monkeypatch.setattr(cli, "update_universe", pipeline.update_universe)
    set_default_transport(httpx.MockTransport(_exchange_server()))
    try:
        out = " ".join(CliRunner().invoke(app, ["update-universe"]).output.split())     # undo line wrapping
    finally:
        set_default_transport(None)
    assert "Exchange lists: Shanghai main board 1,100 of 1,100 dated" in out
    assert "3550 listing dates added (3,550 from the exchanges' lists, 0 from the quote list)" in out
    assert "The quote list was not needed." in out


# --- company batches of ten; a part larger than its parent (findings 61 and 62) ----------------

from test_v206 import _leaf_items, _leaf_total, LEAF_DAY, _status  # noqa: E402
from test_v204 import LiveCNInfo, _run, universe  # noqa: E402,F401


def test_batches_of_ten_close_the_leaf(universe):
    from ashare.market_catalogue import BATCH_SIZE
    assert BATCH_SIZE == 10
    server = LiveCNInfo(_leaf_items(), stock_max=10, sort="ignore")
    r = _run(server, LEAF_DAY, LEAF_DAY, "all")
    st = _status()
    assert st["status"] == "DONE" and "STOCK" in st["method"], st
    batches = [c for c in server.calls if c.get("stock")]
    assert batches and max(c["stock"].count(";") + 1 for c in batches) <= 10
    assert r["filters"].get("stock") is not False


def test_a_part_larger_than_its_parent_turns_the_filter_off(universe):
    """As live: a long company list is ignored, so a batch reports more rows than the query it splits."""
    import ashare.market_catalogue as mc
    old = mc.BATCH_SIZE
    mc.BATCH_SIZE = 150
    from test_v204 import items_for, CHINEXT
    items = _leaf_items()
    extra = items_for(LEAF_DAY, 3000, rcjy_share=1.0, codes=CHINEXT)      # 日常经营 elsewhere, as live
    for i, it in enumerate(extra):
        it["announcementId"] = f"{LEAF_DAY}-cy{i}"
    try:
        server = LiveCNInfo(items + extra, stock_max=10, sort="ignore")
        r = _run(server, LEAF_DAY, LEAF_DAY, "all")
    finally:
        mc.BATCH_SIZE = old
    st = _status()
    assert r["filters"].get("stock") is False and "filter not applied" in (st["partition"] or "")
    # no batch was read beyond its first page
    assert not [c for c in server.calls if c.get("stock") and ";" in c["stock"] and c["pageNum"] != "1"]
    assert st["status"] == "DONE" and "SINGLE_COMPANIES" in st["method"]       # closed one company at a time


def test_costly_splits_counted_only_when_needed(universe):
    """A busy day the boards and categories cover never asks for company batches."""
    from test_v204 import _april29
    server = LiveCNInfo(_april29())
    _run(server, LEAF_DAY, LEAF_DAY, "all")
    assert _status()["status"] == "DONE"
    assert not [c for c in server.calls if c.get("stock")]


def test_manifest_records_the_pseudonymisation_rule(company, tmp_path):
    from ashare.release import build_release, PERSON_RULE
    r = build_release(str(tmp_path / "rel"), name="m", pseudonymise=True, key_file=str(tmp_path / "k.key"),
                      quality=False)
    m = json.loads((Path(r["release"]) / "manifest.json").read_text(encoding="utf-8"))
    assert m["pseudonymisation"]["rule"] == PERSON_RULE and "v2.0.7" in PERSON_RULE


def test_entities_left_by_misread_rows_are_removed(company, tmp_path):
    from ashare.models import SessionLocal, OwnershipObservation, Entity
    from ashare.control import resolve_entities, _entity_type
    assert _entity_type("张三境内自然人") == "PERSON" and _entity_type("西安投资控股有限公司国有法人") == "COMPANY"
    s = SessionLocal()
    o = OwnershipObservation(company_id=company.id, observation_date="2026-03-31",
                             shareholder_name="西安投资控股有限公司国有法人", source="CNINFO")
    s.add(o)
    s.commit()
    s.close()
    resolve_entities()
    s = SessionLocal()
    assert s.query(Entity).filter_by(name="西安投资控股有限公司国有法人").count() == 1
    s.query(OwnershipObservation).filter_by(shareholder_name="西安投资控股有限公司国有法人").update(
        {"shareholder_name": "西安投资控股有限公司", "entity_id": None})
    s.commit()
    s.close()
    r = resolve_entities()
    s = SessionLocal()
    names = {e.name for e in s.query(Entity)}
    s.close()
    assert "西安投资控股有限公司国有法人" not in names and "西安投资控股有限公司" in names and r["removed"] == 1
