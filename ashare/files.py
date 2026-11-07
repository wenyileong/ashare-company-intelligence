"""Organising downloaded and fetched files (v2.1.2, the author's request).

Downloaded documents are stored as ``disclosures/<code>/<hash>.<ext>``: the paths the database and the provenance
records hold, so they are never renamed. This module works around them:

* :func:`files_summary`: documents on disk by kind and by year, with their size, and the other folders;
* :func:`files_list`: the documents of one company (or a kind and year) with readable names and the extractors
  that read them;
* :func:`export_files`: readable copies, arranged by company and year, with an index (CSV and HTML) giving each
  copy's source address and database record;
* :func:`check_files`: files no record names, records whose file is missing, one file under several records, and
  summaries or English versions downloaded by earlier versions;
* :func:`tidy_files`: removes a chosen class of files; previews unless ``apply``, clears the path in the database
  of every file it removes (so a later run downloads it again if needed) and logs every removal.

Nothing here sends anything anywhere.
"""
from __future__ import annotations

import csv
import os
import html
import re
import shutil
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from .config import disclosure_dir, market_raw_dir
from .storepaths import document_path, has_document  # v2.3.0 (B1)

TIDY_CLASSES = ("unnamed", "summaries_english", "kind")
_BAD = re.compile(r'[\\/:*?"<>|\r\n\t]+')


def _safe(text: str, limit: int = 80) -> str:
    t = _BAD.sub(" ", text or "").strip(" .")
    t = re.sub(r"\s+", " ", t)
    return t[:limit].rstrip(" .") or "untitled"


def _size(path: Path) -> int:
    try:
        return path.stat().st_size
    except OSError:
        return 0


def _folder_size(folder: Path) -> tuple[int, int]:
    n = total = 0
    if folder.exists():
        for p in folder.rglob("*"):
            if p.is_file():
                n += 1
                total += _size(p)
    return n, total


def _year(d) -> str:
    m = re.search(r"(20\d{2}|19\d{2})\s*年", d.title_cn or "")
    return m.group(1) if m else (d.announcement_date or "")[:4] or "unknown"


def _rows(session, security_code=None, kind=None, year=None, on_disk=True):
    from .models import Company, Disclosure
    q = (session.query(Disclosure, Company).join(Company, Disclosure.company_id == Company.id)
         .filter(Disclosure.local_path.isnot(None)))
    if security_code:
        q = q.filter(Company.security_code == str(security_code).zfill(6))
    if kind:
        q = q.filter(Disclosure.kind == kind)
    out = []
    for d, c in q.order_by(Company.security_code, Disclosure.announcement_date, Disclosure.id):
        if year and _year(d) != str(year):
            continue
        p = document_path(d)
        if on_disk and not p.exists():
            continue
        out.append((d, c, p))
    return out


def readable_name(d, c) -> str:
    """``<code> <date> <title>.<ext>``, safe as a Windows file name."""
    ext = os.path.splitext(d.local_path or "")[1] or ".pdf"
    return _safe(f"{c.security_code} {d.announcement_date or ''} {d.title_cn or d.announcement_id}", 120) + ext


def files_summary() -> dict:
    """Documents on disk by kind and by year, with their size; and the other folders the program writes."""
    from .models import SessionLocal, init_db
    init_db()
    s = SessionLocal()
    try:
        by_kind: dict = defaultdict(lambda: [0, 0])
        by_year: dict = defaultdict(lambda: [0, 0])
        missing = 0
        for d, c, p in _rows(s, on_disk=False):
            if not p.exists():
                missing += 1
                continue
            size = _size(p)
            by_kind[d.kind or "other"][0] += 1
            by_kind[d.kind or "other"][1] += size
            by_year[_year(d)][0] += 1
            by_year[_year(d)][1] += size
    finally:
        s.close()
    folders = {}
    for label, folder in (("market data", market_raw_dir()), ("exports", Path("exports")), ("logs", Path("logs"))):
        n, total = _folder_size(folder)
        folders[label] = {"folder": str(folder), "files": n, "mb": round(total / 1048576, 1)}
    return {
        "documents": sum(v[0] for v in by_kind.values()),
        "mb": round(sum(v[1] for v in by_kind.values()) / 1048576, 1),
        "missing": missing,
        "by_kind": [{"kind": k, "files": v[0], "mb": round(v[1] / 1048576, 1)}
                    for k, v in sorted(by_kind.items(), key=lambda kv: -kv[1][1])],
        "by_year": [{"year": k, "files": v[0], "mb": round(v[1] / 1048576, 1)} for k, v in sorted(by_year.items())],
        "folders": folders,
    }


