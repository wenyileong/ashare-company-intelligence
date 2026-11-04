"""v2.1.2: fixes from the v2.1 and v2.1.1 live runs (findings 118 to 131), the scrollable side panel, the Files
page and the paper (docs/plan_v2.1.2.md)."""
import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from helpers import make_pdf, add_disclosure


# --- 1. the missing console in the reading processes (finding 124) ---------------------------------------------------

def test_a_worker_without_a_console_reads_every_document(tmp_path):
    from ashare.parallel import imap
    jobs = [{"id": i, "path": str(tmp_path / "none.pdf"), "group": i % 3} for i in range(30)]
    got = list(imap("parallel_helpers:heartbeat_job", jobs, n_workers=2))
    assert len(got) == 30 and not [r for r in got if r.get("error")]
    assert all(r["result"] == 30 for r in got)          # each job ran its 30 heartbeats


def test_the_worker_initialiser_replaces_missing_streams(monkeypatch):
    from ashare import parallel, http
    monkeypatch.setattr(sys, "stdout", None)
    monkeypatch.setattr(sys, "stderr", None)
    monkeypatch.setitem(http._READ, "quiet", False)
    parallel._worker_init()
    try:
        assert sys.stdout is not None and sys.stderr is not None and http._READ["quiet"] is True
        sys.stdout.write("nothing\n")
    finally:
        sys.stdout.close()
        sys.stderr.close()


def test_the_heartbeat_without_a_console_does_nothing(monkeypatch):
    from ashare import http
    monkeypatch.setattr(sys, "stdout", None)
    monkeypatch.setitem(http._READ, "quiet", False)
    http.reset_heartbeat()
    for _ in range(60):
        http.document_heartbeat()                         # v2.1.1 raised AttributeError on the 25th


# --- 2. and 3. downloads: batches, the catalogue's download step, progress and estimates (119 to 121) ---------------

def _adapter():
    def get(url):
        return SimpleNamespace(content=b"%PDF-1.4 " + url.encode(), headers={"content-type": "application/pdf"})
    return SimpleNamespace(http=SimpleNamespace(get=get), close=lambda: None)


def test_downloads_take_any_number_of_ids(company, tmp_path):
    from ashare.disclosure_pipeline import download_pending
    d = add_disclosure(company, "2025年年度报告", "2026-03-30", None, ann_id="AR25")
    lines = []
    r = download_pending([d.id] + list(range(10_000_000, 10_040_000)), progress=lines.append, adapter=_adapter())
    assert r == {"downloaded": 1, "download_failed": 0}
    assert any("1 of 1 documents" in x and "s each" in x for x in lines)          # progress as in extraction


def test_the_estimate_uses_the_rate_of_the_last_download(company, tmp_path):
    # v2.2 (finding 135): rates are kept by kind, and only from runs of 25 documents or more (test_v22 covers it);
    # this test now checks the v2.1.2 behaviour that remains: a measured rate is used, a damaged file is ignored
    from ashare import disclosure_pipeline as dp
    for i in range(25):
        add_disclosure(company, f"{2000 + i}年年度报告", f"{2001 + i}-03-30", None, ann_id=f"A{i}")
    dp.download_pending(None, ("annual_report",), adapter=_adapter())
    rates = json.loads(dp._rates_file().read_text(encoding="utf-8"))
    assert "annual_report" in rates["kinds"]
    rows = [SimpleNamespace(kind="annual_report")] * 3600
    rates["kinds"]["annual_report"]["seconds"] = 6.0
    dp._rates_file().write_text(json.dumps(rates), encoding="utf-8")
    est = dp.download_estimate(rows)
    assert est["approx_hours"] == 6.0 and est["measured"] is True
    dp._rates_file().write_text("{damaged", encoding="utf-8")
    assert dp.download_estimate(rows)["approx_hours"] == 5.0                          # the default, 5 s


from test_v203 import CNInfo, make_items, universe  # noqa: E402,F401  (the mock CNINFO and its universe)


def _report_items(day, n):
    items = make_items(day, n)
    for i, it in enumerate(items):
        it["announcementTitle"] = f"2025年年度报告{i}" if i % 2 == 0 else f"公告{i}"
    return items


