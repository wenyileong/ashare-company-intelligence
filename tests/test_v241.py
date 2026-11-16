"""v2.4.1: the defects and refinements found in the review of v2.4.0 (docs/plan_v2.4.md, "Review after the build")."""
import io
import json
from types import SimpleNamespace

import pytest

from ashare import progressbar as pb
from tests.test_v24 import _calendar, _dealing, _disclosure


@pytest.fixture(autouse=True)
def _fresh():
    from ashare.rulepacks import clear_cache
    clear_cache()
    pb.set_sink(None)
    yield
    clear_cache()
    pb.set_sink(None)


# --- progress ---------------------------------------------------------------------------------------------------------

def test_a_finished_job_no_longer_holds_the_bar_in_later_stages():
    got = []
    pb.set_sink(got.append)
    pb.stage(1, 3, "announcements and documents")
    job = pb.Counter(2, "items", outer=True)
    job.done = 2
    job.step(0)
    job.close()
    pb.stage(2, 3, "prices")
    c = pb.Counter(100, "companies")
    for _ in range(100):
        c.step()
    d = got[-1]
    assert (d["done"], d["total"], d["unit"], d["stage"]) == (100, 100, "companies", 2) and "sub" not in d
    assert pb.text(d) == "Stage 2 of 3: prices; 100%  100 of 100 companies; 66% overall"


def test_stage_alone_releases_the_counters_of_the_stage_before():
    got = []
    pb.set_sink(got.append)
    pb.Counter(2, "items", outer=True)                      # never closed
    pb.stage(2, 2, "prices")
    pb.Counter(4, "companies").step()
    assert got[-1]["unit"] == "companies" and "sub" not in got[-1]


def test_run_job_releases_its_bar(db):
    from ashare import ops
    got = []
    pb.set_sink(got.append)
    ops.HANDLERS["_t"] = lambda key, params: {"ok": key}
    try:
        ops.run_job(ops.create_job("_t", {}, items=["a", "b"]))
    finally:
        ops.HANDLERS.pop("_t", None)
    assert pb._outer is None


def test_a_total_of_zero_is_complete_not_unknown():
    got = []
    pb.set_sink(got.append)
    pb.Counter(0, "companies")
    assert pb.fraction(got[-1]) == 1.0 and pb.text(got[-1]) == "100%  nothing to do"
    assert pb.fraction({"done": None, "total": None}) is None


def test_other_output_clears_the_terminal_bar_first(monkeypatch):
    import sys

    class Tty(io.StringIO):
        def isatty(self):
            return True
    t = Tty()
    monkeypatch.setattr("sys.stdout", t)
    monkeypatch.delenv("ASHARE_PROGRESS", raising=False)
    c = pb.Counter(3, "files")
    c.step()
    print("Not written: the panel has no rows")
    pb.end()
    text = t.getvalue()
    assert "files\r\x1b[KNot written: the panel has no rows\n" in text       # the bar's line is cleared first
    assert sys.stdout is t                                                    # and stdout is put back


def test_megabytes_speed_units_and_stage_names_in_chinese():
    got = []
    pb.set_sink(got.append)
    c = pb.Counter(10, "documents")
    pb.add_megabytes(12.5)
    import time
    time.sleep(0.3)
    c.step()
    d = got[-1]
    assert d["mb"] == 12.5 and "MB at" in pb.text(d)
    zh = {"progress.unit.documents": "份文件", "progress.stage.prices": "行情"}
    tr = lambda key, default: zh.get(key, default)                            # noqa: E731
    assert "份文件" in pb.text({"done": 1, "total": 2, "unit": "documents"}, tr)
    assert "行情" in pb.text({"done": 1, "total": 2, "unit": "x", "stage": 2, "stages": 3, "stage_label": "prices"}, tr)
    pb.set_sink(None)
    assert pb._megabytes[0] == 0.0                                            # reset with the action


