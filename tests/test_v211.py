"""v2.1.1: fixes from the v2.0.9 live run (findings 112 to 117)."""
import time

from helpers import make_pdf, add_disclosure

ESG_PAGE = [
    "第五节 环境和社会责任", "公司属于环境保护部门公布的重点排污单位。",
    "化学需氧量 排放总量 120.5 吨；二氧化硫年排放量1,050 吨。",
    "报告期内温室气体排放总量为 35.6 万吨二氧化碳当量。",
    "报告期内公司对外捐赠合计 2,000 万元。",
]


def _long_annual_report(path, filler_pages=30, early_mention=False):
    lines = ["2025年年度报告", "第一节 重要提示、目录和释义"]
    for i in range(filler_pages):
        lines += ["<PAGE>", f"第{i + 2}页 经营情况讨论与分析", "本页讨论主营业务与行业格局。" * 3]
        if early_mention and i == 3:
            lines += ["公司在其他章节提及捐赠合计 999 万元。"]   # outside the section: not read in section mode
    lines += ["<PAGE>"] + ESG_PAGE + ["<PAGE>", "第六节 重要事项", "其他内容。"]
    return make_pdf(path, lines)


# --- finding 113: one slow document must not hold back the other companies ---------------------------------------

def test_a_slow_document_holds_back_only_its_own_company(tmp_path):
    from ashare.parallel import imap
    path = str(tmp_path / "none.pdf")
    jobs = [{"id": "A0", "path": path, "delay": 2.0, "group": "A"}, {"id": "A1", "path": path, "group": "A"}]
    jobs += [{"id": f"B{i}", "path": path, "group": "B"} for i in range(8)]
    order, t0, when = [], time.monotonic(), {}
    for r in imap("parallel_helpers:slow_job", jobs, n_workers=2):
        order.append(r["id"])
        when[r["id"]] = time.monotonic() - t0
    assert sorted(order) == sorted(j["id"] for j in jobs)
    assert order.index("A0") < order.index("A1")                       # a company's documents keep their order
    assert [x for x in order if x.startswith("B")] == [f"B{i}" for i in range(8)]
    assert all(when[f"B{i}"] < when["A0"] for i in range(8))          # B was not held back behind A0


def test_each_result_says_how_long_its_document_took(tmp_path):
    from ashare.parallel import parse_one
    r = parse_one("parallel_helpers:slow_job", {"id": 1, "path": str(tmp_path / "none.pdf"), "delay": 0.3})
    assert r["seconds"] >= 0.3


def test_the_slowest_documents_are_named_only_when_they_are_slow():
    from ashare.parallel import Slowest
    s = Slowest(keep=2)
    for i, sec in enumerate([5, 400, 30, 7000, 150]):
        s.add({"id": i, "seconds": sec, "pages": 200}, f"60000{i} 年度报告")
    assert [r["disclosure_id"] for r in s.report()] == [3, 1]          # kept two, both over two minutes
    quick = Slowest()
    quick.add({"id": 1, "seconds": 3.0})
    assert quick.report() == []
    quick.add({"id": 2, "error": "x"})                                 # no seconds recorded: ignored
    assert quick.report() == []


def test_extraction_totals_name_a_slow_document(company, tmp_path, monkeypatch):
    from ashare import human_capital, parallel
    pdf = make_pdf(tmp_path / "ar.pdf", ["2025年年度报告", "九、员工情况", "在职员工的数量合计（人） 10,000"])
    add_disclosure(company, "2025年年度报告", "2026-03-30", pdf, ann_id="AR25")
    real = parallel.parse_one

    def slow(parse, job, take_notices=True):
        out = real(parse, job, take_notices)
        out["seconds"] = 5400.0
        return out
    monkeypatch.setattr(parallel, "parse_one", slow)
    r = human_capital.extract_human_capital("600519")
    assert r["slowest"][0]["seconds"] == 5400.0 and "600519" in r["slowest"][0]["title"]


# --- finding 114: ESG extraction resumes, shows progress and reads the section pages -----------------------------

