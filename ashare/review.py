"""Review queue and manual corrections (v1.5).

The queue collects what needs a person's eye: validation flags (including
parser disagreements) and low-confidence values, ordered by materiality.
Each item can be accepted, corrected (new value and reason), rejected (the
value is not disclosed) or deferred.

Corrections are stored in ``manual_corrections`` with reviewer, time and
reason, keyed by the observation's *natural key* (company, document, period,
metric …) rather than its row id, so they survive re-extraction. Original
observations are never altered; views apply corrections when they read
(:class:`CorrectionIndex`) and say that they did.
"""
from __future__ import annotations

import getpass
import hashlib
import json
import math

from .timeutil import utcnow
from .models import (SessionLocal, init_db, Company, ValidationFlag, ReviewItem, ManualCorrection,
                     FinancialFact, SegmentObservation, SubsidiaryObservation, HumanCapitalObservation,
                     EsgObservation, ManagementObservation)

# table -> (model, natural-key columns, default field, label columns)
REVIEWABLE = {
    "financial_facts": (FinancialFact, ("company_id", "disclosure_id", "reporting_period", "period_type", "metric",
                                        "consolidation_scope"), "value", ("metric", "reporting_period")),
    "segment_observations": (SegmentObservation, ("company_id", "disclosure_id", "reporting_period", "dimension",
                                                  "segment_name"), "revenue", ("dimension", "segment_name")),
    "subsidiary_observations": (SubsidiaryObservation, ("company_id", "observation_date", "entity_name", "source"),
                                "total_pct", ("entity_name",)),
    "human_capital_observations": (HumanCapitalObservation, ("company_id", "disclosure_id", "reporting_period", "item"),
                                   "value", ("item", "reporting_period")),
    "esg_observations": (EsgObservation, ("company_id", "disclosure_id", "reporting_period", "item"), "value",
                         ("item", "reporting_period")),
    "management_observations": (ManagementObservation, ("company_id", "observation_date", "person_name", "role",
                                                        "source"), "remuneration", ("person_name", "role")),
}
LOW_CONFIDENCE_TABLES = ("financial_facts", "segment_observations", "subsidiary_observations",
                         "human_capital_observations", "esg_observations")
SEVERITY_WEIGHT = {"ERROR": 3.0, "WARN": 2.0, "INFO": 1.0}
ACTIONS = ("accept", "correct", "reject", "defer")


def natural_key(table: str, row) -> str:
    cols = REVIEWABLE[table][1]
    return json.dumps({c: getattr(row, c) for c in cols}, ensure_ascii=False, sort_keys=True, default=str)


def _item_key(kind: str, rule: str | None, table: str, nkey: str, field: str | None) -> str:
    return hashlib.sha256(f"{kind}|{rule}|{table}|{nkey}|{field}".encode("utf-8")).hexdigest()[:40]


def _parse_value(v):
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip().replace(",", "")
    try:
        return float(s.rstrip("%")) / 100 if s.endswith("%") else float(s)
    except ValueError:
        return s


class CorrectionIndex:
    """Latest correction per (natural key, field) for one table."""

    def __init__(self, session, table: str):
        self.table = table
        self.map: dict[tuple, ManualCorrection] = {}
        if table not in REVIEWABLE:
            return
        try:
            rows = (session.query(ManualCorrection).filter_by(table_name=table, superseded=0)
                    .order_by(ManualCorrection.created_at).all())
        except Exception:
            rows = []
        for r in rows:
            self.map[(r.natural_key, r.field)] = r
        self.by_key: dict[str, dict] = {}
        for (k, f), r in self.map.items():
            self.by_key.setdefault(k, {})[f] = r

    def get(self, row, field: str | None = None):
        if not self.map:
            return None
        field = field or REVIEWABLE[self.table][2]
        return self.map.get((natural_key(self.table, row), field))

    def apply(self, row, value, field: str | None = None):
        """Return (value, review) where review is None, 'ACCEPTED', 'CORRECTED' or 'REJECTED'."""
        c = self.get(row, field)
        if c is None:
            return value, None
        if c.action == "REJECT":
            return None, "REJECTED"
        if c.action == "CORRECT":
            return _parse_value(c.corrected_value), "CORRECTED"
        return value, "ACCEPTED"


