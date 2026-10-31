"""Build the interface catalogues (v2.1, plan workstream D).

    python packaging/i18n_catalogue.py            write ashare/i18n/en.json and zh_CN.json
    python packaging/i18n_catalogue.py --todo     list the English texts that have no Chinese yet

English is written in the code, once, where it is used: the pages, actions and fields of ``gui.SECTIONS`` (keys from
their identifiers) and every ``tr("key", "English")`` call in the desktop's modules. ``en.json`` is that list.

The Chinese comes from ``packaging/i18n/zh_CN_source.json``, which maps each English text to its rendering under the
approved glossary (``docs/glossary_zh_CN.md``); an entry ``"@<key>"`` gives one key a rendering of its own where the
same English needs another word in context. ``zh_CN.json`` records, for each key, the Chinese and a hash of the
English it was translated from, so that a later change to the English shows as stale (and English is shown instead).
"""
from __future__ import annotations

import ast
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
MODULES = ("ashare/gui.py", "ashare/gui_review.py", "ashare/errors.py")
SOURCE = ROOT / "packaging" / "i18n" / "zh_CN_source.json"


def _add(out: dict, key: str, en: str, where: str) -> None:
    if not en:
        return
    if key in out and out[key] != en:
        raise SystemExit(f"key {key} has two English texts ({where}): {out[key]!r} and {en!r}")
    out[key] = en


def section_strings() -> dict:
    from ashare.gui import SECTIONS
    out: dict = {}
    for sec in SECTIONS:
        _add(out, f"section.{sec['id']}.title", re.sub(r"^\d+\s+", "", sec["title"]), "SECTIONS")
        _add(out, f"section.{sec['id']}.intro", sec.get("intro") or "", "SECTIONS")
        if sec.get("group"):
            _add(out, f"group.{sec['group'].lower()}", sec["group"], "SECTIONS")
        for a in sec["actions"]:
            _add(out, f"{a['key']}.label", a["label"], a["key"])
            _add(out, f"{a['key']}.note", a.get("note") or "", a["key"])
            for f in a["fields"]:
                _add(out, f"{a['key']}.field.{f['key']}.label", f["label"], a["key"])
                _add(out, f"{a['key']}.field.{f['key']}.hint", f.get("hint") or "", a["key"])
    return out


def call_strings() -> dict:
    out: dict = {}
    for mod in MODULES:
        tree = ast.parse((ROOT / mod).read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and getattr(node.func, "id", None) == "tr":
                if len(node.args) != 2:
                    raise SystemExit(f"{mod}:{node.lineno}: tr() needs a key and the English text")
                try:
                    key, en = ast.literal_eval(node.args[0]), ast.literal_eval(node.args[1])
                except ValueError:
                    raise SystemExit(f"{mod}:{node.lineno}: tr() needs literal strings (no f-strings); "
                                     "use .format() on the result")
                _add(out, key, en, f"{mod}:{node.lineno}")
    return out


def english() -> dict:
    out = section_strings()
    for k, v in call_strings().items():
        _add(out, k, v, "tr()")
    return dict(sorted(out.items()))


def chinese(en: dict) -> tuple[dict, list[str]]:
    from ashare.i18n import source_hash
    src = json.loads(SOURCE.read_text(encoding="utf-8")) if SOURCE.exists() else {}
    out, todo = {}, []
    for key, text in en.items():
        zh = src.get("@" + key) or src.get(text)
        if not zh:
            todo.append(text)
            continue
        out[key] = {"zh": zh, "en_hash": source_hash(text)}
    return out, sorted(set(todo))


def main(argv: list[str]) -> int:
    en = english()
    zh, todo = chinese(en)
    if "--todo" in argv:
        print(json.dumps(todo, ensure_ascii=False, indent=1))
        return 0
    (ROOT / "ashare" / "i18n" / "en.json").write_text(json.dumps(en, ensure_ascii=False, indent=1) + "\n",
                                                      encoding="utf-8")
    (ROOT / "ashare" / "i18n" / "zh_CN.json").write_text(json.dumps(zh, ensure_ascii=False, indent=1,
                                                                    sort_keys=True) + "\n", encoding="utf-8")
    print(f"{len(en)} keys; {len(set(en.values()))} distinct English texts; {len(zh)} translated; "
          f"{len(todo)} distinct texts without Chinese")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
