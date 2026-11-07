"""The data folder (v2.3.0, plan section B1, finding 145): the paths report (phase 0), normalising stored paths with
an undo (phase 4), and moving or adopting the folder (phase 5).

Phase 0 only reads. Phases 4 and 5 change stored data or move files only when asked, after a preview, with a backup of
the database and a record of every change, so that each can be undone.
"""
from __future__ import annotations

import shutil
from collections import Counter
from pathlib import Path

from .features import data_root
from . import storepaths as sp

SOURCE_DOCUMENT_TABLES = (
    "financial_facts", "ownership_observations", "regulatory_events", "corporate_actions", "esg_observations",
    "esg_ratings", "segment_observations", "subsidiary_observations", "management_events", "management_observations",
    "human_capital_observations", "capital_structure_observations", "industry_classifications",
)


def _models():
    from . import models, transactions  # noqa: F401
    return models


def _folder_size(folder: Path) -> tuple[int, int]:
    n = total = 0
    if folder.exists():
        for p in folder.rglob("*"):
            try:
                if p.is_file():
                    n += 1
                    total += p.stat().st_size
            except OSError:
                pass
    return n, total


def paths_report(check_files: bool = True) -> dict:
    """Phase 0 (read-only): the stored paths by form, the files present, missing or recoverable, the caches, the
    folder's size and free space, and the outputs inside and outside the folder."""
    m = _models()
    from sqlalchemy import text
    m.init_db()
    s = m.SessionLocal()
    root = data_root()
    sp.clear_cache()
    out: dict = {"data_root": str(root), "tables": {}}
    try:
        for label, model, col in (("documents", m.Disclosure, "local_path"), ("archived responses", m.RawRecord,
                                                                             "payload_path")):
            forms, files = Counter(), Counter()
            q = s.query(getattr(model, col), model.sha256).filter(getattr(model, col).isnot(None))
            for value, sha in q.yield_per(2000):
                forms[sp.classify(value)] += 1
                if check_files:
                    own = Path(value) if sp.classify(value) != "relative" else None
                    found = sp.resolve_stored(value, sha)
                    if own is not None and own.exists():
                        files["present"] += 1
                    elif found is not None and found.exists():
                        files["present" if own is None else "recoverable"] += 1
                    else:
                        files["missing"] += 1
            out["tables"][label] = {"forms": dict(forms), "files": dict(files)}
        src = Counter()
        with m.engine().connect() as conn:
            for t in SOURCE_DOCUMENT_TABLES:
                try:
                    rows = conn.execute(text(f"SELECT source_document FROM {t} WHERE source_document IS NOT NULL "
                                             f"AND source_document NOT LIKE '%://%'")).fetchall()
                except Exception:                                         # noqa: BLE001  (table not yet created)
                    continue
                for (v,) in rows:
                    src[sp.classify(v)] += 1
        out["tables"]["source_document (local paths)"] = {"forms": dict(src), "files": {}}
    finally:
        s.close()
    from .config import disclosure_dir
    idx = disclosure_dir() / ".section_index"
    n, size = _folder_size(idx)
    out["caches"] = {"section_indexes": n, "mb": round(size / 1048576, 1)}
    try:
        du = shutil.disk_usage(root)
        out["disk"] = {"free_gb": round(du.free / 1e9, 1), "total_gb": round(du.total / 1e9, 1)}
    except OSError:
        out["disk"] = {}
    out["recovery"] = sp.recovery_stats()
    try:
        from .outputs import inside_outside
        out["outputs"] = inside_outside()
    except Exception:                                                     # noqa: BLE001  (B11 not yet available)
        pass
    return out


# --- Phase 4: normalise stored paths (explicit; preview, backup, record, undo) -------------------------------------

PATH_COLUMNS = (("disclosures", "local_path", "sha256"), ("raw_records", "payload_path", "sha256"))


