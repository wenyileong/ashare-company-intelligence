"""v1.3 environmental, social and governance (ESG) information.

Disclosure-based, not score-based: the system records what companies and
rating providers disclose, and assembles an ESG profile from the
environmental and social data points extracted here together with the
governance (v1.1) and regulatory (v0.9) layers. It does not compute a
composite ESG score, because any weighting would be the system's own
judgement rather than an observation.

Sources:
* annual reports (环境信息情况 / 环境和社会责任 section) and
  sustainability / CSR / ESG reports (``sustainability_report`` kind):
  key pollutant-discharge-unit status, pollutant and greenhouse-gas
  emissions, emission reductions, donations, rural revitalisation;
* third-party ESG ratings, imported from licensed data;
* regulatory events whose authority is an environmental regulator.
"""
from __future__ import annotations

import csv
import re
from collections import defaultdict
from pathlib import Path

from .evaluation import calibrated_confidence
from .timeutil import utcnow
from .models import (SessionLocal, Company, Disclosure, EsgObservation, EsgRating, RegulatoryEvent, init_db)
from .disclosures import SUSTAINABILITY_RE
from .ownership import normalise_date

#: item -> (pillar, unit, description)
ITEMS = {
    "key_pollutant_discharge_unit": ("E", "FLAG", "重点排污单位 (1 = yes, 0 = no)"),
    "emission_cod": ("E", "TONNE", "化学需氧量排放"),
    "emission_ammonia_nitrogen": ("E", "TONNE", "氨氮排放"),
    "emission_so2": ("E", "TONNE", "二氧化硫排放"),
    "emission_nox": ("E", "TONNE", "氮氧化物排放"),
    "emission_particulates": ("E", "TONNE", "颗粒物/烟尘排放"),
    "ghg_emissions": ("E", "TCO2E", "温室气体排放总量"),
    "ghg_reduction": ("E", "TCO2E", "减少二氧化碳当量排放"),
    "environmental_investment": ("E", "CNY", "环保投入"),
    "donations": ("S", "CNY", "对外捐赠"),
    "rural_revitalisation": ("S", "CNY", "巩固拓展脱贫攻坚成果、乡村振兴投入"),
    "sustainability_report_published": ("G", "FLAG", "披露社会责任/可持续发展/ESG报告"),
}

_NUM = r"(\d[\d,]*(?:\.\d+)?)"
_MASS = r"\s*(万吨|吨|千克|kg|t)(?![a-zA-Z])"
_MONEY = r"\s*(亿元|万元|元)"

POLLUTANTS = (
    ("emission_cod", r"(?:化学需氧量|COD)"), ("emission_ammonia_nitrogen", r"(?:氨氮|NH3-N)"),
    ("emission_so2", r"(?:二氧化硫|SO2|SO₂)"), ("emission_nox", r"(?:氮氧化物|NOx|NOX)"),
    ("emission_particulates", r"(?:颗粒物|烟尘|粉尘)"),
)


def _mass(v: str, unit: str) -> float:
    x = float(v.replace(",", ""))
    return x * 1e4 if unit == "万吨" else (x / 1000 if unit in ("千克", "kg") else x)


def _money(v: str, unit: str) -> float:
    x = float(v.replace(",", ""))
    return x * (1e8 if unit == "亿元" else 1e4 if unit == "万元" else 1)