class ReviewedRow:
    """Read-only view of an observation with corrections applied."""

    def __init__(self, row, overrides: dict, review: dict):
        object.__setattr__(self, "_row", row)
        object.__setattr__(self, "_overrides", overrides)
        object.__setattr__(self, "review", review)

    def __getattr__(self, name):
        if name in self._overrides:
            return self._overrides[name]
        return getattr(self._row, name)

    def __setattr__(self, name, value):
        raise AttributeError("reviewed rows are read-only")


def reviewed_rows(session, table: str, rows: list) -> list:
    """Wrap rows whose fields have corrections; other rows are returned as they are."""
    idx = CorrectionIndex(session, table)
    if not idx.map:
        return list(rows)
    out = []
    for row in rows:
        corr = idx.by_key.get(natural_key(table, row))
        if not corr:
            out.append(row)
            continue
        overrides, review = {}, {}
        for field, c in corr.items():
            if c.action == "REJECT":
                overrides[field], review[field] = None, "REJECTED"
            elif c.action == "CORRECT":
                overrides[field], review[field] = _parse_value(c.corrected_value), "CORRECTED"
            else:
                review[field] = "ACCEPTED"
        out.append(ReviewedRow(row, overrides, review))
    return out


# --- queue ----------------------------------------------------------------------

def _revenue_scale(session, company_id) -> float | None:
    f = (session.query(FinancialFact).filter_by(company_id=company_id, metric="revenue")
         .order_by(FinancialFact.reporting_period.desc()).first())
    return abs(f.value) if f and f.value else None


def _materiality(severity_w: float, value, scale: float | None, confidence) -> float:
    m = severity_w
    if isinstance(value, (int, float)) and value and scale:
        m += min(2.0, 2.0 * abs(value) / scale)
    elif isinstance(value, (int, float)) and value:
        m += min(1.0, math.log10(abs(value) + 1) / 12)
    if confidence is not None:
        m += max(0.0, 1.0 - confidence)
    return round(m, 3)


def build_review_queue(security_code: str | None = None, low_confidence_below: float = 0.6) -> dict:
    """Create or refresh review items; resolved items keep their status."""
    init_db()
    s = SessionLocal()
    totals = {"flags": 0, "low_confidence": 0, "new": 0, "obsolete": 0}
    try:
        cq = s.query(Company)
        if security_code:
            cq = cq.filter(Company.security_code == str(security_code).zfill(6))
        companies = cq.all()
        ids = [c.id for c in companies]
        existing = {i.item_key: i for i in s.query(ReviewItem).filter(ReviewItem.company_id.in_(ids)).all()}
        live = set()

        def upsert(kind, rule, severity, company_id, table, row, field, value, confidence, details, scale):
            nkey = natural_key(table, row) if table in REVIEWABLE and row is not None else json.dumps(
                {"row_ids": details.get("row_ids")})
            key = _item_key(kind, rule, table, nkey, field)
            live.add(key)
            item = existing.get(key)
            if item is None:
                item = ReviewItem(item_key=key, kind=kind, rule=rule, company_id=company_id, table_name=table,
                                  natural_key=nkey, status="OPEN", created_at=utcnow())
                s.add(item)
                existing[key] = item
                totals["new"] += 1
            elif item.status == "OBSOLETE":
                item.status = "OPEN"
            item.severity, item.row_id, item.field = severity, getattr(row, "id", None), field
            item.value = None if value is None else str(value)
            item.confidence = confidence
            item.details = json.dumps(details, ensure_ascii=False, default=str)
            item.materiality = _materiality(SEVERITY_WEIGHT.get(severity, 1.5), value, scale, confidence)
            item.updated_at = utcnow()

        for c in companies:
            scale = _revenue_scale(s, c.id)
            for f in s.query(ValidationFlag).filter_by(company_id=c.id).all():
                row_ids = json.loads(f.row_ids or "[]")
                table = f.table_name
                row = None
                if table in REVIEWABLE and row_ids:
                    row = s.get(REVIEWABLE[table][0], row_ids[0])
                field = REVIEWABLE[table][2] if table in REVIEWABLE else None
                value = getattr(row, field, None) if row is not None and field else None
                details = {"row_ids": row_ids, "flag": json.loads(f.details or "{}")}
                kind = "DISAGREEMENT" if f.rule == "PARSER_DISAGREEMENT" else "FLAG"
                upsert(kind, f.rule, f.severity, c.id, table, row, field, value,
                       getattr(row, "confidence", None), details, scale)
                totals["flags"] += 1
            for table in LOW_CONFIDENCE_TABLES:
                model, _, field, _ = REVIEWABLE[table]
                q = s.query(model).filter(model.company_id == c.id, model.confidence.isnot(None),
                                          model.confidence < low_confidence_below)
                for row in q.all():
                    value = getattr(row, field, None)
                    if value is None:
                        continue
                    upsert("LOW_CONFIDENCE", None, "INFO", c.id, table, row, field, value, row.confidence,
                           {"row_ids": [row.id], "method": getattr(row, "extraction_method", None)}, scale)
                    totals["low_confidence"] += 1
        for key, item in existing.items():
            if key not in live and item.status in ("OPEN", "DEFERRED"):
                item.status = "OBSOLETE"
                totals["obsolete"] += 1
        s.commit()
        totals["open"] = s.query(ReviewItem).filter(ReviewItem.company_id.in_(ids), ReviewItem.status == "OPEN").count()
        return totals
    finally:
        s.close()