def test_progress_texts_have_chinese():
    from ashare.i18n import set_language, tr
    set_language("zh_CN")
    try:
        assert pb.text({"done": 1, "total": 2, "unit": "documents", "stage": 2, "stages": 3, "stage_label": "prices"},
                       tr).replace("\xa0", " ") == "第 2 阶段，共 3 个阶段: 行情; 50%  1 / 2 份文件; 总进度 50%"
        assert pb.text({"done": 0, "total": 0, "unit": "items"}, tr).replace("\xa0", " ") == "100%  无需处理"
    finally:
        set_language("en")


# --- share dealings -----------------------------------------------------------------------------------------------------

def test_plan_titles_exclude_notices_that_a_plan_ended_or_progressed():
    from ashare.insider import is_plan_title as p
    assert p("关于董事减持股份计划的预披露公告") and p("关于控股股东减持股份预披露公告") and p("关于高管拟减持股份的公告")
    for t in ("关于股东减持计划实施完毕的公告", "关于董事减持计划时间过半的进展公告", "股东减持股份结果公告",
              "关于减持计划期限届满暨实施情况的公告", "关于提前终止减持计划的公告"):
        assert not p(t), t


def test_the_method_is_read_from_the_row_or_the_page():
    from ashare.insider import read_method
    assert read_method("张三 董事 2025-03-10 集中竞价 卖出 10,000") == "AUCTION"
    assert read_method("李四 2025-03-11 大宗交易 减持 5,000") == "BLOCK"
    assert read_method("王五 2025-03-12 卖出 100", "本次变动均通过协议转让方式完成") == "AGREEMENT"
    assert read_method("王五 2025-03-12 卖出 100", "集中竞价及大宗交易") is None       # two on the page: not guessed
    assert read_method("王五 2025-03-12 卖出 100") is None


def test_the_plan_rule_covers_auction_and_block_trades_but_not_agreements(db, company, monkeypatch):
    from ashare.insider import flags
    monkeypatch.setenv("ASHARE_FEATURES", "insider=on")
    _dealing(company, "2025-03-10", "2025-03-11", method="AUCTION")
    _dealing(company, "2025-03-11", "2025-03-12", method="BLOCK")
    _dealing(company, "2025-03-12", "2025-03-13", method="AGREEMENT")
    by = {r["deal_date"]: r for r in flags("600519")["rows"]}
    assert "no reduction plan" in by["2025-03-10"]["flags"] and "method not given" not in by["2025-03-10"]["flags"]
    assert "no reduction plan" in by["2025-03-11"]["flags"] and by["2025-03-11"]["method"] == "block trade"
    assert by["2025-03-12"]["flags"] == ""


def test_dealings_before_the_rules_present_form_say_so(db, company, monkeypatch):
    from ashare.insider import flags
    monkeypatch.setenv("ASHARE_FEATURES", "insider=on")
    _disclosure(company, "2020-03-14", "2019年年度报告", kind="annual_report")
    _dealing(company, "2020-03-10", "2020-03-11", direction="BUY")
    _disclosure(company, "2025-03-14", "2024年年度报告", kind="annual_report")
    _dealing(company, "2025-03-10", "2025-03-11", direction="BUY")
    by = {r["deal_date"]: r["flags"] for r in flags("600519")["rows"]}
    assert "before 2024-05-24: an earlier version of the rule applied, which may differ" in by["2020-03-10"]
    assert "earlier version" not in by["2025-03-10"] and "(provisional rule)" in by["2025-03-10"]