def parse_esg_text(pages: list[str]) -> list[dict]:
    """Extract ESG data points from report text (first occurrence wins)."""
    out: dict[str, dict] = {}

    def put(item, value, page, raw, conf=0.55, text=None):
        if item not in out:
            out[item] = {"item": item, "value": value, "value_text": text, "page": page,
                         "raw": re.sub(r"\s+", " ", raw)[:300], "confidence": conf}

    for pno, page in enumerate(pages, start=1):
        flat = re.sub(r"[ \t　]+", "", page)
        # key pollutant discharge unit status
        m = re.search(r"(不属于|不是|非)(?:环境保护部门公布的)?重点排污单位", flat)
        if m:
            put("key_pollutant_discharge_unit", 0.0, pno, flat[max(0, m.start() - 30):m.end() + 20], 0.6)
        else:
            m = re.search(r"(?:属于|是|为|列入)(?:环境保护部门公布的)?(?:的)?重点排污单位|重点排污单位[:：]?是", flat)
            if m:
                put("key_pollutant_discharge_unit", 1.0, pno, flat[max(0, m.start() - 30):m.end() + 20], 0.6)
        for item, pat in POLLUTANTS:
            m = re.search(pat + r"[^。\n]{0,30}?(?:排放总量|排放量|年排放量|实际排放)[^\d\n]{0,12}" + _NUM + _MASS, flat)
            if m:
                put(item, _mass(m.group(1), m.group(2)), pno, m.group(0))
        m = re.search(r"(?:温室气体|二氧化碳|碳)排放(?:总)?量(?:为|合计|约)?[^\d\n]{0,12}" + _NUM + r"\s*(万吨|吨)(?:二氧化碳当量|CO2e|CO₂e|tCO2e)?", flat)
        if m:
            put("ghg_emissions", _mass(m.group(1), m.group(2)), pno, m.group(0))
        m = re.search(r"减少(?:排放)?(?:二氧化碳|碳|温室气体)(?:当量)?(?:排放)?(?:约|共计)?[^\d\n]{0,8}" + _NUM + r"\s*(万吨|吨)", flat)
        if m:
            put("ghg_reduction", _mass(m.group(1), m.group(2)), pno, m.group(0))
        m = re.search(r"环保(?:资金)?投入(?:资金)?(?:总额|金额|合计)?(?:为|约|共计)?[^\d\n]{0,8}" + _NUM + _MONEY, flat)
        if m:
            put("environmental_investment", _money(m.group(1), m.group(2)), pno, m.group(0))
        m = re.search(r"(?:对外)?捐赠(?:总额|金额|资金|款物)?(?:合计|共计|为|约)?[^\d\n]{0,8}" + _NUM + _MONEY, flat)
        if m:
            put("donations", _money(m.group(1), m.group(2)), pno, m.group(0))
        m = re.search(r"(?:乡村振兴|脱贫攻坚)[^。\n]{0,30}?(?:投入|资金|金额)(?:总额|合计|共计|为|约)?[^\d\n]{0,8}" + _NUM + _MONEY, flat)
        if m:
            put("rural_revitalisation", _money(m.group(1), m.group(2)), pno, m.group(0))
    return list(out.values())


def _period(d: Disclosure) -> str | None:
    m = re.search(r"(20\d{2})\s*年", d.title_cn or "")
    if m:
        return f"{m.group(1)}-12-31"
    if d.announcement_date:
        return f"{int(d.announcement_date[:4]) - 1}-12-31"
    return None


def _upsert(session, company_id, disclosure_id, period, item, value, source, doc, page, raw, method, conf, text=None):
    row = session.query(EsgObservation).filter_by(company_id=company_id, reporting_period=period, item=item,
                                                  source=source, disclosure_id=disclosure_id).one_or_none()
    created = row is None
    if created:
        row = EsgObservation(company_id=company_id, reporting_period=period, item=item, source=source,
                             disclosure_id=disclosure_id, pillar=ITEMS[item][0], extraction_method=method)
        session.add(row)
    row.value, row.value_text, row.unit = value, text, ITEMS[item][1]
    row.source_document, row.source_page, row.raw_value = doc, page, raw
    row.extraction_method, row.confidence, row.retrieved_at = method, conf, utcnow()
    return "inserted" if created else "updated"


def extract_esg(security_code: str | None = None) -> dict:
    """Read ESG data points from annual reports and sustainability reports,
    and record which years have a sustainability report."""
    from .corporate_actions import _document_pages
    init_db()
    session = SessionLocal()
    totals = {"documents": 0, "sustainability_reports": 0, "values": 0, "inserted": 0, "updated": 0, "errors": []}
    try:
        q = session.query(Disclosure, Company).join(Company, Disclosure.company_id == Company.id)
        if security_code:
            q = q.filter(Company.security_code == str(security_code).zfill(6))
        for d, c in q.all():
            is_sr = bool(SUSTAINABILITY_RE.search(d.title_cn or "")) and "摘要" not in (d.title_cn or "")
            if not (is_sr or d.kind == "annual_report"):
                continue
            period = _period(d)
            if not period:
                continue
            try:
                src = d.source or "CNINFO"
                if is_sr:
                    totals["sustainability_reports"] += 1
                    totals[_upsert(session, c.id, d.id, period, "sustainability_report_published", 1.0, src,
                                   d.document_url or d.local_path, None, d.title_cn, "TITLE", 0.9, d.title_cn)] += 1
                if d.local_path and Path(d.local_path).exists():
                    vals = parse_esg_text(_document_pages(Path(d.local_path)))
                    totals["documents"] += 1
                    for v in vals:
                        totals["values"] += 1
                        totals[_upsert(session, c.id, d.id, period, v["item"], v["value"], src,
                                       d.local_path or d.document_url, v["page"], v["raw"],
                                       "PDF_TEXT_HEURISTIC", calibrated_confidence("esg", v["confidence"]), v.get("value_text"))] += 1
                session.commit()
            except Exception as exc:
                session.rollback()
                totals["errors"].append({"disclosure_id": d.id, "error": repr(exc)})
        return totals
    finally:
        session.close()


