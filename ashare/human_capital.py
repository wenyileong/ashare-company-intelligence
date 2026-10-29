"""v1.3 R&D and human capital.

Sources in the annual report:

* 研发投入 table (management discussion): R&D staff and their share, R&D
  investment and its ratio to revenue, capitalised R&D and its share
  (both the SZSE-style and SSE/STAR-style layouts);
* 员工情况: employees of the parent and principal subsidiaries, total,
  professional composition (production, sales, technical, finance,
  administration) and education (doctorate to below college);
* patents: narrative counts (累计获得授权专利X项，其中发明专利Y项) and the
  STAR-market 知识产权列表 table.

Every value keeps its label, page and raw line. Percentages are stored as
fractions; money in yuan; people and patents as counts.
"""
from __future__ import annotations

import csv
import re
from pathlib import Path

from .evaluation import calibrated_confidence  # noqa: F401
from .parsers import PARSERS, dual_run, record_confidence, extraction_note, tally_dual
from .timeutil import utcnow
from .models import SessionLocal, Company, Disclosure, FinancialFact, HumanCapitalObservation, init_db
from .ownership import normalise_date

#: item code -> (category, unit, Chinese description)
ITEMS = {
    "rd_staff": ("RD", "PERSON", "研发人员数量"),
    "rd_staff_ratio": ("RD", "RATIO", "研发人员数量占比"),
    "rd_investment": ("RD", "CNY", "研发投入金额"),
    "rd_expensed": ("RD", "CNY", "费用化研发投入"),
    "rd_capitalised": ("RD", "CNY", "资本化研发投入"),
    "rd_ratio": ("RD", "RATIO", "研发投入占营业收入比例"),
    "rd_capitalised_ratio": ("RD", "RATIO", "资本化研发投入占研发投入的比例"),
    "employees_parent": ("WORKFORCE", "PERSON", "母公司在职员工的数量"),
    "employees_subsidiaries": ("WORKFORCE", "PERSON", "主要子公司在职员工的数量"),
    "employees_total": ("WORKFORCE", "PERSON", "在职员工的数量合计"),
    "retirees_borne": ("WORKFORCE", "PERSON", "需承担费用的离退休职工人数"),
    "staff_production": ("WORKFORCE", "PERSON", "生产人员"),
    "staff_sales": ("WORKFORCE", "PERSON", "销售人员"),
    "staff_technical": ("WORKFORCE", "PERSON", "技术人员"),
    "staff_rd": ("WORKFORCE", "PERSON", "研发人员"),
    "staff_finance": ("WORKFORCE", "PERSON", "财务人员"),
    "staff_admin": ("WORKFORCE", "PERSON", "行政/管理人员"),
    "staff_other": ("WORKFORCE", "PERSON", "其他人员"),
    "staff_total": ("WORKFORCE", "PERSON", "专业构成合计"),
    "edu_doctorate": ("EDUCATION", "PERSON", "博士"),
    "edu_master": ("EDUCATION", "PERSON", "硕士"),
    "edu_postgraduate": ("EDUCATION", "PERSON", "研究生及以上"),
    "edu_bachelor": ("EDUCATION", "PERSON", "本科"),
    "edu_college": ("EDUCATION", "PERSON", "大专"),
    "edu_below_college": ("EDUCATION", "PERSON", "大专以下"),
    "edu_total": ("EDUCATION", "PERSON", "教育程度合计"),
    "patents_granted_cum": ("PATENT", "COUNT", "累计获得授权专利"),
    "invention_patents_granted_cum": ("PATENT", "COUNT", "累计获得发明专利"),
    "invention_patents_applied_year": ("PATENT", "COUNT", "发明专利本年新增申请"),
    "invention_patents_granted_year": ("PATENT", "COUNT", "发明专利本年新增获得"),
    "invention_patents_applied_cum": ("PATENT", "COUNT", "发明专利累计申请"),
}

