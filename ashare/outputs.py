"""The outputs register (v2.3.0, plan section B11).

Every output the program writes (a view, a topology view, a panel, an event study, a release, an export, a chart
export, a query result) is recorded in ``outputs`` by :func:`record_output`, so that Files > Outputs can show them in
one place, check them against their manifests, and remove them; and so that the data-folder move can say which
outputs lie inside the folder (and move with it) and which do not. Recording never fails the output itself.
"""
from __future__ import annotations

import hashlib
import json
import logging
import shutil
from collections import Counter
from pathlib import Path

from .features import data_root, enabled

log = logging.getLogger(__name__)

KINDS = ("view", "topology", "panel", "event_study", "release", "export", "files_export", "chart", "query")
SCAN_FOLDERS = ("visualise", "topology", "panels", "releases", "exports", "event_studies", "research")


def _sha(p: Path) -> str | None:
    try:
        h = hashlib.sha256()
        with open(p, "rb") as f:
            for chunk in iter(lambda: f.read(1 << 20), b""):
                h.update(chunk)
        return h.hexdigest()
    except OSError:
        return None


def _stored(path: Path) -> str:
    try:
        return path.resolve().relative_to(data_root()).as_posix()
    except (ValueError, OSError):
        return str(path.resolve())


def resolve(stored: str) -> Path:
    p = Path(stored)
    return p if p.is_absolute() else data_root() / p


def _group(path: Path) -> list[Path]:
    """The files of a file output: those its manifest lists (for ``*_manifest.json``), or those sharing its stem
    (``chart.svg``, ``chart.csv``, ``chart.png``), with the manifest."""
    if path.name.endswith("_manifest.json"):
        try:
            listed = json.loads(path.read_text(encoding="utf-8")).get("files") or {}
        except (OSError, ValueError):
            listed = {}
        names = list(listed) if isinstance(listed, dict) else [Path(x).name for x in listed]
        return [path.parent / n for n in names if (path.parent / n).exists()] + [path]
    sibs = [f for f in path.parent.glob(path.stem + ".*") if f.is_file()]
    man = path.with_name(path.stem + "_manifest.json")
    return sorted(set(sibs + ([man] if man.exists() else [])))


def _size(path: Path) -> tuple[int, int]:
    if path.is_file():
        g = _group(path)
        return len(g), sum(f.stat().st_size for f in g if f.exists())
    n = total = 0
    if path.exists():
        for f in path.rglob("*"):
            try:
                if f.is_file():
                    n += 1
                    total += f.stat().st_size
            except OSError:
                pass
    return n, total


def record_output(kind: str, path, command: str | None = None, params: dict | None = None,
                  manifest=None) -> int | None:
    """Record one output (a folder or a file). Returns the row id, or None when the switch is off or recording
    failed (logged, never raised)."""
    if not enabled("outputs.register"):
        return None
    try:
        from .models import SessionLocal, init_db
        from .models_v23 import OutputRecord
        p = Path(path)
        if not p.exists():
            return None
        files, size = _size(p)
        man = Path(manifest) if manifest else None
        init_db()
        s = SessionLocal()
        try:
            stored = _stored(p)
            row = s.query(OutputRecord).filter(OutputRecord.path == stored,
                                               OutputRecord.status != "REMOVED").one_or_none()
            if row is None:
                row = OutputRecord(path=stored)
                s.add(row)
            row.kind, row.command = kind, command
            row.params_json = json.dumps(params or {}, ensure_ascii=False, default=str)
            row.is_folder = int(p.is_dir())
            row.files, row.bytes = files, size
            row.manifest_sha256 = _sha(man) if man is not None and man.exists() else None
            row.status = "PRESENT"
            from .timeutil import utcnow
            row.created_at = utcnow()
            s.commit()
            return row.id
        finally:
            s.close()
    except Exception as exc:                                      # noqa: BLE001  recording never fails an output
        log.warning("outputs register: %s not recorded: %s", path, exc)
        return None


def list_outputs(kind: str | None = None, include_removed: bool = False) -> list[dict]:
    from .models import SessionLocal, init_db
    from .models_v23 import OutputRecord
    init_db()
    s = SessionLocal()
    try:
        q = s.query(OutputRecord)
        if kind:
            q = q.filter(OutputRecord.kind == kind)
        if not include_removed:
            q = q.filter(OutputRecord.status != "REMOVED")
        out = []
        for r in q.order_by(OutputRecord.created_at.desc(), OutputRecord.id.desc()):
            p = resolve(r.path)
            status = r.status if r.status == "REMOVED" else ("PRESENT" if p.exists() else "MISSING")
            inside = not Path(r.path).is_absolute()
            out.append({"id": r.id, "kind": r.kind, "command": r.command, "path": str(p), "status": status,
                        "inside_data_folder": inside, "files": r.files, "mb": round((r.bytes or 0) / 1048576, 2),
                        "created": r.created_at.isoformat(timespec="seconds") if r.created_at else None})
        return out
    finally:
        s.close()


def inside_outside() -> dict:
    rows = list_outputs()
    return {"inside": sum(1 for r in rows if r["inside_data_folder"]),
            "outside": sum(1 for r in rows if not r["inside_data_folder"]),
            "outside_paths": [r["path"] for r in rows if not r["inside_data_folder"]][:50]}


def _manifest_of(p: Path) -> Path | None:
    if p.is_file():
        cand = p.with_name(p.stem + "_manifest.json")
        return cand if cand.exists() else None
    for name in ("manifest.json",):
        if (p / name).exists():
            return p / name
    found = sorted(p.glob("*_manifest.json")) if p.exists() else []
    return found[0] if found else None


