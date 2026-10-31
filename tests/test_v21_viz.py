"""v2.1 workstream E: expectations (E2), the graph snapshot (V0, E1), the layered chart (V1, E3) and the offline
viewer adapted from the NVF Topology Tester v0.1. Acceptance as in docs/plan_v2.0.8_and_visualisation.md, 7.7."""
import csv
import json

import pytest

KEY = b"k" * 32


def _set(code, **kw):
    from ashare.models import SessionLocal, Company
    s = SessionLocal()
    try:
        c = s.query(Company).filter_by(security_code=code).one()
        for k, v in kw.items():
            setattr(c, k, v)
        s.commit()
    finally:
        s.close()


def _report(tmp_path, seed, year_shift=0):
    import random
    from ashare.corpus import _annual_report, _write_pdf
    title, pages, truth = _annual_report(random.Random(seed), 1)
    pdf = tmp_path / f"ar{seed}.pdf"
    _write_pdf(pdf, pages)
    return title, pdf, truth


@pytest.fixture
def nvf(company, tmp_path, monkeypatch):
    """600519 with two years of reports read by every extractor, guidance, prices, an event and a classification;
    000001 with nothing (gaps)."""
    from helpers import add_disclosure, make_pdf
    from ashare.storage import upsert_ashares
    from ashare.models import SessionLocal, MarketBar, RegulatoryEvent, IndustryClassification, Company
    monkeypatch.setenv("ASHARE_WORKERS", "1")
    upsert_ashares([{"code": "000001", "exchange": "SZSE", "legal_name_cn": "平安银行股份有限公司",
                     "short_name_cn": "平安银行", "org_id": "z"}])
    _set("600519", listing_date="2001-08-27", status="LISTED")
    titles = {}
    for seed, ann in ((3, "2023-03-30"), (7, "2024-03-29")):
        title, pdf, _ = _report(tmp_path, seed)
        d = add_disclosure(company, title, ann, pdf, ann_id=f"AR{seed}")
        titles[seed] = (title, d.id)
    flash = make_pdf(tmp_path / "flash.pdf", ["贵州茅台2023年度业绩快报", "单位：万元",
                                              "项目 本报告期 上年同期 增减变动幅度（%）",
                                              "营业总收入 150,000.00 120,000.00 25.00",
                                              "归属于上市公司股东的净利润 60,000.00 50,000.00 20.00"])
    add_disclosure(company, "2023年度业绩快报", "2024-01-20", flash, ann_id="F23")
    fc = make_pdf(tmp_path / "fc.pdf", ["2023年年度业绩预告", "项目 本报告期 上年同期",
                                        "归属于上市公司股东的净利润 盈利：55,000万元–65,000万元 盈利：50,000万元",
                                        "比上年同期增长：10%–30%"])
    add_disclosure(company, "2023年年度业绩预告", "2024-01-10", fc, ann_id="G23")
    from ashare import financials, control, human_capital, expectations
    financials.extract_financials("600519")
    control.extract_top_holders("600519")
    control.extract_control("600519")
    human_capital.extract_human_capital("600519")
    expectations.read_guidance("600519", download=False)
    s = SessionLocal()
    try:
        cid = s.query(Company).filter_by(security_code="600519").one().id
        for day, close in (("2022-12-30", 1700.0), ("2023-12-29", 1750.0), ("2024-02-01", 1600.0)):
            s.add(MarketBar(company_id=cid, trade_date=day, close=close, adjustment="none", source="EASTMONEY"))
        s.add(MarketBar(company_id=cid, trade_date="2023-12-29", close=9.0, adjustment="none", source="CSV_IMPORT"))
        d_id = titles[7][1]
        s.add(RegulatoryEvent(company_id=cid, disclosure_id=d_id, event_id="E1", event_type="REGULATORY_LETTER",
                              legal_classification="EXCHANGE_SUPERVISORY_MEASURE", authority="SSE",
                              announcement_date="2023-05-10", event_date="2023-05-09",
                              title_cn="关于收到上海证券交易所监管工作函的公告", extraction_method="TITLE",
                              source="CNINFO"))
        s.add(IndustryClassification(company_id=cid, scheme="CSRC_2012", effective_date="2023-01-01",
                                     level1_code="C", level1_name="制造业", level2_code="C15",
                                     level2_name="酒、饮料和精制茶制造业", source="CSRC"))
        s.commit()
    finally:
        s.close()
    return titles


