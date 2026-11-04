"""Writing a view of the Visualise section (v2.2, plan section B4.5).

For every view, in its output folder:
* ``view.json``: the snapshot, canonical (the same parameters and database give the same bytes);
* the data, exactly what is drawn: ``nodes.csv`` and ``edges.csv`` (graph views) or one CSV per table (chart views);
* ``view.schema.json``: the JSON Schema the snapshot follows;
* ``view.html``: the offline interactive page (graph or chart mode), when asked for;
* each figure as ``figure_<name>.svg`` and ``.csv`` (PNG too where matplotlib is installed), and ``figures.html``, a print-ready page with
  the figures at journal widths (single column 85 mm, full width 175 mm) and their captions; printing it to PDF from
  the browser gives a PDF;
* ``manifest.json``: the parameters, definition version, evidential status, policy, database fingerprint and a
  SHA-256 for every file.
"""
from __future__ import annotations

import csv
import hashlib
import html
import json
from pathlib import Path

WIDTHS = {"column": ("85mm", 480), "page": ("175mm", 760)}


def dumps(snap: dict) -> str:
    return json.dumps(snap, ensure_ascii=False, sort_keys=True, indent=1, allow_nan=False, default=str) + "\n"


def _csv(path: Path, rows: list[dict], columns: list[str] | None = None) -> Path:
    cols = list(columns or [])
    for r in rows:
        for k in r:
            if k not in cols:
                cols.append(k)
    with path.open("w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols or ["empty"], lineterminator="\n")
        w.writeheader()
        for r in rows:
            w.writerow({k: ("" if r.get(k) is None else (json.dumps(r[k], ensure_ascii=False, sort_keys=True)
                                                         if isinstance(r.get(k), (dict, list)) else r[k]))
                        for k in cols})
    return path


def node_rows(snap: dict) -> list[dict]:
    return [{"id": n["id"], "kind": n["kind"], "label": n["label"], "masked": n["masked"],
             "flags": ";".join(n.get("flags") or []), "code": n.get("code"), "group": n.get("group"),
             "ring": n.get("ring"), "depth": n.get("depth"), "degree": n.get("degree")} for n in snap["nodes"]]


def edge_rows(snap: dict) -> list[dict]:
    out = []
    for e in snap["edges"]:
        b, d = e.get("basis") or {}, e.get("dates") or {}
        out.append({"id": e["id"], "source": e["source"], "target": e["target"], "relation": e["relation"],
                    "value": e.get("value"), "label": e.get("label"), "evidence_status": e["evidence_status"],
                    "basis_kind": b.get("kind"), "disclosure_id": b.get("disclosure_id"), "page": b.get("page"),
                    "method": b.get("method"), "basis_source": b.get("source"),
                    "published_date": d.get("published_date"), "observed_date": d.get("observed_date")})
    return out


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def figures_page(view, snap: dict, figures: list[tuple[str, Path]], width: str = "page") -> str:
    """A print-ready page: each figure at a journal width, with its caption (evidential status, source, as-of)."""
    from .view import EVIDENCE
    mm = WIDTHS.get(width, WIDTHS["page"])[0]
    p = snap.get("parameters", {})
    caption = (f"{EVIDENCE.get(snap.get('evidence'), '')} As published by {p.get('as_of')}. "
               f"{snap.get('policy', {}).get('licences', '')}. Definitions: {snap.get('definitions')}. "
               f"Source: {snap.get('software')}, view '{snap.get('view')}'; data in the CSV beside each figure.")
    body = "\n".join(
        f'<figure><img src="{html.escape(svg.name)}" alt="{html.escape(name)}">'
        f'<figcaption><b>Figure {i}.</b> {html.escape(name)}. {html.escape(caption)}</figcaption></figure>'
        for i, (name, svg) in enumerate(figures, start=1))
    notes = "".join(f"<li>{html.escape(n)}</li>" for n in snap.get("notes", []))
    return ("<!doctype html><html lang='en'><head><meta charset='utf-8'><title>" + html.escape(view.title)
            + "</title><style>@page{size:A4;margin:20mm}body{font-family:'Times New Roman',serif;margin:24px;"
            "color:#000}figure{margin:0 0 18px;width:" + mm + ";page-break-inside:avoid}figure img{width:100%}"
            "figcaption{font-size:9pt;line-height:1.35;margin-top:4px}h1{font-size:13pt}ul{font-size:9pt}"
            "</style></head><body><h1>" + html.escape(view.title) + "</h1>" + body
            + (f"<p style='font-size:9pt'><b>Notes.</b></p><ul>{notes}</ul>" if notes else "")
            + "<p style='font-size:8pt;color:#555'>Print this page (Ctrl+P) and choose 'Save as PDF' for a PDF.</p>"
            "</body></html>\n")


def write_view(view, built, out_dir: str | Path, formats: tuple[str, ...] = ("html", "svg", "csv"),
               width: str = "page") -> dict:
    from .schema import graph_schema, series_schema, check_view
    from ..research import database_fingerprint
    from ..timeutil import utcnow
    snap = built.snapshot
    problems = check_view(snap)
    if problems:
        raise ValueError("the view breaks its schema: " + "; ".join(problems[:10]))
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    files: list[Path] = []
    p = out / "view.json"
    p.write_text(dumps(snap), encoding="utf-8")
    files.append(p)
    p = out / "view.schema.json"
    p.write_text(json.dumps(graph_schema() if snap["kind"] == "graph" else series_schema(), ensure_ascii=False,
                            indent=1, sort_keys=True) + "\n", encoding="utf-8")
    files.append(p)
    if "csv" in formats:
        if snap["kind"] == "graph":
            files.append(_csv(out / "nodes.csv", node_rows(snap)))
            files.append(_csv(out / "edges.csv", edge_rows(snap)))
        else:
            for name, t in sorted(snap["tables"].items()):
                files.append(_csv(out / f"{name}.csv", t["rows"], t["columns"]))
    if "html" in formats:
        from .pages import write_page
        files.append(write_page(snap, out / "view.html"))
    figs: list[tuple[str, Path]] = []
    if "svg" in formats and built.figures:
        from ..charts.builders import export_chart
        px = WIDTHS.get(width, WIDTHS["page"])[1]
        for name, spec in built.figures:
            if spec.width > px:
                spec.width = px
            base = f"figure_{name}"                   # apart from the data tables' CSV files
            written = export_chart(spec, str(out / base))
            files += [Path(f) for f in written]
            figs.append((spec.title, out / f"{base}.svg"))
        page = out / "figures.html"
        page.write_text(figures_page(view, snap, figs, width), encoding="utf-8")
        files.append(page)
    manifest = {"written_at": utcnow().isoformat(timespec="seconds") + "Z", "software": snap["software"],
                "view": snap["view"], "kind": snap["kind"], "schema_version": snap["schema_version"],
                "definitions": snap["definitions"], "evidence": snap["evidence"], "parameters": snap["parameters"],
                "policy": snap["policy"], "database_fingerprint": database_fingerprint(),
                "files": {f.name: _sha(f) for f in files}}
    (out / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2, default=str),
                                       encoding="utf-8")
    return {"folder": str(out), "files": [f.name for f in files] + ["manifest.json"]}
