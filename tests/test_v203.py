"""v2.0.3: complete, trustworthy catalogue (findings 3, 6, 13, 14, 15), listing dates and panels (finding 4),
PDF warning summary (finding 5)."""
import math
from datetime import date, timedelta

import httpx
import pytest

from ashare.http import set_default_transport
from ashare.market_catalogue import ALL_CATEGORIES

CODES = [f"{600000 + i}" for i in range(60)] + [f"{i:06d}" for i in range(1, 61)] + \
        [f"{300000 + i}" for i in range(1, 41)] + [f"{688000 + i}" for i in range(1, 21)]


def _plate(code):
    return "shkcp" if code.startswith("688") else "sh" if code.startswith("6") else \
        "szcy" if code.startswith("3") else "sz"


def _ms(day):
    return int((date.fromisoformat(day) - date(1970, 1, 1)).total_seconds() * 1000) + 8 * 3600 * 1000


def make_items(day, n, uncategorised=0, unmatched=0, cat=None, uncategorised_last=False):
    out = []
    for i in range(n):
        code = CODES[i % len(CODES)] if i >= unmatched else f"{920000 + i}"
        unc = i >= n - uncategorised if uncategorised_last else i < uncategorised
        c = None if unc else (cat or ALL_CATEGORIES[i % len(ALL_CATEGORIES)])
        out.append({"announcementId": f"{day}-{i}", "announcementTitle": f"公告{i}", "secCode": code,
                    "adjunctUrl": f"finalpage/{day}/{i}.PDF", "announcementTime": _ms(day), "_cat": c})
    return out


class CNInfo:
    """A mock CNINFO search that behaves like the live one in the v2.0.2 logs:
    the column is ignored, one query returns at most 100 pages, and later pages
    repeat page 100 while hasMore stays true."""

    def __init__(self, days, cap=True):
        self.items = [it for d in sorted(days) for it in days[d]]
        self.cap = cap
        self.calls = []
        self.fail = None          # callable(body) -> exception or None

    def __call__(self, request):
        url = str(request.url)
        if "hisAnnouncement/query" not in url:
            return httpx.Response(404)
        body = dict(httpx.QueryParams(request.content.decode()))
        self.calls.append(body)
        if self.fail:
            exc = self.fail(body)
            if exc:
                raise exc
        a, b = body["seDate"].split("~")
        cats = [c for c in body.get("category", "").split(";") if c]
        plate = body.get("plate", "")
        sel = [it for it in self.items
               if a <= date.fromtimestamp((it["announcementTime"] - 8 * 3600 * 1000) / 1000).isoformat() <= b
               and (not cats or it["_cat"] in cats) and (not plate or _plate(it["secCode"]) == plate)]
        page = int(body["pageNum"])
        eff = min(page, 100) if self.cap else page
        chunk = sel[(eff - 1) * 30: eff * 30]
        return httpx.Response(200, json={"announcements": [{k: v for k, v in it.items() if k != "_cat"}
                                                             for it in chunk] or None,
                                         "totalAnnouncement": len(sel), "hasMore": page * 30 < len(sel) or
                                         (self.cap and len(sel) > 3000)})


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


def _stored_ids():
    from ashare.models import SessionLocal, Disclosure
    s = SessionLocal()
    try:
        return [d.announcement_id for d in s.query(Disclosure)]
    finally:
        s.close()


def test_busy_day_is_split_complete_and_queried_once(universe):
    from ashare.market_catalogue import day_status
    days = {"2026-04-23": make_items("2026-04-23", 80),
            "2026-04-24": make_items("2026-04-24", 6500, unmatched=200),
            "2026-04-25": make_items("2026-04-25", 40)}
    server = CNInfo(days)
    lines = []
    r = _run(server, "2026-04-23", "2026-04-25", "all", progress=lines.append)
    st = {x["day"]: x for x in day_status("all")}
    assert st["2026-04-24"]["status"] == "DONE" and st["2026-04-24"]["expected"] == 6500
    assert st["2026-04-24"]["stored"] == 6500 and st["2026-04-24"]["method"] == "CATEGORY_SPLIT"
    assert r["announcements"] == 6620 and r["unmatched"] == 200 and not r["days_failed"]
    ids = _stored_ids()
    assert len(ids) == len(set(ids)) == 6620 - 200                       # every matched announcement, once
    assert {c["column"] for c in server.calls} == {"szse"}                 # one market-wide query, not per exchange
    assert max(int(c["pageNum"]) for c in server.calls) <= 101             # no runaway paging
    assert len(server.calls) < 6620 / 30 + 60
    assert any("category 5 of 26 done" in x for x in lines)               # progress within a busy day


