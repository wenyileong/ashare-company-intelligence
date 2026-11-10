"""Swappable rule packs (v2.4.0, plan Part A).

The legal and reference rules the program applies are kept as **packs**: JSON files that can be replaced without a new
version of the program. Each pack, and each rule in it, carries a status:

* ``provisional``: applied, and every result it produces says so (the author has not yet confirmed the rule against
  the official text);
* ``confirmed``: applied as it is;
* ``withdrawn``: kept for the record, not applied.

The bundled packs ship in ``ashare/rules`` and are never edited. An updated pack is placed in the data folder's
``rules`` folder (``rules-import``), where it takes precedence over the bundled one while the switch
``rules.overrides`` is on. Every pack is validated when it is imported and when it is loaded. An override that fails
validation is not used: the bundled pack is used instead, and Diagnostics and the results say why. A replaced pack is
kept in ``rules/_replaced`` and every change is logged in ``rules/_changes.jsonl``.

The loader's cache is keyed by each file's modification time, so an imported pack applies from the next action
without restarting the program.
"""
from __future__ import annotations

import json
import re
import shutil
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

BUNDLED_DIR = Path(__file__).resolve().parent / "rules"
STATUSES = ("provisional", "confirmed", "withdrawn")
APPLIED = ("provisional", "confirmed")
_ISO = re.compile(r"^\d{4}-\d{2}-\d{2}$")
REPORT_KINDS = {"annual_report", "interim_report", "quarterly_report", "earnings_forecast_or_flash",
                "earnings_forecast", "earnings_flash"}


class PackError(ValueError):
    """A pack that cannot be used (unknown, unreadable or invalid)."""


# --- validation ----------------------------------------------------------------------------------------------------

def _pos_int(v) -> bool:
    return isinstance(v, int) and not isinstance(v, bool) and v > 0


def _date_ok(v) -> bool:
    return v is None or (isinstance(v, str) and bool(_ISO.match(v)))


def _common_rule(r: dict, i: int, errors: list, warnings: list, known: set | None) -> None:
    rid = r.get("id")
    where = f"rule {i + 1} ({rid or 'no id'})"
    if not isinstance(rid, str) or not rid:
        errors.append(f"{where}: needs an 'id'")
    elif known is not None and rid not in known:
        errors.append(f"{where}: unknown id; the program knows {', '.join(sorted(known))}")
    st = r.get("status")
    if st not in STATUSES:
        errors.append(f"{where}: 'status' must be one of {', '.join(STATUSES)}")
    if not isinstance(r.get("source"), str) or not r["source"].strip():
        errors.append(f"{where}: needs a 'source' (the instrument and article)")
    for k in ("effective_from", "effective_to"):
        if not _date_ok(r.get(k)):
            errors.append(f"{where}: '{k}' must be a date such as 2024-05-24, or null")
    if r.get("effective_from") and r.get("effective_to") and r["effective_to"] < r["effective_from"]:
        errors.append(f"{where}: 'effective_to' is before 'effective_from'")
    if st == "confirmed" and not r.get("verified"):
        warnings.append(f"{where}: confirmed, but 'verified' does not say how it was checked")


def _validate_insider(d: dict, errors: list, warnings: list) -> None:
    rules = d.get("rules")
    if not isinstance(rules, list) or not rules:
        errors.append("'rules' must be a non-empty list")
        return
    ids = [r.get("id") for r in rules if isinstance(r, dict)]
    if len(ids) != len(set(ids)):
        errors.append("each rule id may appear only once")
    for i, r in enumerate(rules):
        if not isinstance(r, dict):
            errors.append(f"rule {i + 1}: must be an object")
            continue
        _common_rule(r, i, errors, warnings, {"report_within", "plan_before_sale", "blackout"})
        if r.get("id") in ("report_within", "plan_before_sale") and not _pos_int(r.get("trading_days")):
            errors.append(f"rule {r['id']}: 'trading_days' must be a whole number above 0")
        if r.get("id") == "blackout":
            ws = r.get("windows")
            if not isinstance(ws, list) or not ws:
                errors.append("rule blackout: 'windows' must be a non-empty list")
                continue
            for w in ws:
                if not isinstance(w, dict) or w.get("before") not in REPORT_KINDS:
                    errors.append(f"rule blackout: each window needs 'before', one of {', '.join(sorted(REPORT_KINDS))}")
                elif not _pos_int(w.get("calendar_days")):
                    errors.append(f"rule blackout, window before {w['before']}: 'calendar_days' must be a whole "
                                  "number above 0")


