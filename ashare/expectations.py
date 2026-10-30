"""Expectations: management guidance first, analyst forecasts by import (v2.1, plan workstream E2).

**Management guidance** is read from the company's own announcements:
* an earnings forecast (业绩预告) gives a range for a period not yet reported, for example "归属于上市公司股东的净利润
  盈利：5,000万元–6,000万元, 比上年同期增长：25%–50%";
* a flash report (业绩快报) gives the period's preliminary figures before the report itself.

It is a disclosed proxy for expectations, not investors' expectations, and is labelled MANAGEMENT_GUIDANCE.

**Analyst forecasts** enter only by import from a file the researcher is licensed to use
(``import-analyst-forecasts-csv``), labelled ANALYST_FORECAST, with the licence recorded. The two are never mixed in
one series: every reader of ``expectation_observations`` selects one ``source_kind``.
"""
from __future__ import annotations

import csv
import re
from pathlib import Path

from .models import Company, Disclosure, ExpectationObservation, SessionLocal, init_db

GUIDANCE = "MANAGEMENT_GUIDANCE"
ANALYST = "ANALYST_FORECAST"
SOURCE_KINDS = (GUIDANCE, ANALYST)

# measure -> label patterns, the longer (more specific) first; 扣除非经常性损益 is tested before the plain label
MEASURES = (
    ("net_profit_parent_ex_nonrecurring",
     r"扣除非经常性损益(?:后)?的净利润|扣除非经常性损益后归属于(?:上市公司股东|母公司所有者|母公司股东)的净利润|扣非后?净利润"),
    ("net_profit_parent", r"归属于(?:上市公司|本公司|公司)?(?:股东|母公司所有者|母公司股东|母公司普通股股东)的净利润|归母净利润"),
    ("revenue", r"营业总收入|营业收入"),
    ("operating_profit", r"营业利润"),
    ("total_profit", r"利润总额"),
    ("eps", r"基本每股收益"),
)
_LABEL = re.compile("|".join(f"(?P<{m}>{p})" for m, p in MEASURES))
_NUM = r"[-－−]?\s*\d[\d,，]*(?:\.\d+)?"
_UNIT = r"(?:亿元|万元|千元|元/股|元)"
_SEP = r"\s*(?:–|—|－|~|～|至|到|-)\s*"
_SIGN = r"(?:(?P<{0}>盈利|亏损)\s*[:：]?\s*)?"
RANGE = re.compile(_SIGN.format("s1") + rf"(?P<a>{_NUM})\s*(?P<ua>{_UNIT})?" + _SEP + _SIGN.format("s2")
                   + rf"(?P<b>{_NUM})\s*(?P<ub>{_UNIT})")
SINGLE = re.compile(_SIGN.format("s1") + rf"(?P<a>{_NUM})\s*(?P<ua>{_UNIT})")
PCT_RANGE = re.compile(rf"(?P<dir>增长|增加|上升|下降|减少|变动)\s*[:：]?\s*(?:幅度\s*[:：]?\s*)?(?P<a>{_NUM})\s*[%％]"
                       + _SEP + rf"(?P<b>{_NUM})\s*[%％]")
DIRECTIONS = ("扭亏为盈", "扭亏", "首亏", "续亏", "预增", "预减", "略增", "略减", "续盈", "预盈", "减亏", "增亏")
UNIT_MULT = {"亿元": 1e8, "万元": 1e4, "千元": 1e3, "元": 1.0, "元/股": 1.0}


def _num(raw: str) -> float | None:
    s = raw.replace(",", "").replace("，", "").replace("－", "-").replace("−", "-").replace(" ", "")
    try:
        return float(s)
    except ValueError:
        return None


def _value(raw, unit, sign) -> float | None:
    v = _num(raw)
    if v is None or unit is None:
        return None
    v *= UNIT_MULT[unit]
    if sign == "亏损" and v > 0:
        v = -v
    return round(v, 4)


def document_kind(title: str) -> str:
    return "FLASH" if "快报" in (title or "") else "FORECAST"


