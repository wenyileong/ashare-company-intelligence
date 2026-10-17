"""v1.1 directors, supervisors and senior management.

Two kinds of observation are kept separately:

* ``management_events``: appointments, elections, resignations, dismissals
  and similar, from company announcements (or an authorised CSV);
* ``management_observations``: who held which role at a reporting date,
  with tenure, shareholdings and remuneration, from the 董事、监事、高级管理
  人员情况 table of annual reports (or an authorised CSV).

``roster_at`` combines them point-in-time; ``governance`` derives research
variables (board size and independence, CEO duality, turnover, tenure, pay).
Names, gender, age and pay of directors and officers are disclosed under
mandatory rules; they are stored only as disclosed, for research use.
"""
from __future__ import annotations

import csv
import hashlib
import re
from datetime import date
from pathlib import Path

from .evaluation import calibrated_confidence  # noqa: F401
from .parsers import PARSERS, dual_run, record_confidence, extraction_note, tally_dual
from .timeutil import utcnow
from .models import (SessionLocal, Company, Disclosure, ManagementEvent, ManagementObservation, init_db)
from .corporate_actions import _clean, parse_cn_date, _DATE, _document_pages, _page_of
from .ownership import normalise_date

# ---------------------------------------------------------------------------
# Roles
# ---------------------------------------------------------------------------

ROLE_PATTERNS = (  # most specific first
    ("INDEPENDENT_DIRECTOR", ("独立董事", "独立非执行董事")),
    ("EMPLOYEE_DIRECTOR", ("职工代表董事", "职工董事")),
    ("VICE_CHAIR", ("副董事长",)),
    ("CHAIR", ("董事长",)),
    ("BOARD_SECRETARY", ("董事会秘书", "董秘")),
    ("SUPERVISOR_CHAIR", ("监事会主席", "监事长")),
    ("EMPLOYEE_SUPERVISOR", ("职工代表监事", "职工监事")),
    ("SUPERVISOR", ("监事",)),
    ("DIRECTOR", ("非独立董事", "执行董事", "董事")),
    ("DEPUTY_GM", ("副总经理", "副总裁")),
    ("GENERAL_MANAGER", ("总经理", "总裁", "首席执行官", "CEO")),
    ("CFO", ("财务总监", "财务负责人", "首席财务官", "总会计师", "CFO")),
    ("CHIEF_ENGINEER", ("总工程师", "首席技术官", "技术总监", "CTO")),
    ("OTHER_EXECUTIVE", ("高级管理人员", "总监", "首席")),
)
BOARD_ROLES = {"CHAIR", "VICE_CHAIR", "DIRECTOR", "INDEPENDENT_DIRECTOR", "EMPLOYEE_DIRECTOR"}
SUPERVISORY_ROLES = {"SUPERVISOR_CHAIR", "SUPERVISOR", "EMPLOYEE_SUPERVISOR"}
EXECUTIVE_ROLES = {"GENERAL_MANAGER", "DEPUTY_GM", "CFO", "BOARD_SECRETARY", "CHIEF_ENGINEER", "OTHER_EXECUTIVE"}
KEY_ROLES = ("CHAIR", "GENERAL_MANAGER", "CFO", "BOARD_SECRETARY")


def classify_role(text: str | None) -> str | None:
    t = (text or "").strip()
    if not t or "证券事务代表" in t:
        return None
    for code, terms in ROLE_PATTERNS:
        if any(term in t for term in terms):
            return code
    return None


def split_roles(text: str | None) -> list[tuple[str, str]]:
    """'董事长兼总经理、董事会秘书' -> [('CHAIR','董事长'), ('GENERAL_MANAGER','总经理'), ...]."""
    out = []
    for part in re.split(r"[、,，;；/兼及和\s]+", text or ""):
        part = part.strip()
        code = classify_role(part)
        if code and len(part) > 12:  # keep only the role words of a long fragment
            part = next(t for c, ts in ROLE_PATTERNS if c == code for t in ts if t in part)
        if code and (code, part) not in out:
            out.append((code, part))
    return out


# ---------------------------------------------------------------------------
# Events from announcements
# ---------------------------------------------------------------------------