def _run(server, *args, **kw):
    import httpx
    from ashare.http import set_default_transport
    from ashare.market_catalogue import catalogue
    set_default_transport(httpx.MockTransport(server))
    try:
        return catalogue(*args, **kw)
    finally:
        set_default_transport(None)


def test_a_rerun_downloads_what_an_earlier_run_left(universe, monkeypatch):
    from ashare import disclosure_pipeline
    days = {"2026-04-23": _report_items("2026-04-23", 20), "2026-04-24": _report_items("2026-04-24", 20)}
    server = CNInfo(days)
    _run(server, "2026-04-23", "2026-04-24", "all")                       # catalogued, not downloaded
    seen = []
    monkeypatch.setattr(disclosure_pipeline, "download_pending",
                        lambda ids, progress=None, adapter=None: seen.append(list(ids)) or
                        {"downloaded": len(ids), "download_failed": 0})
    r = _run(server, "2026-04-23", "2026-04-24", "all", download_documents=True)
    assert r["days_skipped"] == 2                                         # nothing fetched again
    assert len(seen) == 1 and len(seen[0]) == 20                          # the 20 wanted reports, from the database


def test_a_failed_download_step_keeps_the_finished_catalogue(universe, monkeypatch):
    from ashare import disclosure_pipeline
    from ashare.market_catalogue import day_status

    def boom(ids, progress=None, adapter=None):
        raise RuntimeError("too many SQL variables")
    monkeypatch.setattr(disclosure_pipeline, "download_pending", boom)
    lines = []
    r = _run(CNInfo({"2026-04-23": _report_items("2026-04-23", 10)}), "2026-04-23", "2026-04-23", "all",
             download_documents=True, progress=lines.append)
    assert r["days_done"] == 1 and "too many SQL variables" in r["download_error"]
    assert {x["status"] for x in day_status("all")} == {"DONE"}
    assert any("download-documents" in x for x in lines)


def test_refresh_fetches_only_the_last_days_again(universe):
    days = {f"2026-04-{d:02d}": make_items(f"2026-04-{d:02d}", 5) for d in range(20, 25)}
    server = CNInfo(days)
    _run(server, "2026-04-20", "2026-04-24", "all")
    lines = []
    _run(server, "2026-04-20", "2026-04-24", "all", refresh=True, refresh_days=2, progress=lines.append)
    assert any("2 day(s) to fetch" in x and "3 already finished" in x for x in lines)
    lines.clear()
    _run(server, "2026-04-20", "2026-04-24", "all", refresh=True, progress=lines.append)
    assert any("5 day(s) to fetch" in x for x in lines)                   # without a window: every day, as before


# --- 4. financial extraction leaves out documents without figures (finding 126) ----------------------------------

def test_kind_all_leaves_out_english_versions_and_sustainability_reports(company, tmp_path):
    from ashare.financials import extract_financials
    lines = ["2025年年度报告", "单位：元", "资产总计 1,000.00 900.00", "负债合计 400.00 300.00",
             "所有者权益合计 600.00 600.00"]
    add_disclosure(company, "2025年年度报告", "2026-03-30", make_pdf(tmp_path / "a.pdf", lines), ann_id="A")
    add_disclosure(company, "2025年年度报告（英文版）", "2026-03-30", make_pdf(tmp_path / "e.pdf", lines), ann_id="E")
    add_disclosure(company, "2025 Annual Report", "2026-03-30", make_pdf(tmp_path / "e2.pdf", lines), ann_id="E2")
    add_disclosure(company, "2025年度可持续发展报告", "2026-04-20", make_pdf(tmp_path / "s.pdf", lines), ann_id="S")
    r = extract_financials("600519", kind="all")
    assert r["not_financial"] == 3 and r["to_read"] == 1 and r["documents"] == 1
    assert "not_financial" not in extract_financials("600519", kind="reports", again=True)


# --- 5. the scanned-page check (finding 125) -----------------------------------------------------------------------

def _scanned(path):
    from reportlab.pdfgen import canvas
    c = canvas.Canvas(str(path))
    c.rect(50, 50, 400, 600, fill=1)
    c.showPage()
    c.save()
    return path