def _validate_deadlines(d: dict, errors: list, warnings: list) -> None:
    rules = d.get("rules")
    if not isinstance(rules, list) or not rules:
        errors.append("'rules' must be a non-empty list")
        return
    ids = [r.get("id") for r in rules if isinstance(r, dict)]
    if len(ids) != len(set(ids)):
        errors.append("each rule id may appear only once")
    for i, r in enumerate(rules):
        if not isinstance(r, dict):
            errors.append(f"rule {i + 1}: must be an object")
            continue
        _common_rule(r, i, errors, warnings, None)
        kinds = r.get("kinds")
        if not isinstance(kinds, list) or not kinds or not all(k in REPORT_KINDS for k in kinds):
            errors.append(f"rule {r.get('id')}: 'kinds' must list report kinds such as annual_report")
        pt = r.get("period_type")
        pts = pt if isinstance(pt, list) else [pt]
        if not pts or not all(p in ("FY", "H1", "Q1", "Q3", "Q2", "Q4") for p in pts):
            errors.append(f"rule {r.get('id')}: 'period_type' must be FY, H1, Q1 or Q3 (or a list of them)")
        m = r.get("months_after_period_end")
        if not _pos_int(m) or m > 12:
            errors.append(f"rule {r.get('id')}: 'months_after_period_end' must be a whole number from 1 to 12")


def _validate_nominees(d: dict, errors: list, warnings: list) -> None:
    names = d.get("names")
    if not isinstance(names, list) or not names or not all(isinstance(n, str) and n.strip() for n in names):
        errors.append("'names' must be a non-empty list of holder names")


@dataclass(frozen=True)
class Spec:
    name: str
    file: str
    title: str
    validator: object
    has_rules: bool = True


PACKS: dict[str, Spec] = {s.name: s for s in [
    Spec("insider", "insider_rules.json", "Share dealings of directors, supervisors and senior managers",
         _validate_insider),
    Spec("deadlines", "disclosure_deadlines.json", "Periodic-report deadlines", _validate_deadlines),
    Spec("nominees", "nominee_holders.json", "Nominee and custody accounts", _validate_nominees, has_rules=False),
]}
TOP_KEYS = {"pack", "version", "schema", "swappable", "status", "updated", "note", "how_to_update", "rules",
            "not_applied", "names"}


def _spec(name: str) -> Spec:
    if name not in PACKS:
        raise PackError(f"unknown rule pack '{name}'; the packs are {', '.join(PACKS)}")
    return PACKS[name]


def validate(name: str, data) -> tuple[list[str], list[str]]:
    """(errors, warnings) for a pack's data. A pack with errors is never applied."""
    spec = _spec(name)
    errors: list[str] = []
    warnings: list[str] = []
    if not isinstance(data, dict):
        return ["the file must hold one JSON object"], []
    if data.get("pack") not in (None, name):
        errors.append(f"this file is the '{data.get('pack')}' pack, not '{name}'")
    if not isinstance(data.get("version"), str) or not data["version"].strip():
        errors.append("needs a 'version', such as insider-2")
    if data.get("schema") not in (None, 1):
        errors.append(f"schema {data.get('schema')} is newer than this program understands (1)")
    if data.get("status") is not None and data["status"] not in STATUSES:
        errors.append(f"the pack's 'status' must be one of {', '.join(STATUSES)}")
    spec.validator(data, errors, warnings)
    extra = sorted(set(data) - TOP_KEYS)
    if extra:
        warnings.append(f"fields the program does not use (kept): {', '.join(extra)}")
    return errors, warnings