def test_supervisors_are_not_judged_after_they_left_the_rules(db, company, monkeypatch):
    from ashare.insider import flags, _supervisor_only
    from ashare.models import SessionLocal
    from ashare.models_v23 import InsiderDealing
    monkeypatch.setenv("ASHARE_FEATURES", "insider=on")
    assert _supervisor_only("监事") and _supervisor_only("监事会主席")
    assert not _supervisor_only("董事") and not _supervisor_only("职工监事、副总经理") and not _supervisor_only(None)
    s = SessionLocal()
    for role, when in (("监事", "2025-04-10"), ("监事", "2025-03-10"), ("董事", "2025-04-11")):
        s.add(InsiderDealing(company_id=company.id, person_name="x", role=role, deal_date=when, direction="SELL",
                             shares=1, published_date=when))
    s.commit()
    s.close()
    r = flags("600519")
    by = {x["deal_date"]: x["flags"] for x in r["rows"]}
    assert by["2025-04-10"] == "" and "no reduction plan" in by["2025-03-10"] and "no reduction plan" in by["2025-04-11"]
    assert "a supervisor's dealing on or after 2025-03-27" in r["note"]


def test_the_twelve_months_are_exact(db, company, monkeypatch):
    from ashare.insider import company_measures
    from ashare.models import SessionLocal
    _dealing(company, "2023-12-31", "2024-01-02", direction="BUY", shares=100)       # exactly a year before: outside
    _dealing(company, "2024-01-01", "2024-01-02", direction="BUY", shares=7)
    s = SessionLocal()
    assert company_measures(s, company, "2024-12-31")["net_buy"] == 7.0
    assert company_measures(s, company, "2024-02-29")["n"] == 2                      # a leap day does not fail
    s.close()


# --- rule packs -----------------------------------------------------------------------------------------------------------

def test_the_packs_record_what_was_checked_and_stay_provisional():
    from ashare.rulepacks import load
    ins, dl = load("insider"), load("deadlines")
    assert ins.version == "insider-2" and dl.version == "deadlines-2" and ins.status == dl.status == "provisional"
    plan = ins.rule("plan_before_sale")
    assert plan["methods"] == ["AUCTION", "BLOCK"] and plan["in_this_form_from"] == "2024-05-24"
    assert all(r["verified"] and "confirmed by the author" in r["verified"] for r in ins.rules + dl.rules)
    q = next(r for r in dl.rules if r["id"] == "quarterly")
    assert "listing rules" in q["source"]


def test_a_pack_with_an_unknown_method_is_refused(tmp_path):
    from ashare.rulepacks import bundled_path, check
    d = json.loads(bundled_path("insider").read_text(encoding="utf-8"))
    d["rules"][1]["methods"] = ["AUCTION", "TELEPATHY"]
    f = tmp_path / "x.json"
    f.write_text(json.dumps(d), encoding="utf-8")
    c = check("insider", f)
    assert not c["ok"] and "methods" in c["errors"][0]


def test_diff_and_confirmation_sheet(tmp_path):
    from typer.testing import CliRunner
    from ashare.cli import app
    from ashare.rulepacks import bundled_path, diff, confirmation_sheet
    assert diff("insider")["rows"] == []
    d = json.loads(bundled_path("insider").read_text(encoding="utf-8"))
    d["rules"][0]["trading_days"] = 3
    d["rules"][0]["status"] = "confirmed"
    f = tmp_path / "edited.json"
    f.write_text(json.dumps(d), encoding="utf-8")
    rows = {r["field"]: r for r in diff("insider", f)["rows"]}
    assert rows["rule report_within: trading_days"]["shipped"] == "2" and len(rows) == 2
    sheet = confirmation_sheet()
    assert "### `plan_before_sale` (provisional)" in sheet and "| Date it took effect | |" in sheet
    run = CliRunner().invoke
    r = run(app, ["rules-diff", "insider", "--file", str(f)], env={"COLUMNS": "200"})
    assert r.exit_code == 0 and "trading_days" in r.output
    out = tmp_path / "sheet.md"
    assert run(app, ["rules-sheet", "--out", str(out)]).exit_code == 0 and "Rule confirmation sheet" in out.read_text(
        encoding="utf-8")


def test_the_rehearsal_passes():
    import subprocess
    import sys
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    p = subprocess.run([sys.executable, str(root / "packaging" / "rehearsal.py")], capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=900)
    assert p.returncode == 0, p.stdout[-3000:]