def classify_management_title(title: str | None) -> list[str]:
    t = title or ""
    if not t or re.search(r"(年度报告|季度报告|股东大会决议|会议通知|法律意见|候选人声明|提名人声明|履职情况|述职报告)", t):
        return []
    if not any(k in t for k in ("董事", "监事", "总经理", "总裁", "高级管理人员", "财务总监", "财务负责人",
                                "董事会秘书", "首席", "高管")):
        return []
    types = []
    if "辞职" in t or "辞任" in t or "离任" in t or "辞去" in t:
        types.append("RESIGNATION")
    if "聘任" in t or "任命" in t:
        types.append("APPOINTMENT")
    if "选举" in t or "补选" in t:
        types.append("ELECTION")
    if "换届" in t and "ELECTION" not in types:
        types.append("BOARD_RENEWAL")
    if "罢免" in t or "解聘" in t or "免去" in t or "免职" in t:
        types.append("DISMISSAL")
    if "逝世" in t or "去世" in t:
        types.append("DEATH")
    if "留置" in t or "无法履行职责" in t or "被采取" in t:
        types.append("UNABLE_TO_PERFORM")
    return types


_NAME = r"([一-鿿]{1,3}(?:·[一-鿿]{1,6})?[一-鿿]?)"
_HON = r"(?:先生|女士)"

REASONS = (
    ("RETIREMENT", ("退休", "到龄")), ("TERM_EXPIRY", ("任期届满", "届满离任")),
    ("WORK_ARRANGEMENT", ("工作调整", "工作变动", "工作安排", "工作需要")),
    ("HEALTH_REASONS", ("身体原因", "健康原因")), ("PERSONAL", ("个人原因", "家庭原因")),
    ("REGULATORY_INELIGIBILITY", ("不得担任", "任职资格", "市场禁入")),
)


def _reason(text: str) -> tuple[str | None, str | None]:
    m = re.search(r"(?:因|由于)([^，。,]{2,30}?)(?:原因|需要|届满)?[，,]?\s*(?:申请|请求|辞去|辞任)", text)
    raw = m.group(0) if m else None
    for code, terms in REASONS:
        if any(term in text[:600] for term in terms):
            return code, raw
    return (None, raw)


_ROLE_TERMS = sorted({t for _c, ts in ROLE_PATTERNS for t in ts} | {"董事会", "监事会", "高管"}, key=len, reverse=True)
_LEADING_WORDS = ("同意", "聘任", "任命", "选举", "补选", "罢免", "解聘", "免去", "收到", "接到", "公司", "原", "由",
                  "及", "和", "与", "暨", "其中", "现任", "离任", "新任")


def _split_name(run: str) -> str | None:
    """'副总经理张三' -> '张三'; '选举李四' -> '李四'; returns None if no plausible name."""
    cut = 0
    for term in _ROLE_TERMS:
        i = run.rfind(term)
        if i >= 0:
            cut = max(cut, i + len(term))
    name = run[cut:]
    changed = True
    while changed:
        changed = False
        for w in _LEADING_WORDS:
            if name.startswith(w) and len(name) - len(w) >= 2:
                name, changed = name[len(w):], True
    return name if 2 <= len(name.replace("·", "")) <= 4 or "·" in name else None


