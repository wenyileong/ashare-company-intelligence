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
    """Open one document and parse it; never raises (the error is returned)."""
    from .reportreader import ReportReader
    out = {"id": job["id"]}
    reader = None
    try:
        reader = ReportReader(job["path"])
        out["result"] = _resolve(parse)(job, reader)
        out["read_whole"] = reader.fallback_full
    except Exception as exc:          # noqa: BLE001 - returned to the main process, which records it
        out["error"] = repr(exc)
    finally:
        if reader is not None:
            reader.close()
    out["notices"] = _take_notices() if take_notices else None    # in the main process they are counted already
    return out


def imap(parse: str, jobs: list[dict], n_workers: int | None = None, check=None):
    """Yield ``parse_one`` results for ``jobs``, in the order of ``jobs``, so that the main process writes in the same
    order as a serial run (later documents may supersede earlier ones). ``check`` is called between results and may
    raise (the Stop button); the workers are then stopped and nothing more is yielded."""
    n_workers = workers() if n_workers is None else n_workers
    if n_workers <= 1 or len(jobs) < MIN_JOBS:
        for job in jobs:
            if check:
                check()
            yield parse_one(parse, job, take_notices=False)
        return
    import multiprocessing
    ctx = multiprocessing.get_context("spawn")
    ex = ProcessPoolExecutor(max_workers=n_workers, mp_context=ctx, initializer=_worker_init)
    pending, it = set(), iter(jobs)
    order = {job["id"]: k for k, job in enumerate(jobs)}
    done_early: dict[int, dict] = {}
    next_k = 0
    finished = False
    window = n_workers * 2                       # bounded, so that Stop does not wait for a long queue
    exhausted = False

    def refill():
        nonlocal exhausted
        while not exhausted and len(pending) + len(done_early) < window:
            job = next(it, None)
            if job is None:
                exhausted = True
            else:
                pending.add(ex.submit(parse_one, parse, job))
    try:
        refill()
        while pending:
            done, pending = wait(pending, timeout=0.5, return_when=FIRST_COMPLETED)
            if check:
                check()                          # Stop is answered within half a second, even during a long document
            for f in done:
                res = f.result()
                merge_notices(res.pop("notices", None))
                done_early[order[res["id"]]] = res
            while next_k in done_early:
                if check:
                    check()
                yield done_early.pop(next_k)
                next_k += 1
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