def test_the_scanned_page_check_classifies_as_before(company, tmp_path):
    from ashare.layout import scan_documents, text_layer
    add_disclosure(company, "2025年年度报告", "2026-03-30", _scanned(tmp_path / "s.pdf"), ann_id="S")
    txt = make_pdf(tmp_path / "t.pdf", ["2025年年度报告第一页的文字足够长，超过二十个字符。"] * 3)
    add_disclosure(company, "2024年年度报告", "2025-03-30", txt, ann_id="T")
    said = []
    r = scan_documents("600519", progress=said.append)
    assert r["NONE"] == 1 and r["FULL"] == 1 and r["checked"] == 2
    assert text_layer(txt)["status"] == "FULL"                            # the slow reader agrees
    assert any("2 of 2 documents" in x for x in said)


def test_a_stopped_scan_keeps_what_it_checked(company, tmp_path, monkeypatch):
    from ashare import layout
    from ashare.http import Cancelled
    from ashare.models import SessionLocal, Disclosure
    for i in range(3):
        add_disclosure(company, f"{2020 + i}年年度报告", f"{2021 + i}-03-30", _scanned(tmp_path / f"s{i}.pdf"),
                       ann_id=f"S{i}")
    real, calls = layout.scan_job, []

    def stop_on_third(job, reader):
        calls.append(job["id"])
        if len(calls) == 3:
            raise Cancelled("stopped by the user")
        return real(job, reader)
    monkeypatch.setattr(layout, "scan_job", stop_on_third)
    monkeypatch.setenv("ASHARE_WORKERS", "1")
    with pytest.raises(Cancelled):
        layout.scan_documents("600519")
    s = SessionLocal()
    try:
        assert sum(1 for d in s.query(Disclosure) if d.text_layer == "NONE") == 2   # v2.1.1 kept none
    finally:
        s.close()
    monkeypatch.setattr(layout, "scan_job", real)
    r = layout.scan_documents("600519")
    assert r["to_check"] == 1 and r["NONE"] == 3


# --- 6. a leading digit dropped from a balance-sheet total (finding 129) ------------------------------------------

def _bs(**values):
    return [{"metric": m, "value": v, "period": "2026-03-31", "period_type": "Q1", "method": "PDF_STATEMENT_TABLE",
             "consolidation_scope": None, "confidence": 0.7, "extraction_note": None, "raw_value": f"{v:,.2f}"}
            for m, v in values.items()]


def _by(facts):
    return {f["metric"]: f for f in facts}


def test_equity_short_by_twenty_billion_is_restored_when_its_parts_confirm_it():
    from ashare.financials import repair_leading_digits
    f = _by(repair_leading_digits(_bs(total_assets=58_318_402_807.42, total_liabilities=35_105_649_903.71,
                                      equity=3_212_752_903.71, equity_parent=22_000_000_000.00,
                                      minority_interests=1_212_752_903.71)))
    # the first row of the author's v2.1 run: out by exactly 20 billion
    assert round(f["equity"]["value"], 2) == 23_212_752_903.71 and f["equity"]["raw_value"] == "3,212,752,903.71"
    note = json.loads(f["equity"]["extraction_note"])
    assert note["repair"] == "LEADING_DIGIT_RESTORED" and note["read_value"] == 3_212_752_903.71
    assert f["equity"]["confidence"] < 0.7 and f["total_liabilities"]["value"] == 35_105_649_903.71


def test_nothing_is_restored_without_a_confirming_identity():
    from ashare.financials import repair_leading_digits
    facts = _bs(total_assets=58_318_402_807.42, total_liabilities=35_105_649_903.71, equity=3_212_752_903.71)
    assert _by(repair_leading_digits(facts))["equity"]["value"] == 3_212_752_903.71
    # nor when the difference is not a single digit times a power of ten
    facts = _bs(total_assets=22_350_904_261.25, total_liabilities=13_575_608_444.29, equity=1_457_450_353.97,
                equity_parent=8_775_295_816.96, minority_interests=0.0)
    assert _by(repair_leading_digits(facts))["equity"]["value"] == 1_457_450_353.97