def test_uncategorised_announcements_are_recovered_by_board(universe):
    from ashare.market_catalogue import day_status
    days = {"2026-04-29": make_items("2026-04-29", 4000, uncategorised=37)}
    r = _run(CNInfo(days), "2026-04-29", "2026-04-29", "all")
    st = day_status("all")[0]
    assert (st["status"], st["stored"]) == ("DONE", 4000) and st["method"] == "CATEGORY_SPLIT+BOARD_REMAINDER"
    assert not r["days_shortfall"]


def test_shortfall_is_recorded_and_busy_days_listed(universe):
    from ashare.market_catalogue import day_status, busy_days
    # 12,000 on one day: the Shanghai main board alone holds 4,000, so its uncategorised
    # announcements beyond its first 3,000 cannot be reached by any query.
    days = {"2026-04-30": make_items("2026-04-30", 12000, uncategorised=37, uncategorised_last=True)}
    r = _run(CNInfo(days), "2026-04-30", "2026-04-30", "all")
    (sf,) = r["days_shortfall"]
    assert sf["day"] == "2026-04-30" and sf["expected"] == 12000 and 12000 - 37 <= sf["stored"] < 12000
    assert day_status("all")[0]["status"] == "SHORTFALL"
    assert busy_days("all") == ["2026-04-30"]


def test_runaway_paging_stops_without_splitting_when_uncapped_kind_fits(universe):
    days = {"2026-03-02": make_items("2026-03-02", 2990)}
    server = CNInfo(days)
    r = _run(server, "2026-03-02", "2026-03-02", "all")
    assert r["days_done"] == 1 and len(server.calls) == 100 and not r["days_shortfall"]


def test_rerun_resumes_from_unfinished_days(universe):
    from ashare.http import Cancelled, request_cancel, reset_cancel
    days = {f"2026-01-{d:02d}": make_items(f"2026-01-{d:02d}", 1200) for d in range(5, 10)}
    days.update({f"2026-02-{d:02d}": make_items(f"2026-02-{d:02d}", 50) for d in range(2, 6)})
    server = CNInfo(days)
    orig = server.__call__

    def handler(request):
        if len(server.calls) == 160:
            request_cancel()                                 # Stop pressed mid-run
        return orig(request)
    with pytest.raises(Cancelled):
        _run(handler, "2026-01-01", "2026-02-28", "all")
    reset_cancel()
    from ashare.market_catalogue import day_status
    done_first = {x["day"] for x in day_status("all") if x["status"] == "DONE"}
    assert done_first and len(done_first) < 59
    server.calls.clear()
    r = _run(server, "2026-01-01", "2026-02-28", "all")
    assert r["days_skipped"] == len(done_first)
    asked = {c["seDate"] for c in server.calls}
    assert not any(a == b and a in done_first for a, b in (s.split("~") for s in asked))
    ids = _stored_ids()
    assert len(ids) == len(set(ids)) == 5 * 1200 + 4 * 50
    server.calls.clear()
    r = _run(server, "2026-01-01", "2026-02-28", "all")                   # everything finished: no queries
    assert server.calls == [] and r["days_skipped"] == 59


