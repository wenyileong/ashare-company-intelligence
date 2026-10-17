"""Ownership and capital-structure observations (v0.7, corrected in v0.8).

v0.8 fixes:
- shareholders' meeting notices (股东大会 / 股东会) are no longer classified
  as shareholder-register disclosures;
- quantities expressed in 万股 / 亿股 are scaled, not merely stripped;
- controlling-shareholder and actual-controller flags are tri-state, so a
  missing column is recorded as unknown (None) rather than as False;
- observation dates are normalised to YYYY-MM-DD;
- a conservative internal validation pass is provided.
"""
from __future__ import annotations

import csv
import re
from pathlib import Path

from .models import (
    SessionLocal, Company, Disclosure, OwnershipObservation,
    CapitalStructureObservation, init_db,
)

OWNERSHIP_TERMS = (
    "十大股东", "前十大股东", "前十名股东", "股东持股", "股权质押", "股份质押",
    "权益变动", "持股变动", "股东增减持", "实际控制人", "控股股东",
)

_MEETING_TERMS = ("股东大会", "股东会")


def classify_ownership_title(title):
    t = title or ""
    if "质押" in t:
        return "PLEDGE"
    if "增减持" in t or "增持" in t or "减持" in t or "权益变动" in t or "持股变动" in t:
        return "OWNERSHIP_CHANGE"
    if "实际控制人" in t or "控股股东" in t:
        return "CONTROL"
    if any(m in t for m in _MEETING_TERMS):
        return None
    if "股东" in t:
        return "SHAREHOLDERS"
    return None


_SCALES = (("亿股", 1e8), ("万股", 1e4), ("亿", 1e8), ("万", 1e4), ("股", 1.0))


def _num(v):
    """Parse a share count or percentage, applying 万/亿 multipliers."""
    if v is None:
        return None
    x = str(v).strip()
    if x in ("", "-", "--", "—"):
        return None
    x = x.replace(",", "").replace("，", "").replace("%", "").replace("％", "").strip()
    multiplier = 1.0
    for suffix, factor in _SCALES:
        if x.endswith(suffix):
            x = x[: -len(suffix)].strip()
            multiplier = factor
            break
    try:
        return float(x) * multiplier
    except ValueError:
        return None


def _flag(v):
    """Tri-state boolean: True / False / None (unknown)."""
    if v is None:
        return None
    s = str(v).strip().lower()
    if s in ("1", "true", "yes", "y", "是"):
        return True
    if s in ("0", "false", "no", "n", "否"):
        return False
    return None


def normalise_date(value) -> str | None:
    if not value:
        return None
    s = str(value).strip()
    m = re.match(r"^(\d{4})[-/.年](\d{1,2})[-/.月](\d{1,2})日?$", s)
    if m:
        return f"{int(m.group(1)):04d}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
    m = re.match(r"^(\d{4})(\d{2})(\d{2})$", s)
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    return s[:10]


def _int(v):
    return int(float(v)) if v not in (None, "") else None


def _company(session, code):
    if code in (None, ""):
        return None
    return session.query(Company).filter_by(security_code=str(code).strip().zfill(6)).first()