def _readers(session, ids: list[int]) -> dict[int, list[str]]:
    from .models import ExtractionState, Disclosure
    from .dbutil import in_chunks
    out: dict[int, list[str]] = defaultdict(list)
    for st in in_chunks(session.query(ExtractionState), ExtractionState.disclosure_id, ids):
        out[st.disclosure_id].append(st.extractor)
    for d in in_chunks(session.query(Disclosure).filter(Disclosure.extracted_version.isnot(None)), Disclosure.id, ids):
        out[d.id].append("financials")
    return out


def files_list(security_code: str | None = None, kind: str | None = None, year: str | None = None,
               limit: int = 500) -> list[dict]:
    """Documents on disk, with readable names and the extractors that read them."""
    from .models import SessionLocal, init_db
    init_db()
    s = SessionLocal()
    try:
        rows = _rows(s, security_code, kind, year)[:limit]
        readers = _readers(s, [d.id for d, _, _ in rows])
        return [{"id": d.id, "code": c.security_code, "date": d.announcement_date, "kind": d.kind,
                 "name": readable_name(d, c), "kb": round(_size(p) / 1024), "path": str(p),
                 "read_by": ", ".join(sorted(set(readers.get(d.id, [])))) or "-"} for d, c, p in rows]
    finally:
        s.close()


def export_files(out: str | Path = "exports/files", security_code: str | None = None, kind: str | None = None,
                 year: str | None = None, year_from: str | None = None, year_to: str | None = None) -> dict:
    """Readable copies of a chosen set, under ``<out>/<code> <name>/<year>/``, with ``index.csv`` and ``index.html``.

    The originals are not touched; the index gives each copy's source address and database record."""
    from .models import SessionLocal, init_db
    init_db()
    s = SessionLocal()
    base = Path(out)
    try:
        rows = _rows(s, security_code, kind, year)
        if year_from or year_to:
            rows = [(d, c, p) for d, c, p in rows
                    if (not year_from or _year(d) >= str(year_from)) and (not year_to or _year(d) <= str(year_to))]
        if not rows:
            return {"copied": 0, "folder": str(base), "note": "no downloaded document matches"}
        base.mkdir(parents=True, exist_ok=True)
        index, copied, skipped, used = [], 0, 0, set()
        for d, c, p in rows:
            folder = base / _safe(f"{c.security_code} {c.short_name_cn or c.legal_name_cn or ''}", 60) / _year(d)
            name = readable_name(d, c)
            try:
                folder.mkdir(parents=True, exist_ok=True)
            except OSError:
                # a drive that cannot hold Chinese names (some network shares and older file systems): the code,
                # the date and the record's ID instead; the index still gives the title
                folder = base / c.security_code / _year(d)
                folder.mkdir(parents=True, exist_ok=True)
                name = f"{c.security_code} {d.announcement_date or ''} {d.id}{Path(name).suffix}"
            target = folder / name
            if str(target).lower() in used or (target.exists() and _size(target) != _size(p)):
                target = folder / f"{Path(name).stem} ({d.id}){Path(name).suffix}"
            used.add(str(target).lower())
            if target.exists() and _size(target) == _size(p):
                skipped += 1
            else:
                shutil.copyfile(p, target)          # with the dates, as copy2 would (copy2 needs CopyFile2
                shutil.copystat(p, target)          # on Windows, which some environments lack)
                copied += 1
            index.append({"copy": str(target.relative_to(base)), "code": c.security_code,
                          "company": c.short_name_cn or "", "date": d.announcement_date, "kind": d.kind,
                          "title": d.title_cn, "disclosure_id": d.id, "announcement_id": d.announcement_id,
                          "source_url": d.document_url, "sha256": d.sha256, "original": str(p)})
        cols = list(index[0])
        with (base / "index.csv").open("w", encoding="utf-8-sig", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=cols)
            w.writeheader()
            w.writerows(index)
        trs = "\n".join(
            "<tr>" + "".join(f"<td>{html.escape(str(r[k] or ''))}</td>" for k in ("code", "company", "date", "kind"))
            + f'<td><a href="{html.escape(r["copy"].replace(chr(92), "/"))}">{html.escape(r["title"] or "")}</a></td>'
            + f'<td><a href="{html.escape(r["source_url"] or "")}">source</a></td>'
            + f"<td>{r['disclosure_id']}</td></tr>" for r in index)
        (base / "index.html").write_text(
            "<!doctype html><meta charset='utf-8'><title>Downloaded documents</title>"
            "<style>body{font-family:sans-serif;margin:24px}td,th{padding:3px 8px;border-bottom:1px solid #ddd;"
            "font-size:13px}</style><h1>Downloaded documents</h1>"
            f"<p>{len(index):,} documents, copied from the program's store; the originals are unchanged. "
            "'source' is the address each document was downloaded from.</p>"
            "<table><tr><th>Code</th><th>Company</th><th>Date</th><th>Kind</th><th>Title</th><th>Source</th>"
            f"<th>Record</th></tr>{trs}</table>", encoding="utf-8")
        return {"copied": copied, "already_there": skipped, "documents": len(index), "folder": str(base),
                "index": str(base / "index.html")}
    finally:
        s.close()