# --- E2. Expectations ----------------------------------------------------------------------------------------------

def test_forecast_ranges_in_both_exchanges_wording():
    from ashare.expectations import parse_forecast_text
    table = ["项目 本报告期 上年同期\n归属于上市公司股东的净利润 盈利：5,000万元–6,000万元 盈利：4,000万元\n"
             "比上年同期增长：25.00%–50.00%\n扣除非经常性损益后的净利润 盈利：4,500万元–5,500万元 盈利：3,800万元\n"
             "比上年同期下降：18.42%–44.74%\n基本每股收益 盈利：0.50元/股–0.60元/股 盈利：0.40元/股"]
    got = {r["measure"]: r for r in parse_forecast_text(table)}
    assert (got["net_profit_parent"]["low"], got["net_profit_parent"]["high"]) == (5e7, 6e7)
    assert got["net_profit_parent"]["prior_value"] == 4e7
    assert (got["net_profit_parent"]["change_low_pct"], got["net_profit_parent"]["change_high_pct"]) == (25.0, 50.0)
    assert (got["net_profit_parent_ex_nonrecurring"]["change_low_pct"],
            got["net_profit_parent_ex_nonrecurring"]["change_high_pct"]) == (-44.74, -18.42)
    assert got["eps"]["unit"] == "CNY_PER_SHARE" and got["eps"]["high"] == 0.6
    sse = ["1．经财务部门初步测算，预计2025年年度实现归属于母公司所有者的净利润为-8,000万元到-6,000万元。\n"
           "二、上年同期业绩情况\n（一）归属于母公司所有者的净利润：1,200万元。"]
    got = {r["measure"]: r for r in parse_forecast_text(sse)}
    assert (got["net_profit_parent"]["low"], got["net_profit_parent"]["high"]) == (-8e7, -6e7)
    loss = ["预计2025年半年度归属于上市公司股东的净利润亏损：3,000万元至5,000万元。"]
    assert [(r["low"], r["high"]) for r in parse_forecast_text(loss)] == [(-5e7, -3e7)]
    assert parse_forecast_text(["归属于上市公司股东的净利润将有所增长"]) == []        # no figure: nothing guessed


def test_flash_report_figures_with_their_unit():
    from ashare.expectations import parse_guidance
    pages = ["单位：万元\n项目 本报告期 上年同期 增减变动幅度（%）\n营业总收入 123,456.78 100,000.00 23.46\n"
             "基本每股收益（元） 0.50 0.40 25.00"]
    got = {r["measure"]: r for r in parse_guidance(pages, "2025年度业绩快报")}
    assert got["revenue"]["low"] == got["revenue"]["high"] == 1_234_567_800.0
    assert got["revenue"]["prior_value"] == 1_000_000_000.0 and got["revenue"]["change_low_pct"] == 23.46
    assert got["eps"]["low"] == 0.5
    assert parse_guidance(["项目 本报告期 上年同期\n营业总收入 123.00 100.00"], "2025年度业绩快报") == []  # no unit


