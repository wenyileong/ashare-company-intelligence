"""CSV export of database tables (UTF-8 with BOM so Excel reads Chinese)."""
from __future__ import annotations

import csv
from pathlib import Path

from sqlalchemy import select

from .models import Base, SessionLocal, Company

TABLES = sorted(Base.metadata.tables)


def export_table(table: str, out_dir: str = "exports", security_code: str | None = None):
    names = TABLES if table == "all" else [table]
    unknown = [n for n in names if n not in Base.metadata.tables]
    if unknown:
        raise ValueError(f"unknown table(s) {unknown}; choose from {TABLES}")
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    session = SessionLocal()
    results = []
    try:
        company_id = None
        if security_code:
            c = session.query(Company).filter_by(security_code=str(security_code).zfill(6)).first()
            company_id = c.id if c else -1
        for name in names:
            t = Base.metadata.tables[name]
            stmt = select(t)
            if company_id is not None:
                if "company_id" in t.c:
                    stmt = stmt.where(t.c.company_id == company_id)
                elif name == "companies":
                    stmt = stmt.where(t.c.id == company_id)
                else:
                    continue
            rows = session.execute(stmt).all()
            suffix = f"_{str(security_code).zfill(6)}" if security_code else ""
            path = out / f"{name}{suffix}.csv"
            with path.open("w", encoding="utf-8-sig", newline="") as fh:
                w = csv.writer(fh)
                w.writerow([c.name for c in t.columns])
                for r in rows:
                    w.writerow(list(r))
            results.append((str(path), len(rows)))
        return results
    finally:
        session.close()
