"""Progress and resume for the document extractors (v2.0.8, findings 76, 77 and 79).

Financial extraction has shown its progress and resumed since v2.0.6. The table extractors (top-10 holders,
control, segments, R&D and workforce, subsidiaries, the management roster) printed "... 25 documents read
(0.0 per second)", counting readings rather than documents, and started again from the beginning when stopped.

Each document an extractor finishes is recorded in ``extraction_state`` with the extractor's version. A rerun
skips documents already read by that version; a new version (a corrected parser) reads every document again.
"""
from __future__ import annotations

import time
from pathlib import Path

# Bump a version when its parser changes what it reads, so that a normal run re-reads every document.
VERSIONS = {
    "top_holders": "top10-2",            # v2.0.7 layouts; v2.0.8 targeted reading (finding 77: finish the re-read)
    "control": "control-2",              # v2.0.8: both exchanges' layouts (findings 78 and 89)
    "segments": "segments-2",            # v2.0.8: page breaks, subtotals, table kind (finding 83)
    "human_capital": "human_capital-1",
    "subsidiaries": "subsidiaries-1",
    "roster": "roster-1",
}


def _duration(seconds: float) -> str:
    from .financials import _duration as d
    return d(seconds)


class Progress:
    """'250 of 9,800 documents; 8.7 s each; about 23 hours left', every ``every`` documents and once a minute."""

    def __init__(self, total: int, say=None, every: int = 25, interval: float = 60.0):
        self.total, self.say, self.every, self.interval = total, say or (lambda m: None), every, interval
        self.done = 0
        self.t0 = self.last = time.monotonic()

    def step(self) -> None:
        self.done += 1
        now = time.monotonic()
        if self.done % self.every == 0 or now - self.last >= self.interval or self.done == self.total:
            each = (now - self.t0) / self.done
            left = f"; about {_duration(each * (self.total - self.done))} left" if self.done < self.total else ""
            self.say(f"  {self.done:,} of {self.total:,} documents; {each:.1f} s each{left}")
            self.last = now


def read_versions(session, extractor: str) -> dict[int, str]:
    from .models import ExtractionState
    return {d: v for d, v in session.query(ExtractionState.disclosure_id, ExtractionState.version)
            .filter(ExtractionState.extractor == extractor)}


def mark(session, disclosure_id: int, extractor: str, outcome: str = "READ") -> None:
    from .models import ExtractionState
    from .timeutil import utcnow
    row = session.query(ExtractionState).filter_by(disclosure_id=disclosure_id, extractor=extractor).one_or_none()
    if row is None:
        row = ExtractionState(disclosure_id=disclosure_id, extractor=extractor)
        session.add(row)
    row.version, row.outcome, row.extracted_at = VERSIONS[extractor], outcome, utcnow()


def run(extractor: str, rows, handle, totals: dict, again: bool = False, progress=None, session=None) -> dict:
    """Run ``handle(disclosure, company, reader)`` over ``rows`` (disclosure, company) with resume and progress.

    ``handle`` returns an outcome ('READ' or 'EMPTY'), or None when the document was not applicable (no file, no
    period), which is not recorded so that it is tried again once it is. Errors are recorded in ``totals`` and not
    marked, so a rerun tries the document again; ``again`` reads every document."""
    from .http import quiet_heartbeat
    from .reportreader import ReportReader
    say = progress or (lambda m: None)
    done = read_versions(session, extractor)
    version = VERSIONS[extractor]
    todo = [(d, c) for d, c in rows if again or done.get(d.id) != version]
    totals["already_read"] = len(rows) - len(todo)
    totals["to_read"] = n = len(todo)
    say(f"{n:,} document(s) to read from {len({c.id for _, c in todo}):,} companies"
        + (f"; {totals['already_read']:,} already read by this version are skipped (--again reads them too)"
           if totals["already_read"] else ""))
    prog = Progress(n, say)
    with quiet_heartbeat():
        for d, c in todo:
            reader = None
            try:
                path = Path(d.local_path) if d.local_path else None
                if path is None or not path.exists():
                    totals["missing_files"] = totals.get("missing_files", 0) + 1
                else:
                    reader = ReportReader(path)
                    outcome = handle(d, c, reader)
                    if outcome:
                        mark(session, d.id, extractor, outcome)
                    session.commit()
                    if reader.fallback_full:
                        totals["read_whole"] = totals.get("read_whole", 0) + 1
            except Exception as exc:
                from .http import Cancelled
                if isinstance(exc, Cancelled):
                    raise
                session.rollback()
                totals.setdefault("errors", []).append({"disclosure_id": d.id, "error": repr(exc)})
            finally:
                if reader is not None:
                    reader.close()
            prog.step()
    return totals
