"""Watchlists and alerts (v2.3.0, plan section B9; switch ``watchlists``).

A watchlist names companies and the kinds of item to watch. Its first run records what is already there as a
baseline; each later run reports only what is new, as alerts kept inside the program (Operations > Alerts, and a CSV
from the command line). Nothing is sent anywhere: email and push notifications wait for a later version.
The daily update runs the watchlists when it finishes.
"""
from __future__ import annotations

KINDS = {
    "announcement": "any new announcement",
    "regulatory": "regulatory events (letters, measures, penalties)",
    "guidance": "earnings forecasts and flash reports",
    "controller_change": "a different actual controller read from a report",
    "late_report": "a periodic report published after its legal deadline",
    "insider": "directors' and officers' share dealings (when that experimental reader is on)",
}


def _items(s, kind: str, company_ids: list[int]) -> list[dict]:
    from .models import Disclosure, Company, RegulatoryEvent, ControlObservation
    code = {c.id: c.security_code for c in s.query(Company).filter(Company.id.in_(company_ids))}
    out = []
    if kind in ("announcement", "guidance"):
        q = s.query(Disclosure).filter(Disclosure.company_id.in_(company_ids))
        if kind == "guidance":
            q = q.filter(Disclosure.kind == "earnings_forecast_or_flash")
        for d in q:
            out.append({"key": f"D{d.id}", "code": code[d.company_id], "title": d.title_cn,
                        "date": d.announcement_date, "reference": d.document_url})
    elif kind == "regulatory":
        for e in s.query(RegulatoryEvent).filter(RegulatoryEvent.company_id.in_(company_ids)):
            out.append({"key": f"R{e.id}", "code": code[e.company_id],
                        "title": e.title_cn or e.legal_classification or e.event_type,
                        "date": e.announcement_date or e.event_date, "reference": e.primary_source_url})
    elif kind == "controller_change":
        by: dict = {}
        for o in s.query(ControlObservation).filter(ControlObservation.company_id.in_(company_ids)):
            by.setdefault(o.company_id, []).append(o)
        for cid, obs in by.items():
            obs.sort(key=lambda o: (o.observation_date or "", o.id))
            prev = None
            for o in obs:
                if o.actual_controller and prev and o.actual_controller != prev:
                    out.append({"key": f"C{o.id}", "code": code[cid], "title": f"actual controller now "
                                f"{o.actual_controller} (before: {prev})", "date": o.observation_date,
                                "reference": None})
                prev = o.actual_controller or prev
    elif kind == "late_report":
        from .timeliness import report_rows
        for r in report_rows(s, company_ids):
            if r["late"]:
                out.append({"key": f"L{r['disclosure_id']}", "code": r["code"], "title": f"{r['title']}: "
                            f"{r['days_late']} days after the deadline", "date": r["published"], "reference": None})
    elif kind == "insider":
        from .features import enabled
        if enabled("insider"):
            from .models_v23 import InsiderDealing
            for x in s.query(InsiderDealing).filter(InsiderDealing.company_id.in_(company_ids)):
                out.append({"key": f"I{x.id}", "code": code[x.company_id],
                            "title": f"{x.direction or ''} {x.shares or ''} shares".strip(),
                            "date": x.deal_date, "reference": None})
    return out


def add_watchlist(name: str, codes, kinds) -> dict:
    from .features import require
    from .util import parse_codes
    from .models import SessionLocal, init_db
    from .models_v23 import Watchlist
    require("watchlists")
    init_db()
    codes, _ = parse_codes(codes)
    kinds = [k.strip() for k in (kinds if isinstance(kinds, (list, tuple)) else str(kinds).split(",")) if k.strip()]
    bad = [k for k in kinds if k not in KINDS]
    if bad or not kinds:
        raise ValueError(f"kinds must be among: {', '.join(KINDS)}")
    if not codes:
        raise ValueError("name at least one company")
    s = SessionLocal()
    try:
        w = s.query(Watchlist).filter_by(name=name).one_or_none() or Watchlist(name=name)
        w.codes, w.kinds = ",".join(codes), ",".join(kinds)
        s.add(w)
        s.commit()
        return {"name": w.name, "codes": codes, "kinds": kinds}
    finally:
        s.close()


def run_watchlists(name: str | None = None) -> dict:
    """Run one watchlist or all: the first run records a baseline; later runs return the new items."""
    from .features import require
    from .models import SessionLocal, Company, init_db
    from .models_v23 import Watchlist, Alert
    from .timeutil import utcnow
    require("watchlists")
    init_db()
    s = SessionLocal()
    out = {"watchlists": 0, "new": []}
    try:
        q = s.query(Watchlist)
        if name:
            q = q.filter(Watchlist.name == name)
        for w in q:
            out["watchlists"] += 1
            ids = [c.id for c in s.query(Company).filter(Company.security_code.in_(w.codes.split(",")))]
            seen = {a.key for a in s.query(Alert.key).filter(Alert.watchlist_id == w.id)}
            baseline = w.baseline_at is None
            for kind in w.kinds.split(","):
                for it in _items(s, kind, ids):
                    key = f"{kind}:{it['key']}"
                    if key in seen:
                        continue
                    seen.add(key)
                    s.add(Alert(watchlist_id=w.id, key=key, kind=kind, security_code=it["code"],
                                title=(it["title"] or "")[:500], item_date=it["date"], reference=it["reference"],
                                baseline=int(baseline)))
                    if not baseline:
                        out["new"].append({"watchlist": w.name, "kind": kind, **{k: it[k] for k in
                                                                                  ("code", "title", "date")}})
            if baseline:
                w.baseline_at = utcnow()
            s.commit()
        return out
    finally:
        s.close()


def alerts(unseen_only: bool = True, mark_seen: bool = False) -> list[dict]:
    from .models import SessionLocal, init_db
    from .models_v23 import Alert, Watchlist
    from .timeutil import utcnow
    init_db()
    s = SessionLocal()
    try:
        q = (s.query(Alert, Watchlist).join(Watchlist, Watchlist.id == Alert.watchlist_id)
             .filter(Alert.baseline == 0))
        if unseen_only:
            q = q.filter(Alert.seen_at.is_(None))
        rows = []
        for a, w in q.order_by(Alert.created_at.desc(), Alert.id.desc()):
            rows.append({"id": a.id, "watchlist": w.name, "kind": a.kind, "code": a.security_code,
                         "date": a.item_date, "title": a.title, "reference": a.reference})
            if mark_seen and a.seen_at is None:
                a.seen_at = utcnow()
        s.commit()
        return rows
    finally:
        s.close()