def _disk_files() -> list[Path]:
    root = disclosure_dir()
    if not root.exists():
        return []
    # the program's own caches (".section_index") are not documents
    return [p for p in root.rglob("*") if p.is_file()
            and not any(part.startswith(".") for part in p.relative_to(root).parts)]


def check_files() -> dict:
    """Files no record names, records whose file is missing, files under several records, and summaries or English
    versions on disk (earlier versions downloaded them)."""
    from .models import SessionLocal, Disclosure, init_db
    init_db()
    s = SessionLocal()
    try:
        named: dict[str, list[int]] = defaultdict(list)
        missing, extra = [], []
        for d in s.query(Disclosure).filter(Disclosure.local_path.isnot(None)):
            p = document_path(d)
            key = str(p.resolve()).lower()
            named[key].append(d.id)
            if not p.exists():
                missing.append(d.id)
            elif (d.kind or "").endswith(("_summary", "_english")):
                extra.append(d.id)
        unnamed = [str(p) for p in _disk_files() if str(p.resolve()).lower() not in named]
        shared = [{"path": k, "records": v} for k, v in named.items() if len(v) > 1]
        return {"unnamed_files": len(unnamed), "unnamed_mb": round(sum(_size(Path(p)) for p in unnamed) / 1048576, 1),
                "missing_files": len(missing), "shared_files": len(shared), "summaries_english": len(extra),
                "examples": {"unnamed": unnamed[:10], "missing": missing[:10], "shared": shared[:5],
                             "summaries_english": extra[:10]}}
    finally:
        s.close()


def tidy_files(what: str, apply: bool = False, kind: str | None = None, security_code: str | None = None) -> dict:
    """Remove a chosen class of files: ``unnamed`` (files no record names), ``summaries_english``, or ``kind`` (the
    documents of one ``kind``). Previews unless ``apply``; when applied, clears the path of every record of a removed
    file and writes ``logs/tidy_<time>.csv``."""
    from .models import SessionLocal, Disclosure, Company, init_db
    if what not in TIDY_CLASSES:
        raise ValueError(f"choose one of {', '.join(TIDY_CLASSES)}")
    if what == "kind" and not kind:
        raise ValueError("give the kind of document to remove (--kind)")
    init_db()
    s = SessionLocal()
    try:
        targets: list[tuple[Path, list]] = []
        if what == "unnamed":
            named = {str(document_path(d).resolve()).lower()
                     for d in s.query(Disclosure).filter(Disclosure.local_path.isnot(None))}
            targets = [(p, []) for p in _disk_files() if str(p.resolve()).lower() not in named]
        else:
            everyone: dict[str, list[int]] = defaultdict(list)
            for d in s.query(Disclosure.id, Disclosure.local_path).filter(Disclosure.local_path.isnot(None)):
                everyone[str(document_path(d).resolve()).lower()].append(d.id)
            q = s.query(Disclosure).filter(Disclosure.local_path.isnot(None))
            if security_code:
                q = q.join(Company, Disclosure.company_id == Company.id).filter(
                    Company.security_code == str(security_code).zfill(6))
            by_path: dict[str, tuple[Path, list]] = {}
            for d in q:
                if what == "summaries_english" and not (d.kind or "").endswith(("_summary", "_english")):
                    continue
                if what == "kind" and d.kind != kind:
                    continue
                p = document_path(d)
                if p.exists():
                    by_path.setdefault(str(p.resolve()).lower(), (p, []))[1].append(d)
            for key, (p, recs) in by_path.items():
                if set(everyone[key]) <= {d.id for d in recs}:     # a file another record still names is kept
                    targets.append((p, recs))
        mb = round(sum(_size(p) for p, _ in targets) / 1048576, 1)
        result = {"class": what, "files": len(targets), "mb": mb, "applied": bool(apply),
                  "examples": [str(p) for p, _ in targets[:10]]}
        if not apply:
            result["note"] = "preview only: nothing was removed. Tick 'Apply' (--apply) to remove these files."
            return result
        logs = Path("logs")
        logs.mkdir(parents=True, exist_ok=True)
        log = logs / f"tidy_{datetime.now():%Y%m%d-%H%M%S}.csv"
        removed = 0
        with log.open("w", encoding="utf-8-sig", newline="") as fh:
            w = csv.writer(fh)
            w.writerow(["path", "bytes", "disclosure_ids", "removed"])
            for p, recs in targets:
                size = _size(p)
                try:
                    p.unlink()
                    ok = True
                    removed += 1
                except OSError as exc:
                    ok = repr(exc)
                if ok is True:
                    for d in recs:
                        d.local_path = None
                        d.text_layer = None
                w.writerow([str(p), size, " ".join(str(d.id) for d in recs), ok])
        s.commit()
        result.update({"removed": removed, "log": str(log)})
        return result
    finally:
        s.close()