def _label(s, item: ReviewItem) -> str:
    if item.table_name in REVIEWABLE and item.row_id:
        row = s.get(REVIEWABLE[item.table_name][0], item.row_id)
        if row is not None:
            return " ".join(str(getattr(row, c)) for c in REVIEWABLE[item.table_name][3] if getattr(row, c, None))
    return item.table_name


def review_queue(security_code: str | None = None, status: str = "OPEN", limit: int = 200) -> list[dict]:
    init_db()
    s = SessionLocal()
    try:
        q = s.query(ReviewItem, Company).join(Company, ReviewItem.company_id == Company.id)
        if security_code:
            q = q.filter(Company.security_code == str(security_code).zfill(6))
        if status and status.upper() != "ALL":
            q = q.filter(ReviewItem.status == status.upper())
        q = q.order_by(ReviewItem.materiality.desc(), ReviewItem.id).limit(limit)
        return [{"id": i.id, "code": c.security_code, "kind": i.kind, "rule": i.rule, "severity": i.severity,
                 "table": i.table_name, "row_id": i.row_id, "item": _label(s, i), "field": i.field,
                 "value": i.value, "confidence": i.confidence, "materiality": i.materiality, "status": i.status}
                for i, c in q.all()]
    finally:
        s.close()


def review_item(item_id: int) -> dict:
    """Everything the Review page shows for one item, including the trace."""
    from .research import trace
    init_db()
    s = SessionLocal()
    try:
        i = s.get(ReviewItem, int(item_id))
        if i is None:
            raise ValueError(f"no review item {item_id}")
        out = {"id": i.id, "kind": i.kind, "rule": i.rule, "severity": i.severity, "status": i.status,
               "table": i.table_name, "row_id": i.row_id, "field": i.field, "value": i.value,
               "confidence": i.confidence, "materiality": i.materiality, "label": _label(s, i),
               "details": json.loads(i.details or "{}"), "corrections": []}
        for c in s.query(ManualCorrection).filter_by(table_name=i.table_name, natural_key=i.natural_key).order_by(
                ManualCorrection.created_at):
            out["corrections"].append({"action": c.action, "field": c.field, "original": c.original_value,
                                       "corrected": c.corrected_value, "reason": c.reason, "reviewer": c.reviewer,
                                       "at": c.created_at.isoformat(timespec="seconds"),
                                       "superseded": bool(c.superseded)})
    finally:
        s.close()
    if out["row_id"] and out["table"] in REVIEWABLE:
        try:
            out["trace"] = trace(out["table"], out["row_id"])
        except Exception as exc:  # trace is informative only
            out["trace"] = {"error": repr(exc)}
    return out


def _record(s, table: str, row, field: str, action: str, value, reason: str | None, reviewer: str | None,
            item_id: int | None) -> ManualCorrection:
    nkey = natural_key(table, row)
    for old in s.query(ManualCorrection).filter_by(table_name=table, natural_key=nkey, field=field, superseded=0):
        old.superseded = 1
    original = getattr(row, field, None)
    corr = ManualCorrection(table_name=table, row_id=row.id, natural_key=nkey, field=field, action=action,
                            original_value=None if original is None else str(original),
                            corrected_value=None if value is None else str(value), reason=reason,
                            reviewer=reviewer or _whoami(), created_at=utcnow(), review_item_id=item_id,
                            superseded=0, source="MANUAL_REVIEW")
    s.add(corr)
    return corr


