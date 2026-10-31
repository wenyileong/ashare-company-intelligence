"""The desktop's interface language (v2.1, plan workstream D): English, or Simplified Chinese.

* English is the source and the fallback. Each text is written once, in English, where it is used, with a stable
  key: ``tr("ui.output", "Output")``, or the keys given to the pages, actions and fields of ``gui.SECTIONS``.
* ``en.json`` lists every key with its English text (written by ``packaging/i18n_catalogue.py`` from the code, and
  checked against it by the tests); ``zh_CN.json`` gives each key its Chinese text and a hash of the English it was
  translated from.
* A Chinese entry whose English has changed since is stale and is not shown: the English is, until the translation
  is reviewed. A missing entry also shows English, never a blank.

What stays in English in both languages (plan, section 5.2): command names and the run log, each command's own
output, variable, column and file names, and the source data. So the interface language can never change a dataset.
"""
from __future__ import annotations

import hashlib
import json
import locale
import os
from pathlib import Path

HERE = Path(__file__).resolve().parent
LANGUAGES = {"en": "English", "zh_CN": "中文"}
_lang = "en"
_zh: dict | None = None


def source_hash(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:10]


def _catalogue() -> dict:
    global _zh
    if _zh is None:
        try:
            _zh = json.loads((HERE / "zh_CN.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            _zh = {}
    return _zh


def default_language() -> str:
    """Chinese for a Chinese Windows display language (any zh locale), otherwise English (plan, 5.3)."""
    names = []
    if os.name == "nt":
        try:
            import ctypes
            lang_id = ctypes.windll.kernel32.GetUserDefaultUILanguage()       # type: ignore[attr-defined]
            names.append(locale.windows_locale.get(lang_id, ""))
        except Exception:                                                # noqa: BLE001
            pass
    for var in ("LC_ALL", "LC_MESSAGES", "LANG"):
        names.append(os.environ.get(var, ""))
    try:
        names.append(locale.getlocale()[0] or "")
    except ValueError:
        pass
    return "zh_CN" if any(n.lower().startswith("zh") or n.lower().startswith("chinese") for n in names if n) \
        else "en"


def set_language(code: str | None) -> str:
    global _lang
    _lang = code if code in LANGUAGES else "en"
    return _lang


def language() -> str:
    return _lang


def tr(key: str, en: str) -> str:
    """The text for ``key`` in the interface language; ``en`` is the English source."""
    if _lang == "en" or not en:
        return en
    entry = _catalogue().get(key)
    if not entry or not entry.get("zh") or entry.get("en_hash") != source_hash(en):
        return en
    # Tk wraps only at spaces, so a Chinese line broke at the space beside a Latin word ("留空 =" / "默认…") and
    # left a ragged edge; with no-break spaces it wraps character by character, as Chinese text should
    return entry["zh"].replace(" ", "\u00a0")


def is_stale(key: str, en: str) -> bool:
    entry = _catalogue().get(key)
    return bool(entry) and entry.get("en_hash") != source_hash(en)


# --- the pages, actions and fields of the desktop (gui.SECTIONS) -----------------------------------------------------

def section_title(sec: dict) -> str:
    import re
    m = re.match(r"^(\d+\s+)(.*)$", sec["title"])
    num, base = (m.group(1), m.group(2)) if m else ("", sec["title"])
    return num + tr(f"section.{sec['id']}.title", base)


def section_intro(sec: dict) -> str:
    return tr(f"section.{sec['id']}.intro", sec.get("intro") or "")


def group_label(group: str) -> str:
    return tr(f"group.{group.lower()}", group) if group else ""


def action_label(action: dict) -> str:
    return tr(f"{action['key']}.label", action["label"])


def action_note(action: dict) -> str:
    return tr(f"{action['key']}.note", action.get("note") or "")


def field_label(action: dict, f: dict) -> str:
    return tr(f"{action['key']}.field.{f['key']}.label", f["label"])


def field_hint(action: dict, f: dict) -> str:
    return tr(f"{action['key']}.field.{f['key']}.hint", f.get("hint") or "")
