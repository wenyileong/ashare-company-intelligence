"""Targeted reading of periodic reports (v2.0.8, findings 76, 77 and 82).

The table extractors used to read every page of a report twice over: the plain text of the whole document
(pypdf) and the layout of every page (rows rebuilt from character positions in Python), for each table sought.
An annual report has 200 to 300 pages and the table is on two or three of them, so "Read top-10 shareholders"
took about five minutes a report.

A :class:`ReportReader` opens a report once and:

1. reads the text of every page quickly with pdfium (one call per page, in C) to find the sections sought;
2. reads the plain text (pypdf) and the layout rows only of the pages in those sections, each page at most once;
3. returns pages of the document's full length, blank outside the sections, so page numbers stay right and the
   parsers run unchanged.

When no section is found, or pdfium is not installed, the whole document is read as before, so nothing that worked
before is lost (``fallback_full``).
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

INDEX_VERSION = 1          # bump when SECTIONS changes, so cached indexes are rebuilt

# section -> (heading patterns, pages after the heading page that belong to it)
SECTIONS: dict[str, tuple[tuple[str, ...], int]] = {
    "top10": (("前十名股东持股情况", "前10名股东持股情况", "前十名股东", "前10名股东"), 2),
    "top10_tradable": (("前十名无限售条件股东", "前10名无限售条件股东", "前十名流通股东", "前10名流通股东",
                        "前十名无限售流通股", "前10名无限售流通股"), 2),
    "control": (("控股股东情况", "实际控制人情况", "实际控制人及其一致行动人", "控股股东及实际控制人",
                 "控股股东、实际控制人"), 2),
    "segments": (("营业收入构成", "主营业务分行业", "主营业务分产品", "主营业务分地区", "分行业情况", "分产品情况",
                  "分地区情况", "占公司营业收入或营业利润10%以上"), 2),
    "human_capital": (("研发投入", "研发人员", "员工情况", "员工数量", "专业构成", "教育程度", "专利"), 1),
    "subsidiaries": (("在子公司中的权益", "企业集团的构成", "主要控股参股公司", "主要子公司"), 2),
    "roster": (("董事、监事和高级管理人员", "董事、监事、高级管理人员", "董事和高级管理人员", "董事、高级管理人员"), 3),
}
_WS = re.compile(r"\s+")


def _pdfium():
    try:
        import pypdfium2 as pdfium
        return pdfium
    except Exception:
        return None


class ReportReader:
    """One open report, its section pages, and caches of what has been read."""

    def __init__(self, path):
        self.path = Path(path)
        self.fallback_full = False
        self.layout_pages_read = 0
        self.text_pages_read = 0
        self._fast: dict[int, str] = {}
        self._text: dict[int, str] = {}
        self._layout: dict[int, str] = {}
        self._full: dict[str, list[str]] = {}
        self._index: dict[str, list[int]] | None = None
        self._pypdf = None
        self._pdf = None
        self.n = 0
        pdfium = _pdfium() if self.path.suffix.lower() == ".pdf" else None
        if pdfium is not None:
            try:
                self._pdf = pdfium.PdfDocument(str(self.path))
                self.n = len(self._pdf)
            except Exception:
                self._pdf = None

    # --- finding sections ---------------------------------------------------------------------------------------

    def fast_text(self, i: int) -> str:
        if i not in self._fast:
            page = self._pdf[i]
            tp = page.get_textpage()
            try:
                self._fast[i] = tp.get_text_range() or ""
            finally:
                tp.close()
                page.close()
        return self._fast[i]

    def index(self) -> dict[str, list[int]]:
        """Heading pages of every known section, found in one pass and kept beside the documents
        (``disclosures/.section_index``), so that the other extractors reading the same report skip the pass."""
        if self._index is not None:
            return self._index
        cache = None
        try:
            st = self.path.stat()
            from .config import disclosure_dir
            key = hashlib.sha1(f"{self.path.resolve()}|{st.st_size}|{int(st.st_mtime)}|{INDEX_VERSION}".encode()).hexdigest()
            cache = disclosure_dir() / ".section_index" / f"{key}.json"
            if cache.exists():
                self._index = {k: list(v) for k, v in json.loads(cache.read_text(encoding="utf-8")).items()}
                return self._index
        except Exception:
            cache = None
        found: dict[str, list[int]] = {name: [] for name in SECTIONS}
        for i in range(self.n):
            flat = _WS.sub("", self.fast_text(i))
            for name, (pats, _) in SECTIONS.items():
                if any(p in flat for p in pats):
                    found[name].append(i)
        self._index = found
        if cache is not None:
            try:
                cache.parent.mkdir(parents=True, exist_ok=True)
                cache.write_text(json.dumps(found), encoding="utf-8")
            except Exception:
                pass
        return found

    def section_pages(self, sections) -> list[int]:
        """Zero-based page numbers of the named sections (heading page and the pages after it)."""
        if self._pdf is None:
            return []
        idx = self.index()
        hits: set[int] = set()
        for name in sections:
            if name not in SECTIONS:
                continue
            after = SECTIONS[name][1]
            for i in idx.get(name, []):
                hits.update(range(i, min(self.n, i + after + 1)))
        return sorted(hits)

    # --- reading ------------------------------------------------------------------------------------------------

    def _text_page(self, i: int) -> str:
        if i not in self._text:
            if self._pypdf is None:
                from pypdf import PdfReader
                from .http import document_heartbeat
                from .pdfwarnings import set_document
                document_heartbeat(self.path)
                set_document(self.path)
                self._pypdf = PdfReader(str(self.path))
            try:
                self._text[i] = self._pypdf.pages[i].extract_text() or ""
            except Exception:
                self._text[i] = ""
            self.text_pages_read += 1
        return self._text[i]

    def _layout_page(self, i: int) -> str:
        if i not in self._layout:
            from .layout import page_rows, merge_wrapped
            page = self._pdf[i]
            tp = page.get_textpage()
            try:
                self._layout[i] = "\n".join(r.text for r in merge_wrapped(page_rows(tp)))
            finally:
                tp.close()
                page.close()
            self.layout_pages_read += 1
        return self._layout[i]

    def _whole(self, input: str) -> list[str]:
        if input not in self._full:
            from .parsers import load_pages
            self._full[input] = load_pages(self.path, input)
        return self._full[input]

    def pages(self, input: str, sections) -> list[str]:
        """Pages for a parser ('text' or 'layout'): the sections' pages filled, the others blank."""
        from .http import check_cancel
        check_cancel()
        if self._pdf is None:
            self.fallback_full = True
            return self._whole(input) if input == "text" else []
        if input == "layout":
            from .layout import available
            if not available():
                return []
        idx = self.section_pages(sections)
        if not idx:
            self.fallback_full = True
            return self._whole(input)
        read = self._layout_page if input == "layout" else self._text_page
        out = [""] * self.n
        for i in idx:
            out[i] = read(i)
        return out

    def close(self) -> None:
        if self._pdf is not None:
            try:
                self._pdf.close()
            except Exception:
                pass
            self._pdf = None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
