"""Layout-aware PDF text (v1.5).

The plain extractor (pypdf) returns text in content-stream order, so a table
cell that wraps onto a second line becomes a separate line, and the parser
sees a broken row ("贵州茅台酱香酒营销有" / "限公司 贵州仁怀 … 100.00").

This module rebuilds rows and cells from character positions (pypdfium2):

1. characters are grouped into rows by their vertical centre;
2. a row is split into cells wherever the horizontal gap exceeds about one
   character height;
3. *fragment* rows (no numeric cell, at most two cells, not a heading or a
   sentence) are merged into the nearest row with figures whose cell they
   overlap horizontally, before or after its text, within 1.35 line heights.

The result is returned both as structured rows and as text lines in the
form the existing parsers read, so each table parser runs unchanged on
either extractor (see ``ashare.parsers``).

pypdfium2 is optional for source installs; without it, ``available()`` is
False and the pipeline falls back to the plain extractor.
"""
from __future__ import annotations

import re
import statistics
from dataclasses import dataclass, field
from pathlib import Path


def available() -> bool:
    try:
        import pypdfium2  # noqa: F401
        return True
    except Exception:
        return False


@dataclass
class Cell:
    x0: float
    x1: float
    y0: float
    y1: float
    text: str

    @property
    def numeric(self) -> bool:
        toks = self.text.split()
        return bool(toks) and all(_NUMERIC.fullmatch(t) for t in toks)


@dataclass
class Row:
    y: float               # vertical centre (PDF coordinates, larger = higher on page)
    height: float
    cells: list[Cell] = field(default_factory=list)

    @property
    def text(self) -> str:
        return " ".join(c.text for c in self.cells)

    def has_numeric(self) -> bool:
        return any(c.numeric for c in self.cells)


_NUMERIC = re.compile(r"[-−(（]?\d[\d,，]*(?:\.\d+)?[)）]?%?|[-－—]+")
_HEADING = re.compile(
    r"^(分行业|分产品|分地区|分销售模式|分渠道|分部|分业务|分板块|合计|小计|总计|项目|单位|金额单位|币种|"
    r"第[一二三四五六七八九十]+节|[一二三四五六七八九十]+、|[（(][一二三四五六七八九十\d]+[)）]|\d+[、.])")
_CJK = re.compile("[\u4e00-\u9fff\u3000-\u303f\uff00-\uffef]")  # ideographs and CJK punctuation


def _chars(textpage):
    n = textpage.count_chars()
    out = []
    for i in range(n):
        ch = textpage.get_text_range(i, 1)
        if not ch or ch in "\r\n":
            continue
        l, b, r, t = textpage.get_charbox(i, loose=True)
        if r - l <= 0 and not ch.isspace():
            continue
        out.append((ch, l, b, r, t))
    return out


def page_rows(textpage) -> list[Row]:
    """Group characters into rows and cells."""
    chars = _chars(textpage)
    if not chars:
        return []
    heights = [t - b for ch, l, b, r, t in chars if not ch.isspace() and t > b]
    h = statistics.median(heights) if heights else 10.0
    # rows by vertical centre, top of page first
    chars.sort(key=lambda c: (-(c[2] + c[4]) / 2, c[1]))
    rows: list[list] = []
    for c in chars:
        cy = (c[2] + c[4]) / 2
        if rows and abs(rows[-1][0] - cy) <= 0.5 * h:
            rows[-1][1].append(c)
        else:
            rows.append([cy, [c]])
    out = []
    for cy, cs in rows:
        cs.sort(key=lambda c: c[1])
        row = Row(y=cy, height=h)
        cur = None
        prev_r = None
        pending_space = False
        for ch, l, b, r, t in cs:
            if ch.isspace():
                pending_space = True
                continue
            gap = (l - prev_r) if prev_r is not None else 0
            if cur is None or gap > 1.0 * h:
                cur = Cell(l, r, b, t, ch)
                row.cells.append(cur)
            else:
                if pending_space or gap > 0.2 * h:
                    cur.text += " "
                cur.text += ch
                cur.x1, cur.y0, cur.y1 = max(cur.x1, r), min(cur.y0, b), max(cur.y1, t)
            prev_r = r
            pending_space = False
        if row.cells:
            out.append(row)
    return out


def _is_fragment(row: Row) -> bool:
    if row.has_numeric() or not (1 <= len(row.cells) <= 2):
        return False
    text = row.text.strip()
    if _HEADING.match(text) or re.search(r"[。；;：:]$|。|\d{4}\s*年", text) or len(text) > 40:
        return False
    return True


def _overlaps(a: Cell, b: Cell, tol: float) -> bool:
    return a.x0 <= b.x1 + tol and b.x0 <= a.x1 + tol


