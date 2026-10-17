"""v1.7: statements, derived measures, adjustment factors, valuation, panels, event studies, explorer."""
import json
import math
import random
from datetime import date, timedelta

import pytest

from helpers import add_disclosure


def _fact(company, disclosure, period, ptype, metric, value):
    from ashare.models import SessionLocal, FinancialFact
    s = SessionLocal()
    s.add(FinancialFact(company_id=company.id, disclosure_id=disclosure.id, reporting_period=period, period_type=ptype,
                        metric=metric, value=value, extraction_method="XBRL", confidence=0.98,
                        consolidation_scope="CONSOLIDATED_DEFAULT", unit="CNY", source_document="x"))
    s.commit()
    s.close()


@pytest.fixture
def fin(db, company):
    # YTD revenue: 2024 Q1 10, H1 25, 9M 45, FY 70; 2025 Q1 12, H1 30, 9M 54, FY 84
    reports = [("2024年第一季度报告", "2024-04-25", "2024-03-31", "Q1", 10), ("2024年半年度报告", "2024-08-20", "2024-06-30", "H1", 25),
               ("2024年第三季度报告", "2024-10-25", "2024-09-30", "Q3", 45), ("2024年年度报告", "2025-03-28", "2024-12-31", "FY", 70),
               ("2025年第一季度报告", "2025-04-25", "2025-03-31", "Q1", 12), ("2025年半年度报告", "2025-08-20", "2025-06-30", "H1", 30),
               ("2025年第三季度报告", "2025-10-25", "2025-09-30", "Q3", 54), ("2025年年度报告", "2026-03-28", "2025-12-31", "FY", 84)]
    for i, (title, ann, period, ptype, rev) in enumerate(reports):
        d = add_disclosure(company, title, ann, None, ann_id=f"R{i}")
        _fact(company, d, period, ptype, "revenue", rev * 1e8)
        _fact(company, d, period, ptype, "net_profit_parent", rev * 0.5e8)
        _fact(company, d, period, ptype, "total_assets", 1000e8 + i * 10e8)
        _fact(company, d, period, ptype, "equity_parent", 600e8 + i * 5e8)
        _fact(company, d, period, ptype, "net_profit", rev * 0.55e8)
        if ptype == "FY":
            _fact(company, d, period, ptype, "net_profit_parent_ex_nonrecurring", rev * 0.45e8)
    return company


def test_statement_items_parser():
    from ashare.cas import parse_statement_items, CHART
    pages = ["管理层讨论：货币资金充足，营业收入增长。\n营业收入 999.00",
             "合并资产负债表\n单位：元\n项目 附注 期末余额 期初余额\n货币资金 七、1 1,000.00 800.00\n应收账款 七、5 200.00 150.00\n"
             "资产总计 5,000.00 4,000.00\n短期借款 七、32 300.00 -\n负债合计 2,000.00 1,500.00\n"
             "归属于母公司所有者权益（或股东权益）合计 2,900.00 2,400.00\n少数股东权益 100.00 100.00",
             "合并利润表\n单位：万元\n一、营业总收入 3,000.00 2,500.00\n其中：营业收入 3,000.00 2,500.00\n"
             "投资收益（损失以“－”号填列） (12.50) 3.00\n五、净利润（净亏损以“－”号填列） 450.00 400.00\n"
             "（一）基本每股收益(元/股) 1.25 1.10\n母公司资产负债表\n货币资金 5.00 4.00"]
    items = {i["metric"]: i for i in parse_statement_items(pages)}
    assert items["cash"]["value"] == 1000 and items["accounts_receivable"]["value"] == 200
    assert items["equity_parent"]["value"] == 2900 and items["minority_interests"]["value"] == 100
    assert items["revenue"]["value"] == 3000e4 and items["investment_income"]["value"] == -12.5e4
    assert items["net_profit"]["value"] == 450e4 and items["eps_basic"]["value"] == 1.25
    assert items["short_term_borrowings"]["value"] == 300
    assert len(CHART) >= 120