def guidance_period(title: str, announcement_date: str | None) -> tuple[str | None, str]:
    from .financials import infer_period
    period, ptype = infer_period(title or "", "", announcement_date)
    if ptype == "UNKNOWN" and period:
        ptype = "FY"
    return period, ptype


def _segments(text: str):
    """(measure, text that follows its label up to the next label) for every label in the text."""
    hits = list(_LABEL.finditer(text))
    for k, m in enumerate(hits):
        end = hits[k + 1].start() if k + 1 < len(hits) else min(len(text), m.end() + 220)
        yield m.lastgroup, text[m.end():min(end, m.end() + 220)], m.start()


def parse_forecast_text(pages: list[str]) -> list[dict]:
    """Ranges of an earnings forecast (业绩预告): one record per measure, the first statement of each."""
    text = re.sub(r"[ \t　]+", " ", "\n".join(pages))
    flat = text.replace("\n", " ")
    out, seen = [], set()
    for measure, tail, pos in _segments(flat):
        if measure in seen:                 # the first statement is the forecast; later ones describe the prior year
            continue
        rec = None
        m = RANGE.search(tail)
        if m and m.start() < 80:
            ua = m.group("ua") or m.group("ub")
            sign_b = m.group("s2") or m.group("s1")
            lo, hi = _value(m.group("a"), ua, m.group("s1")), _value(m.group("b"), m.group("ub"), sign_b)
            if lo is not None and hi is not None:
                lo, hi = sorted((lo, hi))
                rec = {"low": lo, "high": hi, "raw_value": m.group(0).strip(), "confidence": 0.8,
                       "unit": "CNY_PER_SHARE" if m.group("ub") == "元/股" else "CNY"}
        if rec is None:
            m = SINGLE.search(tail)
            if m and m.start() < 60:
                v = _value(m.group("a"), m.group("ua"), m.group("s1"))
                if v is not None:
                    rec = {"low": v, "high": v, "raw_value": m.group(0).strip(), "confidence": 0.6,
                           "unit": "CNY_PER_SHARE" if m.group("ua") == "元/股" else "CNY"}
        if rec is None:
            continue
        after = tail[m.end():]
        p = PCT_RANGE.search(after[:120])
        if p:
            a, b = _num(p.group("a")), _num(p.group("b"))
            if a is not None and b is not None:
                if p.group("dir") in ("下降", "减少"):
                    a, b = -a, -b
                rec["change_low_pct"], rec["change_high_pct"] = sorted((a, b))
        prior = re.search(r"^[^。；;]{0,40}?(?:上年同期|去年同期)\s*[:：]?\s*" + _SIGN.format("s1")
                          + rf"(?P<a>{_NUM})\s*(?P<ua>{_UNIT})", after)
        if not prior:                       # the table layout: the prior-year column follows the range
            prior = SINGLE.match(after.lstrip())
        if prior:
            rec["prior_value"] = _value(prior.group("a"), prior.group("ua"), prior.group("s1"))
        rec["measure"] = measure
        out.append(rec)
        seen.add(measure)
    return out


def parse_flash_text(pages: list[str]) -> list[dict]:
    """Preliminary figures of a flash report (业绩快报): the current-period column of its table."""
    from .units import first_declared
    out, seen = [], set()
    for page in pages:
        declared = first_declared(page)
        for raw in page.splitlines():
            line = re.sub(r"[ \t　]+", " ", raw).strip()
            m = _LABEL.match(line)
            if not m or m.lastgroup in seen:
                continue
            rest = line[m.end():]
            rest = re.sub(r"^[（(][^）)]*[）)]", "", rest).strip()          # 基本每股收益（元）
            nums = re.findall(_NUM, rest)
            if len(nums) < 2:
                continue
            measure = m.lastgroup
            mult = 1.0 if measure == "eps" else (declared[1] if declared else None)
            if mult is None:
                continue
            cur, prior = _num(nums[0]), _num(nums[1])
            if cur is None:
                continue
            rec = {"measure": measure, "low": round(cur * mult, 4), "high": round(cur * mult, 4),
                   "prior_value": round(prior * mult, 4) if prior is not None else None,
                   "unit": "CNY_PER_SHARE" if measure == "eps" else "CNY", "raw_value": line[:200],
                   "confidence": 0.75}
            if len(nums) >= 3 and _num(nums[2]) is not None:
                rec["change_low_pct"] = rec["change_high_pct"] = _num(nums[2])
            out.append(rec)
            seen.add(measure)
    return out


