"""v2.2: the remaining data fixes (findings 132 to 139) and the visualisation section (docs/plan_v2.2.md)."""
import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from helpers import make_pdf, add_disclosure


# --- A1. the balance-sheet repair: across readings and by the grand total (finding 132) ---------------------------

def _facts(method, **values):
    return [{"metric": m, "value": v, "period": "2026-03-31", "period_type": "Q1", "method": method,
             "consolidation_scope": None, "confidence": 0.7, "extraction_note": None, "raw_value": f"{v:,.2f}"}
            for m, v in values.items()]


def _get(facts, method, metric):
    return next(f for f in facts if f["method"] == method and f["metric"] == metric)


def test_the_key_figures_reading_is_restored_from_the_statement_reading():
    from ashare.financials import repair_leading_digits
    key = _facts("PDF_TEXT_HEURISTIC", total_assets=58_318_402_807.42, total_liabilities=35_105_649_903.71,
                 equity=3_212_752_903.71)
    stmt = _facts("PDF_STATEMENT_TABLE", total_assets=58_318_402_807.42, total_liabilities=35_105_649_903.71,
                  equity=23_212_752_903.71)
    out = repair_leading_digits(key + stmt)
    f = _get(out, "PDF_TEXT_HEURISTIC", "equity")
    assert round(f["value"], 2) == 23_212_752_903.71
    assert json.loads(f["extraction_note"])["confirmed_by"] == "other reading (PDF_STATEMENT_TABLE)"


def test_the_statement_reading_is_restored_from_the_key_figures_reading():
    from ashare.financials import repair_leading_digits
    key = _facts("PDF_TEXT_HEURISTIC", total_assets=28_460_594_610.19, total_liabilities=11_863_198_800.65,
                 equity=16_597_395_809.54)
    stmt = _facts("PDF_STATEMENT_TABLE", total_assets=28_460_594_610.19, total_liabilities=11_863_198_800.65,
                  equity=6_597_395_809.54)
    out = repair_leading_digits(key + stmt)
    assert round(_get(out, "PDF_STATEMENT_TABLE", "equity")["value"], 2) == 16_597_395_809.54


def test_the_grand_total_confirms_when_only_one_total_can_be_short():
    from ashare.financials import repair_leading_digits
    # equity_parent cut in the same way, so the parts cannot confirm; the grand total can
    stmt = _facts("PDF_STATEMENT_TABLE", total_assets=58_318_402_807.42, total_liabilities=35_105_649_903.71,
                  equity=3_212_752_903.71, equity_parent=2_000_000_000.0, minority_interests=1_212_752_903.71,
                  total_liabilities_and_equity=58_318_402_807.42)
    out = repair_leading_digits(stmt)
    f = _get(out, "PDF_STATEMENT_TABLE", "equity")
    assert round(f["value"], 2) == 23_212_752_903.71
    assert json.loads(f["extraction_note"])["confirmed_by"] == "total_liabilities_and_equity"


def test_nothing_is_restored_when_two_totals_could_be_short():
    from ashare.financials import repair_leading_digits
    stmt = _facts("PDF_STATEMENT_TABLE", total_assets=30_000_000_000.0, total_liabilities=8_000_000_000.0,
                  equity=2_000_000_000.0, total_liabilities_and_equity=30_000_000_000.0)
    out = repair_leading_digits(stmt)
    assert _get(out, "PDF_STATEMENT_TABLE", "equity")["value"] == 2_000_000_000.0
    assert _get(out, "PDF_STATEMENT_TABLE", "total_liabilities")["value"] == 8_000_000_000.0


def test_the_same_cut_in_both_readings_is_not_a_confirmation():
    from ashare.financials import repair_leading_digits
    vals = dict(total_assets=58_318_402_807.42, total_liabilities=35_105_649_903.71, equity=3_212_752_903.71)
    out = repair_leading_digits(_facts("PDF_TEXT_HEURISTIC", **vals) + _facts("PDF_STATEMENT_TABLE", **vals))
    assert all(f["value"] == vals[f["metric"]] for f in out)


def test_the_financial_version_is_new():
    from ashare.financials import EXTRACTOR_VERSION
    assert EXTRACTOR_VERSION == "financials-5"


# --- A2. controller names with the legal representative glued on (finding 133) -----------------------------------

