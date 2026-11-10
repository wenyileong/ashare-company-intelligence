"""v2.4.0: swappable rule packs, share-dealing flags on provisional rules, the percentage progress bar (R3), GLEIF
parents on the ego map and regulatory readiness by date (docs/plan_v2.4.md)."""
import json
import time
from datetime import date, timedelta
from types import SimpleNamespace

import pytest

from ashare import progressbar as pb


@pytest.fixture(autouse=True)
def _fresh_packs():
    from ashare.rulepacks import clear_cache
    clear_cache()
    pb.set_sink(None)
    yield
    clear_cache()
    pb.set_sink(None)


# --- Part A: rule packs ----------------------------------------------------------------------------------------------

def test_bundled_packs_are_valid_marked_swappable_and_returned_unchanged():
    from ashare.rulepacks import PACKS, bundled_path, load, validate
    for name in PACKS:
        raw = json.loads(bundled_path(name).read_text(encoding="utf-8"))
        pk = load(name)
        assert pk.origin == "bundled" and pk.data == raw                     # no override: exactly the bundled data
        assert raw["swappable"] is True and raw["pack"] == name and "SWAPPABLE" in raw["how_to_update"]
        assert validate(name, raw) == ([], [])
    assert load("insider").status == "provisional" and load("insider").provisional_ids() == [
        "report_within", "plan_before_sale", "blackout"]
    assert "PROVISIONAL RULES, SWAPPABLE" in load("insider").data["note"]


def test_the_modules_read_through_the_loader(tmp_path):
    from ashare import timeliness, insider, network_measures
    from ashare.rulepacks import export, clear_cache
    assert timeliness.rules()["version"] == "deadlines-1" and insider.rules()["version"] == "insider-1"
    export("nominees")
    p = tmp_path / "rules" / "nominee_holders.json"
    d = json.loads(p.read_text(encoding="utf-8"))
    d["names"].append("某某代持账户")
    d["version"] = "nominees-2"
    time.sleep(0.01)
    p.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
    clear_cache()
    assert network_measures._norm("某某代持账户") in network_measures.nominees()   # seen without a restart


def test_an_updated_pack_applies_from_the_next_action_and_reset_keeps_it(tmp_path):
    from ashare.rulepacks import export, import_pack, load, reset
    from ashare.timeliness import deadline
    assert deadline("annual_report", "2024-12-31", "FY")[0] == "2025-04-30"
    f = tmp_path / "edited.json"
    export("deadlines", f)
    d = json.loads(f.read_text(encoding="utf-8"))
    d["version"] = "deadlines-test"
    d["rules"][0]["months_after_period_end"] = 3
    d["rules"][0]["status"] = "confirmed"
    d["rules"][0]["verified"] = "checked against the official text (test)"
    f.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
    preview = import_pack("deadlines", f)                              # without apply: only checked
    assert preview["ok"] and not preview["applied"] and load("deadlines").origin == "bundled"
    r = import_pack("deadlines", f, apply=True)
    assert r["applied"] and "deadlines-test (data folder; provisional)" in r["now"]
    assert deadline("annual_report", "2024-12-31", "FY")[0] == "2025-03-31"
    assert (tmp_path / "rules" / "_changes.jsonl").exists()
    back = reset("deadlines", apply=True)
    assert back["applied"] and list((tmp_path / "rules" / "_replaced").glob("disclosure_deadlines.*.json"))
    assert deadline("annual_report", "2024-12-31", "FY")[0] == "2025-04-30"


def test_an_invalid_pack_is_refused_and_a_broken_override_falls_back(tmp_path):
    from ashare.rulepacks import check, import_pack, load, override_path
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"pack": "insider", "version": "x", "rules": [
        {"id": "report_within", "trading_days": -1, "status": "maybe", "source": ""},
        {"id": "made_up", "status": "confirmed", "source": "s"}]}), encoding="utf-8")
    c = check("insider", bad)
    assert not c["ok"] and len(c["errors"]) >= 4
    assert any("unknown id" in e for e in c["errors"])
    assert not import_pack("insider", bad, apply=True)["applied"]
    p = override_path("insider")
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("{not json", encoding="utf-8")
    pk = load("insider")
    assert pk.origin == "bundled" and "could not be read" in pk.fallback and "was not used" in pk.describe()


def test_the_switch_off_uses_only_the_bundled_packs(tmp_path, monkeypatch):
    from ashare.rulepacks import export, load
    export("insider")
    assert load("insider").origin == "data folder"
    monkeypatch.setenv("ASHARE_FEATURES", "rules.overrides=off")
    assert load("insider").origin == "bundled"