def parse_guidance(pages: list[str], title: str) -> list[dict]:
    recs = parse_flash_text(pages) if document_kind(title) == "FLASH" else parse_forecast_text(pages)
    direction = next((d for d in DIRECTIONS if d in (title or "") or d in "".join(pages)[:2000]), None)
    flat = [re.sub(r"\s+", "", p) for p in pages]
    for r in recs:
        r["direction"] = direction
        probe = re.sub(r"\s+", "", r.get("raw_value") or "")
        r["page"] = next((i for i, p in enumerate(flat, start=1) if probe and probe in p), None)
    return recs


def parse_guidance_job(job: dict, reader) -> list[dict]:
    """The reading half of :func:`read_guidance` (worker processes; no database)."""
    recs = parse_guidance(reader.pages("text", []), job.get("title") or "")
    if not recs:                                   # tables the plain text scrambles: try the layout reading
        lay = reader.pages("layout", [])
        if lay:
            recs = parse_guidance(lay, job.get("title") or "")
    return recs


def read_guidance(security_code: str | None = None, again: bool = False, progress=None, download: bool = True) -> dict:
    """Read management guidance from earnings forecasts and flash reports.

    These announcements are downloaded first (kind ``earnings_forecast_or_flash`` only; review round 3), since a
    catalogue run downloads periodic reports, not announcements."""
    from .extractstate import run
    init_db()
    say = progress or (lambda m: None)
    totals = {"documents": 0, "observations": 0, "inserted": 0, "updated": 0, "empty": 0, "errors": []}
    s = SessionLocal()
    try:
        q = (s.query(Disclosure, Company).join(Company, Disclosure.company_id == Company.id)
             .filter(Disclosure.kind == "earnings_forecast_or_flash"))
        if security_code:
            q = q.filter(Company.security_code == str(security_code).zfill(6))
        if download:
            missing = [d.id for d, _ in q if not d.local_path or not Path(d.local_path).exists()]
            if missing:
                from .disclosure_pipeline import download_pending
                say(f"Downloading {len(missing):,} earnings forecast and flash report document(s) first")
                totals["download"] = download_pending(missing, ("earnings_forecast_or_flash",), progress=say)
                s.expire_all()
        rows = [(d, c) for d, c in q.order_by(Company.security_code, Disclosure.announcement_date, Disclosure.id)
                if d.local_path]

        def handle(d, c, recs):
            period, ptype = guidance_period(d.title_cn, d.announcement_date)
            if not period:
                return None
            if not recs:
                totals["empty"] += 1
                return "EMPTY"
            totals["documents"] += 1
            for r in recs:
                key = dict(company_id=c.id, source_kind=GUIDANCE, reporting_period=period, measure=r["measure"],
                           issuer=c.security_code, published_date=d.announcement_date, source=d.source or "CNINFO")
                row = s.query(ExpectationObservation).filter_by(**key).one_or_none()
                if row is None:
                    row = ExpectationObservation(**key)
                    s.add(row)
                    totals["inserted"] += 1
                else:
                    totals["updated"] += 1
                row.disclosure_id, row.document_kind, row.period_type = d.id, document_kind(d.title_cn), ptype
                for k in ("low", "high", "change_low_pct", "change_high_pct", "prior_value", "direction", "unit",
                          "raw_value", "confidence"):
                    setattr(row, k, r.get(k))
                row.source_page = r.get("page")
                row.extraction_method = "GUIDANCE_TEXT"
                totals["observations"] += 1
            return "READ"
        run("guidance", rows, handle, totals, again=again, progress=say, session=s,
            parse="ashare.expectations:parse_guidance_job")
        return totals
    finally:
        s.close()