@pytest.mark.parametrize("tokens,expected", [
    (["国务院国有资产监督", "张玉卓管理委员会"], ["国务院国有资产监督管理委员会"]),
    (["深圳市人民政府国有", "杨军资产监督管理委员会"], ["深圳市人民政府国有资产监督管理委员会"]),
    (["山西省人民政府国有", "洪强资产监督管理委员会"], ["山西省人民政府国有资产监督管理委员会"]),
    (["代表国家履行出资人", "深圳市人民政府国有", "杨军资产监督管理委员会"], ["深圳市人民政府国有资产监督管理委员会"]),
    # v2.1.2's cases are unchanged
    (["国务院国有资产监督", "张玉卓", "管理委员会"], ["国务院国有资产监督管理委员会"]),
    (["中国移动", "杨杰", "甲公司"], ["中国移动", "甲公司"]),
    (["甲投资有限公司", "乙集团"], ["甲投资有限公司", "乙集团"]),
])
def test_the_four_garbled_names_of_the_v212_run_are_rejoined(tokens, expected):
    from ashare.control import _repair_entity_names
    assert _repair_entity_names(tokens, True) == expected


def test_the_glued_layout_read_from_report_lines():
    from ashare.control import parse_control_text
    text = """3、公司实际控制人及其一致行动人
实际控制人名称 法定代表人/单位负责人 成立日期 组织机构代码 主要经营业务
深圳市人民政府国有
杨军资产监督管理委员会 2004年06月01日 11440300K317280672 国资监管
实际控制人报告期内变更"""
    assert parse_control_text([text])["actual_controller"] == "深圳市人民政府国有资产监督管理委员会"


def test_a_place_name_is_never_taken_for_a_legal_representative():
    from ashare.control import _repair_entity_names
    assert _repair_entity_names(["代表国家履行出资人", "深圳市人民政府国有资产监督管理委员会"], True) == \
        ["深圳市人民政府国有资产监督管理委员会"]


def test_provincial_government_forms_are_grouped_as_one():
    from ashare.control import controller_key
    assert controller_key("四川省政府国有资产监督管理委员会") == controller_key("四川省人民政府国有资产监督管理委员会")
    assert controller_key("宁夏回族自治区人民政府") != controller_key("宁夏回族自治区国有资产监督管理委员会")


# --- A4. download rates, stop messages, ESG counts, short documents (findings 135 to 138) -------------------------

def test_rates_are_kept_by_kind_and_only_from_runs_of_25_or_more(tmp_path):
    from ashare import disclosure_pipeline as dp
    dp._record_rates({"earnings_forecast_or_flash": (5.2 * 3, 0.3, 3)})                 # a run stopped early
    assert not dp._rates_file().exists()
    dp._record_rates({"earnings_forecast_or_flash": (5.0 * 100, 10.0, 100), "annual_report": (2.0 * 40, 240.0, 40)})
    rows = [SimpleNamespace(kind="annual_report")] * 1800 + [SimpleNamespace(kind="earnings_forecast_or_flash")] * 720
    est = dp.download_estimate(rows)
    assert est["approx_hours"] == 2.0 and est["measured"]                              # 1 h + 1 h
    dp._record_rates({"annual_report": (4.0 * 30, 180.0, 30)})                          # half old, half new
    assert json.loads(dp._rates_file().read_text())["kinds"]["annual_report"]["seconds"] == 3.0
    other = dp.download_estimate([SimpleNamespace(kind="interim_report")])
    assert other["seconds_each"] == 4.0 and not other["measured"]                      # the mean of known kinds


def test_the_stop_note_of_a_finished_catalogue_says_it_downloads_the_rest():
    pytest.importorskip("tkinter")
    from ashare.gui import stop_message
    msg = stop_message(["catalogue-disclosures"], "stopped by the user")
    assert "downloads the documents still missing" in msg
    assert "checks the rest" in stop_message(["scan-documents"], "stopped")


def test_unchanged_sustainability_titles_are_not_counted_as_updated(company):
    from ashare.esg import extract_esg
    add_disclosure(company, "2025年度可持续发展报告", "2026-04-20", None, ann_id="SR")
    first = extract_esg("600519")
    assert first["inserted"] == 1
    again = extract_esg("600519")
    assert again["updated"] == 0 and again["unchanged"] == 1