def backup_database(label: str) -> str | None:
    """A copy of a SQLite database beside it, by SQLite's backup function (consistent while open). For another
    database, None: the caller asks the author to make a dump first."""
    import sqlite3
    from datetime import datetime
    from .timeutil import utcnow
    m = _models()
    url = m.database_url()
    if not url.startswith("sqlite"):
        return None
    from .config import db_path
    src = Path(db_path())
    dst = src.with_name(f"{src.name}.bak-{label}-{utcnow():%Y%m%dT%H%M%S}")
    m.engine().dispose()
    with sqlite3.connect(str(src)) as a, sqlite3.connect(str(dst)) as b:
        a.backup(b)
    return str(dst)


def _new_value(value: str, sha: str | None, old_root: Path | None = None) -> str | None:
    """The relative form of a stored path, if it can be given one; None to leave it. After a move, a path under the
    old folder is mapped to the same place under the new one (the old folder may still exist after a copy)."""
    root = data_root()
    if old_root is not None and sp.classify(value) != "relative":
        absolute, parts = sp._parts(value)
        try:
            rel = Path(value).relative_to(old_root)
        except ValueError:
            rel = None
        if rel is not None and (root / rel).exists():
            return rel.as_posix()
    found = sp.resolve_stored(value, sha)
    if found is None or not found.exists():
        return None
    try:
        rel = found.resolve().relative_to(root).as_posix()
    except ValueError:
        return None                                             # outside the data folder: left as it is
    return rel if rel != value else None


def normalise_paths(apply: bool = False, confirm_other_database: bool = False, old_root: Path | None = None) -> dict:
    """Phase 4. Stored paths that resolve to a file under the data folder are rewritten relative to it; every change
    is recorded in ``path_rewrites`` so that :func:`undo_paths` can restore it. Preview unless ``apply``."""
    import uuid
    from sqlalchemy import text
    from .features import require
    require("storage.normalise")
    m = _models()
    m.init_db()
    sp.clear_cache()
    run_id = uuid.uuid4().hex[:16]
    changes, left = [], Counter()
    with m.engine().connect() as conn:
        for table, col, shacol in PATH_COLUMNS:
            for rid, value, sha in conn.execute(text(f"SELECT id, {col}, {shacol} FROM {table} "
                                                     f"WHERE {col} IS NOT NULL")):
                new = _new_value(value, sha, old_root)
                if new:
                    changes.append((table, rid, col, value, new))
                elif sp.classify(value) != "relative":
                    left[table] += 1
        for table in SOURCE_DOCUMENT_TABLES:
            try:
                rows = conn.execute(text(f"SELECT id, source_document FROM {table} WHERE source_document IS NOT "
                                         f"NULL AND source_document NOT LIKE '%://%'")).fetchall()
            except Exception:                                    # noqa: BLE001
                continue
            for rid, value in rows:
                if sp.classify(value) in ("inside", "outside"):
                    new = _new_value(value, None, old_root)
                    if new:
                        changes.append((table, rid, "source_document", value, new))
                    else:
                        left[table] += 1
    by = Counter(c[0] for c in changes)
    result = {"run_id": run_id, "changes": len(changes), "by_table": dict(by), "left_unchanged": dict(left),
              "applied": False, "examples": [{"table": t, "old": o, "new": n} for t, _, _, o, n in changes[:10]]}
    if not apply or not changes:
        result["note"] = ("Preview only: nothing changed. Apply to rewrite these paths; a backup of the database is "
                          "taken first and 'paths-undo' restores every value.") if changes else "Nothing to change."
        return result
    backup = backup_database("normalise")
    if backup is None and not confirm_other_database:
        raise RuntimeError("This database is not a SQLite file, so no backup can be taken here. Make a dump first "
                           "(for PostgreSQL, pg_dump), then confirm.")
    from .models_v23 import PathRewrite
    s = m.SessionLocal()
    try:
        for table, rid, col, old, new in changes:
            s.add(PathRewrite(run_id=run_id, table_name=table, row_id=rid, column_name=col, old_value=old,
                              new_value=new))
            s.execute(text(f"UPDATE {table} SET {col} = :v WHERE id = :i"), {"v": new, "i": rid})
        s.commit()
    finally:
        s.close()
    sp.clear_cache()
    files = [c for c in changes if c[2] != "source_document"]
    bad = [c for c in files if not (data_root() / c[4]).exists()]
    result.update(applied=True, backup=backup, verified=len(files) - len(bad), not_verified=len(bad))
    result["note"] = f"Rewritten. To undo: ashare-cli paths-undo {run_id}"
    return result