def _join(a: str, b: str) -> str:
    if a and b and _CJK.search(a[-1]) and _CJK.search(b[0]):
        return a + b
    if a.endswith(("(", "（")) or b.startswith((")", "）")):
        return a + b
    return (a + " " + b).strip()


def merge_wrapped(rows: list[Row]) -> list[Row]:
    """Merge wrapped-cell fragments into the row they belong to."""
    if not rows:
        return rows
    keep = [True] * len(rows)
    for i, row in enumerate(rows):
        if not _is_fragment(row):
            continue
        best = None
        for j in (i - 1, i + 1, i - 2, i + 2):
            if j < 0 or j >= len(rows) or j == i or not keep[j] or _is_fragment(rows[j]):
                continue
            target = rows[j]
            if not target.has_numeric():
                continue
            dist = abs(target.y - row.y)
            if dist > 1.35 * row.height:
                continue
            match = []
            for fc in row.cells:
                tc = next((tc for tc in target.cells if _overlaps(fc, tc, 0.6 * row.height) and not tc.numeric), None)
                if tc is None and not any(_overlaps(fc, x, 0.2 * row.height) for x in target.cells):
                    tc = "insert"  # a vertically centred cell: the row itself has no text in this column
                match.append(tc)
            if any(m is None for m in match):
                continue
            if best is None or dist < best[0]:
                best = (dist, j, match)
        if best is None:
            continue
        _, j, match = best
        above = row.y > rows[j].y
        target = rows[j]
        for fc, tc in zip(row.cells, match):
            if tc == "insert":
                target.cells.append(Cell(fc.x0, fc.x1, fc.y0, fc.y1, fc.text))
                target.cells.sort(key=lambda c: c.x0)
            else:
                tc.text = _join(fc.text, tc.text) if above else _join(tc.text, fc.text)
                tc.x0, tc.x1 = min(tc.x0, fc.x0), max(tc.x1, fc.x1)
        keep[i] = False
    return [r for r, k in zip(rows, keep) if k]


def layout_pages_rows(path: str | Path) -> list[list[Row]]:
    import pypdfium2 as pdfium
    pdf = pdfium.PdfDocument(str(path))
    try:
        pages = []
        for i in range(len(pdf)):
            page = pdf[i]
            tp = page.get_textpage()
            try:
                pages.append(merge_wrapped(page_rows(tp)))
            finally:
                tp.close()
                page.close()
        return pages
    finally:
        pdf.close()


def layout_text_pages(path: str | Path) -> list[str]:
    """Pages as text lines, one line per reconstructed row."""
    return ["\n".join(r.text for r in rows) for rows in layout_pages_rows(path)]


def text_layer(path: str | Path) -> dict:
    """How much of a PDF has a text layer: FULL, PARTIAL or NONE (scanned)."""
    from .financials import _pdf_text_pages
    try:
        pages = _pdf_text_pages(Path(path))
    except Exception as exc:
        return {"status": "UNREADABLE", "pages": 0, "pages_with_text": 0, "error": repr(exc)}
    with_text = sum(1 for p in pages if len(re.sub(r"\s+", "", p)) >= 20)
    if not pages:
        status = "UNREADABLE"
    elif with_text == 0:
        status = "NONE"
    elif with_text < 0.8 * len(pages):
        status = "PARTIAL"
    else:
        status = "FULL"
    return {"status": status, "pages": len(pages), "pages_with_text": with_text}


def scan_documents(security_code: str | None = None, recheck: bool = False) -> dict:
    """Record whether each downloaded PDF has a text layer; list scanned ones.

    Scanned documents (no text layer) cannot be read by any parser. OCR is
    out of scope, so they are listed for manual entry or a licensed source.
    """
    from .models import SessionLocal, Disclosure, Company, init_db
    init_db()
    s = SessionLocal()
    totals = {"checked": 0, "FULL": 0, "PARTIAL": 0, "NONE": 0, "UNREADABLE": 0, "missing": 0, "scanned": []}
    try:
        q = s.query(Disclosure, Company).join(Company, Disclosure.company_id == Company.id).filter(
            Disclosure.local_path.isnot(None))
        if security_code:
            q = q.filter(Company.security_code == str(security_code).zfill(6))
        for d, c in q.all():
            path = Path(d.local_path)
            if path.suffix.lower() != ".pdf":
                continue
            if not path.exists():
                totals["missing"] += 1
                continue
            if d.text_layer and not recheck:
                status = d.text_layer
            else:
                status = text_layer(path)["status"]
                d.text_layer = status
                totals["checked"] += 1
            totals[status] = totals.get(status, 0) + 1
            if status in ("NONE", "PARTIAL"):
                totals["scanned"].append({"disclosure_id": d.id, "code": c.security_code, "title": d.title_cn,
                                          "date": d.announcement_date, "text_layer": status})
        s.commit()
        return totals
    finally:
        s.close()
