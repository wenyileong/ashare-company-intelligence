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