# --- loading ---------------------------------------------------------------------------------------------------------

@dataclass
class Pack:
    name: str
    data: dict
    origin: str                       # "bundled" or "data folder"
    path: str
    fallback: str | None = None       # why an override was not used
    warnings: list = field(default_factory=list)

    @property
    def version(self) -> str:
        return str(self.data.get("version") or "")

    @property
    def rules(self) -> list[dict]:
        return list(self.data.get("rules") or [])

    @property
    def status(self) -> str:
        return pack_status(self.data)

    def applied(self, confirmed_only: bool = False) -> list[dict]:
        ok = ("confirmed",) if confirmed_only else APPLIED
        return [r for r in self.rules if rule_status(r) in ok]

    def rule(self, rule_id: str, confirmed_only: bool = False) -> dict | None:
        for r in self.applied(confirmed_only):
            if r.get("id") == rule_id:
                return r
        return None

    def provisional_ids(self) -> list[str]:
        return [r["id"] for r in self.rules if rule_status(r) == "provisional"]

    def describe(self) -> str:
        """'insider pack insider-1 (bundled; provisional)', with the fallback reason when there is one."""
        s = f"{self.name} pack {self.version} ({self.origin}; {self.status})"
        if self.fallback:
            s += f"; the updated pack in the data folder was not used: {self.fallback}"
        return s


def rule_status(r: dict) -> str:
    st = r.get("status")
    return st if st in STATUSES else "provisional"


def pack_status(data: dict) -> str:
    """The lowest status of the rules applied: provisional if any applied rule is, else confirmed."""
    if data.get("rules") is None:
        st = data.get("status")
        return st if st in STATUSES else "provisional"
    applied = [rule_status(r) for r in data.get("rules") or [] if rule_status(r) in APPLIED]
    if not applied:
        return "withdrawn"
    return "provisional" if "provisional" in applied else "confirmed"


def bundled_path(name: str) -> Path:
    return BUNDLED_DIR / _spec(name).file


def rules_dir() -> Path:
    from .features import data_root
    return data_root() / "rules"


def override_path(name: str) -> Path:
    return rules_dir() / _spec(name).file


def _overrides_on() -> bool:
    try:
        from .features import enabled
        return enabled("rules.overrides")
    except Exception:                                      # noqa: BLE001
        return True


_CACHE: dict = {}


def _read(path: Path) -> dict:
    key = (str(path), *_stamp(path))
    hit = _CACHE.get(key)
    if hit is not None:
        return hit
    data = json.loads(path.read_text(encoding="utf-8"))
    _CACHE[key] = data
    return data


def _stamp(path: Path) -> tuple:
    try:
        st = path.stat()
        return (st.st_mtime_ns, st.st_size)
    except OSError:
        return (None, None)


def clear_cache() -> None:
    _CACHE.clear()


def load(name: str) -> Pack:
    """The pack in use: the data folder's override when there is a valid one and the switch is on, else the bundled
    pack. Never raises for a bad override (it falls back and says why)."""
    _spec(name)
    fallback = None
    if _overrides_on():
        p = override_path(name)
        if p.exists():
            try:
                data = _read(p)
                errors, warnings = validate(name, data)
                if not errors:
                    return Pack(name, data, "data folder", str(p), None, warnings)
                fallback = "; ".join(errors[:3]) + (" …" if len(errors) > 3 else "")
            except (OSError, ValueError) as exc:
                fallback = f"it could not be read ({exc})"
    p = bundled_path(name)
    data = _read(p)
    return Pack(name, data, "bundled", str(p), fallback, validate(name, data)[1])


def data(name: str) -> dict:
    return load(name).data