def import_esg_csv(path: str, source: str = "CSV_IMPORT") -> dict:
    """Long format: security_code, reporting_period, item, value[, value_text]."""
    init_db()
    session = SessionLocal()
    inserted = updated = 0
    errors = []
    try:
        with Path(path).open("r", encoding="utf-8-sig", newline="") as fh:
            rows = list(csv.DictReader(fh))
        for i, r in enumerate(rows, 1):
            try:
                c = session.query(Company).filter_by(security_code=str(r.get("security_code") or "").strip().zfill(6)).first()
                if not c:
                    raise ValueError("company not found")
                item = (r.get("item") or "").strip()
                if item not in ITEMS:
                    raise ValueError(f"unknown item {item!r}")
                raw = (r.get("value") or "").replace(",", "").strip()
                v = float(raw) if raw else None
                res = _upsert(session, c.id, None, normalise_date(r.get("reporting_period")), item, v, source,
                              r.get("source_document"), None, None, "CSV_IMPORT",
                              float(r["confidence"]) if r.get("confidence") else None, r.get("value_text"))
                inserted += res == "inserted"
                updated += res == "updated"
                session.flush()
            except Exception as exc:
                errors.append({"row": i, "error": str(exc)})
        session.commit()
        return {"inserted": inserted, "updated": updated, "errors": errors}
    finally:
        session.close()


def import_esg_ratings_csv(path: str, source: str = "CSV_IMPORT") -> dict:
    """Columns: security_code, provider, rating_date, rating, score,
    pillar_e, pillar_s, pillar_g. Ratings are licensed data; the provider's
    own scale is kept as given."""
    init_db()
    session = SessionLocal()
    inserted = updated = 0
    errors = []
    try:
        with Path(path).open("r", encoding="utf-8-sig", newline="") as fh:
            rows = list(csv.DictReader(fh))
        for i, r in enumerate(rows, 1):
            try:
                c = session.query(Company).filter_by(security_code=str(r.get("security_code") or "").strip().zfill(6)).first()
                if not c:
                    raise ValueError("company not found")
                prov, d = (r.get("provider") or "").strip(), normalise_date(r.get("rating_date"))
                if not prov or not d:
                    raise ValueError("provider and rating_date are required")
                row = session.query(EsgRating).filter_by(company_id=c.id, provider=prov, rating_date=d, source=source).one_or_none()
                if row is None:
                    row = EsgRating(company_id=c.id, provider=prov, rating_date=d, source=source)
                    session.add(row)
                    inserted += 1
                else:
                    updated += 1
                num = lambda k: float(r[k]) if r.get(k) not in (None, "") else None
                row.rating, row.score = (r.get("rating") or None), num("score")
                row.pillar_e, row.pillar_s, row.pillar_g = num("pillar_e"), num("pillar_s"), num("pillar_g")
                row.source_document = r.get("source_document")
                session.flush()
            except Exception as exc:
                errors.append({"row": i, "error": str(exc)})
        session.commit()
        return {"inserted": inserted, "updated": updated, "errors": errors}
    finally:
        session.close()


def _published(session, row):
    if row.disclosure_id:
        d = session.get(Disclosure, row.disclosure_id)
        return (d.announcement_date if d else None) or row.reporting_period
    return row.reporting_period


def _mandate(security_code, year):
    if not year:
        return None
    try:
        from .security_master import sustainability_mandate
        return sustainability_mandate(security_code, int(year))
    except Exception as exc:  # informative only
        return {"mandatory": None, "basis": repr(exc)}