def test_guidance_read_resumes_and_downloads_announcements_first(company, tmp_path, monkeypatch):
    from helpers import add_disclosure, make_pdf
    from ashare import expectations, disclosure_pipeline
    from ashare.models import SessionLocal, ExpectationObservation, Disclosure
    monkeypatch.setenv("ASHARE_WORKERS", "1")
    pdf = make_pdf(tmp_path / "f.pdf", ["2025年年度业绩预告",
                                        "归属于上市公司股东的净利润 盈利：1,000万元–2,000万元 盈利：800万元"])
    add_disclosure(company, "2025年年度业绩预告", "2026-01-15", None, ann_id="G1")
    asked = []

    def fake_download(ids, kinds, progress=None):
        asked.append((list(ids), kinds))
        s = SessionLocal()
        try:
            for d in s.query(Disclosure).filter(Disclosure.id.in_(ids)):
                d.local_path = str(pdf)
            s.commit()
        finally:
            s.close()
        return {"downloaded": len(ids)}
    monkeypatch.setattr(disclosure_pipeline, "download_pending", fake_download)
    r = expectations.read_guidance("600519")
    assert asked and asked[0][1] == ("earnings_forecast_or_flash",)
    assert r["inserted"] == 1 and r["documents"] == 1
    s = SessionLocal()
    try:
        row = s.query(ExpectationObservation).one()
        assert (row.source_kind, row.reporting_period, row.low, row.high, row.document_kind) == \
            ("MANAGEMENT_GUIDANCE", "2025-12-31", 1e7, 2e7, "FORECAST")
        assert row.source_page == 1 and row.published_date == "2026-01-15"
    finally:
        s.close()
    assert expectations.read_guidance("600519")["already_read"] == 1


def test_analyst_forecasts_need_a_licence_and_never_mix_with_guidance(company, tmp_path):
    from ashare.expectations import import_analyst_forecasts_csv, expectation_series
    from ashare.licences import row_licence
    p = tmp_path / "af.csv"
    p.write_text("code,period,measure,low,high,issuer,published_date\n"
                 "600519,2025-12-31,net_profit_parent,9e10,9.5e10,某证券,2025-11-01\n"
                 "999999,2025-12-31,net_profit_parent,1,2,x,2025-11-01\n", encoding="utf-8")
    with pytest.raises(ValueError):
        import_analyst_forecasts_csv(str(p), licence="")
    r = import_analyst_forecasts_csv(str(p), licence="Wind terminal licence, research use")
    assert r["inserted"] == 1 and r["skipped"][0]["reason"].startswith("unknown code")
    a = expectation_series("600519", "net_profit_parent", "ANALYST_FORECAST")
    assert a[0]["licence"].startswith("Wind") and a[0]["low"] == 9e10
    assert expectation_series("600519", "net_profit_parent", "MANAGEMENT_GUIDANCE") == []
    with pytest.raises(ValueError):
        expectation_series("600519", "net_profit_parent", "BOTH")
    assert row_licence("expectation_observations", {"source": "ANALYST_CSV"}) == "LICENSED"


# --- E1. The snapshot (V0) -----------------------------------------------------------------------------------------

def test_snapshot_layers_coverage_and_documented_links(nvf):
    from ashare.viz.snapshot import build_snapshot
    snap = build_snapshot(["600519", "000001"], "2022-01-01", "2023-12-31", as_of="2024-06-30", key=KEY)
    kinds = {n["kind"] for n in snap["nodes"]}
    assert {"company", "observation", "shareholder", "controller", "sector", "regulatory_event"} <= kinds
    layers = {n["layer"] for n in snap["nodes"] if n["kind"] == "observation"}
    assert {"fundamentals", "capability", "expectations", "valuation"} <= layers
    cov = {c["layer"]: c for c in snap["coverage"]}
    assert cov["fundamentals"]["status"] == "PARTIAL" and cov["fundamentals"]["companies_covered"] == 1
    assert all(e["evidence_status"] == "DOCUMENTED_FACT" for e in snap["edges"])
    by_id = {n["id"]: n for n in snap["nodes"]}
    for e in snap["edges"]:
        b = e["basis"]
        if b["kind"] in ("page", "xbrl"):
            assert b["disclosure_id"] and (b["page"] is not None or b["kind"] == "xbrl"), e
        assert e["source"] in by_id and e["target"] in by_id
    # the guidance is the latest statement for the year: the flash report (published after the forecast)
    exp = [n for n in snap["nodes"] if n["layer"] == "expectations" and n.get("metric") == "net_profit_parent"]
    assert len(exp) == 1 and exp[0]["low"] == exp[0]["high"] == 6e8 and exp[0]["provenance"]["revisions"] == 2
    assert "proxy" in exp[0]["description"]
    # prices: unadjusted, licensed imports excluded as in releases
    close = by_id["obs:600519:close:2023-12-31"]
    assert close["value"] == 1750.0 and close["provenance"]["source"] == "EASTMONEY"
    assert snap["series"][0]["metric"] == "revenue" and snap["series"][0]["points"]