def listing() -> list[dict]:
    rows = []
    for name, spec in PACKS.items():
        pk = load(name)
        n = {s: 0 for s in STATUSES}
        for r in pk.rules:
            n[rule_status(r)] += 1
        rows.append({"pack": name, "title": spec.title, "version": pk.version, "status": pk.status,
                     "in_use": pk.origin, "rules": len(pk.rules) if spec.has_rules else "",
                     "provisional": n["provisional"] if spec.has_rules else "",
                     "confirmed": n["confirmed"] if spec.has_rules else "",
                     "withdrawn": n["withdrawn"] if spec.has_rules else "",
                     "problem": pk.fallback or "", "path": pk.path})
    return rows


# --- updating --------------------------------------------------------------------------------------------------------

def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _log(event: dict) -> None:
    d = rules_dir()
    d.mkdir(parents=True, exist_ok=True)
    with (d / "_changes.jsonl").open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({"at": datetime.now(timezone.utc).isoformat(timespec="seconds"), **event},
                            ensure_ascii=False) + "\n")


def _keep(name: str) -> str | None:
    """Move the current override to ``rules/_replaced``; returns where it went."""
    p = override_path(name)
    if not p.exists():
        return None
    dest = rules_dir() / "_replaced" / f"{p.stem}.{_now()}{p.suffix}"
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(p), dest)
    return str(dest)


def check(name: str, file: str | Path | None = None) -> dict:
    """Validate a file, or the pack in use."""
    if file:
        try:
            d = json.loads(Path(file).read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            return {"pack": name, "file": str(file), "ok": False, "errors": [f"could not be read: {exc}"],
                    "warnings": []}
        errors, warnings = validate(name, d)
        return {"pack": name, "file": str(file), "ok": not errors, "errors": errors, "warnings": warnings,
                "version": d.get("version") if isinstance(d, dict) else None,
                "status": pack_status(d) if isinstance(d, dict) and not errors else None}
    pk = load(name)
    errors, warnings = validate(name, pk.data)
    return {"pack": name, "file": pk.path, "ok": not errors, "errors": errors, "warnings": warnings,
            "version": pk.version, "status": pk.status, "in_use": pk.origin, "fallback": pk.fallback}


def export(name: str, out: str | Path | None = None, force: bool = False) -> dict:
    """Copy the pack in use for editing: to ``out``, or into the data folder's ``rules`` folder (where it is then
    the pack in use). Refuses to overwrite an override unless ``force``."""
    pk = load(name)
    dest = Path(out) if out else override_path(name)
    if dest.is_dir():
        dest = dest / _spec(name).file
    if dest.exists() and not force:
        raise PackError(f"{dest} already exists; give another file, or --force")
    dest.parent.mkdir(parents=True, exist_ok=True)
    if out is None and dest.exists():
        _keep(name)
    dest.write_text(json.dumps(pk.data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if out is None:
        _log({"event": "export", "pack": name, "version": pk.version, "from": pk.origin})
    return {"pack": name, "written": str(dest), "version": pk.version, "from": pk.origin}


def import_pack(name: str, file: str | Path, apply: bool = False) -> dict:
    """Validate ``file`` and, with ``apply``, install it as the pack in use (the one it replaces is kept)."""
    res = check(name, file)
    current = load(name)
    res.update({"replaces": current.describe(), "applied": False})
    if not res["ok"] or not apply:
        return res
    d = json.loads(Path(file).read_text(encoding="utf-8"))
    kept = _keep(name)
    p = override_path(name)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(d, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    _log({"event": "import", "pack": name, "version": d.get("version"), "file": str(file), "kept": kept})
    clear_cache()
    res.update({"applied": True, "kept": kept, "now": load(name).describe()})
    return res


def reset(name: str, apply: bool = False) -> dict:
    """Return to the bundled pack (the override is kept in ``rules/_replaced``)."""
    p = override_path(name)
    res = {"pack": name, "override": str(p) if p.exists() else None, "applied": False}
    if not p.exists() or not apply:
        return res
    kept = _keep(name)
    _log({"event": "reset", "pack": name, "kept": kept})
    clear_cache()
    res.update({"applied": True, "kept": kept, "now": load(name).describe()})
    return res
