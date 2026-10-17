"""One-line summary of PDF reader messages (v2.0.3, finding 5).

pypdf writes a warning for every font or cross-reference table it finds odd.
In the v2.0.2 live run these were 2,428 font notices (each several hundred
characters long) and 260 cross-reference notices, against about 250 lines
of real output.

During a command, this module collects pypdf's messages instead of printing
them, counts them by kind and by document, and at the end of the command
prints one summary line and writes the details to ``logs/`` in the data
folder.

The font notice ("fontTools is required to fully parse the encoding of a CFF
Type1 font") was checked for v2.0.3 (finding 1, docs/font_check_v2.0.3.md):
when the font declares a standard encoding (WinAnsi, Standard, MacRoman), as
2,408 of the 2,428 notices did, the declared encoding decides the characters
and the text, figures included, is extracted correctly without fontTools.
Notices for fonts without a standard encoding are counted separately, and
their documents listed, because only those could be affected.
"""
from __future__ import annotations

import logging
import os
import re
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

STANDARD_ENCODINGS = ("/WinAnsiEncoding", "/StandardEncoding", "/MacRomanEncoding")
LABELS = {
    "font_standard_encoding": "font notices for fonts with a standard encoding (text unaffected)",
    "font_custom_encoding": "font notices for fonts without a standard encoding (check figures from these)",
    "damaged_xref": "damaged cross-reference notices (repaired by the reader)",
    "other": "other notices",
}

_current = {"doc": None}


def log_dir() -> Path:
    return Path(os.getenv("ASHARE_LOG_DIR", "logs"))


def set_document(path) -> None:
    """The document now being read, so that its messages are attributed to it."""
    _current["doc"] = str(path) if path else None


def classify(msg: str) -> str:
    if "fontTools is required" in msg:
        return "font_standard_encoding" if any(e in msg for e in STANDARD_ENCODINGS) else "font_custom_encoding"
    if "wrong pointing object" in msg or "Invalid parent xref" in msg or "xref" in msg.lower():
        return "damaged_xref"
    return "other"


class Collector(logging.Handler):
    def __init__(self):
        super().__init__(logging.WARNING)
        self.reset()

    def reset(self):
        self.kinds: Counter = Counter()
        self.docs: dict[str, Counter] = defaultdict(Counter)
        self.samples: dict[str, str] = {}

    def emit(self, record):
        try:
            msg = record.getMessage()
        except Exception:
            msg = str(record.msg)
        kind = classify(msg)
        self.kinds[kind] += 1
        self.docs[_current["doc"] or "(document not recorded)"][kind] += 1
        key = kind if kind != "other" else re.sub(r"\d+", "#", msg[:80])
        self.samples.setdefault(key, msg[:400])

    @property
    def total(self) -> int:
        return sum(self.kinds.values())


_collector: Collector | None = None


def install() -> Collector:
    """Collect pypdf's messages from now on (idempotent)."""
    global _collector
    log = logging.getLogger("pypdf")
    if _collector is None:
        _collector = Collector()
    if _collector not in log.handlers:
        log.addHandler(_collector)
    log.propagate = False
    return _collector


def summary_line(c: Collector) -> str | None:
    if not c.total:
        return None
    parts = []
    for kind in LABELS:
        n = c.kinds.get(kind)
        if n:
            docs = sum(1 for d in c.docs.values() if d.get(kind))
            parts.append(f"{n:,} {LABELS[kind]} in {docs:,} document{'s' if docs != 1 else ''}")
    return "PDF reader: " + "; ".join(parts) + "."


def write_details(c: Collector, command: str = "") -> Path | None:
    if not c.total:
        return None
    d = log_dir()
    try:
        d.mkdir(parents=True, exist_ok=True)
        path = d / f"pdf_warnings_{datetime.now():%Y%m%d-%H%M%S}.txt"
        lines = [f"PDF reader messages for: {command}".rstrip(), "", summary_line(c) or "", "",
                 "By document (kind: count):"]
        order = sorted(c.docs.items(), key=lambda kv: (-kv[1].get("font_custom_encoding", 0), -sum(kv[1].values())))
        for doc, k in order:
            lines.append(f"  {doc}: " + ", ".join(f"{kind} {n}" for kind, n in k.most_common()))
        lines += ["", "One example of each kind:"]
        for key, msg in c.samples.items():
            lines += [f"  [{key}]", f"    {msg}"]
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return path
    except OSError:
        return None


def finish(command: str = "", say=print) -> None:
    """Print the summary line, write the details file, and start counting afresh."""
    c = _collector
    if c is None or not c.total:
        return
    line = summary_line(c)
    path = write_details(c, command)
    say(line + (f" Details: {path}" if path else ""))
    c.reset()
    set_document(None)
