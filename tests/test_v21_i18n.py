"""v2.1 workstream D: the interface language (plan, section 5.6)."""
import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _catalogues():
    import importlib.util
    spec = importlib.util.spec_from_file_location("i18n_catalogue", ROOT / "packaging" / "i18n_catalogue.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(autouse=True)
def english_after():
    from ashare.i18n import set_language
    yield
    set_language("en")


def test_en_catalogue_matches_the_code():
    """en.json lists exactly the texts the code shows (regenerate with packaging/i18n_catalogue.py)."""
    pytest.importorskip("tkinter")                  # the desktop modules need Tk
    built = _catalogues().english()
    stored = json.loads((ROOT / "ashare" / "i18n" / "en.json").read_text(encoding="utf-8"))
    assert stored == built


def test_every_key_has_chinese_and_none_is_stale():
    from ashare.i18n import source_hash
    en = json.loads((ROOT / "ashare" / "i18n" / "en.json").read_text(encoding="utf-8"))
    zh = json.loads((ROOT / "ashare" / "i18n" / "zh_CN.json").read_text(encoding="utf-8"))
    assert set(zh) == set(en)
    assert all(v["zh"].strip() for v in zh.values())
    stale = [k for k, v in zh.items() if v["en_hash"] != source_hash(en[k])]
    assert not stale, stale[:10]


def test_placeholders_match():
    en = json.loads((ROOT / "ashare" / "i18n" / "en.json").read_text(encoding="utf-8"))
    zh = json.loads((ROOT / "ashare" / "i18n" / "zh_CN.json").read_text(encoding="utf-8"))
    ph = re.compile(r"\{[a-z_]*(?::[^}]*)?\}")
    for k, text in en.items():
        assert sorted(ph.findall(text)) == sorted(ph.findall(zh[k]["zh"])), k


# English phrase -> the glossary's rendering (docs/glossary_zh_CN.md); a phrase in an English text must appear in
# its Chinese text with that rendering
GLOSSARY = {
    "annual report": "年度报告", "earnings forecast": "业绩预告", "flash report": "业绩快报",
    "controlling shareholder": "控股股东", "actual controller": "实际控制人", "top-10 shareholders": "前十名股东",
    "share pledge": "股份质押", "related-party": "关联交易", "external guarantee": "对外担保",
    "restructuring": "重大资产重组", "penalt": "行政处罚", "industry classification": "行业分类",
    "self-test": "自检", "codebook": "变量说明手册", "pseudonymis": "去标识化", "event stud": "事件研究",
    "busy day": "公告密集日", "quote list": "行情列表", "licence class": "许可类别", "winsorise": "缩尾处理",
    "subsidiar": "子公司", "rights issue": "配股", "risk warning": "风险警示", "cninfo": "巨潮资讯网",
    "shenwan": "申万", "csrc": "证监会", "share capital": "股本", "trading calendar": "交易日历",
    "data-quality": "数据质量", "dataset release": "数据集发布", "findings": "校验发现", "catalogue": "目录",
    "point in time": "时点", "fiscal year": "会计年度", "reporting period": "报告期", "r&d investment": "研发投入",
}


def test_glossary_terms_are_rendered_as_approved():
    en = json.loads((ROOT / "ashare" / "i18n" / "en.json").read_text(encoding="utf-8"))
    zh = json.loads((ROOT / "ashare" / "i18n" / "zh_CN.json").read_text(encoding="utf-8"))
    misses = []
    for k, text in en.items():
        low = re.sub(r"\S+\.(csv|json|txt|html)\b", "", text.lower())      # file names are not terms
        for term, rendering in GLOSSARY.items():
            if term in low and rendering not in zh[k]["zh"]:
                misses.append((k, term, zh[k]["zh"]))
    assert not misses, misses[:15]


def test_casual_terms_are_not_used():
    zh = json.loads((ROOT / "ashare" / "i18n" / "zh_CN.json").read_text(encoding="utf-8"))
    for casual in ("年报", "半年报", "中报", "一季报", "三季报", "营收", "归母净利润", "股权质押", "限售股", "流通股",
                   "损益表", "股东大会", "成交额"):
        bad = [k for k, v in zh.items() if casual in v["zh"]]
        assert not bad, (casual, bad[:5])


def test_lookup_falls_back_to_english():
    from ashare.i18n import tr, set_language
    set_language("zh_CN")
    assert tr("ui.output", "Output") == "输出"
    assert tr("ui.output", "Output changed") == "Output changed"           # stale: English shown
    assert tr("no.such.key", "Anything") == "Anything"
    set_language("en")
    assert tr("ui.output", "Output") == "Output"


def test_every_page_action_and_field_appears_in_chinese():
    pytest.importorskip("tkinter")                  # the desktop modules need Tk
    from ashare import gui
    from ashare.i18n import (set_language, section_title, action_label, action_note, field_label, field_hint,
                             group_label)
    set_language("zh_CN")
    cjk = re.compile(r"[一-鿿]")
    for sec in gui.SECTIONS:
        assert cjk.search(section_title(sec)), sec["id"]
        if sec.get("group"):
            assert cjk.search(group_label(sec["group"]))
        for a in sec["actions"]:
            assert cjk.search(action_label(a)), a["key"]
            if a.get("note"):
                assert cjk.search(action_note(a)), a["key"]
            for f in a["fields"]:
                assert cjk.search(field_label(a, f)) or f["label"] in ("SQL",), (a["key"], f["key"])
                if f.get("hint"):
                    assert field_hint(a, f).strip()


def test_form_checks_are_in_the_interface_language():
    pytest.importorskip("tkinter")                  # the desktop modules need Tk
    from ashare.gui import check_values
    from ashare.i18n import set_language
    f = {"key": "on", "label": "Date", "kind": "date", "required": True}
    set_language("zh_CN")
    assert check_values([f], {"on": ""}, label_of=lambda x: "日期") == ["“日期”为必填项。"]
    set_language("en")
    assert check_values([f], {"on": "x"}) == ["Date must be a date like 2026-01-31."]


def test_the_language_never_changes_a_command_or_a_dataset(db, tmp_path):
    """Plan 5.6: the same form gives the same command, and a panel built in Chinese mode is identical."""
    pytest.importorskip("tkinter")                  # the desktop modules need Tk
    from ashare import gui
    from ashare.i18n import set_language
    from ashare.panel import write_panel
    action = next(a for s in gui.SECTIONS for a in s["actions"] if a["command"] == "build-panel")
    vals = {f["key"]: f["default"] for f in action["fields"]}
    result = {"rows": [{"code": "600519", "name": "贵州茅台", "period": "2025-12-31", "revenue": 1.5}],
              "params": {"variables": ["revenue"], "unit": "year", "start": "2025-01-01", "end": "2025-12-31"},
              "max_published": None, "dropped": {}}
    out = {}
    for lang in ("en", "zh_CN"):
        set_language(lang)
        out[lang] = gui.build_argv(action["command"], action["fields"], vals)
        write_panel(result, str(tmp_path / lang), "p", ("csv", "dta"))
    assert out["en"] == out["zh_CN"]
    def same(name):                     # a Stata file records the minute it was written; nothing else may differ
        return re.sub(rb"<timestamp>.*?</timestamp>", b"", (tmp_path / "en" / name).read_bytes()) == \
            re.sub(rb"<timestamp>.*?</timestamp>", b"", (tmp_path / "zh_CN" / name).read_bytes())
    for name in ("p.csv", "p.dta", "p_codebook.md", "p_types.csv", "p_load.R"):
        assert same(name), name
    m = [json.loads((tmp_path / lang / "p_manifest.json").read_text(encoding="utf-8")) for lang in ("en", "zh_CN")]
    for x in m:
        x.pop("created_at")
        x["files"].pop("p.dta")
    assert m[0] == m[1]


def test_default_language_follows_the_locale(monkeypatch):
    from ashare.i18n import default_language
    import locale
    monkeypatch.setattr(locale, "getlocale", lambda: (None, None))
    for var in ("LC_ALL", "LC_MESSAGES"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("LANG", "zh_CN.UTF-8")
    assert default_language() == "zh_CN"
    monkeypatch.setenv("LANG", "en_GB.UTF-8")
    assert default_language() == "en"


def test_friendly_errors_follow_the_language():
    import httpx
    from ashare.errors import friendly_error
    from ashare.i18n import set_language
    exc = httpx.ConnectError("x")
    assert "could not reach" in friendly_error(exc)
    set_language("zh_CN")
    assert "本机无法连接数据源" in friendly_error(exc)


def test_the_window_switches_language_keeping_forms_and_output(tmp_path, monkeypatch):
    import os
    tk = pytest.importorskip("tkinter")
    if not os.environ.get("DISPLAY") and os.name != "nt":
        pytest.skip("no display")
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    from ashare import gui
    monkeypatch.setattr(gui.App, "_init_db", lambda self: None)       # no background thread without a main loop
    gui.save_settings({"data_folder": str(tmp_path / "data"), "language": "en"})
    cwd = os.getcwd()
    try:
        app = gui.App()
    except tk.TclError:
        pytest.skip("no display")
    try:
        app.update()
        assert app.nav["universe"].cget("text").endswith("Universe")
        form = app._forms["action.topology.topology"]
        form["codes"].set("688981")
        app._log("previous output\n")
        app._drain()
        app.show("topology")
        app.switch_language("zh_CN")
        app.update()
        assert app.nav["universe"].cget("text").endswith("上市公司名录")
        assert app.nav["topology"].cget("text") == "拓扑视图"
        assert app._forms["action.topology.topology"]["codes"].get() == "688981"
        assert "previous output" in app.log.get("1.0", "end")
        assert app._current == "topology"
        assert gui.load_settings()["language"] == "zh_CN"
        app.busy = True                                   # locked during an action
        app.switch_language("en")
        assert app.nav["topology"].cget("text") == "拓扑视图"
        app.busy = False
        app.switch_language("en")
        app.update()
        assert app.nav["topology"].cget("text") == "Topology"
    finally:
        app.destroy()
        os.chdir(cwd)