def test_errors_are_recorded_per_day_and_retried(universe):
    from ashare.market_catalogue import day_status
    days = {"2026-05-11": make_items("2026-05-11", 2000), "2026-05-12": make_items("2026-05-12", 2000),
            "2026-06-03": make_items("2026-06-03", 30)}
    server = CNInfo(days)
    server.fail = lambda body: httpx.ConnectError("getaddrinfo failed") if body["seDate"] == "2026-05-12~2026-05-12" else None
    r = _run(server, "2026-05-01", "2026-06-30", "all")
    assert r["days_failed"] == ["2026-05-12"]                              # exactly the day that failed
    st = {x["day"]: x["status"] for x in day_status("all")}
    assert st["2026-05-11"] == "DONE" and st["2026-05-12"] == "FAILED" and st["2026-06-03"] == "DONE"
    server.fail, server.calls[:] = None, []
    r = _run(server, "2026-05-01", "2026-06-30", "all")
    assert {c["seDate"] for c in server.calls} == {"2026-05-12~2026-05-12"}
    assert not r["days_failed"] and day_status("all", "2026-05-12", "2026-05-12")[0]["status"] == "DONE"


def test_three_failures_in_a_row_stop_the_run(universe):
    days = {f"2026-0{m}-03": make_items(f"2026-0{m}-03", 10) for m in range(1, 7)}
    server = CNInfo(days)
    server.fail = lambda body: httpx.ConnectError("down")
    r = _run(server, "2026-01-01", "2026-06-30", "all")
    assert r["stopped_early"] and len(r["errors"]) == 3


def test_today_is_never_finished(universe):
    from ashare.market_catalogue import day_status, _china_today
    today = _china_today()
    r = _run(CNInfo({today: make_items(today, 5)}), today, today, "all")
    assert day_status("all")[0]["status"] == "OPEN" and r["days_done"] == 1


def test_recatalogue_busy_days_from_earlier_versions(universe):
    from ashare.market_catalogue import recatalogue_busy_days
    from ashare.models import SessionLocal, Company, Disclosure
    s = SessionLocal()
    c = s.query(Company).first()
    for i in range(2600):          # a v2.0.2 day cut at the limit, with no day record
        s.add(Disclosure(company_id=c.id, announcement_id=f"old{i}", announcement_date="2026-03-31", title_cn="x"))
    s.commit()
    s.close()
    days = {"2026-03-31": make_items("2026-03-31", 4500)}
    server = CNInfo(days)
    set_default_transport(httpx.MockTransport(server))
    try:
        r = recatalogue_busy_days("all")
    finally:
        set_default_transport(None)
    assert r["days"] == ["2026-03-31"] and r["days_done"] == 1 and not r["days_shortfall"]


def test_probe_paging_verdicts():
    from ashare.market_catalogue import probe_paging
    days = {"2026-04-24": make_items("2026-04-24", 15382)}
    for cap, verdict in ((True, "LIMIT_CONFIRMED"), (False, "NO_LIMIT")):
        set_default_transport(httpx.MockTransport(CNInfo(days, cap=cap)))
        try:
            r = probe_paging("2026-04-24")
        finally:
            set_default_transport(None)
        assert r["total"] == 15382 and r["verdict"] == verdict and r["requests"] == 4
    set_default_transport(httpx.MockTransport(CNInfo({"2026-02-02": make_items("2026-02-02", 100)})))
    try:
        assert probe_paging("2026-02-02")["verdict"] == "INCONCLUSIVE"
    finally:
        set_default_transport(None)


def test_acceptance_24_april_15382(universe):
    """The acceptance check: a day like 24 April 2026 (15,382 announcements) is stored in full."""
    from ashare.market_catalogue import day_status
    days = {"2026-04-24": make_items("2026-04-24", 15382, unmatched=400)}
    r = _run(CNInfo(days), "2026-04-24", "2026-04-24", "all")
    st = day_status("all")[0]
    assert (st["status"], st["expected"], st["stored"]) == ("DONE", 15382, 15382)
    assert r["announcements"] == 15382 and len(set(_stored_ids())) == 15382 - 400


# --- quote list (finding 4) ------------------------------------------------------------------