def undo_paths(run_id: str) -> dict:
    """Restore the values a normalising run (or a move) changed."""
    from sqlalchemy import text
    from .models_v23 import PathRewrite
    from .timeutil import utcnow
    m = _models()
    m.init_db()
    s = m.SessionLocal()
    try:
        rows = s.query(PathRewrite).filter(PathRewrite.run_id == run_id, PathRewrite.undone_at.is_(None)).all()
        for r in rows:
            s.execute(text(f"UPDATE {r.table_name} SET {r.column_name} = :v WHERE id = :i"),
                      {"v": r.old_value, "i": r.row_id})
            r.undone_at = utcnow()
        s.commit()
        sp.clear_cache()
        return {"run_id": run_id, "restored": len(rows)}
    finally:
        s.close()


def rewrite_runs() -> list[dict]:
    from sqlalchemy import func
    from .models_v23 import PathRewrite
    m = _models()
    m.init_db()
    s = m.SessionLocal()
    try:
        q = (s.query(PathRewrite.run_id, func.count(PathRewrite.id), func.min(PathRewrite.created_at),
                     func.count(PathRewrite.undone_at)).group_by(PathRewrite.run_id))
        return [{"run_id": r, "changes": n, "when": w.isoformat(timespec="seconds") if w else None,
                 "undone": u} for r, n, w, u in q]
    finally:
        s.close()


# --- Phase 5: move or adopt the data folder ------------------------------------------------------------------------

_SKIP_SUFFIXES = ("-wal", "-shm", "-journal")


def _same_device(a: Path, b: Path) -> bool:
    import os
    try:
        tb = b if b.exists() else b.parent
        return os.stat(a).st_dev == os.stat(tb).st_dev
    except OSError:
        return False


def plan_move(target: str) -> dict:
    """The dry run of a move: what would be moved, the space it needs, and the warnings. Changes nothing."""
    root = data_root()
    dst = Path(target).expanduser().resolve()
    problems, warnings = [], []
    if dst == root:
        problems.append("the target is the current data folder")
    try:
        dst.relative_to(root)
        problems.append("the target is inside the current data folder")
    except ValueError:
        pass
    try:
        root.relative_to(dst)
        problems.append("the current data folder is inside the target")
    except ValueError:
        pass
    if dst.exists() and any(dst.iterdir()):
        problems.append("the target folder is not empty")
    files, size = _folder_size(root)
    probe = dst if dst.exists() else dst.parent
    while not probe.exists() and probe != probe.parent:
        probe = probe.parent
    try:
        free = shutil.disk_usage(probe).free
    except OSError:
        free = None
    same = _same_device(root, probe)
    if free is not None and not same and free < size * 1.05:
        problems.append(f"not enough free space: {size / 1e9:,.1f} GB needed, {free / 1e9:,.1f} GB free")
    low = str(dst).lower()
    if "onedrive" in low or "dropbox" in low or "google drive" in low or "icloud" in low:
        warnings.append("the target is in a synced folder: syncing can damage an open database and leave "
                        "documents as cloud-only placeholders")
    m = _models()
    if not m.database_url().startswith("sqlite"):
        warnings.append("the database is not a SQLite file in the folder, so it is not moved; only the files are")
    try:
        from .outputs import inside_outside
        io = inside_outside()
        if io["outside"]:
            warnings.append(f"{io['outside']} output(s) are stored outside the data folder and do not move")
    except Exception:                                             # noqa: BLE001
        io = None
    return {"from": str(root), "to": str(dst), "files": files, "gb": round(size / 1e9, 2),
            "free_gb": round(free / 1e9, 1) if free is not None else None,
            "method": "rename (same drive)" if same else "copy, then verify",
            "problems": problems, "warnings": warnings, "outputs": io, "can_move": not problems}