def test_quarterly_ttm_and_non_recurring(fin):
    from ashare.derived import quarterly_series, ttm_series, ttm_at, non_recurring_series
    q = {x["quarter"]: x["value"] for x in quarterly_series("600519", "revenue")}
    assert q == {"2024Q1": 10e8, "2024Q2": 15e8, "2024Q3": 20e8, "2024Q4": 25e8,
                 "2025Q1": 12e8, "2025Q2": 18e8, "2025Q3": 24e8, "2025Q4": 30e8}
    t = {x["period"]: x["value"] for x in ttm_series("600519", "revenue")}
    assert t["2025-06-30"] == pytest.approx((30 + 70 - 25) * 1e8) and t["2024-12-31"] == 70e8
    assert "2024-06-30" not in t                      # no FY 2023 to build TTM from
    k = ttm_at("600519", "revenue", "2025-09-01")      # H1 2025 published 2025-08-20
    assert k["period"] == "2025-06-30" and k["published"] == "2025-08-20"
    bal = quarterly_series("600519", "total_assets")
    assert bal[0]["formula"] == "reported"
    with pytest.raises(ValueError):
        ttm_series("600519", "total_assets")
    [nr2024, nr2025] = non_recurring_series("600519")
    assert nr2024["value"] == pytest.approx(70e8 * 0.05) and nr2025["share_of_net_profit"] == pytest.approx(0.1)


def _bars(company, closes, adjustment="none", source="TEST"):
    from ashare.market import persist_bars
    persist_bars(company, [{"trade_date": d, "open": c, "high": c, "low": c, "close": c, "volume": 1,
                            "adjustment": adjustment, "source": source} for d, c in closes])


def _trading_days(start, n):
    d, out = date.fromisoformat(start), []
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d.isoformat())
        d += timedelta(days=1)
    return out


def test_adjustment_factors_reproduce_provider(fin):
    from ashare.models import SessionLocal, CorporateAction
    from ashare.valuation import compute_adjustment_factors, compare_adjustments, adjusted_closes
    days = _trading_days("2025-01-02", 120)
    ex1, ex2 = days[40], days[80]
    raw, p = [], 100.0
    rng = random.Random(1)
    for d in days:
        if d == ex1:
            p = (p - 2.0) / 1.0          # cash dividend 2.0 per share
        if d == ex2:
            p = p / 1.4                  # 10转4 (0.4 shares per share)
        p *= 1 + rng.uniform(-0.01, 0.01)
        raw.append((d, round(p, 2)))
    _bars(fin, raw)
    s = SessionLocal()
    s.add(CorporateAction(company_id=fin.id, action_id="d1", action_type="CASH_DIVIDEND", status="IMPLEMENTATION_ANNOUNCED",
                          ex_date=ex1, cash_amount=2.0, source="TEST", extraction_method="TEST"))
    s.add(CorporateAction(company_id=fin.id, action_id="c1", action_type="CAPITALISATION_ISSUE", status="COMPLETED",
                          ex_date=ex2, ratio=0.4, source="TEST", extraction_method="TEST"))
    s.add(CorporateAction(company_id=fin.id, action_id="x1", action_type="CASH_DIVIDEND", status="PROPOSED",
                          ex_date=days[60], cash_amount=9.0, source="TEST", extraction_method="TEST"))
    s.commit()
    s.close()
    r = compute_adjustment_factors("600519")
    assert r["ex_dates"] == 2                        # the proposal is ignored
    # provider forward-adjusted series by the same convention
    closes = dict(raw)
    i1, i2 = days.index(ex1), days.index(ex2)
    f1 = closes[days[i1 - 1]] / (closes[days[i1 - 1]] - 2.0)
    f2 = 1.4
    prov = []
    for d, c in raw:
        F = (f1 if d >= ex1 else 1) * (f2 if d >= ex2 else 1)
        prov.append((d, c * F / (f1 * f2)))
    _bars(fin, prov, "forward", "PROVIDER")
    [cmp] = compare_adjustments("600519")
    assert cmp["days"] == 120 and cmp["within_tolerance"] >= 0.99
    back = adjusted_closes("600519", "backward")
    assert back[-1]["factor"] == pytest.approx(f1 * f2)