def test_a_short_document_with_a_seal_page_is_full():
    from ashare.layout import classify_text_pages
    text = "本公司董事会及全体董事保证本公告内容不存在任何虚假记载、误导性陈述或者重大遗漏。"
    assert classify_text_pages([text, ""])["status"] == "FULL"
    assert classify_text_pages([text, text, ""])["status"] == "FULL"
    assert classify_text_pages(["", text])["status"] == "PARTIAL"                  # a blank first page still counts
    assert classify_text_pages([text] * 3 + ["", ""])["status"] == "PARTIAL"      # longer documents as before


# --- Part B. the Visualise section: views, snapshots, publication outputs ---------------------------------------

KEY = b"k" * 32


@pytest.fixture
def rel(company, tmp_path):
    """600519 with a controller and chain, a top-10 table (a company holder, a natural person and an unresolved
    fund), a subsidiary, two directors (one also on 000001's board), a regulatory event and a CSRC sector; a later
    controller reading published after the map's date; 000001 sharing the fund holder."""
    from ashare.storage import upsert_ashares
    from ashare.models import (SessionLocal, Company, Disclosure, ControlObservation, ControlEdge,
                               OwnershipObservation, SubsidiaryObservation, Person, PersonRole, RegulatoryEvent,
                               IndustryClassification)
    upsert_ashares([{"code": "000001", "exchange": "SZSE", "legal_name_cn": "平安银行股份有限公司",
                     "short_name_cn": "平安银行", "org_id": "z"}])
    s = SessionLocal()
    try:
        a = s.query(Company).filter_by(security_code="600519").one()
        b = s.query(Company).filter_by(security_code="000001").one()
        a.listing_date, b.listing_date = "2001-08-27", "1991-04-03"
        d1 = Disclosure(company_id=a.id, announcement_id="AR23", announcement_date="2024-03-29",
                        title_cn="2023年年度报告", kind="annual_report")
        d2 = Disclosure(company_id=a.id, announcement_id="AR24", announcement_date="2025-03-28",
                        title_cn="2024年年度报告", kind="annual_report")
        d3 = Disclosure(company_id=b.id, announcement_id="BR23", announcement_date="2024-03-15",
                        title_cn="2023年年度报告", kind="annual_report")
        s.add_all([d1, d2, d3])
        s.flush()
        s.add(ControlObservation(company_id=a.id, disclosure_id=d1.id, observation_date="2023-12-31",
                                 controlling_shareholder="中国贵州茅台酒厂（集团）有限责任公司",
                                 actual_controller="贵州省人民政府国有资产监督管理委员会", controller_nature="地方国资",
                                 ownership_type="LOCAL_SOE", source="PDF", source_page=40,
                                 extraction_method="PDF_TEXT"))
        s.add(ControlObservation(company_id=a.id, disclosure_id=d2.id, observation_date="2024-12-31",
                                 actual_controller="后来的控制人有限公司", source="PDF", source_page=41,
                                 extraction_method="PDF_TEXT"))
        s.add(ControlEdge(company_id=a.id, observation_date="2023-12-31",
                          parent_name="贵州省人民政府国有资产监督管理委员会",
                          child_name="中国贵州茅台酒厂（集团）有限责任公司", pct=100.0, source="PDF"))
        s.add(ControlEdge(company_id=a.id, observation_date="2023-12-31",
                          parent_name="中国贵州茅台酒厂（集团）有限责任公司", child_name="贵州茅台酒股份有限公司",
                          pct=54.07, source="PDF"))
        holders = [("中国贵州茅台酒厂（集团）有限责任公司", "国有法人", 54.07, 1),
                   ("张三", "境内自然人", 0.5, 2), ("某某证券投资基金", "其他", 0.4, 3)]
        for name, nature, pct, rank in holders:
            s.add(OwnershipObservation(company_id=a.id, disclosure_id=d1.id, observation_date="2023-12-31",
                                       shareholder_name=name, shareholder_nature=nature, ownership_pct=pct,
                                       rank=rank, source="PDF", source_page=30, extraction_method="PDF_TABLE"))
        s.add(OwnershipObservation(company_id=b.id, disclosure_id=d3.id, observation_date="2023-12-31",
                                   shareholder_name="某某证券投资基金", shareholder_nature="其他", ownership_pct=1.2,
                                   rank=5, source="PDF", source_page=20, extraction_method="PDF_TABLE"))
        s.add(SubsidiaryObservation(company_id=a.id, disclosure_id=d1.id, observation_date="2023-12-31",
                                    entity_name="贵州茅台酱香酒营销有限公司", relationship="子公司", total_pct=100.0,
                                    jurisdiction_class="DOMESTIC", source="PDF", source_page=120,
                                    extraction_method="PDF_TABLE"))
        p1, p2 = Person(name="李四"), Person(name="王五")
        s.add_all([p1, p2])
        s.flush()
        s.add(PersonRole(person_id=p1.id, company_id=a.id, role="董事长", first_date="2023-04-01",
                         last_date="2024-03-29"))
        s.add(PersonRole(person_id=p2.id, company_id=a.id, role="独立董事", first_date="2023-04-01",
                         last_date="2024-03-29"))
        s.add(PersonRole(person_id=p2.id, company_id=b.id, role="独立董事", first_date="2023-06-01",
                         last_date="2024-03-15"))
        s.add(RegulatoryEvent(company_id=a.id, disclosure_id=d1.id, event_id="E1", event_type="REGULATORY_LETTER",
                              legal_classification="EXCHANGE_SUPERVISORY_MEASURE", authority="SSE",
                              authority_name="上海证券交易所", announcement_date="2023-05-10",
                              event_date="2023-05-09", title_cn="关于收到监管工作函的公告",
                              extraction_method="TITLE", source="CNINFO"))
        s.add(IndustryClassification(company_id=a.id, scheme="CSRC_2012", effective_date="2023-01-01",
                                     level1_code="C", level1_name="制造业", level2_code="C15",
                                     level2_name="酒、饮料和精制茶制造业", source="CSRC"))
        s.commit()
    finally:
        s.close()
    return tmp_path


