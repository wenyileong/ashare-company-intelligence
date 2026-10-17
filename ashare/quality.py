"""Data-quality report (v2.0), written with every release and on demand.

Sections:

1. coverage by layer, board and year: the share of companies in the data
   with at least one row for that layer in that year;
2. parser precision from the calibration table (Wilson lower bound);
3. review statistics (from the review queue, which is biased towards
   doubtful values and is reported beside calibration, not merged with it);
4. validation-flag rates per 100 companies;
5. confidence classes of the financial values;
6. known gaps, both computed (layers with no rows, scanned documents,
   companies without an extracted annual report) and standing limitations.
"""
from __future__ import annotations

import html
import json
from pathlib import Path

from sqlalchemy import text

from . import __version__
from .timeutil import utcnow

# layer: (table, date column, label)
LAYERS = (
    ("financials", "financial_facts", "reporting_period", "Financial statements"),
    ("prices", "market_bars", "trade_date", "Daily prices"),
    ("disclosures", "disclosures", "announcement_date", "Announcement catalogue"),
    ("ownership", "ownership_observations", "observation_date", "Shareholders"),
    ("management", "management_observations", "observation_date", "Directors and officers"),
    ("segments", "segment_observations", "reporting_period", "Segments"),
    ("subsidiaries", "subsidiary_observations", "observation_date", "Subsidiaries"),
    ("human_capital", "human_capital_observations", "reporting_period", "Workforce and R&D"),
    ("esg", "esg_observations", "reporting_period", "ESG disclosures"),
    ("corporate_actions", "corporate_actions", "announcement_date", "Corporate actions"),
    ("regulatory", "regulatory_events", "announcement_date", "Regulatory events"),
    ("pledges", "pledge_events", "announcement_date", "Pledges"),
    ("control", "control_observations", "observation_date", "Control"),
    ("transactions", "transaction_events", "announcement_date", "Transactions"),
)

STANDING_GAPS = (
    "Live-source adapters are verified by the Self-test on the user's machine, not by the build; endpoints "
    "change without notice.",
    "Scanned PDFs (no text layer) are catalogued but not parsed; there is no OCR.",
    "Ownership diagrams (方框图) are usually images, so intermediate stakes in control chains must be imported.",
    "Beijing Stock Exchange and B shares are off by default; coverage figures exclude them unless enabled.",
    "Values extracted by heuristic parsers carry calibrated confidence; only reviewed values are certain.",
    "Licensed vendor data (ratings, Shenwan industries, index files) are excluded from releases by default.",
)


def _columns(conn, table: str) -> set[str]:
    from sqlalchemy import inspect
    insp = inspect(conn)
    return {c["name"] for c in insp.get_columns(table)} if insp.has_table(table) else set()


def coverage(conn, scope_company: int | None = None) -> dict:
    """Companies per board, and per layer and year the share of them covered."""
    where = f" WHERE id = {int(scope_company)}" if scope_company is not None else ""
    boards = {}
    for board, n in conn.execute(text(f"SELECT COALESCE(board, exchange), COUNT(*) FROM companies{where} "
                                      "GROUP BY COALESCE(board, exchange)")):
        boards[board or "UNKNOWN"] = n
    out = {"companies_by_board": boards, "layers": {}}
    for key, table, col, label in LAYERS:
        cols = _columns(conn, table)
        if col not in cols or "company_id" not in cols:
            out["layers"][key] = {"label": label, "rows": 0, "by_year": {}}
            continue
        rows = conn.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar() or 0
        by_year: dict[str, dict[str, float]] = {}
        q = (f"SELECT SUBSTR(t.{col}, 1, 4) AS y, COALESCE(c.board, c.exchange) AS b, "
             f"COUNT(DISTINCT t.company_id) FROM {table} t JOIN companies c ON c.id = t.company_id "
             f"WHERE t.{col} IS NOT NULL GROUP BY y, b")
        for y, b, n in conn.execute(text(q)):
            if not y or not str(y).isdigit():
                continue
            denom = boards.get(b or "UNKNOWN") or 0
            by_year.setdefault(str(y), {})[b or "UNKNOWN"] = round(n / denom, 4) if denom else None
        out["layers"][key] = {"label": label, "rows": rows, "by_year": dict(sorted(by_year.items()))}
    return out


def calibration(conn) -> list[dict]:
    if not _columns(conn, "parser_calibration"):
        return []
    res = conn.execute(text("SELECT parser, field, parser_version, expected, correct, wrong, missed, spurious, "
                            "precision, precision_lower, recall FROM parser_calibration ORDER BY parser, field"))
    return [dict(r._mapping) for r in res]


