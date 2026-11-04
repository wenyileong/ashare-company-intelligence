"""The series snapshot of the Visualise section (v2.2, plan section B4.3): rows for charts, each with its
provenance columns, plus axes, units and the notes on gaps."""
from __future__ import annotations

SERIES_SCHEMA_VERSION = 2
PROVENANCE_COLUMNS = ("disclosure_id", "page", "published_date", "method", "confidence_class", "source")


def series_snapshot(view_id: str, params: dict, policy: dict, tables: dict[str, dict], coverage: list[dict],
                    notes: list[str], evidence: str, summary: list[dict] | None = None) -> dict:
    """``tables``: name -> {"columns": [...], "rows": [...], "title": str}. Rows are kept in a fixed order (the
    caller sorts them), so the same parameters give the same snapshot."""
    from .. import __version__
    from .definitions import CURRENT
    for name, t in tables.items():
        cols = list(t["columns"])
        for r in t["rows"]:
            extra = [k for k in r if k not in cols]
            if extra:
                raise ValueError(f"table {name}: columns not declared: {extra}")
    return {"schema_version": SERIES_SCHEMA_VERSION, "kind": "series", "view": view_id,
            "software": f"ashare {__version__}", "definitions": CURRENT, "parameters": params, "policy": policy,
            "evidence": evidence, "tables": tables, "coverage": coverage, "summary": summary or [], "notes": notes}