def test_liabilities_are_restored_when_current_and_non_current_confirm_them():
    from ashare.financials import repair_leading_digits
    f = _by(repair_leading_digits(_bs(total_assets=50_000_000_000.0, total_liabilities=5_000_000_000.0,
                                      equity=25_000_000_000.0, total_current_liabilities=20_000_000_000.0,
                                      total_non_current_liabilities=5_000_000_000.0,
                                      equity_parent=24_000_000_000.0, minority_interests=1_000_000_000.0)))
    assert f["total_liabilities"]["value"] == 25_000_000_000.0 and f["equity"]["value"] == 25_000_000_000.0


def test_a_balance_sheet_that_balances_is_untouched():
    from ashare.financials import repair_leading_digits
    facts = _bs(total_assets=100.0e9, total_liabilities=60.0e9, equity=40.0e9, equity_parent=1.0e9,
                minority_interests=0.0)
    assert [f["value"] for f in repair_leading_digits(facts)] == [100.0e9, 60.0e9, 40.0e9, 1.0e9, 0.0]


def test_the_balance_check_writes_a_summary_and_a_csv(tmp_path):
    from ashare.financials import balance_check_summary, write_balance_check
    errors = [{"company_id": 1, "reporting_period": "2026-03-31", "disclosure_id": 31, "assets": 58318402807.42,
               "liabilities": 35105649903.71, "equity": 3212752903.71, "residual": 20000000000.0, "tolerance": 1.0},
              {"company_id": 2, "reporting_period": "2025-12-31", "disclosure_id": 57, "assets": 22350904261.25,
               "liabilities": 28211299370.27, "equity": 1457450353.97, "residual": 7317845462.99, "tolerance": 1.0}]
    assert balance_check_summary(errors) == {"round_difference": 1, "other_difference": 1}
    p = write_balance_check(errors, tmp_path / "b.csv")
    text = p.read_text(encoding="utf-8-sig")
    assert "single digit x power of ten" in text and text.count("\n") == 3


def test_inspect_tables_shows_the_numbers_of_each_balance_sheet_line(company, tmp_path):
    from ashare.inspect_tables import inspect_table
    lines = ["2025年年度报告", "合并资产负债表", "单位：元", "资产总计 58,318,402,807.42 50,000,000,000.00",
             "负债合计 35,105,649,903.71 30,000,000,000.00", "所有者权益合计 1 3,212,752,903.71 20,000,000,000.00"]
    d = add_disclosure(company, "2025年年度报告", "2026-03-30", make_pdf(tmp_path / "bs.pdf", lines), ann_id="B")
    text = inspect_table(d.id, "balance_sheet", tmp_path / "out.txt").read_text(encoding="utf-8")
    assert "Table: balance_sheet" in text and "numbers: 1 | 3,212,752,903.71" in text


# --- 7. controller names (finding 128) -----------------------------------------------------------------------------

WRAPPED_SASAC = """3、公司实际控制人及其一致行动人
实际控制人性质：中央国资管理机构
实际控制人类型：法人
实际控制人名称 法定代表 成立日期 组织机构代码 主要经营业务
人/单位负
责人
国务院国有资产监督
张玉卓 2003年03月16日 11100000000013623G 国有资产监督管理
管理委员会
实际控制人报告期内变更"""

WRAPPED_LOCAL = """2、控股股东情况
控股股东名称 法定代表人/单位负责人 成立日期 组织机构代码 主要经营业务
深圳市投资控股有限公司 何建锋 2004年10月13日 91440300767569153C 投资
3、公司实际控制人及其一致行动人
实际控制人名称 法定代表人/单位负责人 成立日期 组织机构代码 主要经营业务
深圳市人民政府国有
杨军 2004年06月01日 11440300K317280672 国资监管
资产监督管理委员会
实际控制人报告期内变更"""

WRAPPED_HOLDER = """2、控股股东情况
控股股东名称 法定代表人/单位负责人 成立日期 组织机构代码 主要经营业务
湖南省人民政府国有
资产监督管理委员会 张三 2004年 X 国资监管
3、公司实际控制人及其一致行动人
实际控制人名称 法定代表人/单位负责人 成立日期 组织机构代码 主要经营业务
湖南省人民政府国有
资产监督管理委员会 张三 2004年 X 国资监管
实际控制人报告期内变更"""