def esg_profile(security_code: str, year: int | None = None, as_of: str | None = None) -> dict:
    """E, S and G information for one fiscal year, as known at ``as_of``."""
    from .human_capital import human_capital
    from .management import governance
    from .models import ManagementObservation, ManagementEvent
    init_db()
    session = SessionLocal()
    try:
        c = session.query(Company).filter_by(security_code=str(security_code).zfill(6)).first()
        if not c:
            return {"error": "company not found"}
        from .review import reviewed_rows
        obs = reviewed_rows(session, "esg_observations",
                            [o for o in session.query(EsgObservation).filter_by(company_id=c.id)
                             if not as_of or _published(session, o) <= as_of])
        years = sorted({int(o.reporting_period[:4]) for o in obs})
        year = year or (years[-1] if years else (int(as_of[:4]) - 1 if as_of else None))
        period = f"{year}-12-31" if year else None
        values = {}
        for o in obs:
            if o.reporting_period == period:
                cur = values.get(o.item)
                if cur is None or _published(session, o) > cur["published"]:
                    values[o.item] = {"value": o.value, "unit": o.unit, "page": o.source_page,
                                      "method": o.extraction_method, "published": _published(session, o),
                                      "text": o.value_text}
        regs = [e for e in session.query(RegulatoryEvent).filter_by(company_id=c.id)
                if (not as_of or (e.event_date or e.announcement_date or "") <= as_of)
                and year and (e.event_date or e.announcement_date or "")[:4] == str(year)]
        env_actions = [e for e in regs if e.authority == "ENVIRONMENT"]
        other_reg = [e for e in regs if e.authority in ("TAX", "MARKET_REGULATION", "SAFETY")]
        sec_actions = [e for e in regs if e.legal_classification in (
            "ADMINISTRATIVE_PENALTY", "ADMINISTRATIVE_SUPERVISORY_MEASURE", "SELF_REGULATORY_DISCIPLINARY",
            "SELF_REGULATORY_MEASURE") and e.authority not in ("ENVIRONMENT", "TAX", "MARKET_REGULATION", "SAFETY")]
        audit = [e for e in regs if e.event_type == "AUDIT_OPINION" and e.event_subtype
                 and "STANDARD_UNQUALIFIED" not in e.event_subtype and not e.event_subtype.endswith("UNSPECIFIED")]
        ratings = defaultdict(list)
        for r in session.query(EsgRating).filter_by(company_id=c.id):
            if not as_of or r.rating_date <= as_of:
                ratings[r.provider].append(r)
        latest_ratings = {p: {"date": rs[-1].rating_date, "rating": rs[-1].rating, "score": rs[-1].score}
                          for p, rs in ((p, sorted(rs, key=lambda x: x.rating_date)) for p, rs in ratings.items())}
        has_mgmt = session.query(ManagementObservation).filter_by(company_id=c.id).count() + \
            session.query(ManagementEvent).filter_by(company_id=c.id).count()
    finally:
        session.close()
    hc = human_capital(security_code, period, as_of) if period else {"values": {}, "derived": {}}
    gov = governance(security_code, as_of or (f"{year + 1}-04-30" if year else None)) if has_mgmt else None
    pick = lambda *ks: {k: values[k] for k in ks if k in values}
    return {
        "code": str(security_code).zfill(6), "year": year, "as_of": as_of,
        "environmental": {
            **pick("key_pollutant_discharge_unit", "emission_cod", "emission_ammonia_nitrogen", "emission_so2",
                   "emission_nox", "emission_particulates", "ghg_emissions", "ghg_reduction", "environmental_investment"),
            "environmental_regulatory_actions": [{"date": e.event_date, "authority": e.authority_name,
                                                  "type": e.event_type, "fine": e.fine_amount_total} for e in env_actions],
        },
        "social": {
            **pick("donations", "rural_revitalisation"),
            "employees": hc.get("values", {}).get("employees_total"),
            "rd_staff_share": hc.get("derived", {}).get("rd_staff_share"),
            "female_directors": gov.get("female_directors") if gov else None,
            "other_regulatory_actions": [{"date": e.event_date, "authority": e.authority_name, "type": e.event_type}
                                         for e in other_reg],
        },
        "governance": {
            "board_size": gov.get("board_size") if gov else None,
            "independence_ratio": gov.get("independence_ratio") if gov else None,
            "ceo_duality": gov.get("ceo_duality") if gov else None,
            "securities_regulatory_actions": len(sec_actions),
            "non_standard_audit_opinions": [e.event_subtype for e in audit],
        },
        "reporting": {
            "sustainability_report_published": bool(values.get("sustainability_report_published")),
            "sustainability_report_title": (values.get("sustainability_report_published") or {}).get("text"),
            # v1.6: whether index membership made the report mandatory for the year
            "mandate": _mandate(security_code, year),
        },
        "ratings": latest_ratings,
        "notes": [
            "No composite ESG score is computed: weighting would be a judgement, not an observation.",
            "Under the exchanges' 2024 self-regulatory guidelines on sustainability reporting, certain index "
            "constituents and dual-listed companies must publish sustainability reports, starting with the 2025 "
            "reporting year; other companies report voluntarily. Check the guidelines for the current scope.",
        ],
    }