def parse_management_text(text: str, types: list[str]) -> list[dict]:
    """Extract (person, role, event) records from announcement text.

    Names are found as the CJK run before 先生/女士, with any role words or
    verbs at its start removed; the event and role are read from the clause
    around each name.
    """
    t = _clean(text)
    out, seen = [], set()
    when = None
    m = re.search(r"于\s*" + _DATE + r"\s*(?:收到|接到|召开|审议)", t)
    if m:
        when = parse_cn_date(m.group(1))
    remains = None
    if re.search(r"辞职后(?:仍|将继续|继续)(?:在公司)?(?:担任|任职)", t):
        remains = True
    elif re.search(r"(?:辞职|离任)后(?:将)?不再(?:在公司)?担任任何职务|不再在公司及(?:其)?(?:控股)?子公司担任任何职务", t):
        remains = False
    delayed = bool(re.search(r"(?:将在|在)[^。]{0,40}(?:补选|选举产生新任|新任)[^。]{0,30}(?:之日起|后)生效|"
                             r"低于法定(?:最低)?人数|低于三分之一", t))
    reason, reason_text = _reason(t)

    for m in re.finditer(r"([\u4e00-\u9fff·]{2,14})(?:先生|女士)", t):
        name = _split_name(m.group(1))
        if not name:
            continue
        before = t[max(0, m.start() - 60):m.start() + len(m.group(1)) - len(name)]
        after = t[m.end():m.end() + 80]
        clause_before = re.split(r"[，。；;,]", before)[-1]
        if re.search(r"(?:聘任|任命)$", before) or re.search(r"(?:聘任|任命)\s*$", clause_before[-6:]):
            et = "APPOINTMENT"
        elif re.search(r"(?:选举|补选)\s*$", clause_before[-6:]):
            et = "ELECTION"
        elif re.search(r"(?:罢免|解聘|免去)\s*$", clause_before[-6:]):
            et = "DISMISSAL"
        elif re.search(r"^[^。]{0,40}?(?:辞职|辞任|辞去|离任)", after):
            et = "RESIGNATION"
        else:
            continue
        if et not in types and not (et == "ELECTION" and "BOARD_RENEWAL" in types):
            continue
        role_text = None
        if et in ("APPOINTMENT", "ELECTION"):
            rm = re.match(r"^为(?:公司)?(?:第[一二三四五六七八九十\d]+届(?:董事会|监事会))?([^，。,；;]{2,40}?)(?:[，。,；;]|任期|$)", after)
            role_text = rm.group(1) if rm else None
        elif et == "DISMISSAL":
            rm = re.match(r"^(?:的)?(?:公司)?([^，。,]{2,40}?)(?:职务|[，。,])", after)
            role_text = rm.group(1) if rm else None
        else:
            rm = re.search(r"辞去(?:其所担任的|其担任的|所担任的)?(?:公司)?([^，。,]{2,40}?)(?:职务|等职务|的职务)", after)
            role_text = rm.group(1) if rm else clause_before
        for code, part in split_roles(role_text or ""):
            key = (et, name, code)
            if key in seen:
                continue
            seen.add(key)
            out.append({"event_type": et, "person_name": name, "role": code, "role_cn": part,
                        "event_date": when,
                        "effective_date": (None if delayed else when) if et == "RESIGNATION" else when,
                        "remains_with_company": remains if et == "RESIGNATION" else None,
                        "reason": reason if et == "RESIGNATION" else None,
                        "reason_text": reason_text if et == "RESIGNATION" else None,
                        "raw": t[max(0, m.start() - 30):m.end() + 60]})
    return out


def _event_id(company_id, ann_id, et, name, role, source):
    return hashlib.sha256(f"{company_id}|{ann_id}|{et}|{name}|{role}|{source}".encode()).hexdigest()[:40]


