"""v1.0: cross-document validation, linking, tradable reconciliation,
point-in-time intelligence, research tools."""
import json
from helpers import make_pdf, add_disclosure


def _fact(company, disclosure, period, metric, value, method="XBRL", ptype="FY", conf=0.98):
    from ashare.models import SessionLocal, FinancialFact
    s = SessionLocal()
    try:
        f = FinancialFact(company_id=company.id, disclosure_id=disclosure.id, reporting_period=period, period_type=ptype,
                          metric=metric, value=value, extraction_method=method, confidence=conf,
                          consolidation_scope="CONSOLIDATED_DEFAULT", source_document="doc", unit="CNY")
        s.add(f); s.commit(); return f
    finally:
        s.close()


def _get(model, **kw):
    from ashare.models import SessionLocal
    s = SessionLocal()
    try:
        return s.query(model).filter_by(**kw).all()
    finally:
        s.close()


def test_point_in_time_series_and_restatement(company):
    from ashare.intelligence import financial_series
    from ashare.crossvalidation import cross_validate, show_flags
    d1 = add_disclosure(company, "2024年年度报告", "2025-03-30", ann_id="F24")
    d2 = add_disclosure(company, "2025年年度报告", "2026-03-30", ann_id="F25")
    _fact(company, d1, "2024-12-31", "revenue", 100.0e8)
    _fact(company, d2, "2025-12-31", "revenue", 120.0e8)
    _fact(company, d2, "2024-12-31", "revenue", 95.0e8, method="XBRL_COMPARATIVE", conf=0.95)  # restated comparative
    latest = financial_series("600519", "revenue")
    assert [(p["period"], p["value"], p["restated"]) for p in latest] == [
        ("2024-12-31", 95.0e8, True), ("2025-12-31", 120.0e8, False)]
    original = financial_series("600519", "revenue", vintage="original")
    assert original[0]["value"] == 100.0e8
    # as known on 2025-12-31: the 2025 report and its restatement did not yet exist
    pit = financial_series("600519", "revenue", as_of="2025-12-31")
    assert [(p["period"], p["value"], p["restated"]) for p in pit] == [("2024-12-31", 100.0e8, False)]
    r = cross_validate("600519")
    assert r["flags"].get("RESTATEMENT_OR_DISCREPANCY") == 1
    [flag] = show_flags("600519", rule="RESTATEMENT_OR_DISCREPANCY")
    d = json.loads(flag.details)
    assert d["earlier"]["value"] == 100.0e8 and d["later"]["value"] == 95.0e8
    # re-running regenerates rather than duplicates
    cross_validate("600519")
    assert len(show_flags("600519")) == 1


def test_confidence_classes():
    from ashare.crossvalidation import confidence_class
    assert confidence_class(0.98, "UNVALIDATED") == "HIGH"
    assert confidence_class(0.6, "VALIDATED_INTERNAL") == "MEDIUM"
    assert confidence_class(0.88, "VALIDATED_INTERNAL") == "HIGH"
    assert confidence_class(0.98, "FAILED_INTERNAL_BALANCE") == "LOW"
    assert confidence_class(0.4, None) == "LOW"
    assert confidence_class(None) == "UNVALIDATED"


def test_xbrl_comparatives_selected():
    from ashare.financials import _xbrl_facts, select_xbrl_facts, comparative_periods
    from test_financials import XBRL
    assert comparative_periods("2025-06-30", "H1") == [("2024-06-30", "H1"), ("2024-12-31", "FY")]
    facts = _xbrl_facts(XBRL, ".xml")
    prior = {f["metric"]: f for f in select_xbrl_facts(facts, "2024-12-31") if f["consolidation_scope"]}
    assert prior["revenue"]["value"] == 30_000_000


def test_linking_and_status(company):
    from ashare.regulatory import extract_regulatory_events, regulatory_status
    from ashare.linking import link_all
    from ashare.models import RegulatoryEvent
    add_disclosure(company, "关于收到中国证券监督管理委员会立案告知书的公告", "2025-01-10", ann_id="L1")
    add_disclosure(company, "关于收到《行政处罚事先告知书》的公告", "2025-09-01", ann_id="L2")
    add_disclosure(company, "关于收到上海证券交易所问询函的公告", "2025-04-01", ann_id="L3")
    add_disclosure(company, "关于上海证券交易所问询函回复的公告", "2025-04-15", ann_id="L4")
    add_disclosure(company, "关于筹划重大资产重组停牌的公告", "2025-05-01", ann_id="L5")
    add_disclosure(company, "关于股票复牌的公告", "2025-05-15", ann_id="L6")
    extract_regulatory_events("600519")
    r = link_all("600519")
    assert r["regulatory_events_linked"] >= 6
    ev = {e.announcement_id: e for e in _get(RegulatoryEvent)}
    assert ev["L1"].case_key == ev["L2"].case_key and ev["L1"].link_basis == "INVESTIGATION_OPENS_CASE"
    assert ev["L3"].case_key == ev["L4"].case_key and ev["L5"].case_key == ev["L6"].case_key
    st = regulatory_status("600519")
    assert st["investigations"][0]["state"] == "PRIOR_NOTICE_ISSUED"
    assert st["trading_status"].startswith("TRADING")