def _ego(**kw):
    from ashare.viz.registry import get
    p = {"code": "600519", "as_of": "2024-06-30", "depth": "1", "relations": "all", "key": KEY}
    p.update(kw)
    return get("ego_map").build(p)


def test_the_ego_map_shows_each_relation_as_known_on_the_date(rel):
    from ashare.viz.schema import check_view
    built = _ego()
    snap = built.snapshot
    assert check_view(snap) == []
    rels = {e["relation"] for e in snap["edges"]}
    assert {"CONTROLS", "PARENT_OF", "HOLDS", "SUBSIDIARY_OF", "SERVES_ON", "ACTS_ON", "IN_SECTOR"} <= rels
    labels = " ".join(n["label"] for n in snap["nodes"])
    assert "贵州省人民政府国有资产监督管理委员会" in labels
    assert "后来的控制人" not in labels                                   # published after the date
    assert "张三" not in labels and "李四" not in labels and "王五" not in labels   # persons under pseudonyms
    assert any(n["kind"] == "person" and n.get("masked") for n in snap["nodes"])
    fund = next(n for n in snap["nodes"] if n["label"] == "某某证券投资基金")
    assert "UNRESOLVED" in fund["flags"]
    assert not any(n["id"] == "company:000001" for n in snap["nodes"])  # depth 1
    steps = next(x for x in snap["summary"] if x["label"].startswith("Steps"))
    assert steps["value"] == "2"


def test_depth_two_adds_the_companies_shared_holders_hold_and_directors_serve(rel):
    snap = _ego(depth="2").snapshot
    other = [e for e in snap["edges"] if e["target"] == "company:000001"]
    assert {e["relation"] for e in other} == {"HOLDS", "SERVES_ON"}


def test_the_ego_map_is_deterministic_and_filters_relations(rel):
    from ashare.viz.publish import dumps
    assert dumps(_ego().snapshot) == dumps(_ego().snapshot)
    only = _ego(relations="regulators").snapshot
    assert {e["relation"] for e in only["edges"]} <= {"ACTS_ON", "IN_SECTOR"}
    with pytest.raises(Exception):
        _ego(depth="3")