def extract_management_events(security_code: str | None = None, use_documents: bool = True) -> dict:
    init_db()
    session = SessionLocal()
    totals = {"disclosures_scanned": 0, "event_disclosures": 0, "inserted": 0, "updated": 0, "title_only": 0, "errors": []}
    try:
        q = session.query(Disclosure, Company).join(Company, Disclosure.company_id == Company.id)
        if security_code:
            q = q.filter(Company.security_code == str(security_code).zfill(6))
        for d, c in q.order_by(Disclosure.announcement_date).all():
            totals["disclosures_scanned"] += 1
            types = classify_management_title(d.title_cn)
            if not types:
                continue
            try:
                pages = []
                if use_documents and d.local_path and Path(d.local_path).exists():
                    pages = _document_pages(Path(d.local_path))
                text = (d.title_cn or "") + "\n" + "\n".join(pages)
                recs = parse_management_text(text, types) if any(p.strip() for p in pages) else []
                method, conf = "DOCUMENT_TEXT_REGEX", 0.6
                if not recs:
                    # Title-level record: the role is usually in the title; the name often is not.
                    role = classify_role(d.title_cn)
                    m = re.search(r"(?:公司)?(?:" + "|".join(t for _c, ts in ROLE_PATTERNS for t in ts) + r")" + _NAME + r"(?:先生|女士)?(?:辞职|辞任|离任)",
                                  d.title_cn or "")
                    recs = [{"event_type": types[0], "person_name": m.group(1) if m else None, "role": role,
                             "role_cn": None, "event_date": d.announcement_date, "effective_date": None,
                             "reason": None, "reason_text": None, "remains_with_company": None, "raw": d.title_cn}]
                    method, conf = "TITLE_ONLY", 0.3
                    totals["title_only"] += 1
                totals["event_disclosures"] += 1
                for r in recs:
                    eid = _event_id(c.id, d.announcement_id, r["event_type"], r["person_name"], r["role"], d.source or "CNINFO")
                    row = session.query(ManagementEvent).filter_by(event_id=eid).one_or_none()
                    if row is None:
                        row = ManagementEvent(event_id=eid, company_id=c.id, event_type=r["event_type"],
                                              extraction_method=method, source=d.source or "CNINFO")
                        session.add(row)
                        totals["inserted"] += 1
                    else:
                        totals["updated"] += 1
                    for k in ("event_type", "person_name", "role", "role_cn", "effective_date", "reason",
                              "reason_text", "remains_with_company"):
                        setattr(row, k, r.get(k))
                    row.event_date = r.get("event_date") or d.announcement_date
                    row.disclosure_id, row.announcement_date, row.title_cn = d.id, d.announcement_date, d.title_cn
                    row.source_document = d.local_path or d.document_url
                    row.source_page = _page_of(pages, r.get("raw")) if pages else None
                    row.raw_value = r.get("raw")
                    row.extraction_method, row.confidence = method, conf
                    row.retrieved_at = utcnow()
                session.commit()
            except Exception as exc:
                session.rollback()
                totals["errors"].append({"disclosure_id": d.id, "error": repr(exc)})
        return totals
    finally:
        session.close()


# ---------------------------------------------------------------------------
# Roster tables in annual reports
# ---------------------------------------------------------------------------

_TABLE_HEAD = re.compile(r"(董事、监事(?:和|、)?高级管理人员|董事、监事、高级管理人员|现任及报告期内离任董事)")
_ROW = re.compile(
    r"^\s*" + r"([一-鿿]{2,4}(?:·[一-鿿]{1,8})?)" + r"\s+([一-鿿、，,兼（）()]{2,60}?)\s+(男|女)\s+(\d{2})\s+"
    r"(?:(现任|离任)\s+)?"
    r"(\d{4}[年\-/.]\d{1,2}[月\-/.]\d{1,2}日?)?\s*(\d{4}[年\-/.]\d{1,2}[月\-/.]\d{1,2}日?)?(.*)$")


def parse_roster_pages(pages: list[str]) -> list[dict]:
    """Parse rows of the directors/supervisors/officers table (heuristic)."""
    rows = []
    in_table = False
    pay_in_wan = False
    for pno, page in enumerate(pages, start=1):
        if _TABLE_HEAD.search(page):
            in_table = True
            pay_in_wan = pay_in_wan or ("万元" in page)
        if not in_table:
            continue
        for line in page.splitlines():
            m = _ROW.match(line.replace("　", " "))
            if not m:
                continue
            name, roles, gender, age, status, start, end, rest = m.groups()
            if not split_roles(roles):
                continue
            nums = [float(x.replace(",", "")) for x in re.findall(r"-?\d[\d,]*(?:\.\d+)?", rest)]
            related = "是" if re.search(r"\s是\s*$", rest) else ("否" if re.search(r"\s否\s*$", rest) else None)
            pay = nums[-1] if nums else None
            rows.append({
                "person_name": name, "roles": split_roles(roles), "role_text": roles, "gender": gender,
                "age": int(age), "status": {"现任": "SERVING", "离任": "LEFT"}.get(status),
                "tenure_start": parse_cn_date(start.replace(".", "-")) if start else None,
                "tenure_end": parse_cn_date(end.replace(".", "-")) if end else None,
                "shares_start": nums[0] if len(nums) >= 3 else None,
                "shares_end": nums[1] if len(nums) >= 3 else None,
                "remuneration": (pay * 1e4 if pay_in_wan else pay) if pay is not None and len(nums) >= 1 else None,
                "paid_by_related_party": {"是": True, "否": False}.get(related),
                "page": pno, "raw": line.strip(),
            })
        if in_table and re.search(r"(任职情况|董事、监事、高级管理人员报酬情况|公司员工情况|员工情况)", page) and rows:
            # table usually ends before the employment/remuneration narrative
            pass
    return rows