def _quote_server(n=3050, refuse=("push2.eastmoney.com",), fail_pages=()):
    rows = [{"f12": f"{600000 + i}" if i < 1600 else f"{i - 1600 + 1:06d}", "f14": f"名{i}",
             "f26": 20100104 + (i % 20)} for i in range(n)]
    calls = []

    def handler(request):
        url = request.url
        if "clist/get" not in str(url):
            return httpx.Response(404)
        pn, pz = int(url.params["pn"]), int(url.params["pz"])
        calls.append((url.host, url.scheme, pn, request.headers.get("referer"), request.headers.get("user-agent")))
        if url.host in refuse and not request.headers.get("referer"):
            return httpx.Response(502)
        if pn in fail_pages:
            return httpx.Response(502)
        return httpx.Response(200, json={"rc": 0, "data": {"total": n, "diff": rows[(pn - 1) * pz: pn * pz]}})
    return handler, calls


def test_quote_list_falls_back_to_a_variant_that_answers(db):
    from ashare.quotelist import listing_info, _variant_file
    handler, calls = _quote_server()
    set_default_transport(httpx.MockTransport(handler))
    try:
        info = listing_info()
    finally:
        set_default_transport(None)
    assert info.complete and len(info) == 3050 and info["600000"]["listing_date"] == "2010-01-04"
    assert "referer" in _variant_file().read_text(encoding="utf-8")
    plain = [c for c in calls if c[3] is None]
    assert len(plain) == 2 and calls[2][3]                    # plain request refused (and retried once), then Referer
    assert all(c[4].startswith("AshareResearchDataCollector/") for c in calls)  # the honest user agent throughout


def test_quote_list_download_resumes_and_partial_list_is_applied(db, universe):
    from ashare.quotelist import listing_info
    from ashare.pipeline import enrich_listing_status
    handler, calls = _quote_server(refuse=(), fail_pages=(4,))
    set_default_transport(httpx.MockTransport(handler))
    try:
        info = listing_info()
        assert not info.complete and len(info) == 300 and "3 of 31 pages" in info.note
        st = enrich_listing_status(info)
        assert st["NOT_IN_QUOTE_LIST"] == 0 and st["listing_dates_added"] > 0 and not st["quote_list_complete"]
        handler2, calls2 = _quote_server(refuse=())
        set_default_transport(httpx.MockTransport(handler2))
        info = listing_info()
    finally:
        set_default_transport(None)
    assert info.complete and min(c[2] for c in calls2) == 4        # pages 1-3 kept, not fetched again


def test_diagnose_reports_each_variant(db):
    from ashare.quotelist import diagnose, VARIANTS
    set_default_transport(httpx.MockTransport(lambda r: httpx.Response(502)))
    try:
        r = diagnose()
    finally:
        set_default_transport(None)
    assert len(r["results"]) == len(VARIANTS) and not r["working"] and "HTTP 5xx" in r["verdict"]
    handler, _ = _quote_server()
    set_default_transport(httpx.MockTransport(handler))
    try:
        r = diagnose()
    finally:
        set_default_transport(None)
    assert r["working"] == "push2+referer" and not r["results"][0]["ok"]


# --- panels (finding 4) ----------------------------------------------------------------------

def _annual(code, year, pub):
    from ashare.models import SessionLocal, Company, Disclosure
    s = SessionLocal()
    c = s.query(Company).filter_by(security_code=code).one()
    s.add(Disclosure(company_id=c.id, announcement_id=f"a{code}{year}", announcement_date=pub,
                     title_cn=f"{year}年年度报告", kind="annual_report"))
    s.commit()
    s.close()


def test_empty_panel_is_refused_with_reason(universe, tmp_path):
    from typer.testing import CliRunner
    from ashare.cli import app
    from ashare.panel import build_panel, write_panel, EmptyPanel
    r = build_panel(None, unit="quarter", start="2024-01-01", end="2024-12-31")
    assert r["rows"] == []
    with pytest.raises(EmptyPanel) as e:
        write_panel(r, str(tmp_path / "p"))
    assert "no listing date" in str(e.value) and "diagnose-quote-list" in str(e.value)
    res = CliRunner().invoke(app, ["build-panel", "--unit", "quarter", "--start", "2024-01-01", "--end",
                                   "2024-12-31", "--out", str(tmp_path / "q")])
    assert res.exit_code == 1 and "Not written" in res.output and not (tmp_path / "q" / "panel.csv").exists()