def test_a_view_writes_its_files_with_a_manifest(rel, tmp_path):
    from ashare.viz.registry import get
    from ashare.viz.publish import write_view
    view = get("ego_map")
    out = write_view(view, _ego(), tmp_path / "ego", formats=("html", "svg", "csv"), width="page")
    folder = tmp_path / "ego"
    for name in ("view.json", "view.schema.json", "nodes.csv", "edges.csv", "view.html", "figures.html",
                 "manifest.json", "figure_ego_map.svg"):
        assert (folder / name).exists(), name
    man = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
    assert man["view"] == "ego_map" and man["evidence"] == "DOCUMENTED_FACT"
    assert all(len(h) == 64 for h in man["files"].values()) and "view.json" in man["files"]
    svg = (folder / "figure_ego_map.svg").read_text(encoding="utf-8")
    assert svg.startswith("<svg") or "<svg" in svg[:200]
    assert "张三" not in (folder / "nodes.csv").read_text(encoding="utf-8")
    assert out


def test_coverage_counts_companies_listed_and_excludes_later_publications(rel):
    from ashare.viz.registry import get
    from ashare.viz.schema import check_view
    early = get("coverage").build({"start": "2023", "end": "2023", "as_of": "2024-03-01", "key": KEY}).snapshot
    late = get("coverage").build({"start": "2023", "end": "2023", "as_of": "2024-06-30", "key": KEY}).snapshot
    assert check_view(early) == [] and check_view(late) == []

    def share(snap, layer):
        rows = [r for r in snap["tables"]["coverage_total"]["rows"] if r["layer"].startswith(layer)]
        return rows[0]["share"] if rows else 0
    assert share(early, "control") == 0
    assert 0 < share(late, "control") <= 1


def _guidance(company, tmp_path):
    from ashare.models import SessionLocal, Disclosure, ExpectationObservation, FinancialFact
    s = SessionLocal()
    try:
        g = Disclosure(company_id=company.id, announcement_id="G23", announcement_date="2024-01-10",
                       title_cn="2023年年度业绩预告", kind="earnings_forecast_or_flash")
        r = Disclosure(company_id=company.id, announcement_id="R23", announcement_date="2024-03-29",
                       title_cn="2023年年度报告", kind="annual_report")
        s.add_all([g, r])
        s.flush()
        s.add(ExpectationObservation(company_id=company.id, disclosure_id=g.id, source_kind="MANAGEMENT_GUIDANCE",
                                     document_kind="FORECAST", reporting_period="2023-12-31", period_type="FY",
                                     measure="net_profit_parent", low=5.5e8, high=6.5e8, direction="UP",
                                     published_date="2024-01-10", source="PDF", source_page=1,
                                     extraction_method="PDF_TEXT"))
        # a figure read from the forecast itself never counts as the outcome
        s.add(FinancialFact(company_id=company.id, disclosure_id=g.id, reporting_period="2023-12-31",
                            period_type="FY", metric="net_profit_parent", value=1.0e8,
                            extraction_method="PDF_TEXT_HEURISTIC"))
        s.add(FinancialFact(company_id=company.id, disclosure_id=r.id, reporting_period="2023-12-31",
                            period_type="FY", metric="net_profit_parent", value=6.2e8,
                            extraction_method="PDF_STATEMENT_TABLE"))
        s.commit()
    finally:
        s.close()


def test_guidance_is_paired_with_the_later_periodic_report_only(company, tmp_path):
    from ashare.viz.registry import get
    from ashare.viz.schema import check_view
    _guidance(company, tmp_path)
    snap = get("guidance_outcome").build({"start": "2023", "end": "2023", "as_of": "2024-06-30",
                                          "key": KEY}).snapshot
    assert check_view(snap) == []
    rows = snap["tables"]["pairs"]["rows"]
    assert len(rows) == 1 and rows[0]["actual"] == 6.2e8 and rows[0]["within_range"] == 1
    assert rows[0]["relative_error"] == pytest.approx((6.2e8 - 6e8) / 6e8, abs=1e-6)
    before = get("guidance_outcome").build({"start": "2023", "end": "2023", "as_of": "2024-02-01",
                                            "key": KEY}).snapshot
    assert before["tables"]["pairs"]["rows"] == []               # the report was not yet published


def test_views_are_listed_with_readiness_and_the_commands_exist(rel):
    from typer.testing import CliRunner
    from ashare.cli import app
    from ashare.viz.registry import views
    ids = [v.id for v in views()]
    assert {"topology", "ego_map", "coverage", "guidance_outcome"} <= set(ids)
    r = CliRunner().invoke(app, ["viz-list"])
    assert r.exit_code == 0 and "ego_map" in r.output.replace("-", "_")
    r = CliRunner().invoke(app, ["viz-check", "ego_map", "--code", "600519"])
    assert r.exit_code == 0, r.output
    for v in views():
        cmd = v.command()
        assert cmd in [c.name for c in app.registered_commands] or cmd == "topology"