def extract_rosters(security_code: str | None = None) -> dict:
    """Read the officer tables of downloaded annual reports."""
    init_db()
    session = SessionLocal()
    totals = {"reports": 0, "rows": 0, "inserted": 0, "updated": 0, "errors": []}
    try:
        q = session.query(Disclosure, Company).join(Company, Disclosure.company_id == Company.id).filter(
            Disclosure.kind == "annual_report", Disclosure.local_path.isnot(None))
        if security_code:
            q = q.filter(Company.security_code == str(security_code).zfill(6))
        for d, c in q.all():
            try:
                path = Path(d.local_path)
                if not path.exists():
                    continue
                rows, info = dual_run("roster", path, {"title": d.title_cn})
                tally_dual(totals, info, d.id)
                m = re.search(r"(20\d{2})\s*年", d.title_cn or "")
                obs_date = f"{m.group(1)}-12-31" if m else d.announcement_date
                totals["reports"] += 1
                for r in rows:
                    for code, part in r["roles"]:
                        totals["rows"] += 1
                        row = session.query(ManagementObservation).filter_by(
                            company_id=c.id, observation_date=obs_date, person_name=r["person_name"],
                            role=code, source=d.source or "CNINFO").one_or_none()
                        if row is None:
                            row = ManagementObservation(company_id=c.id, observation_date=obs_date,
                                                        person_name=r["person_name"], role=code,
                                                        source=d.source or "CNINFO", extraction_method="PDF_TABLE_HEURISTIC")
                            session.add(row)
                            totals["inserted"] += 1
                        else:
                            totals["updated"] += 1
                        row.role_cn, row.gender, row.age = part, r["gender"], r["age"]
                        row.status, row.tenure_start, row.tenure_end = r["status"], r["tenure_start"], r["tenure_end"]
                        row.shares_start, row.shares_end = r["shares_start"], r["shares_end"]
                        row.remuneration, row.paid_by_related_party = r["remuneration"], r["paid_by_related_party"]
                        row.disclosure_id, row.source_document = d.id, d.local_path or d.document_url
                        row.source_page, row.raw_value = r["page"], r["raw"]
                        row.extraction_method = PARSERS[r["_variant"]].method
                        row.confidence = record_confidence(r, 0.5)
                        row.extraction_note = extraction_note(r)
                        row.retrieved_at = utcnow()
                session.commit()
            except Exception as exc:
                session.rollback()
                totals["errors"].append({"disclosure_id": d.id, "error": repr(exc)})
        return totals
    finally:
        session.close()


# ---------------------------------------------------------------------------
# CSV imports
# ---------------------------------------------------------------------------

def _f(v):
    if v in (None, ""):
        return None
    s = str(v).replace(",", "").strip()
    mult = 1e4 if s.endswith("万") else 1.0
    try:
        return float(s.rstrip("万元").strip()) * mult
    except ValueError:
        return None


def _b(v):
    s = str(v or "").strip().lower()
    return True if s in ("1", "true", "yes", "y", "是") else (False if s in ("0", "false", "no", "n", "否") else None)