def _copy_tree(root: Path, dst: Path, progress=None) -> dict:
    """Copy every file with its times, the database by SQLite's backup function, and check each document's hash."""
    import sqlite3
    from .config import db_path
    from .extractstate import Progress
    say = progress or (lambda m: None)
    db = Path(db_path()).resolve()
    all_files = [p for p in root.rglob("*") if p.is_file() and not p.name.endswith(_SKIP_SUFFIXES)]
    prog = Progress(len(all_files), say, every=2000, unit="files")
    copied = bad = 0
    for p in all_files:
        rel = p.relative_to(root)
        q = dst / rel
        q.parent.mkdir(parents=True, exist_ok=True)
        if p.resolve() == db:
            _models().engine().dispose()
            with sqlite3.connect(str(p)) as a, sqlite3.connect(str(q)) as b:
                a.backup(b)
        else:
            shutil.copy2(p, q)
            stem = q.stem.lower()
            if rel.parts and rel.parts[0] == "disclosures" and len(stem) == 64 and \
                    all(c in "0123456789abcdef" for c in stem):
                if sp.sha256_file(q) != stem:
                    bad += 1
        copied += 1
        prog.step()
    return {"copied": copied, "hash_mismatches": bad}


def _switch_to(folder: Path) -> None:
    """Point this process, and the desktop program's settings, at ``folder``."""
    import os
    os.environ["ASHARE_DB"] = str(folder / "ashares.db")
    os.environ["ASHARE_RAW_DIR"] = str(folder / "raw")
    os.environ["ASHARE_DISCLOSURE_DIR"] = str(folder / "disclosures")
    os.environ["ASHARE_MARKET_RAW_DIR"] = str(folder / "market_raw")
    if os.environ.get("ASHARE_HOME"):
        os.environ["ASHARE_HOME"] = str(folder)
    try:
        os.chdir(folder)
    except OSError:
        pass
    m = _models()
    m.engine().dispose()
    m.reset_init_cache()
    try:
        from .gui import load_settings, save_settings
        st = load_settings()
        st["data_folder"] = str(folder)
        save_settings(st)
    except Exception:                                             # noqa: BLE001  (no desktop program, e.g. tests)
        pass


def _reschedule() -> str | None:
    """Re-create the scheduled daily update for the new folder, if one exists (Windows only)."""
    import platform
    import subprocess
    if platform.system() != "Windows":
        return None
    from .ops import TASK_NAME, schedule
    q = subprocess.run(["schtasks", "/Query", "/TN", TASK_NAME], capture_output=True, text=True)
    if q.returncode != 0 or TASK_NAME not in (q.stdout or ""):      # no scheduled update to re-create
        return None
    r = schedule(True)
    return "re-created" if r.get("returncode") == 0 else f"could not be re-created: {r.get('output')}"


def _log_move(folder: Path, record: dict) -> None:
    import json
    from datetime import datetime
    from .timeutil import utcnow
    logs = folder / "logs"
    logs.mkdir(exist_ok=True)
    (logs / f"move-{utcnow():%Y%m%dT%H%M%S}.json").write_text(json.dumps(record, ensure_ascii=False,
                                                                                     indent=2), encoding="utf-8")
    with open(folder / "run_log.txt", "a", encoding="utf-8") as fh:
        fh.write(f"\n=== {datetime.now():%Y-%m-%d %H:%M:%S}  data folder moved from {record['from']} to "
                 f"{record['to']} ({record['method']})\n")


