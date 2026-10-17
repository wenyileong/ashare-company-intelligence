"""v1.5: layout extraction, dual run, review workflow, charts, page rendering."""
import json
import xml.etree.ElementTree as ET

import pytest

from ashare.layout import layout_text_pages, text_layer, merge_wrapped, Row, Cell
from ashare.parsers import PARSERS, TABLE_FAMILIES, dual_run
from ashare.corpus import build_synthetic_corpus, _write_pdf
from ashare.evaluation import evaluate_corpus


def _table_pdf(path, valign="middle"):
    rows = [{"row": [["贵州茅台酱香酒营", "销有限公司"], "贵州仁怀", "贵州仁怀", "酒类销售", "100.00", "-", "设立"],
             "valign": valign},
            {"row": ["Moutai Holdings Limited", "开曼群岛", "开曼群岛", "投资控股", "-", "100.00", "设立"],
             "valign": valign}]
    _write_pdf(path, [["2025年年度报告", "单位：元", "（1）企业集团的构成",
                       "子公司名称 主要经营地 注册地 业务性质 持股比例 取得方式"] + rows])
    return path


@pytest.mark.parametrize("valign", ["middle", "top"])
def test_layout_merges_wrapped_cells(tmp_path, valign):
    pdf = _table_pdf(tmp_path / "g.pdf", valign)
    text = layout_text_pages(pdf)[0]
    assert "贵州茅台酱香酒营销有限公司 贵州仁怀 贵州仁怀 酒类销售 100.00 - 设立" in text
    from ashare.financials import _pdf_text_pages
    assert "贵州茅台酱香酒营销有限公司" not in _pdf_text_pages(pdf)[0].replace("\n", "|")  # the plain extractor breaks it
    recs, info = dual_run("subsidiaries", pdf)
    names = {r["entity_name"] for r in recs}
    assert names == {"贵州茅台酱香酒营销有限公司", "Moutai Holdings Limited"} and info["primary"] == "subsidiaries@layout"
    # the plain extractor produced a fragment ("销有限公司"), which is dropped, and fused
    # "Limited开曼群岛", so the layout result stands alone
    assert info["secondary_only"] <= 1 and all(r["_agreement"] == "SINGLE" for r in recs)


def test_fragment_rules_do_not_swallow_headings():
    h = 8.0
    rows = [Row(100, h, [Cell(30, 120, 96, 104, "分产品")]),
            Row(88, h, [Cell(30, 60, 84, 92, "茅台酒"), Cell(120, 160, 84, 92, "1,000.00")]),
            Row(70, h, [Cell(30, 200, 66, 74, "主要会计数据 2025年 2024年")]),
            Row(58, h, [Cell(30, 60, 54, 62, "营业收入"), Cell(120, 160, 54, 62, "9.00")])]
    out = merge_wrapped(rows)
    assert [r.text for r in out] == ["分产品", "茅台酒 1,000.00", "主要会计数据 2025年 2024年", "营业收入 9.00"]


def test_layout_variants_improve_table_recall(tmp_path):
    build_synthetic_corpus(tmp_path / "c", n_reports=6, n_notices=1, fmt="pdf")
    r = evaluate_corpus(tmp_path / "c", parsers=[p for p in PARSERS if PARSERS[p].family in TABLE_FAMILIES])
    m = r["parsers"]
    for fam in ("segments", "subsidiaries"):
        assert m[f"{fam}@layout"]["recall"] >= m[fam]["recall"] + 0.15, fam
    for fam in TABLE_FAMILIES:
        assert m[f"{fam}@layout"]["precision"] >= m[fam]["precision"] - 1e-9, fam
        assert m[f"{fam}@layout"]["precision"] >= 0.98, fam


def _load_report(company, tmp_path, layout=True):
    from helpers import add_disclosure
    from ashare.corpus import _annual_report
    import random
    rng = random.Random(7 if layout else 3)
    for _ in range(50):  # find a seed whose report draws tables cell by cell (or not)
        title, pages, exp = _annual_report(rng, 1)
        if any(isinstance(x, dict) for x in pages[2]) == layout:
            break
    pdf = tmp_path / "ar.pdf"
    _write_pdf(pdf, pages)
    year = title[title.index("公司") + 2:title.index("年")]
    d = add_disclosure(company, f"{year}年年度报告", f"{int(year) + 1}-03-30", pdf, ann_id="AR")
    return d, exp, int(year)