def import_management_csv(path: str, source: str = "CSV_IMPORT") -> dict:
    """Roster observations: security_code, observation_date, person_name, role
    (code or Chinese, several separated by 、), gender, age, tenure_start,
    tenure_end, status, shares_start, shares_end, remuneration (yuan)."""
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
                d = normalise_date(r.get("observation_date"))
                name = (r.get("person_name") or "").strip()
                if not d or not name:
                    raise ValueError("observation_date and person_name are required")
                raw_role = (r.get("role") or "").strip()
                roles = [(raw_role.upper(), raw_role)] if raw_role.upper() in BOARD_ROLES | SUPERVISORY_ROLES | EXECUTIVE_ROLES \
                    else split_roles(raw_role)
                if not roles:
                    raise ValueError(f"unrecognised role {raw_role!r}")
                for code, part in roles:
                    row = session.query(ManagementObservation).filter_by(
                        company_id=c.id, observation_date=d, person_name=name, role=code, source=source).one_or_none()
                    if row is None:
                        row = ManagementObservation(company_id=c.id, observation_date=d, person_name=name, role=code,
                                                    source=source, extraction_method="CSV_IMPORT")
                        session.add(row)
                        inserted += 1
                    else:
                        updated += 1
                    row.role_cn = part
                    row.gender = r.get("gender") or None
                    row.age = int(r["age"]) if r.get("age") else None
                    row.tenure_start = normalise_date(r.get("tenure_start"))
                    row.tenure_end = normalise_date(r.get("tenure_end"))
                    row.status = (r.get("status") or "").upper() or None
                    row.shares_start, row.shares_end = _f(r.get("shares_start")), _f(r.get("shares_end"))
                    row.remuneration = _f(r.get("remuneration"))
                    row.paid_by_related_party = _b(r.get("paid_by_related_party"))
                    row.source_document = r.get("source_document")
                    row.extraction_method = r.get("extraction_method") or "CSV_IMPORT"
                    row.confidence = float(r["confidence"]) if r.get("confidence") else None
                    session.flush()
            except Exception as exc:
                errors.append({"row": i, "error": str(exc)})
        session.commit()
        return {"inserted": inserted, "updated": updated, "errors": errors}
    finally:
        session.close()


def import_management_events_csv(path: str, source: str = "CSV_IMPORT") -> dict:
    """Events: security_code, event_type, person_name, role, event_date,
    effective_date, reason, remains_with_company."""
    init_db()
    session = SessionLocal()
    inserted = updated = 0
    errors = []
    types = {"RESIGNATION", "APPOINTMENT", "ELECTION", "BOARD_RENEWAL", "DISMISSAL", "DEATH", "UNABLE_TO_PERFORM"}
    try:
        with Path(path).open("r", encoding="utf-8-sig", newline="") as fh:
            rows = list(csv.DictReader(fh))
        for i, r in enumerate(rows, 1):
            try:
                c = session.query(Company).filter_by(security_code=str(r.get("security_code") or "").strip().zfill(6)).first()
                if not c:
                    raise ValueError("company not found")
                et = (r.get("event_type") or "").strip().upper()
                if et not in types:
                    raise ValueError(f"unknown event_type {et!r}")
                raw_role = (r.get("role") or "").strip()
                role = raw_role.upper() if raw_role.upper() in BOARD_ROLES | SUPERVISORY_ROLES | EXECUTIVE_ROLES else classify_role(raw_role)
                name = (r.get("person_name") or "").strip() or None
                ed = normalise_date(r.get("event_date"))
                eid = _event_id(c.id, r.get("event_key") or ed, et, name, role, source)
                row = session.query(ManagementEvent).filter_by(event_id=eid).one_or_none()
                if row is None:
                    row = ManagementEvent(event_id=eid, company_id=c.id, event_type=et, extraction_method="CSV_IMPORT", source=source)
                    session.add(row)
                    inserted += 1
                else:
                    updated += 1
                row.person_name, row.role, row.role_cn, row.event_date = name, role, raw_role or None, ed
                row.effective_date = normalise_date(r.get("effective_date")) or (ed if et != "RESIGNATION" else None)
                row.reason = (r.get("reason") or "").upper() or None
                row.remains_with_company = _b(r.get("remains_with_company"))
                row.confidence = float(r["confidence"]) if r.get("confidence") else None
                row.source_document = r.get("source_document")
                session.flush()
            except Exception as exc:
                errors.append({"row": i, "error": str(exc)})
        session.commit()
        return {"inserted": inserted, "updated": updated, "errors": errors}
    finally:
        session.close()