def test_snapshot_is_point_in_time(nvf):
    from ashare.viz.snapshot import build_snapshot, validate_snapshot
    early = build_snapshot(["600519"], "2022-01-01", "2023-12-31", as_of="2023-06-30", key=KEY)
    late = build_snapshot(["600519"], "2022-01-01", "2023-12-31", as_of="2024-06-30", key=KEY)
    pub = [n["dates"].get("published_date") for n in early["nodes"] if n["dates"].get("published_date")]
    assert pub and max(pub) <= "2023-06-30"
    assert not any(n["layer"] == "expectations" and n["kind"] == "observation" for n in early["nodes"])
    assert len(late["nodes"]) > len(early["nodes"])
    bad = json.loads(json.dumps(early))
    bad["nodes"][0]["dates"]["published_date"] = "2030-01-01"
    assert any("after 2023-06-30" in p for p in validate_snapshot(bad))


def test_snapshot_is_deterministic(nvf, tmp_path):
    from ashare.viz.snapshot import build_snapshot, dumps
    from ashare.viz.export import export_snapshot
    a = dumps(build_snapshot(["600519", "000001"], "2022-01-01", "2023-12-31", as_of="2024-06-30", key=KEY))
    b = dumps(build_snapshot(["000001", "600519"], "2022-01-01", "2023-12-31", as_of="2024-06-30", key=KEY))
    assert a == b
    r1 = export_snapshot(json.loads(a), tmp_path / "one", viewer=False)
    r2 = export_snapshot(json.loads(b), tmp_path / "two", viewer=False)
    m1 = json.loads((tmp_path / "one" / "manifest.json").read_text(encoding="utf-8"))
    m2 = json.loads((tmp_path / "two" / "manifest.json").read_text(encoding="utf-8"))
    assert m1["files"] == m2["files"] and r1["nodes"] == r2["nodes"]


def test_natural_persons_are_masked_with_the_release_rule(nvf):
    from ashare.viz.snapshot import build_snapshot, dumps
    from ashare.release import pseudonym, is_natural_person
    from ashare.models import SessionLocal, OwnershipObservation
    s = SessionLocal()
    try:
        names = [(o.shareholder_name, o.shareholder_type) for o in s.query(OwnershipObservation)]
    finally:
        s.close()
    persons = [n for n, t in names if is_natural_person(n, t)]
    assert persons                                   # the synthetic reports name natural persons
    snap = build_snapshot(["600519"], "2022-01-01", "2023-12-31", as_of="2024-06-30", key=KEY)
    text = dumps(snap)
    for n in persons:
        assert n not in text
    shown = {x["label"] for x in snap["nodes"] if x["kind"] == "shareholder" and x["masked"]}
    assert shown and all(x.startswith("P") and len(x) == 13 for x in shown)
    from ashare.release import strip_nature
    assert {pseudonym(strip_nature(n)[0], KEY) for n in persons} >= shown
    orgs = [x for x in snap["nodes"] if x["kind"] == "shareholder" and not x["masked"]]
    assert orgs and all("公司" in x["label"] or "基金" in x["label"] for x in orgs)


def test_a_leaked_name_breaks_the_rules(nvf):
    from ashare.viz.snapshot import build_snapshot, validate_snapshot
    snap = build_snapshot(["600519"], "2022-01-01", "2023-12-31", as_of="2024-06-30", key=KEY)
    holder = next(n for n in snap["nodes"] if n["kind"] == "shareholder" and n["masked"])
    holder["label"] = "张三"
    assert any("masked name" in p for p in validate_snapshot(snap, {"张三"}))
    fact = next(e for e in snap["edges"] if e["basis"]["kind"] == "page")
    fact["basis"]["page"] = None
    assert any("without its page" in p for p in validate_snapshot(snap))
    snap["edges"][0]["relation"] = "CAUSES"
    assert any("relation" in p for p in validate_snapshot(snap))