def test_yearly_panel_uses_report_evidence_and_marks_it(universe, tmp_path):
    from ashare.panel import build_panel, write_panel
    from ashare.models import SessionLocal, Company
    _annual("600000", 2024, "2025-04-20")
    _annual("600001", 2023, "2024-04-20")
    s = SessionLocal()
    c = s.query(Company).filter_by(security_code="600002").one()
    c.listing_date = "2000-01-04"
    s.commit()
    s.close()
    r = build_panel(None, unit="year", start="2023-01-01", end="2024-12-31")
    got = {(x["code"], x["period"]): x["universe_basis"] for x in r["rows"]}
    assert got == {("600000", "2024-12-31"): "REPORT_EVIDENCE", ("600001", "2023-12-31"): "REPORT_EVIDENCE",
                   ("600002", "2023-12-31"): "LISTING_RECORD", ("600002", "2024-12-31"): "LISTING_RECORD"}
    w = write_panel(r, str(tmp_path / "p"), formats=("csv",))
    assert w["rows"] == 4 and "universe_basis" in (tmp_path / "p" / "panel_codebook.md").read_text(encoding="utf-8")
    only = build_panel(None, unit="year", start="2023-01-01", end="2024-12-31", universe_basis="listing")
    assert {x["code"] for x in only["rows"]} == {"600002"}
    pit = build_panel(None, unit="year", start="2024-01-01", end="2025-12-31", align="pit", pit_day="04-30")
    pit_codes = {(x["code"], x["period"]) for x in pit["rows"] if x["universe_basis"] == "REPORT_EVIDENCE"}
    assert pit_codes == {("600000", "2025-04-30"), ("600001", "2024-04-30")}  # published by the cut-off only


# --- PDF reader messages (findings 1 and 5) --------------------------------------------------

def test_pdf_warnings_become_one_line_with_details(tmp_path, monkeypatch, capsys):
    import logging
    from ashare import pdfwarnings
    monkeypatch.setenv("ASHARE_LOG_DIR", str(tmp_path / "logs"))
    pdfwarnings.install()
    log = logging.getLogger("pypdf._cmap")
    for doc, n in (("a.pdf", 300), ("b.pdf", 5)):
        pdfwarnings.set_document(doc)
        for _ in range(n):
            log.warning("fontTools is required to fully parse the encoding of a CFF Type1 font in font dictionary "
                        "{'/Encoding': '/WinAnsiEncoding', '/BaseFont': '/X+HelveticaNeueLTPro-Lt'} ...")
    pdfwarnings.set_document("c.pdf")
    log.warning("fontTools is required ... {'/Encoding': IndirectObject(135, 0, 1)}")
    logging.getLogger("pypdf._reader").warning("Ignoring wrong pointing object 12 0 (offset 0)")
    lines = []
    pdfwarnings.finish("extract-financials", lines.append)
    assert len(lines) == 1 and "305 font notices for fonts with a standard encoding" in lines[0]
    assert "in 2 documents" in lines[0] and "1 font notices for fonts without a standard encoding" in lines[0]
    details = next((tmp_path / "logs").glob("pdf_warnings_*.txt")).read_text(encoding="utf-8")
    assert details.index("c.pdf") < details.index("a.pdf")                 # documents to check come first
    assert "fontTools" not in capsys.readouterr().err                     # nothing printed per message