def move_data_folder(target: str, apply: bool = False, progress=None) -> dict:
    """Phase 5. Without ``apply``, the dry run. With it: rename (same drive) or copy and verify; then normalise the
    stored paths in the new folder, switch the setting, re-create the scheduled update and record the move. After a
    copy the old folder is left untouched, so switching the setting back undoes the move."""
    import os
    from .features import require
    require("storage.move")
    plan = plan_move(target)
    if not apply or not plan["can_move"]:
        plan["applied"] = False
        plan["note"] = ("Dry run: nothing moved." if plan["can_move"] else "Cannot move: "
                        + "; ".join(plan["problems"]))
        return plan
    root, dst = Path(plan["from"]), Path(plan["to"])
    say = progress or (lambda m: None)
    record = {"from": str(root), "to": str(dst), "method": None}
    _models().engine().dispose()
    renamed = False
    if plan["method"].startswith("rename"):
        try:
            os.chdir(root.parent)
            if dst.exists():
                dst.rmdir()
            dst.parent.mkdir(parents=True, exist_ok=True)
            os.replace(root, dst)
            renamed = True
            record["method"] = "rename"
        except OSError as exc:
            say(f"Renaming was not possible ({exc}); copying instead")
            try:
                os.chdir(root)
            except OSError:
                pass
    if not renamed:
        dst.mkdir(parents=True, exist_ok=True)
        r = _copy_tree(root, dst, progress)
        record.update(method="copy", **r)
        if r["hash_mismatches"]:
            record["note"] = "Some copies differ from their hash; the old folder is still in use."
            return {**plan, **record, "applied": False}
    _switch_to(dst)
    norm = normalise_paths(apply=True, confirm_other_database=True, old_root=root)
    record["paths_rewritten"] = norm.get("changes", 0)
    record["undo_run"] = norm.get("run_id")
    record["schedule"] = _reschedule()
    _log_move(dst, record)
    out = {**plan, **record, "applied": True}
    out["note"] = ("Moved. The old folder is untouched; delete it yourself once you have checked the new one. "
                   "Restart the program." if not renamed else "Moved by renaming. Restart the program.")
    return out


def adopt_data_folder(folder: str, apply: bool = False, sample: int = 200) -> dict:
    """Use a folder already moved (for example, restored after reinstalling Windows): the paths report and a hash
    check of a sample of documents on it, then (with ``apply``) the setting is switched. Stored paths are found by
    the tolerant reads; 'Normalise paths' can be run later."""
    import random
    from .features import require
    require("storage.move")
    dst = Path(folder).expanduser().resolve()
    if not (dst / "ashares.db").exists() and _models().database_url().startswith("sqlite"):
        return {"applied": False, "note": f"No database (ashares.db) in {dst}: not a data folder."}
    old_env = {k: __import__("os").environ.get(k) for k in ("ASHARE_DB", "ASHARE_RAW_DIR", "ASHARE_DISCLOSURE_DIR",
                                                            "ASHARE_MARKET_RAW_DIR", "ASHARE_HOME")}
    old_cwd = Path.cwd()
    _switch_to(dst) if apply else None
    if not apply:
        import os
        os.environ.update({"ASHARE_DB": str(dst / "ashares.db"), "ASHARE_RAW_DIR": str(dst / "raw"),
                           "ASHARE_DISCLOSURE_DIR": str(dst / "disclosures"),
                           "ASHARE_MARKET_RAW_DIR": str(dst / "market_raw")})
        if old_env["ASHARE_HOME"]:
            os.environ["ASHARE_HOME"] = str(dst)
        _models().reset_init_cache()
    try:
        report = paths_report(check_files=True)
        m = _models()
        s = m.SessionLocal()
        try:
            rows = s.query(m.Disclosure).filter(m.Disclosure.local_path.isnot(None)).all()
            picked = random.Random(0).sample(rows, min(sample, len(rows)))
            ok = bad = missing = 0
            for d in picked:
                p = sp.document_path(d)
                if p is None or not p.exists():
                    missing += 1
                elif d.sha256 and sp.sha256_file(p) != d.sha256:
                    bad += 1
                else:
                    ok += 1
        finally:
            s.close()
    finally:
        if not apply:
            import os
            for k, v in old_env.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v
            _models().engine().dispose()
            _models().reset_init_cache()
            try:
                os.chdir(old_cwd)
            except OSError:
                pass
    res = {"folder": str(dst), "report": report, "sample": {"checked": len(picked), "ok": ok, "mismatched": bad,
                                                             "missing": missing}, "applied": apply}
    if apply:
        _log_move(dst, {"from": "(adopted)", "to": str(dst), "method": "adopt"})
        res["schedule"] = _reschedule()
        res["note"] = "Adopted. Restart the program."
    else:
        res["note"] = "Checked only: nothing changed. Apply to use this folder."
    return res