def test_tradable_reconciliation(company, tmp_path):
    from ashare.ownership import import_capital_csv
    from ashare.corporate_actions import import_corporate_actions_csv
    from ashare.reconciliation import reconcile_capital
    cap = tmp_path / "cap.csv"
    cap.write_text("security_code,observation_date,total_shares,tradable_shares,restricted_shares\n"
                   "600519,2026-03-31,1000,800,200\n600519,2026-06-30,1500,1180,320\n", encoding="utf-8")
    import_capital_csv(str(cap), source="CAP")
    ca = tmp_path / "ca.csv"
    ca.write_text("security_code,action_id,action_type,status,ex_date,effective_date,ratio,share_delta,shares_affected\n"
                  "600519,b1,CAPITALISATION_ISSUE,COMPLETED,2026-04-10,,0.4,,\n"          # 1000->1400; tradable 800->1120
                  "600519,p1,PRIVATE_PLACEMENT,COMPLETED,,2026-05-01,,100,\n"            # restricted; total 1500
                  "600519,u1,RESTRICTED_SHARE_UNLOCK,IMPLEMENTATION_ANNOUNCED,,2026-06-01,,0,60\n",  # tradable 1180
                  encoding="utf-8")
    import_corporate_actions_csv(str(ca), source="ACT")
    [w] = reconcile_capital("600519")["results"]
    assert w["status"] == "RECONCILED" and w["expected_t1"] == 1500
    assert w["tradable_status"] == "RECONCILED" and abs(w["expected_t1_tradable"] - 1180) < 1e-6


def test_profile_timeline_compare_report(company, tmp_path):
    from ashare.intelligence import company_profile, timeline, compare, market_stats
    from ashare.report import write_profile_report
    from ashare.market import import_bars_csv
    d = add_disclosure(company, "2025年年度报告", "2026-03-30", ann_id="P25")
    _fact(company, d, "2025-12-31", "revenue", 1000.0)
    _fact(company, d, "2025-12-31", "net_profit", 250.0)
    bars = tmp_path / "b.csv"
    bars.write_text("code,date,open,high,low,close\n600519,2026-01-02,10,11,9,10\n"
                    "600519,2026-01-05,10,12,10,12\n600519,2026-01-06,12,12,9,9\n", encoding="utf-8")
    import_bars_csv(str(bars), source="VENDOR")
    p = company_profile("600519")
    assert p["identity"]["code"] == "600519" and p["financials_fy"]["revenue"][0]["value"] == 1000.0
    assert p["market_last"]["close"] == 9
    assert timeline("600519")[0]["layer"] == "disclosure"
    c = compare(["600519"], ["revenue", "net_profit"])
    assert c["rows"][0]["net_margin"] == 0.25
    m = market_stats("600519")
    assert abs(m["price_return"] + 0.1) < 1e-9 and abs(m["max_drawdown"] + 0.25) < 1e-9
    path = write_profile_report("600519", str(tmp_path / "r.html"))
    html = open(path, encoding="utf-8").read()
    assert "<html" in html and "600519" in html and "http" not in html.split("<footer>")[0].replace("http-equiv", "")


def test_research_tools(company, tmp_path):
    from ashare.research import (search_disclosures, index_documents, search_documents, inspect_document,
                                 trace, run_query, release_dataset)
    from ashare.models import SessionLocal, Disclosure
    import hashlib
    pdf = make_pdf(tmp_path / "doc.pdf", ["2025年年度权益分派实施公告", "每股派发现金红利27.673元（含税）"])
    d = add_disclosure(company, "2025年年度权益分派实施公告", "2026-06-12", pdf, ann_id="S1")
    s = SessionLocal()
    row = s.get(Disclosure, d.id); row.sha256 = hashlib.sha256(pdf.read_bytes()).hexdigest(); s.commit(); s.close()
    assert search_disclosures("权益分派")[0]["disclosure_id"] == d.id
    idx = index_documents()
    assert idx["documents"] == 1 and idx["pages"] == 1
    hits = search_documents("现金红利")
    assert hits and hits[0]["page"] == 1 and "现金红利" in hits[0]["snippet"]
    assert search_documents("红利")  # two characters: substring fallback
    info = inspect_document(d.id, 1)
    assert info["integrity"] == "VERIFIED" and "27.673" in info["page_text"]
    from ashare.corporate_actions import extract_corporate_actions, show_actions
    extract_corporate_actions("600519")
    a = show_actions("600519")[0]
    t = trace("corporate_actions", a.id)
    assert t["document"]["integrity"] == "VERIFIED" and t["company"]["code"] == "600519"
    assert t["normalised_value"]["cash_amount"] == 27.673 and t["validation"]["confidence_class"] in ("MEDIUM", "HIGH")
    q = run_query("SELECT security_code FROM companies", out=str(tmp_path / "q.csv"), name="codes")
    assert q["rows"] == [("600519",)] and q["output_sha256"] and q["log_id"]
    import pytest
    with pytest.raises(ValueError):
        run_query("DELETE FROM companies")
    rel = release_dataset(str(tmp_path / "rel"), name="r1")
    manifest = json.loads((tmp_path / "rel" / "r1" / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["row_counts"]["companies"] == 1
    assert any(f["path"] == "ashares_snapshot.db" for f in manifest["files"])   # v2.0: built on any back end
    assert all(len(f["sha256"]) == 64 for f in manifest["files"])


def test_validate_all_runs(company):
    from ashare.crossvalidation import validate_all
    r = validate_all("600519")
    assert {"stage1_universe_problems", "event_linking", "stage3_4_cross_validation"} <= set(r)