def _cff_pdf(custom_builtin: bool, encoding: str | None):
    """A one-page PDF whose text is set in an embedded CFF (Type1C) font with no ToUnicode map."""
    import io
    fb_mod = pytest.importorskip("fontTools.fontBuilder")
    from fontTools.pens.t2CharStringPen import T2CharStringPen
    glyphs = [".notdef", "space", "zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine",
              "comma", "period"]
    fb = fb_mod.FontBuilder(1000, isTTF=False)
    fb.setupGlyphOrder(glyphs)
    fb.setupCharacterMap({0x20: "space", 0x2C: "comma", 0x2E: "period", **{0x30 + i: glyphs[2 + i] for i in range(10)}})
    cs = {}
    for g in glyphs:
        pen = T2CharStringPen(500, None)
        pen.moveTo((50, 0)); pen.lineTo((450, 0)); pen.lineTo((450, 700)); pen.closePath()
        cs[g] = pen.getCharString()
    fb.setupCFF("HelveticaNeueLTPro-Lt", {}, cs, {})
    fb.setupHorizontalMetrics({g: (500, 50) for g in glyphs})
    fb.setupHorizontalHeader(ascent=800, descent=-200)
    fb.setupNameTable({"familyName": "T", "styleName": "R"}); fb.setupOS2(); fb.setupPost()
    cff = fb.font["CFF "].cff
    if custom_builtin:
        enc = [".notdef"] * 256
        for i in range(10):
            enc[0x41 + i] = glyphs[2 + i]
        cff[cff.fontNames[0]].Encoding = enc
    buf = io.BytesIO(); cff.compile(buf, fb.font); font = buf.getvalue()
    text = bytes(0x41 + int(ch) if custom_builtin and ch.isdigit() else ord(ch) for ch in "1,234,567.89")
    enc_entry = f" /Encoding /{encoding}".encode() if encoding else b""
    objs = [b"<< /Subtype /Type1C /Length %d >>\nstream\n" % len(font) + font + b"\nendstream",
            b"<< /Type /FontDescriptor /FontName /HelveticaNeueLTPro-Lt /Flags 32 /FontBBox [0 -200 1000 800] "
            b"/ItalicAngle 0 /Ascent 800 /Descent -200 /CapHeight 700 /StemV 80 /FontFile3 1 0 R >>",
            b"<< /Type /Font /Subtype /Type1 /BaseFont /HelveticaNeueLTPro-Lt /FirstChar 32 /LastChar 183 /Widths ["
            + b" ".join([b"500"] * 152) + b"]" + enc_entry + b" /FontDescriptor 2 0 R >>"]
    content = b"BT /F1 12 Tf 72 720 Td (" + text + b") Tj ET"
    objs += [b"<< /Length %d >>\nstream\n" % len(content) + content + b"\nendstream",
             b"<< /Type /Page /Parent 6 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 3 0 R >> >> "
             b"/Contents 4 0 R >>", b"<< /Type /Pages /Kids [5 0 R] /Count 1 >>", b"<< /Type /Catalog /Pages 6 0 R >>"]
    out = io.BytesIO(); out.write(b"%PDF-1.4\n"); offs = []
    for i, o in enumerate(objs, 1):
        offs.append(out.tell()); out.write(b"%d 0 obj\n" % i + o + b"\nendobj\n")
    x = out.tell()
    out.write(b"xref\n0 8\n0000000000 65535 f \n" + b"".join(b"%010d 00000 n \n" % o for o in offs))
    out.write(b"trailer\n<< /Size 8 /Root 7 0 R >>\nstartxref\n%d\n%%%%EOF\n" % x)
    return out.getvalue()


def test_font_check_figures_survive_without_fonttools(monkeypatch):
    """Finding 1: with a declared standard encoding (2,408 of the 2,428 live notices), pypdf without
    fontTools extracts the figures correctly; only a font with its own non-standard encoding and no
    declared encoding loses them, and those notices are counted separately."""
    import io
    import pypdf._font
    from pypdf import PdfReader
    monkeypatch.setattr(pypdf._font, "HAS_FONTTOOLS", False)
    text = PdfReader(io.BytesIO(_cff_pdf(False, "WinAnsiEncoding"))).pages[0].extract_text().strip()
    assert text == "1,234,567.89"
    lost = PdfReader(io.BytesIO(_cff_pdf(True, None))).pages[0].extract_text().strip()
    assert lost != "1,234,567.89"


def test_gui_reports_refusals_as_failures(universe, tmp_path, monkeypatch):
    """typer.Exit(1) returns its code in non-standalone mode; the desktop app must see it as a failure."""
    pytest.importorskip("tkinter")
    from ashare.gui import run_command
    monkeypatch.chdir(tmp_path)
    code, out = run_command(["build-panel", "--unit", "quarter", "--start", "2025-01-01", "--end", "2025-12-31"])
    assert code == 1 and "Not written" in out
    code, out = run_command(["universe-stats"])
    assert code == 0