# Labels for the R&D table (both layouts). First matching pattern wins per line.
RD_LABELS = (
    ("rd_capitalised_ratio", r"(资本化研发投入占研发投入的比例|研发投入资本化的比重)"),
    ("rd_capitalised", r"(研发投入资本化的金额|本期资本化研发投入|资本化研发投入)(?!占)"),
    ("rd_expensed", r"(本期费用化研发投入|费用化研发投入)"),
    ("rd_ratio", r"(研发投入(?:总额)?占营业收入(?:的)?比例|研发投入占营业收入比重)"),
    ("rd_staff_ratio", r"(研发人员数量占比|研发人员数量占公司总人数的比例|研发人员占比)"),
    ("rd_staff", r"(研发人员数量|公司研发人员的数量|研发人员人数)(?!占)"),
    ("rd_investment", r"(研发投入金额|研发投入合计|研发投入总额)(?!占)"),
)
WORKFORCE_LABELS = (
    ("employees_parent", r"母公司在职员工的数量"),
    ("employees_subsidiaries", r"主要子公司在职员工的数量"),
    ("employees_total", r"在职员工的数量合计"),
    ("retirees_borne", r"需承担费用的离退休职工人数"),
)
COMPOSITION = (("staff_production", r"生产人员"), ("staff_sales", r"销售人员"), ("staff_technical", r"技术人员"),
               ("staff_rd", r"研发人员"), ("staff_finance", r"财务人员"), ("staff_admin", r"(行政人员|管理人员|行政管理人员)"),
               ("staff_other", r"其他(?:人员)?"), ("staff_total", r"合计"))
EDUCATION = (("edu_doctorate", r"博士(?:研究生)?(?:及以上)?"), ("edu_master", r"硕士(?:研究生)?"),
             ("edu_postgraduate", r"研究生(?:及以上)?"), ("edu_bachelor", r"(?:大学)?本科"),
             ("edu_below_college", r"(大专以下|大专及以下|专科以下|中专及以下|高中及以下|其他)"),
             ("edu_college", r"(大专|专科)"), ("edu_total", r"合计"))

from .units import first_declared, last_declared

_NUM = r"(-?\d[\d,]*(?:\.\d+)?)\s*(%)?"


def _unit_mult(label: str, page: str, before: str | None = None) -> float:
    if "万元" in label:
        return 1e4
    if "亿元" in label:
        return 1e8
    if "（元）" in label or "(元)" in label:
        return 1.0
    declared = last_declared(before) if before else None
    declared = declared or first_declared(page)
    return declared[1] if declared else 1.0


def parse_human_capital_pages(pages: list[str]) -> list[dict]:
    out: dict[str, dict] = {}

    def put(item, value, label, page, raw, conf=0.6):
        if item not in out and value is not None:
            out[item] = {"item": item, "value": value, "label": label, "page": page, "raw": raw.strip(),
                         "confidence": conf}

    for pno, page in enumerate(pages, start=1):
        mode = None
        before = ""
        for raw in page.splitlines():
            before += raw + "\n"
            line = raw.replace("　", " ").strip()
            if not line:
                continue
            if re.search(r"专业构成(?:类别)?", line):
                mode = "composition"
                continue
            if re.search(r"教育程度(?:类别)?", line):
                mode = "education"
                continue
            # R&D table
            for item, pat in RD_LABELS:
                m = re.search(pat, line)
                if m:
                    rest = line[m.end():]
                    # only a unit in brackets may separate label and value, so that
                    # narrative such as "研发投入金额同比增长11%" is not read as a value
                    n = re.match(r"^\s*(?:[（(][^）)]{0,8}[）)])?\s*" + _NUM, rest)
                    if n:
                        v = float(n.group(1).replace(",", ""))
                        if ITEMS[item][1] == "RATIO":
                            v = v / 100
                        elif ITEMS[item][1] == "CNY":
                            v = v * _unit_mult(line[:m.end() + 6], page, before)
                        put(item, v, m.group(0), pno, line)
                    break
            # workforce totals
            for item, pat in WORKFORCE_LABELS:
                m = re.search(pat, line)
                if m:
                    n = re.search(r"(\d[\d,]*)", line[m.end():])
                    if n:
                        put(item, float(n.group(1).replace(",", "")), m.group(0), pno, line)
            # composition / education rows: "<label> <count>" (sometimes "<label> <count> <share>")
            if mode in ("composition", "education"):
                table = COMPOSITION if mode == "composition" else EDUCATION
                m = re.match(r"^([一-鿿（）()及以上下]{2,12})\s+(\d[\d,]*)\s*(?:\d+(?:\.\d+)?%?)?\s*$", line)
                if m:
                    label = m.group(1)
                    for item, pat in table:
                        if re.fullmatch(pat, label):
                            put(item, float(m.group(2).replace(",", "")), label, pno, line)
                            break
                    if table is EDUCATION and re.fullmatch(r"合计", label):
                        mode = None
                    if table is COMPOSITION and re.fullmatch(r"合计", label):
                        mode = None
        # patents (narrative)
        flat = re.sub(r"\s+", "", page)
        m = re.search(r"累计(?:获得|取得)?(?:授权)?(?:的)?专利(?:权)?(?:共)?(\d[\d,]*)项", flat)
        if m:
            put("patents_granted_cum", float(m.group(1).replace(",", "")), "累计获得授权专利", pno, m.group(0), 0.55)
            n = re.search(r"其中(?:授权)?发明专利(\d[\d,]*)项", flat[m.end():m.end() + 40])
            if n:
                put("invention_patents_granted_cum", float(n.group(1).replace(",", "")), "其中发明专利", pno, n.group(0), 0.55)
        # STAR-market intellectual property table: 发明专利 new-applied new-granted cum-applied cum-granted
        if "知识产权" in page:
            for raw in page.splitlines():
                mm = re.match(r"^\s*发明专利\s+(\d[\d,]*)\s+(\d[\d,]*)\s+(\d[\d,]*)\s+(\d[\d,]*)\s*$", raw)
                if mm:
                    vals = [float(x.replace(",", "")) for x in mm.groups()]
                    for item, v in zip(("invention_patents_applied_year", "invention_patents_granted_year",
                                        "invention_patents_applied_cum", "invention_patents_granted_cum"), vals):
                        put(item, v, "知识产权列表: 发明专利", pno, raw, 0.6)
    return list(out.values())