def flag_rates(conn) -> list[dict]:
    if not _columns(conn, "validation_flags"):
        return []
    n_comp = conn.execute(text("SELECT COUNT(*) FROM companies")).scalar() or 0
    res = conn.execute(text("SELECT rule, severity, COUNT(*) AS n, COUNT(DISTINCT company_id) AS companies "
                            "FROM validation_flags GROUP BY rule, severity ORDER BY n DESC"))
    out = []
    for r in res:
        d = dict(r._mapping)
        d["per_100_companies"] = round(100 * d["n"] / n_comp, 2) if n_comp else None
        out.append(d)
    return out


def confidence_classes(conn) -> dict:
    from .crossvalidation import confidence_class
    if not _columns(conn, "financial_facts"):
        return {}
    out: dict[str, int] = {}
    for conf, status in conn.execute(text("SELECT confidence, validation_status FROM financial_facts")):
        k = confidence_class(conf, status)
        out[k] = out.get(k, 0) + 1
    return dict(sorted(out.items()))


def computed_gaps(conn, cov: dict) -> list[str]:
    gaps = [f"No rows for {v['label'].lower()}." for v in cov["layers"].values() if not v["rows"]]
    cols = _columns(conn, "disclosures")
    if "text_layer" in cols:
        n = conn.execute(text("SELECT COUNT(*) FROM disclosures WHERE text_layer = 'NONE'")).scalar() or 0
        if n:
            gaps.append(f"{n} downloaded documents have no text layer (scanned) and were not parsed.")
    if cols and _columns(conn, "financial_facts"):
        n = conn.execute(text("SELECT COUNT(*) FROM companies c WHERE NOT EXISTS (SELECT 1 FROM financial_facts f "
                              "WHERE f.company_id = c.id)")).scalar() or 0
        if n:
            gaps.append(f"{n} companies have no financial values.")
    return gaps


def build_report(data_engine=None, meta_engine=None, scope_company: int | None = None) -> dict:
    """Compute the report. *data_engine* holds the data described (a release
    snapshot or the working database); *meta_engine* holds calibration and
    review (the working database)."""
    from .models import engine, init_db
    init_db()
    meta = meta_engine or engine()
    data = data_engine or meta
    with data.connect() as conn:
        cov = coverage(conn, scope_company if data is meta else None)
        flags = flag_rates(conn)
        conf = confidence_classes(conn)
        gaps = computed_gaps(conn, cov)
    with meta.connect() as conn:
        cal = calibration(conn)
    from .review import review_stats
    try:
        rev = review_stats()
    except Exception:                       # review tables absent in an unusual database
        rev = []
    return {"created_utc": utcnow().isoformat(timespec="seconds"), "software_version": __version__,
            "coverage": cov, "calibration": cal, "review": rev, "flags": flags, "confidence_classes": conf,
            "known_gaps": {"computed": gaps, "standing": list(STANDING_GAPS)}}


def _pct(v):
    return "" if v is None else f"{100 * v:.0f}%"


def to_markdown(r: dict) -> str:
    L = [f"# Data-quality report", "", f"Created {r['created_utc']} with A-share Company Intelligence "
         f"v{r['software_version']}.", "", "## 1. Coverage", ""]
    boards = r["coverage"]["companies_by_board"]
    L.append("Companies by board: " + (", ".join(f"{b} {n}" for b, n in boards.items()) or "none") + ".")
    L.append("")
    L.append("Share of companies with at least one row, by layer, year and board.")
    L.append("")
    bnames = list(boards)
    L.append("| Layer | Rows | Year | " + " | ".join(bnames) + " |")
    L.append("|---|---:|---|" + "---:|" * len(bnames))
    for v in r["coverage"]["layers"].values():
        if not v["by_year"]:
            L.append(f"| {v['label']} | {v['rows']} | none | " + " | ".join("" for _ in bnames) + " |")
        for y, per in v["by_year"].items():
            L.append(f"| {v['label']} | {v['rows']} | {y} | " + " | ".join(_pct(per.get(b)) for b in bnames) + " |")
    L += ["", "## 2. Parser precision (calibration)", ""]
    if r["calibration"]:
        L.append("| Parser | Field | Version | Values | Precision | Lower bound | Recall |")
        L.append("|---|---|---|---:|---:|---:|---:|")
        for c in r["calibration"]:
            L.append(f"| {c['parser']} | {c['field']} | {c['parser_version'] or ''} | {c['expected']} | "
                     f"{_pct(c['precision'])} | {_pct(c['precision_lower'])} | {_pct(c['recall'])} |")
    else:
        L.append("No verified corpus has been evaluated, so parser confidence uses the default priors.")
    L += ["", "## 3. Review", ""]
    if r["review"]:
        L.append("Reviewed values are chosen for doubt, so these rates overstate the error rate.")
        L.append("")
        L.append("| Table | Method | Reviewed | Accepted | Corrected | Rejected |")
        L.append("|---|---|---:|---:|---:|---:|")
        for d in r["review"]:
            L.append(f"| {d['table']} | {d['method'] or ''} | {d['reviewed']} | {d['accepted']} | {d['corrected']} | "
                     f"{d['rejected']} |")
    else:
        L.append("No values have been reviewed.")
    L += ["", "## 4. Validation flags", ""]
    if r["flags"]:
        L.append("| Rule | Severity | Flags | Companies | Per 100 companies |")
        L.append("|---|---|---:|---:|---:|")
        for f in r["flags"]:
            L.append(f"| {f['rule']} | {f['severity']} | {f['n']} | {f['companies']} | {f['per_100_companies']} |")
    else:
        L.append("No validation flags.")
    L += ["", "## 5. Confidence of financial values", ""]
    L.append(", ".join(f"{k} {v}" for k, v in r["confidence_classes"].items()) or "No financial values.")
    L += ["", "## 6. Known gaps", ""]
    L += [f"- {g}" for g in r["known_gaps"]["computed"]] or ["- None computed."]
    L += ["", "Standing limitations:", ""]
    L += [f"- {g}" for g in r["known_gaps"]["standing"]]
    return "\n".join(L) + "\n"


