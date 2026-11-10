"""Disclosure timeliness (v2.3.0, plan section B5).

For each periodic report: the days from the end of its period to its first publication, the legal deadline that
applied, and whether it was late. The rules, with their sources and how each was checked, are in
``rules/disclosure_deadlines.json``; a report whose deadline fell before a rule took effect gets no deadline (unknown,
never guessed). Only the first publication of the full Chinese report counts: a corrected version or a summary
published later is not a late filing.
"""
from __future__ import annotations

import calendar
from datetime import date
from pathlib import Path

RULES_FILE = Path(__file__).resolve().parent / "rules" / "disclosure_deadlines.json"     # the bundled pack


def rules() -> dict:
    """The deadline rules in use (v2.4.0: a swappable pack, see ``rulepacks``)."""
    from .rulepacks import data
    return data("deadlines")


def rules_note() -> str:
    """Which pack the deadlines came from, and whether its rules are provisional (for notes on every result)."""
    from .rulepacks import load
    pk = load("deadlines")
    s = f"Deadline rules: {pk.describe()}"
    if pk.provisional_ids():
        s += (f"; provisional until confirmed against the official text ({', '.join(pk.provisional_ids())})")
    return s + "."


def add_months(d: date, months: int) -> date:
    m = d.month - 1 + months
    y, m = d.year + m // 12, m % 12 + 1
    return date(y, m, min(d.day, calendar.monthrange(y, m)[1]))


def deadline(kind: str, period_end: str, period_type: str) -> tuple[str | None, str | None]:
    """(deadline, rule id) for a report, or (None, None) when no verified rule applies."""
    try:
        end = date.fromisoformat(period_end[:10])
    except (TypeError, ValueError):
        return None, None
    from .rulepacks import rule_status
    for r in rules()["rules"]:
        if rule_status(r) == "withdrawn":
            continue
        types = r["period_type"] if isinstance(r["period_type"], list) else [r["period_type"]]
        if kind not in r["kinds"] or period_type not in types:
            continue
        due = add_months(end, r["months_after_period_end"])
        if r.get("effective_from") and due.isoformat() < r["effective_from"]:
            return None, None
        if r.get("effective_to") and due.isoformat() > r["effective_to"]:
            continue
        return due.isoformat(), r["id"]
    return None, None


def report_rows(session, company_ids=None, as_of: str | None = None) -> list[dict]:
    """Each periodic report's first publication, with its period, deadline, delay and lateness."""
    from .models import Disclosure, Company
    from .disclosures import REPORT_KINDS
    from .financials import infer_period
    q = (session.query(Disclosure, Company).join(Company, Company.id == Disclosure.company_id)
         .filter(Disclosure.kind.in_(REPORT_KINDS), Disclosure.announcement_date.isnot(None)))
    if company_ids is not None:
        q = q.filter(Disclosure.company_id.in_(list(company_ids)))
    first: dict = {}
    for d, c in q:
        if as_of and d.announcement_date > as_of:
            continue
        period, ptype = infer_period(d.title_cn or "", "", d.announcement_date)
        if not period or ptype == "UNKNOWN":
            continue
        key = (c.id, d.kind, period)
        if key not in first or (d.announcement_date, d.id) < (first[key][0].announcement_date, first[key][0].id):
            first[key] = (d, c, period, ptype)
    out = []
    for d, c, period, ptype in sorted(first.values(), key=lambda x: (x[1].security_code, x[2], x[0].kind)):
        due, rule = deadline(d.kind, period, ptype)
        delay = (date.fromisoformat(d.announcement_date[:10]) - date.fromisoformat(period)).days
        out.append({"code": c.security_code, "company_id": c.id, "kind": d.kind, "period": period,
                    "period_type": ptype, "published": d.announcement_date[:10], "delay_days": delay,
                    "deadline": due, "rule": rule,
                    "late": (None if due is None else int(d.announcement_date[:10] > due)),
                    "days_late": (None if due is None else max(0, (date.fromisoformat(d.announcement_date[:10])
                                                                   - date.fromisoformat(due)).days)),
                    "disclosure_id": d.id, "title": d.title_cn})
    return out


def timeliness(security_code: str | None = None, year: int | None = None, as_of: str | None = None,
               out: str | None = None) -> dict:
    from .features import require
    from .models import SessionLocal, Company, init_db
    require("timeliness")
    init_db()
    s = SessionLocal()
    try:
        ids = None
        if security_code:
            ids = [c.id for c in s.query(Company).filter(Company.security_code == str(security_code).zfill(6))]
        rows = report_rows(s, ids, as_of)
    finally:
        s.close()
    if year:
        rows = [r for r in rows if r["period"].startswith(str(year))]
    judged = [r for r in rows if r["late"] is not None]
    summary = {"reports": len(rows), "with_a_deadline": len(judged), "late": sum(r["late"] for r in judged),
               "rules": rules()["version"], "note": rules_note()}
    if out:
        import csv
        p = Path(out)
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("w", encoding="utf-8-sig", newline="") as fh:
            cols = ["code", "kind", "period", "period_type", "published", "delay_days", "deadline", "late",
                    "days_late", "rule", "disclosure_id", "title"]
            w = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore")
            w.writeheader()
            w.writerows(rows)
        summary["file"] = str(p)
    return {"summary": summary, "rows": rows}