def check_output(output_id: int) -> dict:
    """The output against its manifest: each listed file present with the hash recorded."""
    from .models import SessionLocal, init_db
    from .models_v23 import OutputRecord
    init_db()
    s = SessionLocal()
    try:
        r = s.get(OutputRecord, output_id)
        if r is None:
            return {"error": f"no output {output_id}"}
        p = resolve(r.path)
        if not p.exists():
            return {"id": output_id, "status": "MISSING", "path": str(p)}
        man = _manifest_of(p)
        if man is None:
            return {"id": output_id, "status": "NO_MANIFEST", "path": str(p)}
        result = {"id": output_id, "path": str(p), "manifest": man.name, "checked": 0, "changed": [],
                  "missing": []}
        if r.manifest_sha256 and _sha(man) != r.manifest_sha256:
            result["changed"].append(man.name)
        files = (json.loads(man.read_text(encoding="utf-8")).get("files") or {})
        base = man.parent
        for name, sha in (files.items() if isinstance(files, dict) else []):
            f = base / name
            result["checked"] += 1
            if not f.exists():
                result["missing"].append(name)
            elif sha and _sha(f) != sha:
                result["changed"].append(name)
        result["status"] = "OK" if not result["changed"] and not result["missing"] else "DIFFERS"
        return result
    finally:
        s.close()


def remove_output(output_id: int, apply: bool = False) -> dict:
    """Preview, or remove, one output's files; the row is kept, marked REMOVED with the time."""
    from .models import SessionLocal, init_db
    from .models_v23 import OutputRecord
    from .timeutil import utcnow
    init_db()
    s = SessionLocal()
    try:
        r = s.get(OutputRecord, output_id)
        if r is None:
            return {"error": f"no output {output_id}"}
        p = resolve(r.path)
        files, size = _size(p)
        res = {"id": output_id, "path": str(p), "files": files, "mb": round(size / 1048576, 2), "applied": apply}
        if not apply:
            res["note"] = "Preview only: nothing removed. Tick 'Apply' (or --apply) to remove these files."
            return res
        if p.is_dir():
            shutil.rmtree(p)
        elif p.exists():
            for f in _group(p):
                if f.exists():
                    f.unlink()
        r.status, r.removed_at = "REMOVED", utcnow()
        s.commit()
        return res
    finally:
        s.close()


def _guess_kind(man: Path, data: dict) -> str:
    if "view" in data:
        return "topology" if data.get("view") == "topology" else "view"
    if man.name.endswith("_manifest.json") and "columns" in data:
        return "panel"
    if "release" in data or (man.parent / "CITATION.cff").exists():
        return "release"
    if "nodes" in data or (man.parent / "topology.html").exists():
        return "topology"
    if "estimation_window" in data or "event_window" in data:
        return "event_study"
    return "export"


def scan_outputs(folder: str | None = None, apply: bool = False) -> dict:
    """Outputs made before v2.3, found by their manifests under the usual folders (or ``folder``): preview, or
    record them. Outputs already registered are not added again."""
    from .models import SessionLocal, init_db
    from .models_v23 import OutputRecord
    init_db()
    roots = [Path(folder)] if folder else [data_root() / f for f in SCAN_FOLDERS]
    s = SessionLocal()
    try:
        known = {r.path for r in s.query(OutputRecord.path)}
    finally:
        s.close()
    found, by = [], Counter()
    for root in roots:
        if not root.exists():
            continue
        for man in sorted(list(root.rglob("manifest.json")) + list(root.rglob("*_manifest.json"))):
            try:
                data = json.loads(man.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                data = {}
            target = man.parent if man.name == "manifest.json" else man.parent
            stored = _stored(target)
            if stored in known or any(f["stored"] == stored for f in found):
                continue
            kind = _guess_kind(man, data)
            found.append({"kind": kind, "path": str(target), "stored": stored, "manifest": str(man)})
            by[kind] += 1
    if apply:
        for f in found:
            record_output(f["kind"], f["path"], command="outputs-scan", manifest=f["manifest"])
    return {"found": len(found), "by_kind": dict(by), "applied": apply,
            "rows": [{k: v for k, v in f.items() if k != "stored"} for f in found]}


def disk_use() -> list[dict]:
    """Disk use by category, for the Outputs window."""
    from .config import disclosure_dir, raw_dir, market_raw_dir, db_path
    rows = []

    def add(label, path):
        n, size = _size(Path(path))
        rows.append({"category": label, "path": str(Path(path).resolve()), "files": n, "mb": round(size / 1048576, 1)})
    add("documents", disclosure_dir())
    add("archived responses", raw_dir())
    add("market data", market_raw_dir())
    idx = disclosure_dir() / ".section_index"
    add("section-index cache", idx)
    db = Path(db_path())
    if db.exists():
        rows.append({"category": "database", "path": str(db.resolve()), "files": 1,
                     "mb": round(db.stat().st_size / 1048576, 1)})
        baks = list(db.parent.glob(db.name + ".bak-*"))
        rows.append({"category": "database backups", "path": str(db.parent.resolve()), "files": len(baks),
                     "mb": round(sum(b.stat().st_size for b in baks) / 1048576, 1)})
    by = Counter()
    sizes = Counter()
    for r in list_outputs():
        by[r["kind"]] += 1
        sizes[r["kind"]] += r["mb"] or 0
    for k in sorted(by):
        rows.append({"category": f"outputs: {k}", "path": "", "files": by[k], "mb": round(sizes[k], 1)})
    return rows