def test_market_snapshots_point_in_time(fin):
    from ashare.models import SessionLocal, CapitalStructureObservation, MarketSnapshot
    from ashare.valuation import build_market_snapshots, valuation_at
    _bars(fin, [("2025-03-31", 20.0), ("2025-04-30", 21.0), ("2025-09-30", 22.0)])
    s = SessionLocal()
    s.add(CapitalStructureObservation(company_id=fin.id, observation_date="2024-12-31", total_shares=1e9,
                                      tradable_shares=8e8, source="TEST"))
    s.commit()
    s.close()
    r = build_market_snapshots("600519")
    assert r["snapshots"] == 3
    v = valuation_at("600519", "2025-04-30")
    assert v["market_cap"] == 21e9 and v["float_market_cap"] == pytest.approx(16.8e9)
    # on 2025-04-30 the latest TTM net profit is FY2024 (published 2025-03-28); Q1 2025 (2025-04-25) gives TTM
    assert v["inputs"]["ttm_net_profit_parent"]["period"] == "2025-03-31"
    assert v["pe"] == pytest.approx(21e9 / ((12 + 70 - 10) * 0.5e8))
    v_before = valuation_at("600519", "2025-04-20")
    assert v_before["inputs"]["ttm_net_profit_parent"]["period"] == "2024-12-31"
    s = SessionLocal()
    snaps = s.query(MarketSnapshot).filter_by(source="DERIVED").all()
    s.close()
    assert all(json.loads(x.raw_json) is not None for x in snaps)


def test_panel_has_no_look_ahead_and_writes_files(fin, tmp_path):
    from ashare.panel import build_panel, write_panel, variables
    from ashare.models import SessionLocal, Company
    s = SessionLocal()
    c = s.query(Company).first()
    c.listing_date = "2001-08-27"
    s.commit()
    s.close()
    names = ["revenue", "net_profit_parent", "roe", "sales_growth", "ttm_revenue", "listed_years"]
    assert all(n in variables() for n in names)
    # fiscal panel known by 2025-09-01: FY2025 is excluded (ends later), FY2024 present
    r = build_panel(names, "year", "2024-01-01", "2025-12-31", "fiscal", as_of="2025-09-01", with_dates=True)
    assert [x["period"] for x in r["rows"]] == ["2024-12-31"]
    row = r["rows"][0]
    assert row["revenue"] == 70e8 and row["roe"] == pytest.approx(35e8 / (600e8 + 3 * 5e8))
    pubs = [v for k, v in row.items() if k.endswith("__published") and v]
    assert pubs and max(pubs) <= "2025-09-01" and r["max_published"] <= "2025-09-01"
    # point-in-time quarterly rows: each uses only what was published by the row date
    q = build_panel(["revenue", "ttm_revenue"], "quarter", "2025-01-01", "2025-12-31", "pit", with_dates=True)
    for x in q["rows"]:
        for k, v in x.items():
            if k.endswith("__published") and v:
                assert v <= x["cutoff"], (x["period"], k, v)
    by = {x["period"]: x for x in q["rows"]}
    assert by["2025-03-31"]["revenue"] == 25e8      # Q4 2024 single quarter, published 2025-03-28
    assert by["2025-06-30"]["revenue"] == 12e8      # Q1 2025, published 2025-04-25
    w = write_panel(r, str(tmp_path / "p"), "test", ("csv", "dta"))
    man = json.loads(open(tmp_path / "p" / "test_manifest.json", encoding="utf-8").read())
    assert man["rows"] == 1 and "test.dta" in man["files"] and man["max_published_date"] <= "2025-09-01"
    assert "## revenue" in open(tmp_path / "p" / "test_codebook.md", encoding="utf-8").read()
    pd = pytest.importorskip("pandas")
    df = pd.read_stata(tmp_path / "p" / "test.dta")
    assert df.loc[0, "revenue"] == 70e8 and df.loc[0, "code"] == "600519"