@pytest.mark.parametrize("text,holder,controller", [
    (WRAPPED_SASAC, None, "国务院国有资产监督管理委员会"),
    (WRAPPED_LOCAL, "深圳市投资控股有限公司", "深圳市人民政府国有资产监督管理委员会"),
    (WRAPPED_HOLDER, "湖南省人民政府国有资产监督管理委员会", "湖南省人民政府国有资产监督管理委员会"),
])
def test_names_wrapped_within_their_cell_are_rejoined(text, holder, controller):
    from ashare.control import parse_control_text
    r = parse_control_text([text])
    assert r["controlling_shareholder"] == holder and r["actual_controller"] == controller


def test_two_entities_and_two_persons_stay_two():
    from ashare.control import parse_control_text
    ents = """3、公司实际控制人及其一致行动人
实际控制人名称 法定代表人/单位负责人 成立日期
甲投资有限公司 王一 2001年
乙集团 李二 2002年
实际控制人报告期内变更"""
    assert parse_control_text([ents])["actual_controller"] == "甲投资有限公司、乙集团"
    from test_v208 import SZSE_PERSON
    assert parse_control_text([SZSE_PERSON])["actual_controller"] == "王传福、吕向阳"


def test_forms_of_a_commission_name_are_grouped_as_one():
    from ashare.control import controller_key
    assert controller_key("湖南省国资委") == controller_key("湖南省人民政府国有资产监督管理委员会")
    assert controller_key("国务院国资委") == controller_key("国务院国有资产监督管理委员会")
    assert controller_key("湖南省国资委") != controller_key("湖北省国资委")


def test_the_control_version_is_new():
    from ashare.extractstate import VERSIONS
    assert VERSIONS["control"] not in ("control-1", "control-2")       # v2.2 moved it on to control-4


# --- 8. why a layer is empty (finding 127) -------------------------------------------------------------------------

def test_the_topology_says_why_a_layer_is_empty(company, tmp_path):
    from ashare.viz.snapshot import build_snapshot
    snap = build_snapshot(["600519"], "2021-01-01", "2025-12-31", as_of="2026-11-01")
    notes = {c["layer"]: c["note"] for c in snap["coverage"]}
    assert "No periodic report is catalogued for 600519" in notes["fundamentals"]
    assert "No earnings forecast or flash report is catalogued" in notes["expectations"]
    add_disclosure(company, "2025年年度报告", "2026-03-30", None, ann_id="AR")
    snap = build_snapshot(["600519"], "2021-01-01", "2025-12-31", as_of="2026-11-01")
    notes = {c["layer"]: c["note"] for c in snap["coverage"]}
    assert "No periodic report is downloaded for 600519 (1 catalogued)" in notes["fundamentals"]


def test_guidance_read_outside_the_span_says_so(company, tmp_path):
    from ashare.models import SessionLocal, ExpectationObservation
    from ashare.viz.snapshot import build_snapshot
    d = add_disclosure(company, "2019年年度业绩预告", "2020-01-20", make_pdf(tmp_path / "f.pdf", ["业绩预告"]),
                       ann_id="F")
    s = SessionLocal()
    s.add(ExpectationObservation(company_id=company.id, source_kind="MANAGEMENT_GUIDANCE",
                                 reporting_period="2019-12-31", measure="net_profit_parent", issuer="600519",
                                 published_date="2020-01-20", source="CNINFO", disclosure_id=d.id, low=1.0, high=2.0,
                                 unit="CNY", extraction_method="GUIDANCE_TEXT"))
    s.commit()
    s.close()
    snap = build_snapshot(["600519"], "2021-01-01", "2025-12-31", as_of="2026-11-01")
    note = {c["layer"]: c["note"] for c in snap["coverage"]}["expectations"]
    assert "none of it is for 2021 to 2025" in note


def test_empty_profile_commands_say_why(company):
    from typer.testing import CliRunner
    from ashare.cli import app
    out = CliRunner().invoke(app, ["human-capital", "600519"]).output
    assert "No R&D or workforce data." in out and "No periodic report is catalogued" in out