def test_extractors_store_variant_and_flag_disagreement(db, company, tmp_path, monkeypatch):
    from ashare.segments import extract_segments, segments
    from ashare.crossvalidation import cross_validate, show_flags
    from ashare.models import SessionLocal, SegmentObservation
    d, exp, year = _load_report(company, tmp_path)
    r = extract_segments("600519")
    assert r["dual_run"]["agree"] + r["dual_run"]["single"] > 0
    s = SessionLocal()
    rows = s.query(SegmentObservation).all()
    s.close()
    assert all(x.extraction_method == "PDF_TABLE_LAYOUT" and json.loads(x.extraction_note)["variant"] ==
               "segments@layout" for x in rows)
    truth = {x["segment_name"]: x["revenue"] for x in exp["segments"]["records"] if x["dimension"] == "PRODUCT"}
    got = {x["name"]: x["revenue"] for x in segments("600519")["dimensions"]["PRODUCT"]["segments"]}
    assert got.keys() == truth.keys() and all(abs(got[k] - truth[k]) < 1e-6 * truth[k] for k in truth)
    # make the text variant read a different revenue for the same segment
    base_run = PARSERS["segments"].run

    def skewed(pages, meta):
        out = base_run(pages, meta)
        for x in out:
            if x.get("revenue"):
                x["revenue"] *= 1.5
        return out
    monkeypatch.setattr(PARSERS["segments"], "run", skewed)
    extract_segments("600519")
    flags = cross_validate("600519")["flags"]
    assert flags.get("PARSER_DISAGREEMENT", 0) >= 1
    f = show_flags("600519", rule="PARSER_DISAGREEMENT")[0]
    assert json.loads(f.details)["alternative"]["variant"] == "segments"


def test_review_workflow_survives_reextraction(db, company, tmp_path):
    from ashare.segments import extract_segments, segments
    from ashare.models import SessionLocal, SegmentObservation, FinancialFact
    from ashare.review import build_review_queue, review_queue, resolve, review_item, correct_value, review_stats
    from ashare.intelligence import financial_series
    from ashare.financials import extract_financials
    _load_report(company, tmp_path)
    extract_segments("600519")
    extract_financials("600519")
    q = build_review_queue("600519", low_confidence_below=0.99)
    assert q["low_confidence"] > 0 and q["open"] > 0
    items = review_queue("600519")
    assert items == sorted(items, key=lambda i: -i["materiality"])
    seg_item = next(i for i in items if i["table"] == "segment_observations" and not i["item"].startswith("TOTAL"))
    detail = review_item(seg_item["id"])
    assert detail["trace"]["observation"]["table"] == "segment_observations"
    with pytest.raises(ValueError):
        resolve(seg_item["id"], "correct", "123")            # no reason
    resolve(seg_item["id"], "correct", "123,456", "typo in table", reviewer="tester")
    s = SessionLocal()
    row = s.get(SegmentObservation, seg_item["row_id"])
    original = row.revenue
    s.close()
    assert original != 123456.0                               # the observation itself is untouched
    view = segments("600519")["dimensions"][row.dimension]["segments"]
    assert next(x for x in view if x["name"] == row.segment_name)["revenue"] == 123456.0
    extract_segments("600519")                                # re-extraction keeps the correction
    view = segments("600519")["dimensions"][row.dimension]["segments"]
    assert next(x for x in view if x["name"] == row.segment_name)["revenue"] == 123456.0
    q2 = build_review_queue("600519", low_confidence_below=0.99)
    assert q2["new"] == 0                                     # decisions are kept when the queue is rebuilt
    assert review_queue("600519", "CORRECTED")[0]["id"] == seg_item["id"]
    # financial facts: correction and rejection, applied in the point-in-time series
    s = SessionLocal()
    fact = s.query(FinancialFact).filter_by(metric="revenue").first()
    s.close()
    correct_value("financial_facts", fact.id, "1000", "checked against the report")
    [pt] = financial_series("600519", "revenue")
    assert pt["value"] == 1000.0 and pt["review"] == "CORRECTED" and pt["confidence_class"] == "HIGH"
    assert pt["original_value"] == fact.value
    correct_value("financial_facts", fact.id, None, "not in this report", action="reject")
    assert financial_series("600519", "revenue") == []
    other = next(i for i in review_queue("600519") if i["id"] != seg_item["id"])
    assert resolve(other["id"], "defer")["status"] == "DEFERRED"
    stats = review_stats()
    assert any(r["table"] == "segment_observations" and r["corrected"] == 1 for r in stats)


