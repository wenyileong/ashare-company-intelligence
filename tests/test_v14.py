"""v1.4: self-test, transport injection, golden corpus, evaluation and calibration."""
import json

import httpx
import pytest

from ashare.http import RateLimitedClient, set_default_transport
from ashare.selftest import run_selftest, fixture_handler
from ashare.evaluation import (PARSERS, evaluate_corpus, score_document, gate, baseline_from, save_calibration,
                               calibrated_confidence, corpus_template, wilson_lower, values_equal)
from ashare.corpus import build_synthetic_corpus
from ashare.financials import pdf_facts_from_pages, declared_unit


@pytest.fixture
def mock_default():
    yield lambda handler: set_default_transport(httpx.MockTransport(handler))
    set_default_transport(None)


def test_transport_injection_reaches_adapters(mock_default):
    from ashare.sources.cninfo import CNInfoAdapter
    seen = []

    def handler(request):
        seen.append(str(request.url))
        return httpx.Response(200, json={"stockList": [{"code": "600519", "orgId": "gssh0600519", "zwjc": "贵州茅台"}]})
    mock_default(handler)
    a = CNInfoAdapter()
    rows = list(a.get_stock_mappings())
    a.close()
    assert len(rows) == 1 and rows[0]["org_id"] == "gssh0600519" and rows[0]["exchange"] == "SSE"
    assert len(seen) == 1 and seen[0].endswith("szse_stock.json")   # v2.0.1: one list for all exchanges
    c = RateLimitedClient("ua", 1.0, transport=httpx.MockTransport(lambda r: httpx.Response(503)))
    with pytest.raises(httpx.HTTPStatusError):
        c.get("https://example.invalid/x")  # retries without sleeping when offline


def test_disclosure_and_market_adapters_offline(db, company, mock_default, tmp_path, monkeypatch):
    from ashare.disclosures import CNInfoDisclosureAdapter
    from ashare.market import fetch_eastmoney_bars
    monkeypatch.setenv("ASHARE_MARKET_RAW_DIR", str(tmp_path / "m"))
    mock_default(fixture_handler)
    company.board, company.org_id = "SSE_MAIN", "gssh0600519"
    pages = list(CNInfoDisclosureAdapter().query_pages(company, "2025-01-01", "2026-01-01", "annual"))
    assert pages[0][1]["announcements"][0]["announcementTitle"] == "2025年年度报告"
    bars = fetch_eastmoney_bars(company, "2026-09-01", "2026-09-30")
    assert bars[0]["close"] == 1510 and bars[0]["volume_unit"] == "LOTS_100_SHARES"


def test_selftest_offline_and_failure_modes(tmp_path):
    r = run_selftest(tmp_path / "ok", offline=True)
    assert r["verdict"] == "OK" and r["summary"]["FAIL"] == 0
    assert (tmp_path / "ok" / "selftest_report.json").exists() and (tmp_path / "ok" / "selftest_report.html").exists()

    def broken(request):  # every endpoint answers, in the wrong shape
        return httpx.Response(200, json={"unexpected": True})
    r = run_selftest(None, transport=httpx.MockTransport(broken))
    assert r["verdict"] == "ADAPTERS_NEED_ATTENTION"
    assert {x["check"] for x in r["results"] if x["status"] == "FAIL"} >= {"cninfo_stock_list_sse", "eastmoney_daily_bars"}

    def offline(request):
        raise httpx.ConnectError("no route", request=request)
    r = run_selftest(None, transport=httpx.MockTransport(offline))
    assert r["verdict"] == "NO_NETWORK" and r["summary"]["PASS"] == 0

    def empty_category(request):  # annual reports missing: the category code may have changed
        if "category_ndbg" in request.content.decode(errors="ignore"):
            return httpx.Response(200, json={"announcements": None, "totalAnnouncement": 0})
        return fixture_handler(request)
    r = run_selftest(None, transport=httpx.MockTransport(empty_category))
    row = next(x for x in r["results"] if x["check"] == "cninfo_category_annual")
    assert row["status"] == "WARN" and r["verdict"] == "OK_WITH_WARNINGS"