def test_esg_reads_the_environmental_section_and_resumes(company, tmp_path):
    from ashare.esg import extract_esg, esg_profile
    pdf = _long_annual_report(tmp_path / "ar.pdf", early_mention=True)
    add_disclosure(company, "2025年年度报告", "2026-03-30", pdf, ann_id="AR25")
    said = []
    r = extract_esg("600519", progress=said.append)
    assert r["documents"] == 1 and r["values"] == 5 and not r.get("read_whole") and not r["errors"]
    assert any("1 document(s) to read" in m for m in said) and any("1 of 1 documents" in m for m in said)
    p = esg_profile("600519")
    assert p["social"]["donations"]["value"] == 20_000_000             # the section's figure, not the early mention
    assert p["environmental"]["ghg_emissions"]["value"] == 356_000
    again = extract_esg("600519")
    assert again["to_read"] == 0 and again["already_read"] == 1 and again["documents"] == 0
    assert extract_esg("600519", again=True)["documents"] == 1


def test_esg_reads_a_sustainability_report_whole_and_dates_it_without_the_file(company, tmp_path):
    from ashare.esg import extract_esg, esg_profile
    lines = ["2025年度可持续发展报告"] + ["<PAGE>", "公司概况。"] * 5 + ["<PAGE>", "报告期内温室气体排放总量为 12 万吨二氧化碳当量。"]
    add_disclosure(company, "2025年度可持续发展报告", "2026-04-20", make_pdf(tmp_path / "sr.pdf", lines), ann_id="SR")
    add_disclosure(company, "2024年度社会责任报告", "2025-04-20", None, ann_id="SR24")
    r = extract_esg("600519")
    assert r["sustainability_reports"] == 2 and r["documents"] == 1 and r["read_whole"] == 1
    assert esg_profile("600519", year=2025)["environmental"]["ghg_emissions"]["value"] == 120_000
    assert esg_profile("600519", year=2024)["reporting"]["sustainability_report_published"] is True


def test_esg_gives_the_same_values_in_parallel_and_serial(company, tmp_path, monkeypatch):
    from ashare.esg import extract_esg
    from ashare.models import SessionLocal, EsgObservation
    for y in range(2019, 2025):
        add_disclosure(company, f"{y}年年度报告", f"{y + 1}-03-30",
                       _long_annual_report(tmp_path / f"ar{y}.pdf", filler_pages=4), ann_id=f"AR{y}")

    def rows():
        s = SessionLocal()
        try:
            return sorted((o.disclosure_id, o.item, o.value, o.source_page) for o in s.query(EsgObservation))
        finally:
            s.close()
    monkeypatch.setenv("ASHARE_WORKERS", "1")
    extract_esg("600519")
    serial = rows()
    monkeypatch.setenv("ASHARE_WORKERS", "2")
    par = extract_esg("600519", again=True)
    assert rows() == serial and len(serial) == 30 and not par["errors"]


# --- finding 115: one calendar for the mainland exchanges -------------------------------------------------------

def test_calendar_from_shenzhen_bars_serves_shanghai_suspensions(db):
    from ashare.storage import upsert_ashares
    from ashare.market import persist_bars
    from ashare.models import SessionLocal, Company
    from ashare.security_master import build_trading_calendar, suspensions, trading_days
    upsert_ashares([{"code": c, "exchange": "SZSE", "legal_name_cn": f"公司{c}"} for c in ("000001", "000002")]
                   + [{"code": "600000", "exchange": "SSE", "legal_name_cn": "浦发"}])
    s = SessionLocal()
    comps = {c.security_code: c for c in s.query(Company)}
    s.close()
    days = ["2026-01-05", "2026-01-06", "2026-01-07", "2026-01-08", "2026-01-09"]
    for code in ("000001", "000002"):
        persist_bars(comps[code], [{"trade_date": d, "open": 1, "high": 1, "low": 1, "close": 1, "volume": 1,
                                    "source": "TEST", "adjustment": "none"} for d in days])
    r = build_trading_calendar()
    assert r["exchanges"] == ["BSE", "SSE", "SZSE"] and r["bars_from"] == ["SZSE"] and r["days"] == 5
    assert trading_days("2026-01-01", "2026-01-31", "SSE") == days == trading_days("2026-01-01", "2026-01-31", "BSE")
    assert suspensions("600000", "2026-01-01", "2026-01-31")["days_without_trading"] == 5
    assert build_trading_calendar()["days_added"] == 0                 # a second run adds nothing