ANALYST_COLUMNS = ("code", "period", "measure", "low", "high", "issuer", "published_date")


def import_analyst_forecasts_csv(path: str, licence: str, source_label: str = "ANALYST_CSV") -> dict:
    """Analyst forecasts from a CSV the researcher is licensed to use.

    Columns: code, period (YYYY-MM-DD), measure (net_profit_parent, revenue, eps ...), low, high (or value),
    issuer (the broker), published_date; optional unit (CNY by default; CNY_PER_SHARE for eps). Values in yuan.
    The licence is recorded on every row, and the rows are LICENSED (excluded from releases by default)."""
    if not (licence or "").strip():
        raise ValueError("state the licence under which the forecasts are used (--licence)")
    init_db()
    s = SessionLocal()
    out = {"rows": 0, "inserted": 0, "updated": 0, "skipped": [], "licence": licence}
    codes = {c.security_code: c.id for c in s.query(Company.security_code, Company.id)}
    try:
        with open(path, encoding="utf-8-sig", newline="") as fh:
            reader = csv.DictReader(fh)
            missing = [c for c in ("code", "period", "measure", "issuer", "published_date")
                       if c not in (reader.fieldnames or [])]
            if missing:
                raise ValueError(f"missing column(s): {', '.join(missing)}")
            for n, r in enumerate(reader, start=2):
                code = str(r.get("code") or "").strip().zfill(6)
                if code not in codes:
                    out["skipped"].append({"line": n, "reason": f"unknown code {code}"})
                    continue
                lo = _num(str(r.get("low") or r.get("value") or ""))
                hi = _num(str(r.get("high") or r.get("value") or r.get("low") or ""))
                if lo is None or hi is None or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", r["period"].strip()) \
                        or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", r["published_date"].strip()):
                    out["skipped"].append({"line": n, "reason": "value or date not readable"})
                    continue
                key = dict(company_id=codes[code], source_kind=ANALYST, reporting_period=r["period"].strip(),
                           measure=r["measure"].strip(), issuer=r["issuer"].strip(),
                           published_date=r["published_date"].strip(), source=f"{source_label}")
                row = s.query(ExpectationObservation).filter_by(**key).one_or_none()
                if row is None:
                    row = ExpectationObservation(**key)
                    s.add(row)
                    out["inserted"] += 1
                else:
                    out["updated"] += 1
                lo, hi = sorted((lo, hi))
                row.low, row.high, row.document_kind, row.licence = lo, hi, "IMPORT", licence.strip()
                row.unit = (r.get("unit") or "").strip() or ("CNY_PER_SHARE" if key["measure"] == "eps" else "CNY")
                row.extraction_method, row.confidence = "CSV_IMPORT", None
                out["rows"] += 1
        s.commit()
        return out
    finally:
        s.close()


def expectation_series(code: str, measure: str, source_kind: str, as_of: str | None = None) -> list[dict]:
    """One source kind's expectations for one company and measure, as published by ``as_of`` (never mixed)."""
    if source_kind not in SOURCE_KINDS:
        raise ValueError(f"source_kind must be one of {SOURCE_KINDS}")
    init_db()
    s = SessionLocal()
    try:
        c = s.query(Company).filter_by(security_code=str(code).zfill(6)).one_or_none()
        if c is None:
            return []
        q = s.query(ExpectationObservation).filter_by(company_id=c.id, measure=measure, source_kind=source_kind)
        rows = [r for r in q if not as_of or (r.published_date and r.published_date <= as_of)]
        rows.sort(key=lambda r: (r.reporting_period, r.published_date or "", r.id))
        return [{"period": r.reporting_period, "low": r.low, "high": r.high, "published": r.published_date,
                 "issuer": r.issuer, "document_kind": r.document_kind, "source_kind": r.source_kind,
                 "disclosure_id": r.disclosure_id, "page": r.source_page, "licence": r.licence} for r in rows]
    finally:
        s.close()