def test_declared_unit_ignores_narrative():
    pages = ["报告期内实现营业收入1,500亿元。\n单位：元\n营业收入 150,000,000,000.00 120,000,000,000.00"]
    [f] = [x for x in pdf_facts_from_pages(pages, "2025年年度报告", None) if x["metric"] == "revenue"]
    assert f["value"] == 150_000_000_000.0 and f["unit"] == "CNY"
    assert declared_unit(["金额单位：人民币万元"], 1, 100) == ("CNY_10K", 1e4)
    from ashare.human_capital import parse_human_capital_pages
    [v] = [x for x in parse_human_capital_pages(["单位：人民币万元\n研发投入合计 1,000.00"]) if x["item"] == "rd_investment"]
    assert v["value"] == 1e7


def test_score_document_outcomes():
    spec = PARSERS["esg"]
    exp = {"complete": True, "records": [{"item": "donations", "value": 100.0}, {"item": "emission_cod", "value": 5.0},
                                         {"item": "ghg_emissions", "value": 7.0}, {"item": "emission_so2", "value": None}]}
    pred = [{"item": "donations", "value": 100.004}, {"item": "emission_cod", "value": 6.0},
            {"item": "emission_so2", "value": 1.0}, {"item": "emission_nox", "value": 2.0}]
    t, errors = score_document(spec, exp, pred)
    v = t["value"]
    assert (v.correct, v.wrong, v.missed, v.spurious) == (1, 1, 1, 2)
    assert {e["outcome"] for e in errors} == {"wrong", "missed", "spurious"}
    assert values_equal(0.9462, 94.62 / 100) and not values_equal(1.0, 1.01) and values_equal("A  B", "A B")
    assert wilson_lower(0, 0) is None and 0.9 < wilson_lower(100, 100) < 1.0


def test_synthetic_corpus_evaluation_and_gate(tmp_path):
    build_synthetic_corpus(tmp_path / "c", n_reports=4, n_notices=2, fmt="pdf")
    r = evaluate_corpus(tmp_path / "c")
    assert set(r["parsers"]) == set(PARSERS)
    from ashare.parsers import TABLE_FAMILIES
    for name, m in r["parsers"].items():
        if name in TABLE_FAMILIES:   # the plain extractor breaks on cell-drawn tables (see test_v15)
            continue
        assert m["precision"] >= 0.98, (name, m)
        assert m["recall"] >= 0.95, (name, m)
    assert r["synthetic"] and len(r["fingerprint"]) == 64
    base = baseline_from(r)
    assert gate(r, base)["passed"]
    worse = json.loads(json.dumps(base))
    worse["parsers"]["segments"]["precision"] = 1.5  # baseline better than possible: must fail
    g = gate(r, worse)
    assert not g["passed"] and "segments" in g["failures"][0]


def test_calibration_only_from_real_verified_corpus(db, tmp_path):
    build_synthetic_corpus(tmp_path / "c", n_reports=3, n_notices=1, fmt="txt")
    r = evaluate_corpus(tmp_path / "c")
    save_calibration(r)
    assert calibrated_confidence("roster", 0.5) == 0.5          # synthetic: never used
    r["synthetic"] = False                                       # as if verified against real reports
    save_calibration(r)
    c = calibrated_confidence("roster", 0.5)
    assert c != 0.5 and c <= 0.9                                # Wilson lower bound, capped below HIGH
    from ashare.evaluation import PARSERS as P
    old = P["roster"].version
    try:
        P["roster"].version = "9.9"                             # parser changed since calibration
        assert calibrated_confidence("roster", 0.5) == 0.5
    finally:
        P["roster"].version = old


def test_corpus_template_drafts_unverified(db, tmp_path):
    from helpers import make_pdf
    pdf = make_pdf(tmp_path / "ar.pdf", ["2025年年度报告", "单位：元", "营业收入 1,000.00 900.00", "资产总计 5,000.00"])
    out = corpus_template(tmp_path / "gc", str(pdf), "ar25", "2025年年度报告", "2026-03-30")
    exp = json.loads(open(out["expected"], encoding="utf-8").read())
    assert exp["verified"] is False and "financials" in exp["parsers"] and "regulatory" not in exp["parsers"]
    assert {x["metric"] for x in exp["parsers"]["financials"]["records"]} == {"revenue", "total_assets"}
    r = evaluate_corpus(tmp_path / "gc")
    assert r["parsers"] == {} and r["skipped"][0]["reason"] == "not verified"
    r = evaluate_corpus(tmp_path / "gc", include_unverified=True)
    assert r["parsers"]["financials"]["precision"] == 1.0
    with pytest.raises(ValueError):
        corpus_template(tmp_path / "gc", str(pdf), "ar25")