# ---------------------------------------------------------------------------
# Point-in-time roster and governance variables
# ---------------------------------------------------------------------------

def _company(session, code):
    return session.query(Company).filter_by(security_code=str(code).strip().zfill(6)).first()


def roster_at(security_code: str, as_of: str | None = None) -> dict:
    """Who held which role at ``as_of``.

    Start from the latest roster observation on or before ``as_of`` (people
    reported as having left are excluded), then apply events dated after
    that observation: effective resignations, dismissals and deaths remove;
    appointments and elections add. Every entry records its basis.
    """
    init_db()
    session = SessionLocal()
    try:
        c = _company(session, security_code)
        if not c:
            return {"error": "company not found"}
        obs = session.query(ManagementObservation).filter(ManagementObservation.company_id == c.id)
        if as_of:
            obs = obs.filter(ManagementObservation.observation_date <= as_of)
        from .review import reviewed_rows
        obs = reviewed_rows(session, "management_observations", obs.all())
        base_date = max((o.observation_date for o in obs), default=None)
        members = {}
        for o in obs:
            if o.observation_date == base_date and o.status != "LEFT":
                members[(o.person_name, o.role)] = {
                    "person": o.person_name, "role": o.role, "role_cn": o.role_cn, "gender": o.gender, "age": o.age,
                    "tenure_start": o.tenure_start, "remuneration": o.remuneration,
                    "basis": f"roster {o.observation_date} ({o.source})"}
        evq = session.query(ManagementEvent).filter(ManagementEvent.company_id == c.id)
        events = sorted(evq.all(), key=lambda e: (e.effective_date or e.event_date or "", e.id))
        pending = []
        for e in events:
            d = e.effective_date or e.event_date
            if not d or (base_date and d <= base_date) or (as_of and d > as_of) or not e.role:
                if e.event_type == "RESIGNATION" and not e.effective_date and e.event_date and \
                        (not base_date or e.event_date > base_date) and (not as_of or e.event_date <= as_of):
                    pending.append({"person": e.person_name, "role": e.role, "since": e.event_date,
                                    "note": "resignation takes effect only when a successor is elected"})
                continue
            key = (e.person_name, e.role)
            if e.event_type in ("RESIGNATION", "DISMISSAL", "DEATH"):
                if e.event_type == "RESIGNATION" and not e.effective_date:
                    pending.append({"person": e.person_name, "role": e.role, "since": e.event_date,
                                    "note": "resignation takes effect only when a successor is elected"})
                    continue
                members.pop(key, None)
                if e.person_name is None:  # name unknown: drop the role holder if unique
                    holders = [k for k in members if k[1] == e.role]
                    if len(holders) == 1:
                        members.pop(holders[0])
            elif e.event_type in ("APPOINTMENT", "ELECTION") and e.person_name:
                members[key] = {"person": e.person_name, "role": e.role, "role_cn": e.role_cn, "gender": None,
                                "age": None, "tenure_start": d, "remuneration": None,
                                "basis": f"{e.event_type.lower()} {d} (event {e.id})"}
        return {"code": c.security_code, "as_of": as_of, "base_roster_date": base_date,
                "members": sorted(members.values(), key=lambda m: (_role_order(m["role"]), m["person"] or "")),
                "pending_resignations": pending}
    finally:
        session.close()


def _role_order(role):
    order = ["CHAIR", "VICE_CHAIR", "DIRECTOR", "EMPLOYEE_DIRECTOR", "INDEPENDENT_DIRECTOR", "SUPERVISOR_CHAIR",
             "SUPERVISOR", "EMPLOYEE_SUPERVISOR", "GENERAL_MANAGER", "DEPUTY_GM", "CFO", "BOARD_SECRETARY",
             "CHIEF_ENGINEER", "OTHER_EXECUTIVE"]
    return order.index(role) if role in order else 99


def _years_between(a: str, b: str) -> float | None:
    try:
        d1, d2 = date.fromisoformat(a), date.fromisoformat(b)
        return (d2 - d1).days / 365.25
    except (TypeError, ValueError):
        return None