def _period(d: Disclosure) -> str | None:
    m = re.search(r"(20\d{2})\s*年", d.title_cn or "")
    if not m:
        return None
    return f"{m.group(1)}-06-30" if "半年" in (d.title_cn or "") else f"{m.group(1)}-12-31"


def extract_human_capital(security_code: str | None = None, again: bool = False, progress=None) -> dict:
    """R&D, workforce and patents from annual and interim reports (v2.0.8: targeted pages, progress, resume)."""
    from .extractstate import run
    init_db()
    session = SessionLocal()
    totals = {"reports": 0, "values": 0, "inserted": 0, "updated": 0, "errors": []}
    try:
        q = session.query(Disclosure, Company).join(Company, Disclosure.company_id == Company.id).filter(
            Disclosure.kind.in_(("annual_report", "interim_report")), Disclosure.local_path.isnot(None))
        if security_code:
            q = q.filter(Company.security_code == str(security_code).zfill(6))

        def handle(d, c, reader):
            path, period = Path(d.local_path), _period(d)
            if not period:
                return None
            vals, info = dual_run("human_capital", path, {"title": d.title_cn}, reader=reader,
                                  sections=["human_capital"])
            tally_dual(totals, info, d.id)
            totals["reports"] += 1
            for v in vals:
                totals["values"] += 1
                totals[_upsert(session, c.id, d.id, period, v["item"], v["value"], d.source or "CNINFO",
                               d.local_path or d.document_url, v["page"], v["raw"], v["label"],
                               PARSERS[v["_variant"]].method, record_confidence(v, v["confidence"]),
                               extraction_note(v))] += 1
            return "READ" if vals else "EMPTY"

        rows = q.order_by(Company.security_code, Disclosure.announcement_date, Disclosure.id).all()
        return run("human_capital", rows, handle, totals, again, progress, session)
    finally:
        session.close()


def _upsert(session, company_id, disclosure_id, period, item, value, source, doc, page, raw, label, method, conf,
            note=None):
    row = session.query(HumanCapitalObservation).filter_by(
        company_id=company_id, reporting_period=period, item=item, source=source, disclosure_id=disclosure_id).one_or_none()
    created = row is None
    if created:
        row = HumanCapitalObservation(company_id=company_id, reporting_period=period, item=item, source=source,
                                      disclosure_id=disclosure_id, category=ITEMS[item][0], extraction_method=method)
        session.add(row)
    row.value, row.unit, row.label_cn = value, ITEMS[item][1], label
    row.source_document, row.source_page, row.raw_value = doc, page, raw
    row.extraction_method, row.confidence, row.retrieved_at = method, conf, utcnow()
    row.extraction_note = note
    return "inserted" if created else "updated"


def import_human_capital_csv(path: str, source: str = "CSV_IMPORT") -> dict:
    """Long format: security_code, reporting_period, item, value. Ratios may be
    given as fractions or with a % sign."""
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
                v = float(raw.rstrip("%")) / 100 if raw.endswith("%") else float(raw)
                res = _upsert(session, c.id, None, normalise_date(r.get("reporting_period")), item, v, source,
                              r.get("source_document"), None, None, ITEMS[item][2], "CSV_IMPORT",
                              float(r["confidence"]) if r.get("confidence") else None)
                inserted += res == "inserted"
                updated += res == "updated"
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