def test_snapshot_parameters_are_checked(nvf):
    from ashare.viz.snapshot import build_snapshot, SnapshotError
    for args, msg in ((([], "2022-01-01", "2023-12-31"), "at least one"),
                      ((["600519"], "2023-12-31", "2022-01-01"), "after the end"),
                      ((["600519"], "2022-01-01", "2022-06-30"), "no fiscal year end"),
                      ((["123456"], "2022-01-01", "2023-12-31"), "not in the company list"),
                      ((["600519"], "2022-13-01", "2023-12-31"), "not a date")):
        with pytest.raises(SnapshotError, match=msg):
            build_snapshot(*args, as_of="2024-06-30", key=KEY)


def test_exported_observations_are_what_the_view_plots(nvf, tmp_path):
    from ashare.viz.snapshot import build_snapshot
    from ashare.viz.export import export_snapshot
    snap = build_snapshot(["600519"], "2022-01-01", "2023-12-31", as_of="2024-06-30", key=KEY)
    export_snapshot(snap, tmp_path / "v", viewer=False)
    rows = list(csv.DictReader((tmp_path / "v" / "observations.csv").open(encoding="utf-8-sig")))
    obs = [n for n in snap["nodes"] if n["kind"] == "observation"]
    assert sorted(r["id"] for r in rows) == sorted(n["id"] for n in obs)
    for row in rows:
        n = next(x for x in obs if x["id"] == row["id"])
        if n.get("value") is not None:
            assert float(row["value"]) == pytest.approx(n["value"])
    schema = json.loads((tmp_path / "v" / "snapshot.schema.json").read_text(encoding="utf-8"))
    assert schema["properties"]["schema_version"] == {"enum": [1]}
    assert {"snapshot.json", "observations.csv", "edges.csv", "snapshot.schema.json"} <= \
        set(json.loads((tmp_path / "v" / "manifest.json").read_text(encoding="utf-8"))["files"])


def test_layers_map_every_panel_variable_or_none():
    from ashare.nvf.layers import layer_of, variables_by_layer, LAYER_IDS
    from ashare.panel import variables
    for name in variables():
        assert layer_of(name) in LAYER_IDS + (None,)
    by = variables_by_layer()
    assert "revenue" in by["fundamentals"] and "rd_expense" in by["capability"] and "pe" in by["valuation"]
    with pytest.raises(KeyError):
        layer_of("no_such_variable")


# --- The offline viewer (adapted from the NVF Topology Tester v0.1) -----------------------------------------------

def test_viewer_is_one_offline_file_with_the_snapshot_inside(nvf, tmp_path):
    from ashare.viz.snapshot import build_snapshot, dumps
    from ashare.viz.viewer import write_viewer
    snap = build_snapshot(["600519", "000001"], "2022-01-01", "2023-12-31", as_of="2024-06-30", key=KEY)
    page = write_viewer(snap, tmp_path / "topology.html").read_text(encoding="utf-8")
    # (booleans: a failed comparison of a 1.8 MB page would take pytest minutes to describe)
    app = page.split("'use strict';\n// NVF topology viewer")[1]
    assert not ("cdn.jsdelivr" in page or "<script src=" in page or "<link " in page)
    assert not ("fetch(" in app or "XMLHttpRequest" in app)
    assert not ("/*LIB:" in page or "/*SNAPSHOT*/" in page or "/*APP*/" in page)
    for marker in ("Version 1.80.1 3d-force-graph", "Version 1.52.0 force-graph", "Chart.js v4.4.8"):
        assert bool(marker in page), marker
    inner = page.split('<script type="application/json" id="snapshot">')[1].split("</script>")[0]
    assert json.loads(inner.replace("<\\/", "</")) == json.loads(dumps(snap))
    assert not ("linkOpacity" in app.split("ForceGraph()(graphEl)")[1].split(";")[0])     # finding P5


