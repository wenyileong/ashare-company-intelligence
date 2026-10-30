"""Writing a snapshot: the view, the observations behind it, the schema and a manifest (plan section 7.1, principle 6).

Files, in the output folder:
* ``snapshot.json``: the snapshot, canonical (the same parameters give the same bytes);
* ``observations.csv``: one row per observation node, with its provenance: exactly what the view plots;
* ``edges.csv``: one row per link, with its evidential status and basis;
* ``snapshot.schema.json``: the JSON Schema the snapshot follows;
* ``topology.html``: the offline viewer, when asked for;
* ``manifest.json``: the parameters, the time it was written, the database fingerprint and a SHA-256 for every file.
"""
from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

OBS_COLUMNS = ("id", "company_code", "layer", "metric", "period", "value", "low", "high", "unit", "source_kind",
               "published_date", "observed_date", "disclosure_id", "page", "method", "confidence_class", "review",
               "source", "flags", "label")
EDGE_COLUMNS = ("id", "source", "target", "relation", "evidence_status", "basis_kind", "disclosure_id", "page",
                "method", "basis_source", "basis_date", "published_date", "observed_date", "label")


def observation_rows(snap: dict) -> list[dict]:
    rows = []
    for n in snap["nodes"]:
        if n["kind"] != "observation":
            continue
        prov = n.get("provenance") or {}
        d = n.get("dates") or {}
        rows.append({"id": n["id"], "company_code": n.get("company_code"), "layer": n["layer"],
                     "metric": n.get("metric"), "period": n.get("period"), "value": n.get("value"),
                     "low": n.get("low"), "high": n.get("high"), "unit": n.get("unit"),
                     "source_kind": n.get("source_kind"), "published_date": d.get("published_date"),
                     "observed_date": d.get("observed_date"), "disclosure_id": prov.get("disclosure_id"),
                     "page": prov.get("page"), "method": prov.get("method"),
                     "confidence_class": prov.get("confidence_class"), "review": prov.get("review"),
                     "source": prov.get("source"), "flags": ";".join(n.get("flags") or []), "label": n["label"]})
    return rows


def edge_rows(snap: dict) -> list[dict]:
    rows = []
    for e in snap["edges"]:
        b, d = e.get("basis") or {}, e.get("dates") or {}
        rows.append({"id": e["id"], "source": e["source"], "target": e["target"], "relation": e["relation"],
                     "evidence_status": e["evidence_status"], "basis_kind": b.get("kind"),
                     "disclosure_id": b.get("disclosure_id"), "page": b.get("page"), "method": b.get("method"),
                     "basis_source": b.get("source") or b.get("scheme"), "basis_date": b.get("date")
                     or b.get("effective_date"), "published_date": d.get("published_date"),
                     "observed_date": d.get("observed_date"), "label": e.get("label")})
    return rows


def _csv(path: Path, columns, rows) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(columns), lineterminator="\n")
        w.writeheader()
        for r in rows:
            w.writerow({k: ("" if r.get(k) is None else r.get(k)) for k in columns})


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def export_snapshot(snap: dict, out_dir: str | Path, viewer: bool = True) -> dict:
    from .snapshot import dumps
    from .schema import schema
    from ..research import database_fingerprint
    from ..timeutil import utcnow
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    files = []
    p = out / "snapshot.json"
    p.write_text(dumps(snap), encoding="utf-8")
    files.append(p)
    p = out / "observations.csv"
    _csv(p, OBS_COLUMNS, observation_rows(snap))
    files.append(p)
    p = out / "edges.csv"
    _csv(p, EDGE_COLUMNS, edge_rows(snap))
    files.append(p)
    p = out / "snapshot.schema.json"
    p.write_text(json.dumps(schema(), ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    files.append(p)
    if viewer:
        from .viewer import write_viewer
        files.append(write_viewer(snap, out / "topology.html"))
    manifest = {"written_at": utcnow().isoformat(timespec="seconds") + "Z", "software": snap["software"],
                "schema_version": snap["schema_version"], "parameters": snap["parameters"],
                "database_fingerprint": database_fingerprint(),
                "nodes": len(snap["nodes"]), "edges": len(snap["edges"]),
                "files": {f.name: _sha(f) for f in files}}
    (out / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"folder": str(out), "files": [str(f) for f in files] + [str(out / "manifest.json")],
            "nodes": len(snap["nodes"]), "edges": len(snap["edges"])}