def import_ownership_csv(path, source="CSV_IMPORT"):
    init_db()
    p = Path(path)
    inserted = updated = 0
    errors = []
    with p.open("r", encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    session = SessionLocal()
    try:
        for i, r in enumerate(rows, 1):
            try:
                c = _company(session, r.get("security_code") or r.get("code"))
                if not c:
                    raise ValueError("company not found")
                obs_date = normalise_date(r.get("observation_date") or r.get("date") or r.get("report_date"))
                if not obs_date:
                    raise ValueError("observation_date missing")
                name = (r.get("shareholder_name") or r.get("shareholder") or "").strip() or None
                rank = _int(r.get("rank"))
                row = session.query(OwnershipObservation).filter_by(
                    company_id=c.id, observation_date=obs_date,
                    shareholder_name=name, source=source, rank=rank,
                ).one_or_none()
                vals = dict(
                    shareholder_type=r.get("shareholder_type"),
                    relationship=r.get("relationship"),
                    shares=_num(r.get("shares")),
                    ownership_pct=_num(r.get("ownership_pct")),
                    tradable_shares=_num(r.get("tradable_shares")),
                    pledged_shares=_num(r.get("pledged_shares")),
                    restricted_shares=_num(r.get("restricted_shares")),
                    change_shares=_num(r.get("change_shares")),
                    change_pct=_num(r.get("change_pct")),
                    is_controlling_shareholder=_flag(r.get("is_controlling_shareholder")),
                    is_actual_controller=_flag(r.get("is_actual_controller")),
                    source_document=r.get("source_document"),
                    source_page=_int(r.get("source_page")),
                    extraction_method=r.get("extraction_method") or "CSV_IMPORT",
                    confidence=float(r["confidence"]) if r.get("confidence") else None,
                    raw_text=r.get("raw_text"),
                    source=source,
                    validation_status="UNVALIDATED",
                )
                if row:
                    for k, v in vals.items():
                        setattr(row, k, v)
                    updated += 1
                else:
                    session.add(OwnershipObservation(
                        company_id=c.id, observation_date=obs_date,
                        shareholder_name=name, rank=rank, **vals,
                    ))
                    inserted += 1
                session.flush()
            except Exception as e:
                errors.append({"row": i, "error": str(e)})
        session.commit()
        return {"inserted": inserted, "updated": updated, "errors": errors}
    finally:
        session.close()


CAPITAL_FIELDS = (
    "total_shares", "tradable_shares", "restricted_shares",
    "a_shares", "b_shares", "h_shares", "treasury_shares",
)


def import_capital_csv(path, source="CSV_IMPORT"):
    init_db()
    p = Path(path)
    inserted = updated = 0
    errors = []
    with p.open("r", encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    session = SessionLocal()
    try:
        for i, r in enumerate(rows, 1):
            try:
                c = _company(session, r.get("security_code") or r.get("code"))
                obs_date = normalise_date(r.get("observation_date") or r.get("date") or r.get("report_date"))
                if not c or not obs_date:
                    raise ValueError("company/date missing")
                row = session.query(CapitalStructureObservation).filter_by(
                    company_id=c.id, observation_date=obs_date, source=source,
                ).one_or_none()
                vals = {k: _num(r.get(k)) for k in CAPITAL_FIELDS}
                vals.update(
                    source_document=r.get("source_document"),
                    source_page=_int(r.get("source_page")),
                    extraction_method=r.get("extraction_method") or "CSV_IMPORT",
                    confidence=float(r["confidence"]) if r.get("confidence") else None,
                    raw_text=r.get("raw_text"),
                    source=source,
                    validation_status="UNVALIDATED",
                )
                if row:
                    for k, v in vals.items():
                        setattr(row, k, v)
                    updated += 1
                else:
                    session.add(CapitalStructureObservation(company_id=c.id, observation_date=obs_date, **vals))
                    inserted += 1
                session.flush()
            except Exception as e:
                errors.append({"row": i, "error": str(e)})
        session.commit()
        return {"inserted": inserted, "updated": updated, "errors": errors}
    finally:
        session.close()


def validate_ownership(security_code=None, tolerance_pct=0.05):
    """Internal checks; flags but never alters observed values.

    Checks per (company, observation_date, source):
    - sum of reported ownership percentages does not exceed 100%;
    - pledged and restricted shares do not exceed shares held;
    - a holder's shares do not exceed total shares in a capital observation
      of the same date (any source).
    Capital observations: tradable + restricted ≈ total where all are present.
    """
    init_db()
    session = SessionLocal()
    result = {"ownership_checked": 0, "ownership_failed": 0,
              "capital_checked": 0, "capital_failed": 0, "errors": []}
    try:
        oq = session.query(OwnershipObservation)
        cq = session.query(CapitalStructureObservation)
        if security_code:
            c = _company(session, security_code)
            cid = c.id if c else -1
            oq = oq.filter(OwnershipObservation.company_id == cid)
            cq = cq.filter(CapitalStructureObservation.company_id == cid)
        capitals = cq.all()
        totals_by_date = {}
        for cap in capitals:
            if cap.total_shares:
                totals_by_date.setdefault((cap.company_id, cap.observation_date), cap.total_shares)

        groups = {}
        for o in oq.all():
            groups.setdefault((o.company_id, o.observation_date, o.source), []).append(o)
        for key, rows in groups.items():
            problems = []
            pct = sum(r.ownership_pct or 0 for r in rows)
            if pct > 100 + tolerance_pct:
                problems.append(f"ownership_pct sums to {pct:.4f}")
            total = totals_by_date.get((key[0], key[1]))
            for r in rows:
                row_problems = []
                if r.shares is not None:
                    if r.pledged_shares is not None and r.pledged_shares > r.shares * 1.0001:
                        row_problems.append("pledged > shares")
                    if r.restricted_shares is not None and r.restricted_shares > r.shares * 1.0001:
                        row_problems.append("restricted > shares")
                    if total and r.shares > total * 1.0001:
                        row_problems.append("shares > total_shares")
                r.validation_status = "FAILED_INTERNAL" if (row_problems or problems) else "VALIDATED_INTERNAL"
                if row_problems:
                    problems.append(f"{r.shareholder_name}: {', '.join(row_problems)}")
            result["ownership_checked"] += 1
            if problems:
                result["ownership_failed"] += 1
                result["errors"].append({"company_id": key[0], "date": key[1], "source": key[2], "problems": problems})

        for cap in capitals:
            if None in (cap.total_shares, cap.tradable_shares, cap.restricted_shares):
                continue
            result["capital_checked"] += 1
            residual = abs(cap.total_shares - cap.tradable_shares - cap.restricted_shares)
            if residual > max(cap.total_shares * 0.0001, 1.0):
                cap.validation_status = "FAILED_INTERNAL"
                result["capital_failed"] += 1
                result["errors"].append({"company_id": cap.company_id, "date": cap.observation_date,
                                         "source": cap.source, "problems": [f"total - tradable - restricted = {residual}"]})
            else:
                cap.validation_status = "VALIDATED_INTERNAL"
        session.commit()
        return result
    finally:
        session.close()


def catalogue_ownership_disclosures(security_code=None):
    init_db()
    session = SessionLocal()
    out = []
    try:
        q = session.query(Disclosure).filter(Disclosure.title_cn.is_not(None))
        if security_code:
            c = _company(session, security_code)
            q = q.filter(Disclosure.company_id == c.id) if c else q.filter(Disclosure.id == -1)
        for d in q.order_by(Disclosure.announcement_date.desc()).all():
            kind = classify_ownership_title(d.title_cn)
            if kind:
                out.append({"announcement_id": d.announcement_id, "date": d.announcement_date,
                            "code": d.sec_code, "kind": kind, "title": d.title_cn,
                            "document": d.document_url or d.local_path})
        return out
    finally:
        session.close()


def show_ownership(security_code, shareholder=None):
    init_db()
    session = SessionLocal()
    try:
        c = _company(session, security_code)
        if not c:
            return []
        q = session.query(OwnershipObservation).filter_by(company_id=c.id)
        if shareholder:
            q = q.filter(OwnershipObservation.shareholder_name.contains(shareholder))
        return q.order_by(OwnershipObservation.observation_date, OwnershipObservation.rank).all()
    finally:
        session.close()


def show_capital(security_code):
    init_db()
    session = SessionLocal()
    try:
        c = _company(session, security_code)
        if not c:
            return []
        return (session.query(CapitalStructureObservation)
                .filter_by(company_id=c.id)
                .order_by(CapitalStructureObservation.observation_date).all())
    finally:
        session.close()