def _browser():
    pw = pytest.importorskip("playwright.sync_api")
    return pw.sync_playwright()


def test_viewer_draws_both_views_with_fixed_positions(nvf, tmp_path):
    from ashare.viz.snapshot import build_snapshot
    from ashare.viz.viewer import write_viewer
    snap = build_snapshot(["600519", "000001"], "2022-01-01", "2023-12-31", as_of="2024-06-30", key=KEY)
    path = write_viewer(snap, tmp_path / "topology.html")
    with _browser() as p:
        try:
            browser = p.chromium.launch(args=["--use-gl=swiftshader", "--enable-unsafe-swiftshader"])
        except Exception as exc:                       # noqa: BLE001
            pytest.skip(f"no browser: {exc}")
        try:
            page = browser.new_page(viewport={"width": 1400, "height": 1000})
            errors, requests = [], []
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
            page.on("request", lambda r: requests.append(r.url) if not r.url.startswith(("file:", "data:", "blob:"))
                    else None)
            page.goto(path.as_uri())
            page.wait_for_function("document.getElementById('graphStatus').textContent.includes('nodes')", timeout=120000)
            status = page.inner_text("#graphStatus")
            n_nodes = int(status.split()[0])
            assert n_nodes == len(snap["nodes"])
            assert page.locator(".kpi").count() == 4 and page.locator("#coverageTable tr").count() == 6
            assert "GAP" in page.inner_text("#coverageTable") or "PARTIAL" in page.inner_text("#coverageTable")
            page.wait_for_timeout(1500)
            # the nodes stay where the snapshot puts them (finding P6); 3D only where the browser has WebGL
            if page.evaluate("webglAvailable()"):
                moved = page.evaluate("""() => graph.graphData().nodes.filter(n =>
                    Math.abs(n.x - n.position.x) > 0.01 || Math.abs(n.y - n.position.y) > 0.01 ||
                    Math.abs(n.z - n.position.z) > 0.01).length""")
                assert moved == 0
            page.select_option("#viewMode", "2d")                         # finding P5: the 2D view draws
            page.wait_for_timeout(1500)
            assert page.evaluate("graph.graphData().nodes.length") == n_nodes
            moved = page.evaluate("""() => graph.graphData().nodes.filter(n =>
                Math.abs(n.x - n.position.x) > 0.01 || Math.abs(n.y - n.position.y2) > 0.01).length""")
            assert moved == 0
            page.select_option("#companyFilter", "000001")
            page.wait_for_timeout(300)
            only = page.evaluate("graph.graphData().nodes.map(n => n.company_code || n.kind)")
            assert set(only) <= {"000001", "data_gap", "sector"}
            page.evaluate("showDetails(DATA.nodes.find(n => n.kind === 'shareholder'))")
            assert "pseudonym" in page.inner_text("#detailContent") or "shareholder" in page.inner_text("#detailContent")
            page.evaluate("showLinkDetails(DATA.edges.find(e => e.relation === 'REPORTS'))")
            assert "documented fact" in page.inner_text("#detailContent")
            assert not errors, errors
            assert not requests, requests                                  # nothing fetched from a network
        finally:
            browser.close()


# --- E3. The layered chart and the command ------------------------------------------------------------------------

def test_layered_chart_draws_every_cell_and_exports_what_it_plots(nvf):
    from ashare.viz.snapshot import build_snapshot
    from ashare.charts.layers import layers_chart
    from ashare.charts.layout import scene
    from ashare.charts.svg import render_svg
    snap = build_snapshot(["600519", "000001"], "2022-01-01", "2023-12-31", as_of="2024-06-30", key=KEY)
    spec = layers_chart(snap, row_items=50)
    prims = scene(spec)
    texts = [p["text"] for p in prims if p["type"] == "text"]
    assert all(layer["label"] in texts for layer in snap["layers"])
    assert texts.count("No data") == 5                                  # 000001: every layer empty
    obs = {n["id"] for n in snap["nodes"] if n["kind"] == "observation"}
    assert {r["id"] for r in spec.data_rows()} == obs                   # the CSV is what is drawn
    markers = [p for p in prims if p["type"] == "marker"]
    assert len([m for m in markers if m["meta"]["node"] in obs]) == len(obs)
    assert all(m["dash"] is None for m in markers)                      # all documented facts: solid
    svg = render_svg(spec)
    assert svg.count("<circle") + svg.count("<rect") + svg.count("<polygon") >= len(markers)
    one = layers_chart(snap, year="2023")
    assert all(r["period"].startswith("2023") for r in one.data_rows())