def test_the_ego_command_writes_the_files(rel, tmp_path):
    from typer.testing import CliRunner
    from ashare.cli import app
    out = tmp_path / "cli_ego"
    r = CliRunner().invoke(app, ["viz-ego-map", "--code", "600519", "--as-of", "2024-06-30", "--out", str(out)])
    assert r.exit_code == 0, r.output
    assert "Interactive page:" in r.output and (out / "view.html").exists()


def test_panel_relational_variables(rel):
    from ashare.panel import build_panel
    r = build_panel(["ctrl_group", "ctrl_distance", "reg_actions_12m"], unit="year", start="2024-01-01",
                    end="2024-12-31", codes=["600519"], align="pit", pit_day="04-30")
    row = r["rows"][0]
    assert str(row["ctrl_group"]).startswith("G") and "政府" not in str(row["ctrl_group"])
    assert row["ctrl_distance"] == 2.0
    assert row["reg_actions_12m"] == 1.0


def _open(page_path, ready):
    with _pw() as p:
        try:
            browser = p.chromium.launch()
        except Exception as exc:                       # noqa: BLE001
            pytest.skip(f"no browser: {exc}")
        try:
            page = browser.new_page(viewport={"width": 1300, "height": 900})
            errors = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
            page.goto(Path(page_path).as_uri())
            page.wait_for_function(ready, timeout=60000)
            text = page.inner_text("body")
            return errors, text
        finally:
            browser.close()


def _pw():
    pw = pytest.importorskip("playwright.sync_api")
    return pw.sync_playwright()


def test_the_interactive_pages_draw_without_errors(rel, company, tmp_path):
    from ashare.viz.registry import get
    from ashare.viz.publish import write_view
    write_view(get("ego_map"), _ego(), tmp_path / "e", formats=("html",), width="page")
    errors, text = _open(tmp_path / "e" / "view.html", "window.__relmap !== undefined")
    assert errors == [] and "relations as of 2024-06-30" in text
    _guidance(company, tmp_path)
    built = get("guidance_outcome").build({"start": "2023", "end": "2023", "as_of": "2024-06-30", "key": KEY})
    write_view(get("guidance_outcome"), built, tmp_path / "g", formats=("html",), width="page")
    errors, text = _open(tmp_path / "g" / "view.html", "window.__chartview !== undefined")
    assert errors == [] and "Data (1 row)" in text


def test_the_visualise_pages_hold_the_views_and_their_commands_exist():
    pytest.importorskip("tkinter")
    from ashare import gui
    from ashare.cli import app
    names = {c.name or c.callback.__name__.replace("_", "-") for c in app.registered_commands}
    by_id = {s["id"]: s for s in gui.SECTIONS}
    for sid in ("topology", "relational", "company_views", "econometric", "coverage"):
        assert sid in by_id, sid
    viewish = [a for s in gui.SECTIONS for a in s.get("actions", []) if a.get("view")]
    assert {a["view"] for a in viewish} == {"ego_map", "guidance_outcome", "coverage"}
    for a in viewish:
        assert a["command"] in names and a["after"] == "open_view"
    text = gui.readiness_text([{"requirement": "controllers", "status": "MET", "detail": "3 rows", "action": None},
                               {"requirement": "holders", "status": "MISSING", "detail": "none",
                                "action": "Read top-10 shareholders from reports"}])
    assert "controllers" in text and "Read top-10 shareholders from reports" in text


def test_the_citation_file_names_the_licence_in_a_form_zenodo_accepts():
    """Zenodo reads CITATION.cff when it archives a GitHub release; a "license" that is not an SPDX identifier makes
    the file invalid and the archiving fail (the PolyForm Strict licence has none), so it is given by its address."""
    import re
    cff = (Path(__file__).resolve().parents[1] / "CITATION.cff").read_text(encoding="utf-8")
    assert not re.search(r"^license:\s*PolyForm-Strict", cff, re.M)
    assert 'license-url: "https://polyformproject.org/licenses/strict/1.0.0"' in cff
    try:
        from cffconvert.cli.create_citation import create_citation
    except ImportError:
        return
    create_citation(str(Path(__file__).resolve().parents[1] / "CITATION.cff"), None).validate()