def governance(security_code: str, as_of: str | None = None) -> dict:
    """Board and management variables at ``as_of`` with legal reference checks."""
    r = roster_at(security_code, as_of)
    if "error" in r:
        return r
    ref = as_of or utcnow().date().isoformat()
    members = r["members"]
    board = {m["person"] for m in members if m["role"] in BOARD_ROLES}
    indep = {m["person"] for m in members if m["role"] == "INDEPENDENT_DIRECTOR"}
    sup = {m["person"] for m in members if m["role"] in SUPERVISORY_ROLES}
    holders = lambda role: sorted({m["person"] for m in members if m["role"] == role})
    chair, gm = holders("CHAIR"), holders("GENERAL_MANAGER")
    genders = {m["person"]: m["gender"] for m in members if m["role"] in BOARD_ROLES and m["gender"]}
    pay = [m["remuneration"] for m in members if m["remuneration"] is not None]
    long_indep = []
    for m in members:
        if m["role"] == "INDEPENDENT_DIRECTOR" and m["tenure_start"]:
            yrs = _years_between(m["tenure_start"], ref)
            if yrs is not None and yrs > 6:
                long_indep.append({"person": m["person"], "since": m["tenure_start"], "years": round(yrs, 1)})
    # turnover in the 12 months to as_of
    init_db()
    session = SessionLocal()
    try:
        c = _company(session, security_code)
        start = f"{int(ref[:4]) - 1}{ref[4:]}"
        departures = [e for e in session.query(ManagementEvent).filter(
            ManagementEvent.company_id == c.id, ManagementEvent.event_type.in_(("RESIGNATION", "DISMISSAL", "DEATH")))
            if start < (e.event_date or "") <= ref]
    finally:
        session.close()
    turnover = {role: sum(1 for e in departures if e.role == role) for role in KEY_ROLES}
    checks = []
    if board:
        ratio = len(indep) / len(board)
        checks.append({"rule": "Independent directors at least one third of the board",
                       "reference": "上市公司独立董事管理办法 (CSRC, 2023)",
                       "result": "MET" if ratio >= 1 / 3 - 1e-9 else "NOT MET", "value": f"{len(indep)}/{len(board)}"})
    checks.append({"rule": "Independent director tenure not above six consecutive years",
                   "reference": "上市公司独立董事管理办法 (CSRC, 2023)",
                   "result": "MET" if not long_indep else "CHECK", "value": long_indep or None})
    checks.append({"rule": "Board secretary in office", "reference": "公司法 (2023 revision); listing rules",
                   "result": "MET" if holders("BOARD_SECRETARY") else "NOT OBSERVED", "value": holders("BOARD_SECRETARY") or None})
    return {
        "code": r["code"], "as_of": as_of, "base_roster_date": r["base_roster_date"],
        "board_size": len(board), "independent_directors": len(indep),
        "independence_ratio": len(indep) / len(board) if board else None,
        "female_directors": sum(1 for g in genders.values() if g == "女") if genders else None,
        "supervisory_board_size": len(sup),
        "chair": chair, "general_manager": gm, "ceo_duality": bool(set(chair) & set(gm)) if chair and gm else None,
        "cfo": holders("CFO"), "board_secretary": holders("BOARD_SECRETARY"),
        "key_role_departures_12m": turnover, "pending_resignations": r["pending_resignations"],
        "total_disclosed_remuneration": sum(pay) if pay else None,
        "legal_reference_checks": checks,
        "notes": ["Since the Company Law revision effective 1 July 2024, a company may use an audit committee "
                  "of the board instead of a supervisory board; a supervisory board of size 0 is therefore not "
                  "in itself a defect.",
                  "Checks are screening aids against the cited instruments, not legal conclusions."],
    }


def show_management_events(security_code: str):
    init_db()
    session = SessionLocal()
    try:
        c = _company(session, security_code)
        if not c:
            return []
        return (session.query(ManagementEvent).filter_by(company_id=c.id)
                .order_by(ManagementEvent.event_date, ManagementEvent.id).all())
    finally:
        session.close()