def test_layered_chart_tk_agrees_with_the_scene(nvf):
    import os
    tk = pytest.importorskip("tkinter")
    if not os.environ.get("DISPLAY") and os.name != "nt":
        pytest.skip("no display")
    from ashare.viz.snapshot import build_snapshot
    from ashare.charts.layers import layers_chart
    from ashare.charts.layout import scene
    from ashare.charts.tk import render_tk
    try:
        root = tk.Tk()
    except tk.TclError:
        pytest.skip("no display")
    try:
        c = tk.Canvas(root)
        spec = layers_chart(build_snapshot(["600519"], "2022-01-01", "2023-12-31", as_of="2024-06-30", key=KEY))
        render_tk(c, spec)
        circles = sorted((round(x0 + (x1 - x0) / 2, 1), round(y0 + (y1 - y0) / 2, 1)) for x0, y0, x1, y1 in
                         (c.coords(i) for i in c.find_all() if c.type(i) == "oval"))
        want = sorted((round(p["cx"], 1), round(p["cy"], 1)) for p in scene(spec)
                      if p["type"] == "marker" and p["shape"] == "circle")
        assert circles == want and want                                  # the same positions, to the pixel
    finally:
        root.destroy()


def test_topology_command_writes_the_view(nvf, tmp_path, monkeypatch):
    from typer.testing import CliRunner
    from ashare.cli import app
    monkeypatch.chdir(tmp_path)
    r = CliRunner().invoke(app, ["topology", "--industry", "C15", "--codes", "000001", "--start", "2022-01-01",
                                 "--end", "2023-12-31", "--as-of", "2024-06-30", "--out", "topo"])
    assert r.exit_code == 0, r.output
    names = set(p.name for p in (tmp_path / "topo").iterdir())
    assert {"snapshot.json", "observations.csv", "edges.csv", "snapshot.schema.json", "manifest.json",
            "topology.html", "layers.svg", "layers.csv"} <= names
    assert "fundamentals  PARTIAL" in r.output and "2 companies" in r.output
    r = CliRunner().invoke(app, ["topology", "--industry", "C39", "--start", "2022-01-01", "--end", "2023-12-31"])
    assert r.exit_code == 1 and "No company is classified in C39" in r.output
    r = CliRunner().invoke(app, ["topology", "--codes", "600519", "--start", "2023-01-01", "--end", "2023-06-30"])
    assert r.exit_code == 1 and "no fiscal year end" in r.output


def test_viewer_falls_back_to_2d_without_webgl(nvf, tmp_path):
    """Remote desktops and some graphics drivers give a browser no WebGL: the page must still work."""
    from ashare.viz.snapshot import build_snapshot
    from ashare.viz.viewer import write_viewer
    snap = build_snapshot(["600519"], "2022-01-01", "2023-12-31", as_of="2024-06-30", key=KEY)
    path = write_viewer(snap, tmp_path / "topology.html")
    with _browser() as p:
        try:
            browser = p.chromium.launch(args=["--disable-3d-apis", "--disable-gpu"])
        except Exception as exc:                       # noqa: BLE001
            pytest.skip(f"no browser: {exc}")
        try:
            page = browser.new_page()
            errors = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.goto(path.as_uri())
            page.wait_for_function("document.getElementById('graphStatus').textContent.includes('nodes')",
                                   timeout=120000)
            assert page.input_value("#viewMode") == "2d"
            assert "3D is unavailable" in page.inner_text("#axisNote")
            assert page.locator(".kpi").count() == 4 and not errors
        finally:
            browser.close()
