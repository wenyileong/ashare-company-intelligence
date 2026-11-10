"""Percentage progress (v2.4.0, plan Part C; requirement R3).

Every long action that fetches or reads data reports its progress here, as numbers: the stage, the items done, the
total (or None while it is not yet known), the unit, and for a single download the bytes. Where the numbers go
depends on who runs the action:

* **the desktop program** runs commands in its own process and installs a *sink* (:func:`set_sink`), which drives the
  determinate bar in its status bar;
* **another program** can set ``ASHARE_PROGRESS=machine`` and read lines that start with ``@@ashare-progress``
  followed by JSON;
* **a terminal** gets one line, redrawn in place: ``[██████████░░░░░░░░░░]  52%  1,234 of 2,370 documents; about
  3 min left``;
* **anything else** (output to a file, a log) gets nothing extra: the human progress lines are unchanged.

Reports are throttled to four a second; the first and the last are always sent. ``ASHARE_PROGRESS=off``, or the switch
``progress.bar`` off, turns all of this off.
"""
from __future__ import annotations

import json
import os
import sys
import threading
import time
from collections import deque

MARK = "@@ashare-progress "
MIN_INTERVAL = 0.25
BAR_WIDTH = 20

_lock = threading.Lock()
_sink = None
_last_sent = 0.0
_tty_drawn = False
_stage: dict = {}
_outer = None          # a job's counter (its items), when the work is a job of several actions
_inner = None          # the counter of the action running now


def reset() -> None:
    """Forget the stage and the counters (at the start and end of each action)."""
    global _last_sent, _stage, _outer, _inner
    _last_sent, _stage, _outer, _inner = 0.0, {}, None, None


def set_sink(fn) -> None:
    """Install (or, with None, remove) the callback that receives each progress report as a dict."""
    global _sink
    with _lock:
        _sink = fn
        reset()


def _feature_on() -> bool:
    try:
        from .features import enabled
        return enabled("progress.bar")
    except Exception:                                   # noqa: BLE001
        return True


def mode() -> str:
    """'sink', 'machine', 'tty' or 'off'."""
    env = (os.environ.get("ASHARE_PROGRESS") or "").lower()
    if env == "off" or not _feature_on():
        return "off"
    if _sink is not None:
        return "sink"
    if env == "machine":
        return "machine"
    try:
        if sys.stdout.isatty():
            return "tty"
    except (AttributeError, ValueError):
        pass
    return "off"


def stage(n: int | None, of: int | None, label: str | None) -> None:
    """Set the stage reported with every later report (``None`` clears it)."""
    global _stage
    _stage = {} if n is None else {"stage": n, "stages": of, "stage_label": label}
    report(None, None, None, force=True, stage_only=True)


def report(done: int | None, total: int | None, unit: str | None, left: float | None = None,
           bytes_done: int | None = None, bytes_total: int | None = None, force: bool = False,
           note: str | None = None, stage_only: bool = False, sub: dict | None = None) -> bool:
    """Send one progress report; returns whether it was sent (throttled unless ``force``)."""
    global _last_sent
    m = mode()
    if m == "off":
        return False
    now = time.monotonic()
    if not force and now - _last_sent < MIN_INTERVAL:
        return False
    _last_sent = now
    d = {"done": done, "total": total, "unit": unit, "left": None if left is None else round(left, 1),
         "bytes": bytes_done, "bytes_total": bytes_total, **_stage}
    if note:
        d["note"] = note
    if stage_only:
        d["stage_only"] = True
    if sub:
        d["sub"] = sub
    if m == "sink":
        try:
            _sink(d)
        except Exception:                                # noqa: BLE001
            pass
    elif m == "machine":
        sys.stdout.write(MARK + json.dumps(d, ensure_ascii=False) + "\n")
        sys.stdout.flush()
    elif m == "tty" and not stage_only:
        _draw(d)
    return True


def end() -> None:
    """Finish the terminal line and forget the counters (call when an action ends; harmless otherwise)."""
    global _tty_drawn
    reset()
    if _tty_drawn:
        try:
            sys.stdout.write("\n")
            sys.stdout.flush()
        except (OSError, ValueError):
            pass
        _tty_drawn = False


def clear_line() -> None:
    """Before a human line is printed over a terminal bar."""
    global _tty_drawn
    if _tty_drawn:
        sys.stdout.write("\r\033[K")
        _tty_drawn = False


_atexit = False


def _draw(d: dict) -> None:
    global _tty_drawn, _atexit
    if not _atexit:
        import atexit
        atexit.register(end)
        _atexit = True
    sys.stdout.write("\r\033[K" + render(d))
    sys.stdout.flush()
    _tty_drawn = True


# --- presenting ------------------------------------------------------------------------------------------------------

def fraction(d: dict) -> float | None:
    """0 to 1, or None when the total is unknown. Never above 1."""
    if d.get("bytes_total"):
        return max(0.0, min(1.0, (d.get("bytes") or 0) / d["bytes_total"]))
    if d.get("total"):
        return max(0.0, min(1.0, (d.get("done") or 0) / d["total"]))
    return None