def test_withdrawn_rules_are_not_applied_and_diagnostics_list_the_packs(tmp_path):
    from ashare.rulepacks import export, load, clear_cache
    from ashare.features import diagnostics
    export("insider")
    p = tmp_path / "rules" / "insider_rules.json"
    d = json.loads(p.read_text(encoding="utf-8"))
    for r in d["rules"]:
        r["status"] = "withdrawn"
    p.write_text(json.dumps(d), encoding="utf-8")
    clear_cache()
    assert load("insider").applied() == [] and load("insider").status == "withdrawn"
    packs = {r["pack"]: r for r in diagnostics()["rule_packs"]}
    assert packs["insider"]["in_use"] == "data folder" and packs["deadlines"]["status"] == "provisional"


def test_rule_commands(tmp_path):
    from typer.testing import CliRunner
    from ashare.cli import app
    run = CliRunner().invoke
    r = run(app, ["rules-list"], env={"COLUMNS": "160"})
    assert r.exit_code == 0 and "insider-1" in r.output and "provisional" in r.output
    r = run(app, ["rules-show", "insider"])
    assert "plan_before_sale" in r.output and "provisional" in r.output
    out = tmp_path / "copy.json"
    assert run(app, ["rules-export", "insider", "--out", str(out)]).exit_code == 0
    assert run(app, ["rules-check", "insider", "--file", str(out)]).exit_code == 0
    r = run(app, ["rules-import", "insider", str(out)])
    assert "Not installed" in r.output
    r = run(app, ["rules-import", "insider", str(out), "--apply"])
    assert "Installed" in r.output
    assert "Returned to the bundled pack" in run(app, ["rules-reset", "insider", "--apply"]).output
    assert run(app, ["rules-show", "nonsense"]).exit_code == 1


# --- Part B: share-dealing flags -------------------------------------------------------------------------------------

def _calendar(start, days):
    from ashare.models import SessionLocal, TradingDay
    s = SessionLocal()
    d = date.fromisoformat(start)
    for i in range(days):
        x = d + timedelta(days=i)
        s.add(TradingDay(exchange="SSE", trade_date=x.isoformat(), is_open=int(x.weekday() < 5), source="test"))
    s.commit()
    s.close()


def _dealing(company, deal, published, direction="SELL", shares=10000, method=None):
    from ashare.models import SessionLocal
    from ashare.models_v23 import InsiderDealing
    s = SessionLocal()
    s.add(InsiderDealing(company_id=company.id, person_name="张三", deal_date=deal, direction=direction,
                         shares=shares, published_date=published, method=method))
    s.commit()
    s.close()


def _disclosure(company, d, title, kind="other"):
    from ashare.models import SessionLocal, Disclosure
    s = SessionLocal()
    s.add(Disclosure(company_id=company.id, announcement_id=f"{d}{title}"[:60], announcement_date=d, title_cn=title,
                     kind=kind))
    s.commit()
    s.close()


def test_rule_three_and_late_report_with_the_calendar(db, company, monkeypatch):
    from ashare.insider import flags
    monkeypatch.setenv("ASHARE_FEATURES", "insider=on")
    _calendar("2025-01-01", 120)
    _disclosure(company, "2025-03-03", "关于董事减持股份计划的预披露公告")
    _dealing(company, "2025-03-10", "2025-03-17")              # plan 5 trading days before; reported 5 days after
    _dealing(company, "2025-04-14", "2025-04-15")              # plan 30 trading days before; on time
    rows = {r["deal_date"]: r for r in flags("600519")["rows"]}
    first = rows["2025-03-10"]["flags"]
    assert "reduction plan announced 5 trading days before the sale (rule: at least 15)" in first
    assert "reported 5 trading days after the dealing (rule: within 2)" in first
    assert "method not given, taken as a sale by auction" in first and first.count("(provisional rule)") == 2
    assert rows["2025-04-14"]["flags"] == ""
    assert flags("600519", confirmed_only=True)["rows"][0]["flags"] == ""


def test_a_sale_without_any_plan_and_without_a_calendar(db, company, monkeypatch):
    from ashare.insider import flags
    monkeypatch.setenv("ASHARE_FEATURES", "insider=on")
    _dealing(company, "2025-03-10", "2025-03-20")
    _dealing(company, "2025-03-11", "2025-03-20", direction="BUY")
    _dealing(company, "2025-03-12", "2025-03-20", method="大宗交易")
    r = flags("600519")
    by = {x["deal_date"]: x for x in r["rows"]}
    assert "no reduction plan announced in the 200 days before the sale" in by["2025-03-10"]["flags"]
    assert by["2025-03-11"]["flags"] == "" and by["2025-03-12"]["flags"] == ""       # a purchase; a block trade
    assert "report_within: 3 dealing(s) not checked" in r["note"]