def _whoami() -> str:
    try:
        return getpass.getuser()
    except Exception:
        return "unknown"


def resolve(item_id: int, action: str, value=None, reason: str | None = None, reviewer: str | None = None,
            field: str | None = None) -> dict:
    """Accept, correct, reject or defer a review item."""
    action = action.lower()
    if action not in ACTIONS:
        raise ValueError(f"action must be one of {', '.join(ACTIONS)}")
    if action == "correct" and (value is None or str(value).strip() == ""):
        raise ValueError("a correction needs a value")
    if action in ("correct", "reject") and not (reason or "").strip():
        raise ValueError("a correction or rejection needs a reason")
    init_db()
    s = SessionLocal()
    try:
        item = s.get(ReviewItem, int(item_id))
        if item is None:
            raise ValueError(f"no review item {item_id}")
        if action == "defer":
            item.status, item.updated_at = "DEFERRED", utcnow()
            s.commit()
            return {"id": item.id, "status": item.status}
        if item.table_name not in REVIEWABLE or not item.row_id:
            raise ValueError(f"items on {item.table_name} cannot be corrected here; resolve the source data instead")
        row = s.get(REVIEWABLE[item.table_name][0], item.row_id)
        if row is None:
            raise ValueError("the observation no longer exists; rebuild the queue")
        f = field or item.field or REVIEWABLE[item.table_name][2]
        if not hasattr(row, f):
            raise ValueError(f"{item.table_name} has no field {f}")
        _record(s, item.table_name, row, f, action.upper(), _parse_value(value) if action == "correct" else
                (None if action == "reject" else getattr(row, f)), reason, reviewer, item.id)
        item.status = {"accept": "ACCEPTED", "correct": "CORRECTED", "reject": "REJECTED"}[action]
        item.updated_at = utcnow()
        s.commit()
        return {"id": item.id, "status": item.status, "field": f}
    finally:
        s.close()


def correct_value(table: str, row_id: int, value, reason: str, field: str | None = None,
                  reviewer: str | None = None, action: str = "correct") -> dict:
    """Record a correction directly, without a queue item."""
    if table not in REVIEWABLE:
        raise ValueError(f"table must be one of {', '.join(REVIEWABLE)}")
    if not (reason or "").strip():
        raise ValueError("a correction needs a reason")
    init_db()
    s = SessionLocal()
    try:
        row = s.get(REVIEWABLE[table][0], int(row_id))
        if row is None:
            raise ValueError(f"no row {row_id} in {table}")
        f = field or REVIEWABLE[table][2]
        act = action.upper()
        _record(s, table, row, f, act, _parse_value(value) if act == "CORRECT" else None, reason, reviewer, None)
        s.commit()
        return {"table": table, "row_id": row.id, "field": f, "action": act}
    finally:
        s.close()


def review_stats() -> list[dict]:
    """Review outcomes by table and extraction method.

    These rates come from the items people chose to review (mostly low
    confidence and flagged values), so they are biased towards errors and are
    shown next to calibration rather than merged into it.
    """
    init_db()
    s = SessionLocal()
    try:
        out: dict[tuple, dict] = {}
        for c in s.query(ManualCorrection).filter_by(superseded=0).all():
            model = REVIEWABLE.get(c.table_name, (None,))[0]
            row = s.get(model, c.row_id) if model and c.row_id else None
            method = getattr(row, "extraction_method", None) if row is not None else None
            k = (c.table_name, method)
            d = out.setdefault(k, {"table": c.table_name, "method": method, "accepted": 0, "corrected": 0,
                                   "rejected": 0})
            d[{"ACCEPT": "accepted", "CORRECT": "corrected", "REJECT": "rejected"}[c.action]] += 1
        for d in out.values():
            n = d["accepted"] + d["corrected"] + d["rejected"]
            d["reviewed"] = n
            d["accept_rate"] = d["accepted"] / n if n else None
        return sorted(out.values(), key=lambda d: (d["table"], d["method"] or ""))
    finally:
        s.close()
