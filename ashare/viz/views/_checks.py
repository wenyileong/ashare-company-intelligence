"""Readiness checks shared by the views (v2.2, plan section B4.2): for each kind of data, met, partly met (with
counts) or missing, and the action that fills it."""
from __future__ import annotations

from ..view import Requirement, MET, PARTLY, MISSING


def _codes(params: dict) -> list[str]:
    from ...util import parse_codes
    return parse_codes(params.get("code") or params.get("codes") or "")[0]


def _company_ids(s, params) -> list[int] | None:
    from ...models import Company
    codes = _codes(params)
    if not codes:
        return None
    return [c.id for c in s.query(Company.id).filter(Company.security_code.in_(codes))]


def _count(model, params, *filters) -> tuple[int, int]:
    """(rows, companies) of a table, for the companies named in ``params`` or for all."""
    from ...models import SessionLocal, init_db
    from sqlalchemy import func
    init_db()
    s = SessionLocal()
    try:
        q = s.query(func.count(model.id), func.count(func.distinct(model.company_id))).filter(*filters)
        ids = _company_ids(s, params)
        if ids is not None:
            if not ids:
                return 0, 0
            q = q.filter(model.company_id.in_(ids))
        n, comp = q.one()
        return int(n or 0), int(comp or 0)
    finally:
        s.close()


def _req(key, label, model_name, action, *, filters=None, partly_below: int | None = None):
    def check(params):
        from ... import models
        from ... import transactions  # noqa: F401
        model = getattr(models, model_name)
        if filters is None:
            extra = ()
        elif filters.__code__.co_argcount >= 2:          # v2.4.0: filters that depend on the view's date
            extra = filters(model, params)
        else:
            extra = filters(model)
        n, comp = _count(model, params, *extra)
        if n == 0:
            return MISSING, "none", action
        many = len(_codes(params)) or None
        detail = f"{n:,} rows for {comp:,} compan{'y' if comp == 1 else 'ies'}"
        if many and comp < many:
            return PARTLY, detail + f" of {many}", action
        if partly_below and comp < partly_below:
            return PARTLY, detail, action
        return MET, detail, None
    return Requirement(key, label, check)


def periodic_figures():
    return _req("figures", "financial figures from periodic reports", "FinancialFact",
                "Extract figures from reports",
                filters=lambda m: (m.metric.in_(("revenue", "net_profit_parent", "total_assets")),))


def guidance():
    return _req("guidance", "management guidance", "ExpectationObservation", "Read guidance",
                filters=lambda m: (m.source_kind == "MANAGEMENT_GUIDANCE",))


def control():
    return _req("control", "controllers", "ControlObservation", "Read controlling shareholder and actual controller")


def holders():
    return _req("holders", "top-10 shareholders", "OwnershipObservation", "Read top-10 shareholders from reports",
                filters=lambda m: (m.rank.isnot(None),))


def subsidiaries():
    return _req("subsidiaries", "subsidiaries", "SubsidiaryObservation", "Extract subsidiaries from reports")


def roster():
    return _req("roster", "directors and officers", "PersonRole",
                "Management: Extract from announcements and annual reports")


def regulatory():
    """v2.4.0 (loose end of finding 140): only the events published by the view's date count."""
    def by_date(m, params):
        from datetime import date
        from sqlalchemy import func
        as_of = (params or {}).get("as_of") or date.today().isoformat()
        return (func.coalesce(m.announcement_date, m.event_date) <= as_of,)
    return _req("regulatory", "regulatory events", "RegulatoryEvent", "Regulatory & legal: Extract from announcements",
                filters=by_date)


def industry():
    return _req("industry", "industry classification", "IndustryClassification",
                "Industry: Import a classification list", partly_below=1000)