def test_scanned_pdf_detected(db, company, tmp_path):
    from reportlab.pdfgen import canvas
    from helpers import add_disclosure
    from ashare.layout import scan_documents
    p = tmp_path / "scan.pdf"
    c = canvas.Canvas(str(p))
    c.rect(50, 50, 400, 600, fill=1)
    c.showPage()
    c.save()
    assert text_layer(p)["status"] == "NONE"
    add_disclosure(company, "2025年年度报告", "2026-03-30", p, ann_id="S1")
    r = scan_documents("600519")
    assert r["NONE"] == 1 and r["scanned"][0]["text_layer"] == "NONE"


def test_charts_svg_tooltips_gaps_and_export(tmp_path):
    from ashare.charts import ChartSpec, Series, Point, render_svg, export_chart
    from ashare.charts.layout import scene, nice_ticks, fmt_value
    pts = [Point("2021-12-31", 1e9, {"published": "2022-03-30", "source": "2021年年度报告"}, "HIGH"),
           Point("2022-12-31", None), Point("2023-12-31", 1.5e9, {"method": "PDF"}, "LOW", restated=True),
           Point("2024-12-31", 1.6e9, {}, "MEDIUM", review="CORRECTED")]
    spec = ChartSpec("line", "Revenue", [Series("Revenue", pts)], x_type="time", unit="CNY", as_of="2025-06-30",
                     caption="Source: test")
    svg = render_svg(spec)
    root = ET.fromstring(svg)
    ns = "{http://www.w3.org/2000/svg}"
    assert len(root.findall(f"{ns}polyline")) == 1          # the gap splits the line; a lone point draws no line
    titles = [t.text for t in root.iter(f"{ns}title")]
    assert any("published: 2022-03-30" in t and "2021年年度报告" in t for t in titles)
    assert any("restated" in t for t in titles)
    prims = scene(spec)
    shapes = [p["shape"] for p in prims if p["type"] == "marker"]
    assert shapes == ["circle", "diamond", "square"]
    low = next(p for p in prims if p["type"] == "marker" and p["shape"] == "diamond")
    assert low["dash"] and low["fill"] == "#ffffff"           # LOW: hollow and dashed
    assert any(p["type"] == "text" and p["text"].startswith("as of") for p in prims)
    assert nice_ticks(0, 97)[:3] == [0, 20, 40] and fmt_value(1.5e9) == "1.50bn" and fmt_value(0.25, "RATIO") == "25.0%"
    files = export_chart(spec, str(tmp_path / "c" / "rev"))
    rows = (tmp_path / "c" / "rev.csv").read_text(encoding="utf-8-sig").splitlines()
    assert rows[0].startswith("# Revenue") and len(rows) == 3 + len(pts)
    assert any(f.endswith(".svg") for f in files)
    hb = ChartSpec("hbar", "Segments", [Series("Revenue", [Point("A", 3.0), Point("B", None)])])
    assert "not disclosed" in render_svg(hb)


def test_chart_tk_renderer_matches_scene():
    import os
    tk = pytest.importorskip("tkinter")
    if not os.environ.get("DISPLAY") and os.name != "nt":
        pytest.skip("no display")
    from ashare.charts import ChartSpec, Series, Point
    from ashare.charts.tk import render_tk
    try:
        root = tk.Tk()
    except tk.TclError:
        pytest.skip("no display")
    try:
        c = tk.Canvas(root)
        spec = ChartSpec("line", "x", [Series("a", [Point(str(i), float(i)) for i in range(5)])])
        prims = render_tk(c, spec)
        assert len(c.find_all()) >= len([p for p in prims if p["type"] != "rect"])
    finally:
        root.destroy()


def test_page_render_png_and_highlight(tmp_path):
    from ashare.pagerender import render_page, encode_png
    pdf = _table_pdf(tmp_path / "g.pdf")
    r = render_page(pdf, 1, "Moutai Holdings Limited 开曼群岛")
    assert r["png"].startswith(b"\x89PNG") and r["pages"] == 1 and r["boxes"]
    x0, y0, x1, y1 = r["boxes"][0]
    assert 0 <= x0 < x1 <= r["width"] and 0 <= y0 < y1 <= r["height"]
    assert encode_png(1, 1, b"\xff\x00\x00").startswith(b"\x89PNG")


def test_optional_matplotlib_renderer(tmp_path):
    pytest.importorskip("matplotlib")
    from ashare.charts import ChartSpec, Series, Point
    from ashare.charts.mpl import render_png
    spec = ChartSpec("line", "Revenue", [Series("Revenue", [Point("2021-12-31", 1e9), Point("2022-12-31", None),
                                                           Point("2023-12-31", 2e9)])], x_type="time", unit="CNY")
    out = render_png(spec, str(tmp_path / "r.png"))
    assert open(out, "rb").read(4) == b"\x89PNG"
