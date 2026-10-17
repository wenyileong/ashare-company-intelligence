"""Versioned schema migrations (v2.0).

The schema is managed with Alembic. The migration scripts live in
``ashare/migrations/versions`` and are applied by :func:`upgrade`, which
``init_db`` calls once per process:

* a new database is created and stamped at the head revision;
* a database written by v0.7 to v1.9 (no ``alembic_version`` table) is
  upgraded in place by the baseline revision, which creates missing tables,
  adds missing columns and creates the v1.9 indexes;
* later revisions apply their own changes.

Before a SQLite file is upgraded, a backup copy is written next to it
(``ashares.db.bak-<from>-<UTC time>``), so an upgrade can always be undone
by restoring the copy.

Revision scripts should use the idempotent helpers below
(:func:`add_column_if_missing`, :func:`create_index_if_missing`), so that a
script can be applied safely to a database whose tables were created from the
current models.
"""
from __future__ import annotations

import shutil
from pathlib import Path

from sqlalchemy import inspect, text

MIGRATIONS_DIR = Path(__file__).resolve().parent / "migrations"
_SCRIPT = None


def _config(connection=None):
    from alembic.config import Config
    cfg = Config()
    cfg.set_main_option("script_location", str(MIGRATIONS_DIR))
    cfg.set_main_option("path_separator", "os")
    if connection is not None:
        cfg.attributes["connection"] = connection
    return cfg


def script_directory():
    global _SCRIPT
    if _SCRIPT is None:
        from alembic.script import ScriptDirectory
        _SCRIPT = ScriptDirectory.from_config(_config())
    return _SCRIPT


def head() -> str:
    return script_directory().get_current_head()


def current(eng=None) -> str | None:
    """The database's revision, ``None`` for a database without one."""
    from alembic.runtime.migration import MigrationContext
    from .models import engine
    eng = eng or engine()
    with eng.connect() as conn:
        return MigrationContext.configure(conn).get_current_revision()


def _has_tables(eng) -> bool:
    names = set(inspect(eng).get_table_names())
    return bool(names - {"alembic_version"})


def _backup(rev: str | None) -> str | None:
    from .models import is_sqlite
    from .config import db_path
    from .timeutil import utcnow
    if not is_sqlite():
        return None
    src = Path(db_path())
    if not src.exists() or src.stat().st_size == 0:
        return None
    dst = src.with_name(f"{src.name}.bak-{rev or 'pre-v2.0'}-{utcnow().strftime('%Y%m%dT%H%M%SZ')}")
    import sqlite3
    a, b = sqlite3.connect(str(src)), sqlite3.connect(str(dst))
    try:
        a.backup(b)                 # consistent copy even with WAL files present
    finally:
        b.close()
        a.close()
    return str(dst)


def upgrade(target: str = "head", backup: bool = True) -> dict:
    """Upgrade the configured database to *target* (default: the head)."""
    from alembic import command
    from .models import engine
    eng = engine()
    rev = current(eng)
    want = head() if target == "head" else target
    if rev == want:
        return {"from": rev, "to": want, "changed": False, "backup": None}
    existing = _has_tables(eng)
    copy = _backup(rev) if (backup and existing) else None
    with eng.begin() as conn:
        command.upgrade(_config(conn), target)
    return {"from": rev, "to": want, "changed": True, "backup": copy, "upgraded_existing": existing}


def history() -> list[dict]:
    out = []
    for s in script_directory().walk_revisions():
        out.append({"revision": s.revision, "down_revision": s.down_revision,
                    "message": (s.doc or "").strip().splitlines()[0] if s.doc else ""})
    return list(reversed(out))


def status() -> dict:
    rev = current()
    return {"current": rev, "head": head(), "up_to_date": rev == head(), "history": history()}


# ---------------------------------------------------------------------------
# Idempotent helpers for revision scripts
# ---------------------------------------------------------------------------

def add_column_if_missing(conn, table: str, name: str, ddl: str) -> bool:
    insp = inspect(conn)
    if not insp.has_table(table):
        return False
    if name in {c["name"] for c in insp.get_columns(table)}:
        return False
    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}"))
    return True


def create_index_if_missing(conn, name: str, table: str, cols: str) -> None:
    conn.execute(text(f"CREATE INDEX IF NOT EXISTS {name} ON {table} ({cols})"))


def reconcile_tables(conn, tables) -> dict:
    """Create the listed model tables if absent, and add any model column an
    existing table lacks (as a nullable column: SQLite cannot add a NOT NULL
    column without a default). Used by the baseline revision to bring any
    database from v0.7 onwards up to the v1.9 schema."""
    from .models import Base
    from . import transactions  # noqa: F401
    md = Base.metadata
    insp = inspect(conn)
    present = set(insp.get_table_names())
    created, added = [], []
    md.create_all(conn, tables=[md.tables[t] for t in tables if t in md.tables and t not in present])
    created = [t for t in tables if t not in present and t in md.tables]
    for t in tables:
        if t not in present or t not in md.tables:
            continue
        have = {c["name"] for c in insp.get_columns(t)}
        for col in md.tables[t].columns:
            if col.name in have:
                continue
            ddl = col.type.compile(dialect=conn.dialect)
            conn.execute(text(f"ALTER TABLE {t} ADD COLUMN {col.name} {ddl}"))
            added.append(f"{t}.{col.name}")
    return {"created": created, "added_columns": added}
