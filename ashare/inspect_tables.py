"""``inspect-tables``: what the parsers made of one table in one report (v2.1, finding 98).

The author cannot send the reports themselves. This writes a small text file instead, with:
* the pages of the table's section, in both readings (plain text and layout);
* for each line, the parser's decision: a heading, a header, a row read, a row rejected (with the check that
  failed), or a line outside the table;
* which reading was kept, and what the two readings found.

The file holds the table's lines as the report prints them, shareholder names included. These are disclosed data,
but the file is the author's to share or not; nothing is sent anywhere.
"""
from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

TABLES = {
    "top10": {"sections": ["top10", "top10_tradable"], "family": "top10"},
    "segments": {"sections": ["segments"], "family": "segments"},
    "control": {"sections": ["control"], "family": None},
    # v2.1.2 (finding 129): the consolidated balance sheet, with the numbers each line yields
    "balance_sheet": {"sections": ["fin_bs"], "family": None},
}

_BS_TOTALS = ("total_current_assets", "total_non_current_assets", "total_assets", "total_current_liabilities",
              "total_non_current_liabilities", "total_liabilities", "equity_parent", "minority_interests", "equity",
              "total_liabilities_and_equity")


def _balance_trace(pages: list[str], page_set: set[int]) -> tuple[list[tuple], list[dict], str]:
    """Each line of the balance-sheet pages with the number tokens the reader finds in it, and the totals read."""
    from .cas import parse_statement_items
    from .financials import _PDF_NUM, repair_leading_digits
    items = [it for it in parse_statement_items(pages) if it.get("statement") == "BS"]
    totals = [it for it in items if it["metric"] in _BS_TOTALS]
    out = []
    for pno, page in enumerate(pages, start=1):
        if pno - 1 not in page_set:
            continue
        for raw in page.splitlines():
            line = raw.replace("　", " ").strip()
            if not line:
                continue
            toks = [m.group(0).strip() for m in re.finditer(_PDF_NUM, line)]
            hit = [it["metric"] for it in totals if it.get("page") == pno and it.get("raw_value")
                   and str(it["raw_value"]).strip() in line]
            decision = ("numbers: " + " | ".join(toks)) if toks else ""
            if hit:
                decision += ("; " if decision else "") + "read as " + ", ".join(hit)
            out.append((pno, line, decision))
    facts = [{"metric": it["metric"], "value": it["value"], "period": "p", "period_type": "p",
              "method": "PDF_STATEMENT_TABLE", "consolidation_scope": None} for it in totals]
    by = {f["metric"]: f["value"] for f in facts}
    a, l, e = by.get("total_assets"), by.get("total_liabilities"), by.get("equity")
    if None not in (a, l, e):
        summary = f"assets {a:,.2f}; liabilities {l:,.2f}; equity {e:,.2f}; difference {a - l - e:,.2f}"
        repaired = {f["metric"]: f["value"] for f in repair_leading_digits([dict(f) for f in facts])}
        changed = [m for m in repaired if repaired[m] != by.get(m)]
        if changed:
            summary += "; restored from the balance identity: " + ", ".join(
                f"{m} {by[m]:,.2f} -> {repaired[m]:,.2f}" for m in changed)
    else:
        summary = "totals read: " + (", ".join(f"{m} {v:,.2f}" for m, v in by.items()) or "none")
    return out, totals, summary


def _matching_rows(line: str, rows: list[dict], name_key: str) -> list[dict]:
    flat = re.sub(r"\s+", "", line)
    return [r for r in rows if r.get(name_key) and re.sub(r"\s+", "", str(r[name_key])) in flat]


def _generic_trace(pages: list[str], rows: list[dict], name_key: str, page_set: set[int]) -> list[tuple]:
    """For parsers without a trace of their own: a line is 'read' when a row's name stands in it."""
    out = []
    for pno, page in enumerate(pages, start=1):
        if pno - 1 not in page_set:
            continue
        for raw in page.splitlines():
            line = raw.replace("　", " ").strip()
            if not line:
                continue
            hits = [r for r in _matching_rows(line, rows, name_key) if r.get("page") in (None, pno)]
            out.append((pno, line, ("read: " + ", ".join(str(r[name_key]) for r in hits)) if hits else "not read"))
    return out


def _segments_rows(pages):
    from .segments import parse_segment_pages
    return parse_segment_pages(pages)


def _control_rows(pages):
    from .control import parse_control_text
    r = parse_control_text(pages)
    rows = []
    if r.get("controlling_shareholder"):
        rows.append({"name": r["controlling_shareholder"], "role": "controlling shareholder", "page": None})
    if r.get("actual_controller"):
        rows.append({"name": r["actual_controller"], "role": "actual controller", "page": None})
    return rows, r


