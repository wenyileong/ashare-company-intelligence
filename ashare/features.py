"""Feature switches (v2.3.0, plan section "Scaffolding first"; two added in v2.4.0).

Every feature added in v2.3 is built behind a switch, so that a fault can be isolated by switching one feature off
without touching the others. Switching a feature off never deletes its data.

The switches are kept in ``features.json`` in the data folder, so the desktop program and the command line share them
and they move with the folder. ``ASHARE_FEATURES`` overrides them for one run, as ``name=on,other=off`` (used by the
tests, which run the suite with every switch off as well as at the defaults).
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Feature:
    name: str
    title: str
    default: bool
    part: str
    note: str = ""


FEATURES: dict[str, Feature] = {f.name: f for f in [
    Feature("storage.relative_paths", "Relative paths for new downloads", True, "B1 phase 3",
            "New documents and archived responses are stored relative to the data folder."),
    Feature("storage.normalise", "Normalise stored paths", True, "B1 phase 4",
            "Allows the 'Normalise paths' command; it runs only when asked, after a preview and a backup."),
    Feature("storage.move", "Move or adopt the data folder", True, "B1 phase 5",
            "Allows the 'Move data folder' command; it runs only when asked, after a dry run."),
    Feature("jobs.ledger", "Job ledger", True, "B3", "Records every unit of work; never decides what is skipped."),
    Feature("outputs.register", "Outputs register", True, "B11", "Records every output the program writes."),
    Feature("viz.interactive", "Interactive charts", True, "B4", "Zoom, pan and exact readouts on every chart; off "
            "writes the pages as in v2.2."),
    Feature("timeliness", "Disclosure timeliness", True, "B5", "Reporting delays against the legal deadlines."),
    Feature("insider", "Directors' and officers' share dealings", False, "B6", "Experimental extractor."),
    Feature("gleif", "Entity identifiers from GLEIF", False, "B7", "A network source; on when you choose."),
    Feature("network_measures", "Ownership network measures", True, "B8", "Optional panel variables."),
    Feature("watchlists", "Watchlists and alerts", True, "B9", "Alerts inside the program only."),
    Feature("timestamps", "Trusted timestamps", False, "B10", "Not available in v2.3.0 (scaffold only)."),
    # v2.4.0
    Feature("rules.overrides", "Updated rule packs from the data folder", True, "v2.4 A",
            "Off: only the rule packs shipped with the program are used."),
    Feature("progress.bar", "Percentage progress bar", True, "v2.4 C",
            "Off: the moving bar of v2.3, with progress only as lines in the Output pane."),
]}


class FeatureOff(RuntimeError):
    """Raised by a command whose feature is switched off."""


def data_root() -> Path:
    """The data folder: ``ASHARE_HOME`` when set, else the folder of the database, else the working folder."""
    home = os.environ.get("ASHARE_HOME")
    if home:
        return Path(home).resolve()
    db = os.environ.get("ASHARE_DB")
    if db:
        return Path(db).resolve().parent
    return Path.cwd().resolve()


def _file() -> Path:
    return data_root() / "features.json"


def _stored() -> dict:
    try:
        data = json.loads(_file().read_text(encoding="utf-8"))
        return {k: bool(v) for k, v in data.items() if k in FEATURES}
    except (OSError, ValueError, AttributeError):
        return {}


def _overrides() -> dict:
    out = {}
    for part in (os.environ.get("ASHARE_FEATURES") or "").split(","):
        if "=" not in part:
            continue
        k, v = (x.strip() for x in part.split("=", 1))
        if k == "all":
            out.update({n: v.lower() in ("1", "on", "true", "yes") for n in FEATURES})
        elif k in FEATURES:
            out[k] = v.lower() in ("1", "on", "true", "yes")
    return out


def enabled(name: str) -> bool:
    if name not in FEATURES:
        raise KeyError(f"unknown feature: {name}")
    o = _overrides()
    if name in o:
        return o[name]
    return _stored().get(name, FEATURES[name].default)


def require(name: str) -> None:
    if not enabled(name):
        f = FEATURES[name]
        raise FeatureOff(f"'{f.title}' is switched off (Settings > Diagnostics, or 'ashare-cli features "
                         f"--on {name}').")


def set_feature(name: str, on: bool) -> dict:
    if name not in FEATURES:
        raise KeyError(f"unknown feature: {name}")
    data = _stored()
    data[name] = bool(on)
    p = _file()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")
    return status()


def status() -> list[dict]:
    o, st = _overrides(), _stored()
    rows = []
    for f in FEATURES.values():
        source = "override" if f.name in o else "setting" if f.name in st else "default"
        rows.append({"name": f.name, "title": f.title, "part": f.part, "on": enabled(f.name),
                     "default": f.default, "source": source, "note": f.note})
    return rows


def diagnostics() -> dict:
    """The switches, the schema revision and the data folder, for Settings > Diagnostics."""
    out = {"data_root": str(data_root()), "features": status()}
    try:
        from .migrate import current, head
        out["schema"] = {"current": current(), "head": head()}
    except Exception as exc:                       # noqa: BLE001
        out["schema"] = {"error": str(exc)}
    try:
        from .rulepacks import listing
        out["rule_packs"] = [{k: r[k] for k in ("pack", "version", "status", "in_use", "provisional", "problem")}
                             for r in listing()]
    except Exception as exc:                       # noqa: BLE001
        out["rule_packs"] = [{"pack": "?", "problem": str(exc)}]
    from . import __version__
    out["version"] = __version__
    return out
