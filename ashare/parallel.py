"""Parallel document parsing (v2.1, plan workstream B3).

Several documents are parsed at once, in worker processes; the main process writes every result. So that:

* SQLite sees one writer (review round 2): the workers only open the PDFs and run the parsers;
* a stopped run marks nothing it did not write (the main process marks each document after writing it);
* the PDF reader's notices are not lost: each worker returns its notices with its result, and the main process adds
  them to the command's summary;
* nothing is printed by a worker: the desktop program has no standard output (review round 5).

Workers are started with ``spawn`` on every platform, as Windows requires, and a frozen program calls
``multiprocessing.freeze_support()`` first in its launcher (``packaging/launcher.py``).

The number of workers is ``ASHARE_WORKERS`` (set from Settings in the desktop), by default the processor count less
one, at most eight; 1 turns parallel parsing off. Fewer than four documents are parsed in the main process, where
starting workers would cost more than it saves.
"""
from __future__ import annotations

import importlib
import os
from concurrent.futures import ProcessPoolExecutor, FIRST_COMPLETED, wait

MIN_JOBS = 4
MAX_WORKERS = 8


def workers() -> int:
    raw = os.environ.get("ASHARE_WORKERS", "").strip()
    if raw:
        try:
            return max(1, min(MAX_WORKERS, int(raw)))
        except ValueError:
            pass
    return max(1, min(MAX_WORKERS, (os.cpu_count() or 2) - 1))


def _resolve(name: str):
    module, func = name.split(":")
    return getattr(importlib.import_module(module), func)


def _take_notices() -> dict | None:
    from . import pdfwarnings
    c = pdfwarnings._collector
    if c is None or not c.total:
        return None
    state = {"kinds": dict(c.kinds), "docs": {d: dict(k) for d, k in c.docs.items()}, "samples": dict(c.samples)}
    c.reset()
    return state


def merge_notices(state: dict | None) -> None:
    """Add a worker's PDF reader notices to this process's collector."""
    if not state:
        return
    from . import pdfwarnings
    c = pdfwarnings.install()
    for k, n in state["kinds"].items():
        c.kinds[k] += n
    for d, kinds in state["docs"].items():
        for k, n in kinds.items():
            c.docs[d][k] += n
    for k, v in state["samples"].items():
        c.samples.setdefault(k, v)


def _worker_init() -> None:
    from . import pdfwarnings
    pdfwarnings.install()


def parse_one(parse: str, job: dict, take_notices: bool = True) -> dict:
    """Open one document and parse it; never raises (the error is returned). v2.1.1: records the seconds it took
    and the document's page count, so that a run can name its slowest documents (finding 113)."""
    import time
    from .reportreader import ReportReader
    out = {"id": job["id"]}
    reader = None
    t0 = time.monotonic()
    try:
        reader = ReportReader(job["path"])
        out["pages"] = getattr(reader, "n", None)
        out["result"] = _resolve(parse)(job, reader)
        out["read_whole"] = reader.fallback_full
    except Exception as exc:          # noqa: BLE001 - returned to the main process, which records it
        out["error"] = repr(exc)
    finally:
        if reader is not None:
            reader.close()
    out["seconds"] = round(time.monotonic() - t0, 1)
    out["notices"] = _take_notices() if take_notices else None    # in the main process they are counted already
    return out


class Slowest:
    """The few slowest documents of a run, for its summary (v2.1.1, finding 113)."""

    def __init__(self, keep: int = 5):
        self.keep, self.rows = keep, []

    def add(self, res: dict, title: str | None = None) -> None:
        if res.get("seconds") is None:
            return
        self.rows.append({"disclosure_id": res["id"], "seconds": res["seconds"], "pages": res.get("pages"),
                          "title": (title or "")[:60]})
        self.rows.sort(key=lambda r: -r["seconds"])
        del self.rows[self.keep:]

    def report(self, floor: float = 120.0) -> list[dict]:
        """Only documents that took longer than ``floor`` seconds are worth naming."""
        return [r for r in self.rows if r["seconds"] >= floor]


def imap(parse: str, jobs: list[dict], n_workers: int | None = None, check=None):
    """Yield ``parse_one`` results for ``jobs``. ``check`` is called between results and may raise (the Stop button);
    the workers are then stopped and nothing more is yielded.

    Order: the documents of one company (a job's ``group``) are yielded in their order in ``jobs``, so that the main
    process writes them as a serial run would (a later report may supersede an earlier one). Different companies are
    not held back by each other: v2.1.0 yielded everything in one order, so one document that took an hour and a
    half (finding 113) would have held back every later result and left the other workers idle once the window
    filled. Only documents in progress count against the window; finished ones waiting for an earlier document of
    their company do not."""
    n_workers = workers() if n_workers is None else n_workers
    if n_workers <= 1 or len(jobs) < MIN_JOBS:
        for job in jobs:
            if check:
                check()
            yield parse_one(parse, job, take_notices=False)
        return
    import multiprocessing
    from collections import defaultdict, deque
    ctx = multiprocessing.get_context("spawn")
    ex = ProcessPoolExecutor(max_workers=n_workers, mp_context=ctx, initializer=_worker_init)
    pending, it = set(), iter(jobs)
    group_of = {job["id"]: job.get("group", job["id"]) for job in jobs}
    queue = defaultdict(deque)                  # group -> job ids, in their order, not yet yielded
    for job in jobs:
        queue[group_of[job["id"]]].append(job["id"])
    finished_early: dict = {}                    # job id -> result, waiting for an earlier job of its group
    finished = False
    window = n_workers * 2                       # documents in progress at most, so that Stop has little to wait for
    exhausted = False

    def refill():
        nonlocal exhausted
        while not exhausted and len(pending) < window:
            job = next(it, None)
            if job is None:
                exhausted = True
            else:
                pending.add(ex.submit(parse_one, parse, job))

    def ready():
        for jid in list(finished_early):
            q = queue[group_of[jid]]
            while q and q[0] in finished_early:
                head = q.popleft()
                yield finished_early.pop(head)
    try:
        refill()
        while pending:
            done, pending = wait(pending, timeout=0.5, return_when=FIRST_COMPLETED)
            if check:
                check()                          # Stop is answered within half a second, even during a long document
            for f in done:
                res = f.result()
                merge_notices(res.pop("notices", None))
                finished_early[res["id"]] = res
            for res in ready():
                if check:
                    check()
                yield res
            refill()
        finished = True
    finally:
        if finished:
            ex.shutdown(wait=True)
        else:                                    # stopped, or an error in the main process: stop the workers now
            for f in pending:
                f.cancel()
            procs = list((getattr(ex, "_processes", None) or {}).values())
            ex.shutdown(wait=False, cancel_futures=True)
            for p in procs:
                try:
                    p.terminate()
                except Exception:
                    pass