def find_report(code: str, year: int | None = None) -> int:
    """The ID of the latest downloaded annual or interim report of a company (for one fiscal year, if given)."""
    from .models import SessionLocal, Disclosure, Company, init_db
    from .disclosures import REPORT_KINDS
    init_db()
    s = SessionLocal()
    try:
        q = (s.query(Disclosure).join(Company, Disclosure.company_id == Company.id)
             .filter(Company.security_code == str(code).zfill(6), Disclosure.local_path.isnot(None),
                     Disclosure.kind.in_(REPORT_KINDS)))
        docs = [d for d in q.order_by(Disclosure.announcement_date.desc(), Disclosure.id.desc())
                if year is None or f"{year}年" in (d.title_cn or "")]
        if not docs:
            raise ValueError(f"no downloaded periodic report for {code}" + (f" for {year}" if year else ""))
        return docs[0].id
    finally:
        s.close()


def inspect_table(disclosure_id: int, table: str, out: str | Path | None = None) -> Path:
    """Write the inspection file for one table of one document; returns its path."""
    from .models import SessionLocal, Disclosure, Company, init_db
    from .reportreader import ReportReader
    from . import __version__
    if table not in TABLES:
        raise ValueError(f"unknown table {table!r}; choose one of {', '.join(TABLES)}")
    init_db()
    s = SessionLocal()
    try:
        d = s.get(Disclosure, int(disclosure_id))
        if d is None:
            raise ValueError(f"no document with ID {disclosure_id}")
        c = s.get(Company, d.company_id)
        path = Path(d.local_path) if d.local_path else None
        title, code, ann = d.title_cn, c.security_code if c else "", d.announcement_date
    finally:
        s.close()
    if path is None or not path.exists():
        raise ValueError(f"document {disclosure_id} is not downloaded (run 'Download documents' first)")
    spec = TABLES[table]
    lines = [f"inspect-tables, A-share Company Intelligence {__version__}, {datetime.now():%Y-%m-%d %H:%M}",
             f"Document {disclosure_id}: {code} {title} ({ann})",
             f"File: {path.name}",
             f"Table: {table}",
             "",
             "This file holds the table's lines as the report prints them. It is yours to share or not.",
             ""]
    with ReportReader(path) as rr:
        page_set = set(rr.section_pages(spec["sections"]))
        lines.append(f"Pages: {rr.n}; section pages found: "
                     + (", ".join(str(i + 1) for i in sorted(page_set)) if page_set else
                        "none (the parsers read the whole document)"))
        readings = {}
        for variant in ("text", "layout"):
            pages = rr.pages(variant, spec["sections"])
            if not pages:
                lines += ["", f"=== {variant} reading: not available ==="]
                continue
            if not page_set:
                page_set_v = set(range(len(pages)))
            else:
                page_set_v = page_set
            if table == "top10":
                from .control import parse_top10_pages, parse_top10_tradable_pages
                trace: list = []
                rows = parse_top10_pages(pages, trace)
                tradable = parse_top10_tradable_pages(pages)
                summary = f"{len(rows)} top-10 row(s), {len(tradable)} tradable-holder row(s)"
                readings[variant] = rows
            elif table == "segments":
                rows = _segments_rows(pages)
                trace = _generic_trace(pages, rows, "segment_name", page_set_v)
                summary = f"{len(rows)} segment row(s)"
                readings[variant] = rows
            elif table == "balance_sheet":
                trace, rows, summary = _balance_trace(pages, page_set_v)
                readings[variant] = rows
            else:
                rows, r = _control_rows(pages)
                trace = _generic_trace(pages, rows, "name", page_set_v)
                summary = (f"controlling shareholder: {r.get('controlling_shareholder') or '-'}; "
                           f"actual controller: {r.get('actual_controller') or '-'}")
                readings[variant] = rows
            lines += ["", f"=== {variant} reading: {summary} ==="]
            last = None
            for pno, line, decision in trace:
                if pno != last and pno is not None:
                    lines.append(f"--- page {pno} ---")
                    last = pno
                lines.append(f"  {line}" if not decision else f"  {line}\n      -> {decision}")
    if spec["family"]:
        from .parsers import dual_run
        with ReportReader(path) as rr2:
            kept, info = dual_run(spec["family"], path, {"title": title}, sections=spec["sections"], reader=rr2)
        extra = info.pop("secondary_rows", [])
        lines += ["", "=== Decision ===",
                  f"Reading kept: {info.get('primary') or '-'}",
                  f"Rows kept: {len(kept)}; rows only the other reading found: {len(extra)}"]
        if table == "top10":
            from .control import merge_top10
            merged, n_added = merge_top10([dict(r) for r in kept], [dict(r) for r in extra])
            lines.append(f"Rows added from the other reading (the table still passing its checks): {n_added}")
            for r in merged:
                lines.append(f"  {r['rank']:>2}. {r['shareholder_name']}  {r['shares']:,.0f}  {r['ownership_pct']}%"
                             + ("  (added; other reading only)" if r.get("_added") else ""))
        else:
            for r in extra:
                lines.append(f"  other reading only: {r.get('segment_name') or r}")
    target = Path(out) if out else Path("exports") / f"inspect_{disclosure_id}_{table}.txt"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return target