def test_a_rule_applies_only_from_its_effective_date(db, company, monkeypatch, tmp_path):
    from ashare.insider import flags
    from ashare.rulepacks import export, clear_cache
    monkeypatch.setenv("ASHARE_FEATURES", "insider=on")
    _disclosure(company, "2025-03-14", "2024年年度报告", kind="annual_report")
    _dealing(company, "2025-03-10", "2025-03-11", direction="BUY")
    assert "4 day(s) before a annual report" in flags("600519")["rows"][0]["flags"]
    export("insider")
    p = tmp_path / "rules" / "insider_rules.json"
    d = json.loads(p.read_text(encoding="utf-8"))
    for r in d["rules"]:
        r["effective_from"] = "2025-06-01"
    p.write_text(json.dumps(d), encoding="utf-8")
    clear_cache()
    assert flags("600519")["rows"][0]["flags"] == ""


def test_panel_variables_for_share_dealings(db, company, monkeypatch):
    from ashare.insider import company_measures
    from ashare.models import SessionLocal
    from ashare.panel import variables
    v = variables()
    assert v["insider_net_buy_12m"].group == "insider" and "provisional" in v["insider_window_sales_12m"].definition
    _disclosure(company, "2025-03-14", "2024年年度报告", kind="annual_report")
    _dealing(company, "2025-03-10", "2025-03-11", direction="SELL", shares=3000)
    _dealing(company, "2025-01-10", "2025-01-11", direction="BUY", shares=10000)
    _dealing(company, "2023-01-10", "2023-01-11", direction="BUY", shares=99999)      # outside the year
    _dealing(company, "2025-06-10", "2025-12-31", direction="BUY", shares=55555)      # published after the date
    s = SessionLocal()
    m = company_measures(s, company, "2025-06-30")
    s.close()
    assert m == {"net_buy": 7000.0, "window_sales": 1.0, "n": 2}
    ctx = SimpleNamespace(code="600519", measure_date="2025-06-30", cutoff="2025-06-30", cache={})
    assert v["insider_net_buy_12m"].getter(ctx)[0] is None                           # the switch is off
    monkeypatch.setenv("ASHARE_FEATURES", "insider=on")
    assert v["insider_net_buy_12m"].getter(ctx)[0] == 7000.0
    assert v["insider_window_sales_12m"].getter(ctx)[0] == 1.0


# --- Part C: progress -------------------------------------------------------------------------------------------------

def test_counter_reports_numbers_throttled_with_first_and_last(monkeypatch):
    got = []
    pb.set_sink(got.append)
    c = pb.Counter(1000, "documents")
    for _ in range(1000):
        c.step()
    assert got[0]["done"] == 0 and got[-1]["done"] == 1000 and got[-1]["total"] == 1000
    assert len(got) < 20                                         # throttled to four a second
    assert pb.fraction(got[-1]) == 1.0 and pb.render(got[-1]).startswith("[" + "█" * 20 + "]  100%")


def test_unknown_and_growing_totals_never_pass_100_percent():
    got = []
    pb.set_sink(got.append)
    c = pb.Counter(None, "pages")
    assert pb.fraction(got[-1]) is None and "counting…" in pb.text(got[-1])
    c.set_total(4)
    for _ in range(6):
        c.step()
        time.sleep(0.26)
    assert all((pb.fraction(d) or 0) <= 1 for d in got)
    assert got[-1]["total"] == 6 and got[-1].get("note") == "about"


def test_resume_starts_the_bar_at_the_count_done():
    from ashare.extractstate import Progress
    got = []
    pb.set_sink(got.append)
    lines = []
    p = Progress(10, lines.append, start=90)
    assert got[0]["done"] == 90 and got[0]["total"] == 100 and got[0]["note"] == "resuming"
    for _ in range(10):
        p.step()
    assert got[-1]["done"] == 100 and lines[-1].startswith("  10 of 10 documents")


def test_a_job_bar_shows_the_action_within_it():
    got = []
    pb.set_sink(got.append)
    pb.stage(2, 3, "prices")
    outer = pb.Counter(4, "items", outer=True)
    inner = pb.Counter(10, "companies")
    for _ in range(10):
        inner.step()
    d = got[-1]
    assert (d["done"], d["total"], d["stage"], d["stages"]) == (0, 4, 2, 3)
    assert d["sub"] == {"done": 10, "total": 10, "unit": "companies"}
    assert "Stage 2 of 3: prices" in pb.text(d) and "within it 10 of 10 companies" in pb.text(d)
    outer.step()