def duration(seconds: float | None) -> str:
    if seconds is None:
        return ""
    s = int(round(seconds))
    if s < 60:
        return f"{s} s"
    if s < 3600:
        return f"{max(1, round(s / 60))} min"
    h, m = divmod(s // 60, 60)
    return f"{h} h {m:02d} min" if h < 48 else f"{h // 24} days {h % 24} h"


def _mb(n: int) -> str:
    return f"{n / 1_048_576:,.1f} MB"


def text(d: dict, tr=None) -> str:
    """'52%  1,234 of 2,370 documents; about 3 min left' (without the bar); 'counting…' with no total."""
    tr = tr or (lambda key, default: default)
    parts = []
    if d.get("stage") and d.get("stages"):
        lab = d.get("stage_label") or ""
        parts.append(tr("progress.stage", "Stage {n} of {of}").format(n=d["stage"], of=d["stages"])
                     + (f": {lab}" if lab else ""))
    f = fraction(d)
    if f is None:
        if d.get("done"):
            parts.append(tr("progress.counting_n", "{done:,} {unit} so far").format(done=d["done"],
                                                                                   unit=d.get("unit") or ""))
        else:
            parts.append(tr("progress.counting", "counting…"))
    else:
        pct = f"{int(f * 100)}%"
        if d.get("bytes_total"):
            count = tr("progress.bytes", "{done} of {total}").format(done=_mb(d.get("bytes") or 0),
                                                                     total=_mb(d["bytes_total"]))
        else:
            count = tr("progress.count", "{done:,} of {total:,} {unit}").format(
                done=d.get("done") or 0, total=d["total"], unit=d.get("unit") or "")
        if d.get("note"):
            count += f" ({d['note']})"
        parts.append(f"{pct}  {count.strip()}")
        if d.get("left") is not None and f < 1:
            parts.append(tr("progress.left", "about {time} left").format(time=duration(d["left"])))
    sub = d.get("sub")
    if sub and sub.get("total"):
        parts.append(tr("progress.within", "within it {done:,} of {total:,} {unit}").format(
            done=sub.get("done") or 0, total=sub["total"], unit=sub.get("unit") or ""))
    return "; ".join(parts)


def render(d: dict, width: int = BAR_WIDTH) -> str:
    """'[██████████░░░░░░░░░░]  52%  1,234 of 2,370 documents; about 3 min left'."""
    f = fraction(d)
    if f is None:
        bar = "[" + "·" * width + "]"
    else:
        n = int(round(f * width))
        bar = "[" + "█" * n + "░" * (width - n) + "]"
    return f"{bar}  {text(d)}"


def parse(line: str) -> dict | None:
    """A machine line back to its dict (for programs reading ``ASHARE_PROGRESS=machine``)."""
    if not line.startswith(MARK):
        return None
    try:
        return json.loads(line[len(MARK):])
    except ValueError:
        return None


# --- counting --------------------------------------------------------------------------------------------------------

class Counter:
    """Counts the items of one action and reports them; a smoothed estimate of the time left.

    ``start`` is the number already done before this run (a resumed action), so its bar starts there. The total may be
    None (unknown) and set later with :meth:`set_total`; if the total grows past what was said, the bar steps back and
    the count is marked 'about'. An ``outer`` counter counts the items of a job (each item an action with its own
    counter): the bar then follows the job, and the action running now is shown within it."""

    def __init__(self, total: int | None, unit: str = "items", start: int = 0, window: int = 50,
                 outer: bool = False):
        global _outer, _inner
        self.total, self.unit, self.start = total, unit, start
        self.done = start
        self.t0 = time.monotonic()
        self._times: deque = deque(maxlen=window)
        self._grown = False
        self.outer = outer
        if outer:
            _outer, _inner = self, None
        else:
            _inner = self
        self._emit(True, "resuming" if start else None)

    def _fields(self) -> dict:
        return {"done": self.done, "total": self.total, "unit": self.unit}

    def _emit(self, force: bool, note: str | None = None) -> None:
        main = _outer if (_outer is not None and _outer is not self) else self
        sub = self._fields() if main is not self else (
            _inner._fields() if (_inner is not None and _inner is not self and self.outer) else None)
        report(main.done, main.total, main.unit, main.left(), force=force,
               note=note or ("about" if main._grown else None), sub=sub)

    def set_total(self, total: int | None) -> None:
        if total is not None and self.total is not None and total > self.total:
            self._grown = True
        self.total = total
        self._emit(True)

    def left(self) -> float | None:
        if not self.total or self.done <= self.start:
            return None
        now = time.monotonic()
        whole = (now - self.t0) / (self.done - self.start)
        recent = whole
        if len(self._times) >= 2:
            recent = (self._times[-1] - self._times[0]) / (len(self._times) - 1)
        each = 0.5 * whole + 0.5 * recent
        return max(0.0, each * (self.total - self.done))

    def step(self, n: int = 1) -> None:
        self.done += n
        self._times.append(time.monotonic())
        if self.total is not None and self.done > self.total:
            self.total, self._grown = self.done, True
        last = self.total is not None and self.done >= self.total
        self._emit(last)

    def bytes(self, done: int, total: int | None) -> None:
        report(self.done, self.total, self.unit, None, bytes_done=done, bytes_total=total)


def count(items, total: int | None = None, unit: str = "items"):
    """Iterate ``items``, reporting each one."""
    if total is None:
        try:
            total = len(items)
        except TypeError:
            total = None
    c = Counter(total, unit)
    for x in items:
        yield x
        c.step()