def test_event_study_matches_hand_computation(db, company):
    from ashare.storage import upsert_ashares
    from ashare.models import SessionLocal, Company
    from ashare.eventstudy import event_study
    upsert_ashares([{"code": "600000", "exchange": "SSE", "legal_name_cn": "市场公司"}])
    s = SessionLocal()
    other = s.query(Company).filter_by(security_code="600000").first()
    s.close()
    days = _trading_days("2024-01-02", 320)
    rng = random.Random(3)
    rm = [rng.uniform(-0.02, 0.02) for _ in days]
    ev_i = 300
    # stock: R = 0.001 + 1.5 * Rm exactly, plus +5% on the event day
    px, pm, a_, b_ = [100.0], [100.0], 0.001, 1.5
    for i in range(1, len(days)):
        r = a_ + b_ * rm[i] + (0.05 if i == ev_i else 0.0)
        px.append(px[-1] * (1 + r))
        pm.append(pm[-1] * (1 + rm[i]))
    _bars(company, list(zip(days, px)))
    _bars(other, list(zip(days, pm)))
    from ashare.eventstudy import benchmark_returns
    bench = benchmark_returns("ew")
    # the equal-weighted benchmark includes the stock itself; use a CSV benchmark of the market instead
    import csv, tempfile, os
    tmp = tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False, newline="")
    w = csv.writer(tmp)
    w.writerow(["date", "close"])
    w.writerows(zip(days, pm))
    tmp.close()
    r = event_study([{"code": "600519", "date": days[ev_i]}], (-250, -31), (-1, 1), "market", tmp.name)
    os.unlink(tmp.name)
    [e] = r["events"]
    assert e["alpha"] == pytest.approx(a_, abs=1e-9) and e["beta"] == pytest.approx(b_, abs=1e-9)
    assert e["car"] == pytest.approx(0.05, abs=1e-9) and e["ar"][0] == pytest.approx(0.05, abs=1e-9)
    assert r["caar"][-1]["caar"] == pytest.approx(0.05, abs=1e-9) and r["summary"]["used"] == 1
    r2 = event_study([{"code": "600519", "date": days[10]}])
    assert r2["summary"]["used"] == 0 and "beyond" in r2["skipped"][0]["reason"]
    assert len(bench) > 300


def test_explorer_and_new_charts(tmp_path):
    from ashare.explorer import summary, correlations, chart_for
    from ashare.charts import render_svg
    import xml.etree.ElementTree as ET
    rng = random.Random(5)
    rows = [{"code": f"{i:06d}", "name": "x", "period": f"{2020 + i % 4}-12-31", "measure_date": "", "cutoff": "",
             "a": rng.gauss(0, 1), "b": None if i % 7 == 0 else rng.gauss(1, 2), "sec": "C"} for i in range(80)]
    for r in rows:
        if r["b"] is not None:
            r["b"] = 2 * r["a"] + 0.1 * r["b"]
    s = {x["variable"]: x for x in summary(rows)}
    assert s["b"]["missing"] == 12 and s["a"]["n"] == 80
    c = {x["variable"]: x for x in correlations(rows)}
    assert c["a"]["b"] > 0.9
    for kind, x, y in (("hist", "a", None), ("box", "a", None), ("scatter", "a", "b"), ("coverage", None, None)):
        svg = render_svg(chart_for(rows, kind, x, y))
        ET.fromstring(svg)
        assert "<rect" in svg or "<circle" in svg
    assert "R² =" in render_svg(chart_for(rows, "scatter", "a", "b"))
    from ashare.charts import ChartSpec, Series, Point
    st = ChartSpec("stacked", "mix", [Series("A", [Point("2024", 3.0), Point("2025", 1.0)]),
                                      Series("B", [Point("2024", 1.0), Point("2025", 3.0)])], percent=True)
    assert "75.0%" in render_svg(st)
    band = ChartSpec("line", "car", [Series("CAAR", [Point(str(d), d * 0.01) for d in range(-2, 3)],
                                            band=[(d * 0.01 - 0.005, d * 0.01 + 0.005) for d in range(-2, 3)])])
    assert "<polygon" in render_svg(band)
    ev = ChartSpec("line", "price", [Series("c", [Point("2025-01-02", 1.0), Point("2025-03-03", 2.0)])], x_type="time",
                   markers=[{"x": "2025-02-01", "label": "CASH_DIVIDEND", "group": "corporate action"}])
    assert "CASH_DIVIDEND" in render_svg(ev)
