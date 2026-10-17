"""Golden-corpus evaluation and parser calibration (v1.4).

A *golden corpus* is a folder of real (or synthetic) documents with values a
person has checked by hand::

    corpus/
      manifest.json          name, synthetic flag, list of documents
      docs/<file>            the PDF (or .txt with form-feed page breaks)
      expected/<id>.json     verified values per parser

``expected/<id>.json``::

    {"id": "moutai_2024_ar", "verified": true,
     "parsers": {
       "segments": {"complete": true,
                    "records": [{"dimension": "PRODUCT", "segment_name": "茅台酒",
                                 "revenue": 145928000000.0, "gross_margin": 0.9393}]},
       "financials": {"records": [{"metric": "revenue", "value": 170899000000.0}]}}}

Every parser's records are matched on its key fields; each other field in an
expected record is scored. Fields starting with ``_`` (page hints, notes) are
ignored. ``complete: true`` says the expected records are exhaustive, so any
extra record the parser produces counts against precision.

Per field the outcome is one of:

* correct   expected value present and parser value equal (0.01% tolerance)
* wrong     both present, unequal
* missed    expected value present, parser gave nothing (an abstention)
* spurious  parser gave a value where none is expected

precision = correct / (correct + wrong + spurious)
recall    = correct / (correct + wrong + missed)
abstention = missed / (correct + wrong + missed)

Abstaining is preferred to guessing: the CI gate fails on a precision drop,
and only reports a recall drop.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from .timeutil import utcnow

from .parsers import ParserSpec, PARSERS, PARSER_VERSION, load_pages, pages_for  # noqa: F401 (re-exported)


# --- corpus I/O ---------------------------------------------------------------

def load_corpus(corpus_dir: str | Path) -> dict:
    root = Path(corpus_dir)
    manifest_path = root / "manifest.json"
    if not manifest_path.exists():
        raise FileNotFoundError(f"{manifest_path} not found; create one with 'corpus-template' or 'synthetic-corpus'")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest.setdefault("documents", [])
    manifest["_root"] = root
    return manifest


def corpus_fingerprint(corpus_dir: str | Path) -> str:
    root = Path(corpus_dir)
    h = hashlib.sha256()
    for p in sorted(x for x in root.rglob("*") if x.is_file()):
        h.update(str(p.relative_to(root)).replace("\\", "/").encode())
        h.update(hashlib.sha256(p.read_bytes()).digest())
    return h.hexdigest()


# --- comparison -----------------------------------------------------------------

def _norm(v):
    if v is None:
        return None
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, (list, tuple)):
        return "|".join(sorted(str(x) for x in v))
    s = re.sub(r"\s+", " ", str(v)).strip()
    return s or None


def values_equal(expected, predicted) -> bool:
    e, p = _norm(expected), _norm(predicted)
    if isinstance(e, float) and isinstance(p, float):
        return abs(e - p) <= max(1e-6, 1e-4 * abs(e))
    if isinstance(e, float) and isinstance(p, str):
        try:
            return values_equal(e, float(p))
        except ValueError:
            return False
    return e == p


def _key(rec: dict, key: tuple[str, ...]):
    return tuple(_norm(rec.get(k)) for k in key)


@dataclass
class Tally:
    correct: int = 0
    wrong: int = 0
    missed: int = 0
    spurious: int = 0

    def add(self, other: "Tally"):
        self.correct += other.correct
        self.wrong += other.wrong
        self.missed += other.missed
        self.spurious += other.spurious

    @property
    def expected(self):
        return self.correct + self.wrong + self.missed

    @property
    def predicted(self):
        return self.correct + self.wrong + self.spurious

    def metrics(self) -> dict:
        p = self.correct / self.predicted if self.predicted else None
        r = self.correct / self.expected if self.expected else None
        return {"expected": self.expected, "predicted": self.predicted, "correct": self.correct,
                "wrong": self.wrong, "missed": self.missed, "spurious": self.spurious,
                "precision": p, "precision_lower": wilson_lower(self.correct, self.predicted),
                "recall": r, "abstention": self.missed / self.expected if self.expected else None}


def wilson_lower(successes: int, n: int, z: float = 1.96) -> float | None:
    """Lower bound of the Wilson score interval (95% by default)."""
    if n <= 0:
        return None
    phat = successes / n
    denom = 1 + z * z / n
    centre = phat + z * z / (2 * n)
    margin = z * math.sqrt(phat * (1 - phat) / n + z * z / (4 * n * n))
    return max(0.0, (centre - margin) / denom)


def score_document(spec: ParserSpec, expected: dict, predicted: list[dict]) -> tuple[dict[str, Tally], list[dict]]:
    """Score one parser on one document; returns per-field tallies and error details."""
    records = expected.get("records") or []
    complete = bool(expected.get("complete"))
    tallies: dict[str, Tally] = {}
    errors: list[dict] = []
    by_key: dict[tuple, dict] = {}
    for p in predicted:
        by_key.setdefault(_key(p, spec.key), p)
    seen = set()
    for exp in records:
        k = _key(exp, spec.key)
        seen.add(k)
        pred = by_key.get(k)
        for f, ev in exp.items():
            if f in spec.key or f.startswith("_"):
                continue
            t = tallies.setdefault(f, Tally())
            pv = pred.get(f) if pred else None
            if ev is None:
                if _norm(pv) is not None:
                    t.spurious += 1
                    errors.append({"key": list(k), "field": f, "expected": None, "predicted": pv, "outcome": "spurious"})
                continue
            if _norm(pv) is None:
                t.missed += 1
                errors.append({"key": list(k), "field": f, "expected": ev, "predicted": None, "outcome": "missed"})
            elif values_equal(ev, pv):
                t.correct += 1
            else:
                t.wrong += 1
                errors.append({"key": list(k), "field": f, "expected": ev, "predicted": pv, "outcome": "wrong"})
    if complete:
        for k, pred in by_key.items():
            if k in seen:
                continue
            for f in spec.fields:
                if _norm(pred.get(f)) is not None:
                    tallies.setdefault(f, Tally()).spurious += 1
                    errors.append({"key": list(k), "field": f, "expected": None, "predicted": pred.get(f),
                                   "outcome": "spurious"})
    return tallies, errors


# --- evaluation -----------------------------------------------------------------

def evaluate_corpus(corpus_dir: str | Path, parsers: list[str] | None = None,
                    include_unverified: bool = False) -> dict:
    manifest = load_corpus(corpus_dir)
    root = manifest["_root"]
    wanted = parsers or list(PARSERS)
    unknown = [p for p in wanted if p not in PARSERS]
    if unknown:
        raise ValueError(f"unknown parser(s): {', '.join(unknown)}; known: {', '.join(PARSERS)}")
    totals = {p: Tally() for p in wanted}
    fields: dict[str, dict[str, Tally]] = {p: {} for p in wanted}
    docs_used = {p: 0 for p in wanted}
    details, skipped = [], []
    for doc in manifest["documents"]:
        exp_path = root / "expected" / f"{doc['id']}.json"
        if not exp_path.exists():
            skipped.append({"id": doc["id"], "reason": "no expected file"})
            continue
        expected = json.loads(exp_path.read_text(encoding="utf-8"))
        if not expected.get("verified") and not include_unverified:
            skipped.append({"id": doc["id"], "reason": "not verified"})
            continue
        cache: dict = {}
        for name in wanted:
            exp = (expected.get("parsers") or {}).get(PARSERS[name].family)
            if exp is None:
                continue
            spec = PARSERS[name]
            pages = pages_for(root / doc["file"], spec.input, cache)
            if not pages:
                skipped.append({"id": doc["id"], "reason": f"{name}: no {spec.input} text (extractor unavailable)"})
                continue
            try:
                predicted = spec.run(pages, doc)
            except Exception as exc:  # a crash is a full miss, and is reported
                predicted = []
                details.append({"document": doc["id"], "parser": name, "crash": repr(exc)})
            doc_tallies, errors = score_document(spec, exp, predicted)
            docs_used[name] += 1
            for f, t in doc_tallies.items():
                totals[name].add(t)
                fields[name].setdefault(f, Tally()).add(t)
            for e in errors:
                details.append({"document": doc["id"], "parser": name, **e})
    result = {
        "corpus": manifest.get("name") or str(root), "synthetic": bool(manifest.get("synthetic")),
        "fingerprint": corpus_fingerprint(root), "parser_version": PARSER_VERSION,
        "evaluated_at": utcnow().isoformat(timespec="seconds") + "Z",
        "parsers": {p: {**totals[p].metrics(), "documents": docs_used[p],
                        "fields": {f: t.metrics() for f, t in sorted(fields[p].items())}}
                    for p in wanted if docs_used[p]},
        "errors": details, "skipped": skipped,
    }
    return result


def gate(result: dict, baseline: dict, max_precision_drop_pp: float = 1.0) -> dict:
    """Compare against a baseline result; fail on a precision drop > threshold."""
    failures, warnings = [], []
    for name, base in (baseline.get("parsers") or {}).items():
        cur = result["parsers"].get(name)
        if cur is None:
            warnings.append(f"{name}: not evaluated in this run")
            continue
        bp, cp = base.get("precision"), cur.get("precision")
        if bp is not None and cp is not None and (bp - cp) * 100 > max_precision_drop_pp + 1e-9:
            failures.append(f"{name}: precision {cp:.1%} vs baseline {bp:.1%}")
        br, cr = base.get("recall"), cur.get("recall")
        if br is not None and cr is not None and cr < br - 1e-9:
            warnings.append(f"{name}: recall {cr:.1%} vs baseline {br:.1%}")
    return {"passed": not failures, "failures": failures, "warnings": warnings,
            "threshold_pp": max_precision_drop_pp}


def baseline_from(result: dict) -> dict:
    return {"corpus": result["corpus"], "fingerprint": result["fingerprint"],
            "parser_version": result["parser_version"], "created_at": result["evaluated_at"],
            "parsers": {p: {k: m[k] for k in ("precision", "recall", "expected", "predicted")}
                        for p, m in result["parsers"].items()}}


# --- calibration --------------------------------------------------------------

_CAL_CACHE: dict[str, dict] = {}
MIN_CALIBRATION_N = 30
HEURISTIC_CAP = 0.9   # text heuristics never reach HIGH confidence on calibration alone


def save_calibration(result: dict) -> int:
    from .models import SessionLocal, ParserCalibration, init_db
    init_db()
    synthetic = 1 if result.get("synthetic") else 0
    s = SessionLocal()
    n = 0
    try:
        for name, m in result["parsers"].items():
            rows = [("*", m)] + list(m.get("fields", {}).items())
            for fname, fm in rows:
                row = s.query(ParserCalibration).filter_by(parser=name, field=fname, synthetic=synthetic).one_or_none()
                if row is None:
                    row = ParserCalibration(parser=name, field=fname, synthetic=synthetic)
                    s.add(row)
                for k in ("expected", "predicted", "correct", "wrong", "missed", "spurious", "precision",
                          "precision_lower", "recall"):
                    setattr(row, k, fm.get(k))
                row.parser_version = result.get("parser_version")
                row.corpus_name, row.corpus_fingerprint = result.get("corpus"), result.get("fingerprint")
                row.evaluated_at = utcnow()
                n += 1
        s.commit()
    finally:
        s.close()
    _CAL_CACHE.clear()
    return n


def _calibrations() -> dict:
    from .config import db_path
    key = str(db_path())
    if key not in _CAL_CACHE:
        table = {}
        try:
            from .models import SessionLocal, ParserCalibration
            s = SessionLocal()
            try:
                for r in s.query(ParserCalibration).filter_by(field="*", synthetic=0).all():
                    table[r.parser] = r
            finally:
                s.close()
        except Exception:
            table = {}
        _CAL_CACHE[key] = table
    return _CAL_CACHE[key]


def calibrated_confidence(parser: str, default: float, cap: float = HEURISTIC_CAP) -> float:
    """Confidence for a value produced by ``parser``.

    Uses the Wilson lower bound of the parser's precision on a verified,
    non-synthetic corpus when at least MIN_CALIBRATION_N values were scored
    with the current parser version; otherwise returns ``default``.
    """
    row = _calibrations().get(parser)
    spec = PARSERS.get(parser)
    if row is None or spec is None or row.parser_version != spec.version:
        return default
    if (row.predicted or 0) < MIN_CALIBRATION_N or row.precision_lower is None:
        return default
    return round(min(cap, row.precision_lower), 3)


def calibration_table() -> list[dict]:
    from .models import SessionLocal, ParserCalibration, init_db
    init_db()
    s = SessionLocal()
    try:
        return [{"parser": r.parser, "field": r.field, "synthetic": bool(r.synthetic), "version": r.parser_version,
                 "predicted": r.predicted, "precision": r.precision, "precision_lower": r.precision_lower,
                 "recall": r.recall, "corpus": r.corpus_name,
                 "in_use": (not r.synthetic and r.field == "*" and calibrated_confidence(r.parser, -1) != -1)}
                for r in s.query(ParserCalibration).order_by(ParserCalibration.parser, ParserCalibration.field)]
    finally:
        s.close()


# --- corpus template ------------------------------------------------------------

def _layout_families():
    from .parsers import TABLE_FAMILIES
    return TABLE_FAMILIES


def _clean_record(spec: ParserSpec, rec: dict) -> dict:
    out = {k: rec.get(k) for k in spec.key}
    for f in spec.fields:
        v = rec.get(f)
        if v is not None:
            out[f] = v
    if rec.get("page"):
        out["_page"] = rec["page"]
    if rec.get("raw"):
        out["_raw"] = str(rec["raw"])[:200]
    return out


def corpus_template(corpus_dir: str | Path, document: str, doc_id: str | None = None, title: str | None = None,
                    announcement_date: str | None = None, security_code: str | None = None,
                    parsers: list[str] | None = None) -> dict:
    """Add a document to a corpus with its current parser output as a draft.

    ``document`` is a file path or a disclosure id from the database. The
    expected file is written with ``verified: false``: check each value
    against the document, correct it, delete what is wrong, add what was
    missed, then set ``verified`` to true.
    """
    root = Path(corpus_dir)
    src = Path(document)
    if not src.exists() and str(document).isdigit():
        from .models import SessionLocal, Disclosure, Company
        s = SessionLocal()
        try:
            d = s.get(Disclosure, int(document))
            if d is None or not d.local_path:
                raise FileNotFoundError(f"disclosure {document} has no downloaded document")
            src = Path(d.local_path)
            title = title or d.title_cn
            announcement_date = announcement_date or d.announcement_date
            c = s.get(Company, d.company_id)
            security_code = security_code or (c.security_code if c else None)
        finally:
            s.close()
    if not src.exists():
        raise FileNotFoundError(str(src))
    (root / "docs").mkdir(parents=True, exist_ok=True)
    (root / "expected").mkdir(parents=True, exist_ok=True)
    manifest_path = root / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {
        "name": root.name, "synthetic": False, "version": 1, "documents": []}
    doc_id = doc_id or re.sub(r"[^A-Za-z0-9_]+", "_", src.stem)[:60] or "doc"
    if any(d["id"] == doc_id for d in manifest["documents"]):
        raise ValueError(f"document id {doc_id} already in the corpus")
    dest = root / "docs" / (doc_id + src.suffix.lower())
    shutil.copyfile(src, dest)
    entry = {"id": doc_id, "file": f"docs/{dest.name}", "title": title or src.stem,
             "announcement_date": announcement_date, "security_code": security_code}
    manifest["documents"].append(entry)
    cache: dict = {}
    from .disclosures import classify_title
    kind = classify_title(entry["title"])
    is_report = kind.startswith(("annual_report", "interim_report", "quarterly_report"))
    wanted = parsers or [n for n, sp in PARSERS.items()
                         if ("announcement" in sp.doc_kinds) != is_report and sp.input == "text"]
    expected = {"id": doc_id, "verified": False,
                "_instructions": "Check every value against the document. Correct or delete wrong ones, add missed "
                                 "ones, set complete=true only if the list is exhaustive, then set verified=true.",
                "parsers": {}}
    for name in wanted:
        spec = PARSERS[name]
        try:
            pages = pages_for(dest, "layout", cache) if spec.family in _layout_families() else []
            if not pages:
                pages = pages_for(dest, "text", cache)
            recs = [_clean_record(spec, r) for r in spec.run(pages, entry)]
        except Exception as exc:
            recs = []
            expected["parsers"][name] = {"complete": False, "records": [], "_error": repr(exc)}
            continue
        expected["parsers"][spec.family] = {"complete": False, "records": recs}
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    exp_path = root / "expected" / f"{doc_id}.json"
    exp_path.write_text(json.dumps(expected, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"id": doc_id, "document": str(dest), "expected": str(exp_path),
            "parsers": {k: len(v["records"]) for k, v in expected["parsers"].items()}}