def to_html(md: str) -> str:
    """A small Markdown subset (headings, tables, lists, paragraphs) to HTML."""
    out, in_table, in_list = [], False, False
    for line in md.splitlines():
        if line.startswith("|"):
            cells = [c.strip() for c in line.strip("|").split("|")]
            if set("".join(cells)) <= set("-:"):
                continue
            if not in_table:
                out.append("<table>")
                in_table = True
                out.append("<tr>" + "".join(f"<th>{html.escape(c)}</th>" for c in cells) + "</tr>")
                continue
            out.append("<tr>" + "".join(f"<td>{html.escape(c)}</td>" for c in cells) + "</tr>")
            continue
        if in_table:
            out.append("</table>")
            in_table = False
        if line.startswith("- "):
            if not in_list:
                out.append("<ul>")
                in_list = True
            out.append(f"<li>{html.escape(line[2:])}</li>")
            continue
        if in_list:
            out.append("</ul>")
            in_list = False
        if line.startswith("## "):
            out.append(f"<h2>{html.escape(line[3:])}</h2>")
        elif line.startswith("# "):
            out.append(f"<h1>{html.escape(line[2:])}</h1>")
        elif line.strip():
            out.append(f"<p>{html.escape(line)}</p>")
    if in_table:
        out.append("</table>")
    if in_list:
        out.append("</ul>")
    style = ("body{font-family:system-ui,'Microsoft YaHei',sans-serif;max-width:60rem;margin:2rem auto;padding:0 1rem;"
             "color:#222}table{border-collapse:collapse;margin:.5rem 0}td,th{border:1px solid #ddd;padding:.2rem .5rem;"
             "font-size:.9rem}th{background:#f4f4f4;text-align:left}h2{margin-top:2rem}")
    return (f"<!doctype html><html lang='en-GB'><head><meta charset='utf-8'><title>Data-quality report</title>"
            f"<style>{style}</style></head><body>" + "\n".join(out) + "</body></html>")


def write_quality_report(out_dir, data_engine=None, scope_company: int | None = None) -> dict:
    r = build_report(data_engine=data_engine, scope_company=scope_company)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    md = to_markdown(r)
    (out / "quality_report.md").write_text(md, encoding="utf-8")
    (out / "quality_report.html").write_text(to_html(md), encoding="utf-8")
    (out / "quality_report.json").write_text(json.dumps(r, ensure_ascii=False, indent=2, default=str),
                                             encoding="utf-8")
    layers = r["coverage"]["layers"]
    summary = {"companies": sum(r["coverage"]["companies_by_board"].values()),
               "layers_with_data": sorted(k for k, v in layers.items() if v["rows"]),
               "flags": sum(f["n"] for f in r["flags"]), "calibrated_parsers": len(r["calibration"]),
               "reviewed_values": sum(d["reviewed"] for d in r["review"]),
               "computed_gaps": len(r["known_gaps"]["computed"])}
    return {"files": ["quality_report.md", "quality_report.html", "quality_report.json"], "summary": summary,
            "report": r}