# --- 9. the ESG title (finding 130) --------------------------------------------------------------------------------

def test_the_chinese_sustainability_report_is_the_title_shown(company):
    from ashare.esg import extract_esg, esg_profile
    add_disclosure(company, "贵州茅台2025年环境、社会及治理（ESG）报告", "2026-03-30", None, ann_id="C")
    add_disclosure(company, "贵州茅台2025年环境、社会及治理（ESG）报告（英文版）", "2026-04-02", None, ann_id="E")
    extract_esg("600519")
    title = esg_profile("600519", year=2025)["reporting"]["sustainability_report_title"]
    assert title == "贵州茅台2025年环境、社会及治理（ESG）报告"


# --- 10. the scrollable side panel (author's request) -------------------------------------------------------------

def test_the_side_panel_scrolls_when_the_window_is_short(tmp_path, monkeypatch):
    tk = pytest.importorskip("tkinter")
    if not os.environ.get("DISPLAY") and os.name != "nt":
        pytest.skip("no display")
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    from ashare import gui
    monkeypatch.setattr(gui.App, "_init_db", lambda self: None)
    gui.save_settings({"data_folder": str(tmp_path / "data"), "language": "en"})
    cwd = os.getcwd()
    try:
        app = gui.App()
    except tk.TclError:
        pytest.skip("no display")
    try:
        app.geometry("1300x1150")
        for _ in range(3):
            app.update()
        if app.side_canvas.winfo_height() < app.side_inner.winfo_reqheight():
            pytest.skip("the screen is too short for the full-height check")
        assert not app.side_scrollbar.winfo_ismapped()
        app.minsize(1, 1)
        app.geometry("1100x420")
        for _ in range(3):
            app.update()
        assert app.side_scrollbar.winfo_ismapped()
        app.show("settings")
        app.update()
        lbl, c = app.nav["settings"], app.side_canvas
        assert c.canvasy(0) <= lbl.winfo_y() and lbl.winfo_y() + lbl.winfo_height() <= c.canvasy(0) + c.winfo_height()
        assert app.side_folder.winfo_ismapped()
        app.switch_language("zh_CN")
        app.update()
        assert app.nav["files"].cget("text") and hasattr(app, "side_canvas")
    finally:
        app.destroy()
        os.chdir(cwd)


# --- 11. the Files page (author's request) -------------------------------------------------------------------------

def _store(company, tmp_path, title, ann, kind_text=b"x"):
    from ashare.config import disclosure_dir
    folder = disclosure_dir() / "600519"
    folder.mkdir(parents=True, exist_ok=True)
    p = folder / f"{abs(hash(title))}.pdf"
    p.write_bytes(b"%PDF " + kind_text + title.encode())
    return add_disclosure(company, title, ann, p, ann_id=title)


def test_files_summary_and_list(company, tmp_path):
    from ashare.files import files_summary, files_list
    _store(company, tmp_path, "2025年年度报告", "2026-03-30")
    _store(company, tmp_path, "2025年第一季度报告", "2025-04-28")
    r = files_summary()
    assert r["documents"] == 2 and {k["kind"] for k in r["by_kind"]} == {"annual_report", "quarterly_report"}
    rows = files_list("600519")
    assert rows[0]["name"].startswith("600519 2025-04-28 2025年第一季度报告") and rows[0]["read_by"] == "-"


def test_an_export_copies_with_readable_names_and_an_index(company, tmp_path):
    from ashare.files import export_files
    d = _store(company, tmp_path, "2025年年度报告", "2026-03-30")
    original = Path(d.local_path).read_bytes()
    r = export_files(tmp_path / "out", "600519")
    assert r["copied"] == 1
    try:                                                     # Wine on a host without a UTF-8 locale cannot
        (tmp_path / "probe 贵州").mkdir()                    # hold Chinese names; Windows can
        copy = tmp_path / "out" / "600519 贵州茅台" / "2025" / "600519 2026-03-30 2025年年度报告.pdf"
    except OSError:
        copy = tmp_path / "out" / "600519" / "2025" / f"600519 2026-03-30 {d.id}.pdf"
    assert copy.read_bytes() == original and Path(d.local_path).read_bytes() == original
    index = (tmp_path / "out" / "index.csv").read_text(encoding="utf-8-sig")
    assert "static.cninfo.com.cn" in index and str(d.id) in index
    assert export_files(tmp_path / "out", "600519")["already_there"] == 1          # a rerun copies nothing