def test_machine_lines_terminal_and_files(monkeypatch, capsys):
    monkeypatch.setenv("ASHARE_PROGRESS", "machine")
    pb.Counter(3, "days").step()
    out = capsys.readouterr().out.splitlines()
    assert out and all(pb.parse(x) for x in out) and pb.parse(out[0])["unit"] == "days"
    monkeypatch.setenv("ASHARE_PROGRESS", "")
    pb.Counter(3, "days").step()                                  # not a terminal: nothing extra
    assert capsys.readouterr().out == ""
    monkeypatch.setenv("ASHARE_PROGRESS", "machine")
    monkeypatch.setenv("ASHARE_FEATURES", "progress.bar=off")
    pb.Counter(3, "days").step()
    assert capsys.readouterr().out == ""


def test_terminal_bar_is_redrawn_on_one_line(monkeypatch):
    import io

    class Tty(io.StringIO):
        def isatty(self):
            return True
    t = Tty()
    monkeypatch.setattr("sys.stdout", t)
    monkeypatch.delenv("ASHARE_PROGRESS", raising=False)
    c = pb.Counter(2, "files")
    c.step()
    c.step()
    pb.end()
    text = t.getvalue()
    assert "\r\x1b[K[" in text and "100%  2 of 2 files" in text and text.endswith("\n") and text.count("\n") == 1


def test_command_progress_reaches_the_desktop_sink(db, company):
    """run_command passes each report to the desktop program and leaves no control lines in the output."""
    pytest.importorskip("tkinter")
    from ashare.gui import run_command
    got = []
    code, out = run_command(["build-panel", "--codes", "600519", "--start", "2024-01-01", "--end", "2024-12-31",
                             "--name", "t", "--variables", "revenue"], on_progress=got.append)
    assert any(d.get("unit") == "companies" for d in got), out and pb.MARK not in out
    assert pb._sink is None                                       # removed after the action


def test_desktop_status_bar_turns_determinate_and_resets(tmp_path, monkeypatch):
    import os
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
        app.busy = True
        app._running_label = "Read"
        app.progress.pack(side="left")
        app._on_progress({"done": None, "total": None, "unit": "pages"})
        assert str(app.progress.cget("mode")) == "indeterminate" and "counting…" in app.status.get()
        app._on_progress({"done": 26, "total": 50, "unit": "documents", "left": 90})
        assert str(app.progress.cget("mode")) == "determinate" and int(float(app.progress.cget("value"))) == 520
        assert app.status.get() == "Read: 52%  26 of 50 documents; about 2 min left"
        app._done({"command": "x", "label": "x"}, 0, "")
        assert str(app.progress.cget("mode")) == "indeterminate" and int(float(app.progress.cget("value"))) == 0
    finally:
        app.destroy()
        os.chdir(cwd)


# --- Part D: loose ends ----------------------------------------------------------------------------------------------

def test_gleif_parents_are_their_own_relation_on_the_ego_map(db):
    from ashare.models import SessionLocal
    from ashare.models_v23 import ExternalRelationship
    from ashare.viz.graph import Graph, RELATIONS
    from ashare.viz.views.ego_map import EgoMapView
    assert "GLEIF_PARENT" in RELATIONS
    s = SessionLocal()
    s.add_all([ExternalRelationship(child_lei="LEICHILD", parent_lei="LEIPARENT", relation="DIRECT_PARENT",
                                    parent_name="母公司有限公司", observed_date="2026-01-05"),
               ExternalRelationship(child_lei="LEICHILD", parent_lei="LEILATER", relation="ULTIMATE_PARENT",
                                    parent_name="后来的公司", observed_date="2026-09-01")])
    s.commit()
    g = Graph()
    g.node("company:600519", "company", "贵州茅台", lei="LEICHILD")
    n = EgoMapView()._gleif_parents(SimpleNamespace(s=s, as_of="2026-06-30"), g)
    s.close()
    assert n == 1                                                  # the later link is not known by the date
    e = next(iter(g.edges.values()))
    assert e["relation"] == "GLEIF_PARENT" and e["target"] == "company:600519" and e["label"] == "direct parent"
    assert g.nodes[e["source"]]["label"] == "母公司有限公司" and g.nodes[e["source"]]["lei"] == "LEIPARENT"


def test_regulatory_readiness_counts_only_events_published_by_the_date(db, company):
    from ashare.models import SessionLocal, RegulatoryEvent
    from ashare.viz.views import _checks
    s = SessionLocal()
    s.add(RegulatoryEvent(company_id=company.id, event_id="E1", event_type="PENALTY",
                          legal_classification="ADMINISTRATIVE_PENALTY", announcement_date="2025-06-01",
                          extraction_method="TEST", source="test"))
    s.commit()
    s.close()
    check = _checks.regulatory().check
    assert check({"code": "600519", "as_of": "2025-01-01"})[0] == _checks.MISSING
    assert check({"code": "600519", "as_of": "2025-12-31"})[0] == _checks.MET