def human_capital(security_code: str, period: str | None = None, as_of: str | None = None) -> dict:
    """R&D and workforce for one period, with derived ratios."""
    init_db()
    session = SessionLocal()
    try:
        c = session.query(Company).filter_by(security_code=str(security_code).zfill(6)).first()
        if not c:
            return {"error": "company not found"}
        from .review import reviewed_rows
        rows = reviewed_rows(session, "human_capital_observations",
                             [r for r in session.query(HumanCapitalObservation).filter_by(company_id=c.id)
                              if not as_of or _published(session, r) <= as_of])
        if not rows:
            return {"code": c.security_code, "period": None, "values": {}}
        period = period or max(r.reporting_period for r in rows if r.reporting_period.endswith("12-31")) \
            if any(r.reporting_period.endswith("12-31") for r in rows) else max(r.reporting_period for r in rows)
        latest = {}
        for r in rows:
            if r.reporting_period == period and (r.item not in latest or _published(session, r) > _published(session, latest[r.item])):
                latest[r.item] = r
        v = {k: r.value for k, r in latest.items()}
        rev = None
        for f in session.query(FinancialFact).filter_by(company_id=c.id, metric="revenue", reporting_period=period):
            if f.value and f.extraction_method != "XBRL_COMPARATIVE" and (f.consolidation_scope in (None, "CONSOLIDATED_DEFAULT")):
                rev = f.value
        emp = v.get("employees_total") or v.get("staff_total")
        derived = {
            "rd_intensity_reported": v.get("rd_ratio"),
            "rd_intensity_computed": (v["rd_investment"] / rev) if v.get("rd_investment") and rev else None,
            "rd_capitalisation_share": v.get("rd_capitalised_ratio") or (
                v["rd_capitalised"] / v["rd_investment"] if v.get("rd_capitalised") is not None and v.get("rd_investment") else None),
            "rd_staff_share": v.get("rd_staff_ratio") or (v["rd_staff"] / emp if v.get("rd_staff") and emp else None),
            "technical_staff_share": ((v.get("staff_technical") or 0) + (v.get("staff_rd") or 0)) / emp
            if emp and (v.get("staff_technical") or v.get("staff_rd")) else None,
            "postgraduate_share": ((v.get("edu_doctorate") or 0) + (v.get("edu_master") or 0) + (v.get("edu_postgraduate") or 0)) / emp
            if emp and (v.get("edu_doctorate") or v.get("edu_master") or v.get("edu_postgraduate")) else None,
            "degree_share": ((v.get("edu_doctorate") or 0) + (v.get("edu_master") or 0) + (v.get("edu_postgraduate") or 0)
                             + (v.get("edu_bachelor") or 0)) / emp if emp and v.get("edu_bachelor") else None,
            "revenue_per_employee": rev / emp if rev and emp else None,
            "rd_investment_per_rd_staff": v["rd_investment"] / v["rd_staff"] if v.get("rd_investment") and v.get("rd_staff") else None,
        }
        return {"code": c.security_code, "period": period, "as_of": as_of, "values": v,
                "derived": {k: x for k, x in derived.items() if x is not None},
                "provenance": {k: {"page": r.source_page, "method": r.extraction_method, "label": r.label_cn}
                               for k, r in latest.items()}}
    finally:
        session.close()


def human_capital_history(security_code: str, items: tuple[str, ...] = ("rd_investment", "rd_ratio", "rd_staff",
                                                                          "employees_total", "patents_granted_cum")):
    init_db()
    session = SessionLocal()
    try:
        c = session.query(Company).filter_by(security_code=str(security_code).zfill(6)).first()
        if not c:
            return []
        from .review import reviewed_rows
        rows = reviewed_rows(session, "human_capital_observations",
                             session.query(HumanCapitalObservation).filter(HumanCapitalObservation.company_id == c.id,
                                                                           HumanCapitalObservation.item.in_(items)).all())
        periods = sorted({r.reporting_period for r in rows})
        table = {}
        for r in rows:
            table.setdefault(r.item, {})[r.reporting_period] = r.value
        return [{"item": it, **{p: table.get(it, {}).get(p) for p in periods}} for it in items if it in table]
    finally:
        session.close()
