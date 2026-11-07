"""The work ledger (v2.3.0, plan section B3).

Records each unit of work of a run (a document read, a company fetched) with its outcome, so that a run can say how
far it got and why a document was not read. The ledger only records: what is skipped on a rerun is still decided by
the extraction state (and, for the market download, by the prices stored). With the switch ``jobs.ledger`` off,
nothing is recorded. A failure to record never stops the run.
"""
from __future__ import annotations

import logging
import uuid
from collections import Counter

from .features import enabled

log = logging.getLogger(__name__)

DONE, EMPTY, SKIPPED, FAILED, NOT_READ = "DONE", "EMPTY", "SKIPPED", "FAILED", "NOT_READ"
REASONS = {
    "MISSING_FILE": "the downloaded file is missing",
    "PARSE_ERROR": "the document could not be read",
    "NOT_APPLICABLE": "no reporting period, or not a document this reader applies to",
    "NO_VALUES": "read, but no value found",
    "FETCH_ERROR": "the source did not answer",
    "UP_TO_DATE": "already up to date",
}


class Ledger:
    """``with Ledger("financials") as led: led.record(item, state, reason, detail, seconds)``."""

    def __init__(self, job: str, flush_every: int = 200):
        self.job, self.run_id = job, uuid.uuid4().hex[:16]
        self.on = enabled("jobs.ledger")
        self._buf: list[dict] = []
        self.flush_every = flush_every
        self.counts: Counter = Counter()

    def record(self, item, state: str, reason: str | None = None, detail: str | None = None,
               seconds: float | None = None) -> None:
        self.counts[(state, reason)] += 1
        if not self.on:
            return
        self._buf.append({"run_id": self.run_id, "job": self.job, "item": str(item)[:200], "state": state,
                          "reason": reason, "detail": (detail or "")[:2000] or None, "seconds": seconds})
        if len(self._buf) >= self.flush_every:
            self.flush()

    def flush(self) -> None:
        if not self._buf:
            return
        rows, self._buf = self._buf, []
        try:
            from .models import SessionLocal
            from .models_v23 import WorkRecord
            s = SessionLocal()
            try:
                s.bulk_insert_mappings(WorkRecord, rows)
                s.commit()
            finally:
                s.close()
        except Exception as exc:                                  # noqa: BLE001  the ledger never stops a run
            log.warning("work ledger: %d record(s) not written: %s", len(rows), exc)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.flush()
        return False


def not_read(job: str | None = None, limit: int = 2000) -> dict:
    """Documents whose latest record is not a success, by job and reason, with examples (Files > Documents not
    read)."""
    from sqlalchemy import func
    from .models import SessionLocal, Disclosure, Company, init_db
    from .models_v23 import WorkRecord
    init_db()
    s = SessionLocal()
    try:
        latest = (s.query(WorkRecord.job, WorkRecord.item, func.max(WorkRecord.id).label("mx"))
                  .group_by(WorkRecord.job, WorkRecord.item))
        if job:
            latest = latest.filter(WorkRecord.job == job)
        sub = latest.subquery()
        q = (s.query(WorkRecord).join(sub, WorkRecord.id == sub.c.mx)
             .filter(WorkRecord.state.in_((FAILED, NOT_READ))).order_by(WorkRecord.job, WorkRecord.reason))
        rows, by = [], Counter()
        for r in q.limit(limit):
            by[(r.job, r.reason or "")] += 1
            rows.append({"job": r.job, "item": r.item, "state": r.state, "reason": r.reason,
                         "detail": r.detail, "when": r.started_at.isoformat(timespec="seconds")})
        ids = [int(r["item"]) for r in rows if r["item"].isdigit()]
        docs = {d.id: (d, c) for d, c in s.query(Disclosure, Company).join(Company, Company.id == Disclosure.company_id)
                .filter(Disclosure.id.in_(ids))} if ids else {}
        for r in rows:
            if r["item"].isdigit() and int(r["item"]) in docs:
                d, c = docs[int(r["item"])]
                r.update(code=c.security_code, title=d.title_cn, date=d.announcement_date, url=d.document_url)
        summary = [{"job": j, "reason": rsn or "-", "meaning": REASONS.get(rsn, ""), "documents": n}
                   for (j, rsn), n in sorted(by.items())]
        return {"summary": summary, "rows": rows}
    finally:
        s.close()