def test_check_finds_unnamed_and_missing_files(company, tmp_path):
    from ashare.config import disclosure_dir
    from ashare.files import check_files
    _store(company, tmp_path, "2025年年度报告", "2026-03-30")
    stray = disclosure_dir() / "600519" / "stray.pdf"
    stray.write_bytes(b"%PDF stray")
    add_disclosure(company, "2024年年度报告", "2025-03-30", tmp_path / "gone.pdf", ann_id="gone")
    _store(company, tmp_path, "2025年年度报告摘要", "2026-03-30")
    r = check_files()
    assert r["unnamed_files"] == 1 and r["missing_files"] == 1 and r["summaries_english"] == 1


def test_tidy_previews_then_applies_and_logs(company, tmp_path, monkeypatch):
    from ashare.files import tidy_files
    from ashare.models import SessionLocal, Disclosure
    monkeypatch.chdir(tmp_path)
    keep = _store(company, tmp_path, "2025年年度报告", "2026-03-30")
    summ = _store(company, tmp_path, "2025年年度报告摘要", "2026-03-30")
    preview = tidy_files("summaries_english")
    assert preview["files"] == 1 and not preview["applied"] and Path(summ.local_path).exists()
    done = tidy_files("summaries_english", apply=True)
    assert done["removed"] == 1 and not Path(summ.local_path).exists() and Path(keep.local_path).exists()
    s = SessionLocal()
    try:
        assert s.get(Disclosure, summ.id).local_path is None and s.get(Disclosure, keep.id).local_path
    finally:
        s.close()
    assert summ.local_path in Path(done["log"]).read_text(encoding="utf-8-sig")
    with pytest.raises(ValueError):
        tidy_files("kind")                                                  # a kind must be named


def test_tidy_keeps_a_file_another_record_still_names(company, tmp_path):
    from ashare.files import tidy_files
    a = _store(company, tmp_path, "2025年年度报告摘要", "2026-03-30")
    add_disclosure(company, "2025年年度报告", "2026-03-31", a.local_path, ann_id="same-file")
    assert tidy_files("summaries_english")["files"] == 0


def test_the_files_page_commands_exist():
    pytest.importorskip("tkinter")
    from typer.main import get_command
    from ashare.cli import app
    from ashare.gui import SECTIONS
    names = set(get_command(app).commands)
    page = next(s for s in SECTIONS if s["id"] == "files")
    assert {a["command"] for a in page["actions"]} <= names


# --- 12. the paper --------------------------------------------------------------------------------------------------

def test_the_paper_is_cited_in_the_readme_and_citation_file():
    root = Path(__file__).resolve().parent.parent
    readme = (root / "README.md").read_text(encoding="utf-8")
    assert "## The paper this software accompanies" in readme and "https://ssrn.com/abstract=7309399" in readme
    assert "10.2139/ssrn.7309399" in readme and "illustrated, rather than tested" in readme
    cff = (root / "CITATION.cff").read_text(encoding="utf-8")
    assert "references:" in cff and 'doi: "10.2139/ssrn.7309399"' in cff and "date-published: 2026-06-20" in cff


def test_a_whole_name_without_a_usual_ending_is_not_joined_to_the_next():
    from ashare.control import _repair_entity_names
    assert _repair_entity_names(["中国移动", "杨杰", "甲公司"], True) == ["中国移动", "甲公司"]
    assert _repair_entity_names(["国务院国有资产监督", "张玉卓", "管理委员会"], True) == ["国务院国有资产监督管理委员会"]


def test_cached_section_indexes_are_not_taken_for_stray_files(company, tmp_path):
    from ashare.config import disclosure_dir
    from ashare.files import check_files
    cache = disclosure_dir() / ".section_index"
    cache.mkdir(parents=True, exist_ok=True)
    (cache / "abc.json").write_text("{}", encoding="utf-8")
    assert check_files()["unnamed_files"] == 0
