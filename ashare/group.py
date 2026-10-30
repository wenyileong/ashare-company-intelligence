"""v1.2 subsidiaries and group structure.

Sources in the annual report:

* 在其他主体中的权益 → 企业集团的构成 (notes to the financial statements):
  subsidiary name, principal place of business, place of registration,
  business nature, direct and indirect shareholding, acquisition method;
* 主要控股参股公司分析 (management discussion): company type (subsidiary or
  participating company), main business, registered capital, total assets,
  net assets, revenue, net profit.

Both are parsed heuristically (each row keeps its page and raw text) and
merged by entity name; an authorised CSV can be imported instead.

Derived: group-structure summary (by relationship and jurisdiction,
wholly-owned count, offshore entities) and changes in the consolidation
scope between two reporting dates.
"""
from __future__ import annotations

import csv
import re
from collections import Counter
from pathlib import Path

from .evaluation import calibrated_confidence  # noqa: F401
from .parsers import PARSERS, dual_run, record_confidence, extraction_note, tally_dual
from .timeutil import utcnow
from .models import SessionLocal, Company, Disclosure, SubsidiaryObservation, init_db
from .places import jurisdiction_class
from .units import first_declared
from .ownership import normalise_date

_ENTITY_END = (r"(?:有限责任公司|股份有限公司|有限公司|集团公司|公司|合伙企业(?:\(有限合伙\)|（有限合伙）)?|"
               r"Limited|Ltd\.?|LIMITED|Inc\.?|LLC|Corporation|Corp\.?|GmbH|AG|S\.A\.|B\.V\.|PTE\.? LTD\.?|Pte\.? Ltd\.?|株式会社)")
ENTITY = re.compile(r"^(.{2,80}?" + _ENTITY_END + r")(?=\s)")
ACQUISITION = (("ESTABLISHED", ("设立", "投资设立", "新设")),
               ("BUSINESS_COMBINATION_COMMON_CONTROL", ("同一控制下企业合并", "同一控制下")),
               ("BUSINESS_COMBINATION_NOT_COMMON_CONTROL", ("非同一控制下企业合并", "非同一控制下")),
               ("OTHER", ("其他", "划转", "受让")))
RELATIONSHIPS = {"子公司": "SUBSIDIARY", "全资子公司": "SUBSIDIARY", "控股子公司": "SUBSIDIARY",
                 "参股公司": "ASSOCIATE", "联营企业": "ASSOCIATE", "合营企业": "JOINT_VENTURE"}


def _pct(tok: str) -> float | None:
    tok = tok.strip().rstrip("%")
    if tok in ("-", "－", "—", ""):
        return None
    try:
        return float(tok)
    except ValueError:
        return None


def _acq(text: str) -> str | None:
    # 非同一控制 must be tested before 同一控制
    for code, terms in (ACQUISITION[2], ACQUISITION[1], ACQUISITION[0], ACQUISITION[3]):
        if any(t in text for t in terms):
            return code
    return None


def _unit_mult(text: str) -> float:
    declared = first_declared(text)
    return declared[1] if declared else 1.0


def parse_group_pages(pages: list[str]) -> list[dict]:
    """Parse 企业集团的构成 and 主要控股参股公司分析 rows."""
    found: dict[str, dict] = {}
    for pno, page in enumerate(pages, start=1):
        composition = bool(re.search(r"企业集团的构成|在子公司中的权益", page))
        major = bool(re.search(r"主要控股参股公司", page))
        if not (composition or major):
            continue
        mult = _unit_mult(page)
        section = "composition" if composition else "major"
        for raw in page.splitlines():
            line = raw.replace("　", " ").strip()
            declared = first_declared(line)
            if declared:
                mult = declared[1]
            if re.search(r"主要控股参股公司", line):
                section = "major"
            elif re.search(r"企业集团的构成|在子公司中的权益", line):
                section = "composition"
            m = ENTITY.match(line)
            if not m:
                continue
            name = m.group(1).strip()
            rest = line[m.end():].split()
            if not rest:
                continue
            rec = found.setdefault(name, {"entity_name": name, "page": pno, "raw": line})
            if section == "composition":
                # place(s), nature, direct %, [indirect %], acquisition
                nums = [i for i, t in enumerate(rest) if re.fullmatch(r"\d+(?:\.\d+)?%?|[-－—]", t)]
                if not nums:
                    continue
                first = nums[0]
                words = rest[:first]
                pcts = [rest[i] for i in nums]
                tail = " ".join(rest[nums[-1] + 1:])
                if len(words) >= 3:
                    rec["principal_place"], rec["registered_place"], rec["business_nature"] = words[0], words[1], " ".join(words[2:])
                elif len(words) == 2:
                    rec["principal_place"], rec["business_nature"] = words[0], words[1]
                    rec["registered_place"] = words[0]
                elif words:
                    rec["principal_place"] = words[0]
                direct = _pct(pcts[0])
                indirect = _pct(pcts[1]) if len(pcts) > 1 else None
                rec["direct_pct"], rec["indirect_pct"] = direct, indirect
                rec["total_pct"] = (direct or 0) + (indirect or 0) if (direct is not None or indirect is not None) else None
                rec["acquisition_method"] = _acq(tail)
                rec["relationship"] = rec.get("relationship") or "SUBSIDIARY"
                rec["consolidated"] = True
                rec["raw"] = line
                rec["page"] = pno
            else:
                rel = next((RELATIONSHIPS[t] for t in rest[:2] if t in RELATIONSHIPS), None)
                nums = [float(t.replace(",", "")) for t in rest if re.fullmatch(r"-?\d[\d,]*(?:\.\d+)?", t)]
                if rel is None or len(nums) < 4:
                    continue
                rec["relationship"] = rel
                if rel == "SUBSIDIARY":
                    rec.setdefault("consolidated", True)
                elif rel in ("ASSOCIATE", "JOINT_VENTURE"):
                    rec.setdefault("consolidated", False)
                words = [t for t in rest if not re.fullmatch(r"-?\d[\d,]*(?:\.\d+)?", t) and t not in RELATIONSHIPS]
                if words and not rec.get("business_nature"):
                    rec["business_nature"] = " ".join(words)
                # registered capital, total assets, net assets, revenue, [operating profit], net profit
                rec["registered_capital"] = nums[0] * mult
                rec["total_assets"] = nums[1] * mult
                rec["net_assets"] = nums[2] * mult
                rec["revenue"] = nums[3] * mult if len(nums) >= 5 else None
                rec["net_profit"] = nums[-1] * mult
                rec.setdefault("raw", line)
    for rec in found.values():
        rec["jurisdiction_class"] = jurisdiction_class(rec.get("registered_place"), rec.get("principal_place")) \
            or jurisdiction_class(rec["entity_name"])
    return list(found.values())


_FIELDS = ("relationship", "principal_place", "registered_place", "jurisdiction_class", "business_nature",
           "direct_pct", "indirect_pct", "total_pct", "acquisition_method", "consolidated", "registered_capital",
           "total_assets", "net_assets", "revenue", "net_profit")


def parse_subsidiaries_job(job: dict, reader):
    """The reading half of :func:`extract_subsidiaries` (v2.1: run in worker processes)."""
    rows, info = dual_run("subsidiaries", Path(job["path"]), {"title": job["title"]}, reader=reader,
                          sections=["subsidiaries"])
    info.pop("secondary_rows", None)
    return rows, info


def extract_subsidiaries(security_code: str | None = None, again: bool = False, progress=None) -> dict:
    """Subsidiaries and associates from annual and interim reports (v2.0.8: targeted pages, progress, resume)."""
    from .extractstate import run
    init_db()
    session = SessionLocal()
    totals = {"reports": 0, "entities": 0, "inserted": 0, "updated": 0, "errors": []}
    try:
        q = session.query(Disclosure, Company).join(Company, Disclosure.company_id == Company.id).filter(
            Disclosure.kind.in_(("annual_report", "interim_report")), Disclosure.local_path.isnot(None))
        if security_code:
            q = q.filter(Company.security_code == str(security_code).zfill(6))

        def handle(d, c, res):
            m = re.search(r"(20\d{2})\s*年", d.title_cn or "")
            if not m:
                return None
            obs_date = f"{m.group(1)}-06-30" if "半年" in (d.title_cn or "") else f"{m.group(1)}-12-31"
            rows, info = res
            tally_dual(totals, info, d.id)
            totals["reports"] += 1
            for r in rows:
                totals["entities"] += 1
                row = session.query(SubsidiaryObservation).filter_by(
                    company_id=c.id, observation_date=obs_date, entity_name=r["entity_name"],
                    source=d.source or "CNINFO").one_or_none()
                if row is None:
                    row = SubsidiaryObservation(company_id=c.id, observation_date=obs_date,
                                                entity_name=r["entity_name"], source=d.source or "CNINFO",
                                                extraction_method="PDF_TABLE_HEURISTIC")
                    session.add(row)
                    totals["inserted"] += 1
                else:
                    totals["updated"] += 1
                for k in _FIELDS:
                    setattr(row, k, r.get(k))
                row.disclosure_id, row.source_document = d.id, d.local_path or d.document_url
                row.source_page, row.raw_value = r.get("page"), r.get("raw")
                row.extraction_method = PARSERS[r["_variant"]].method
                row.confidence = record_confidence(r, 0.55)
                row.extraction_note = extraction_note(r)
                row.retrieved_at = utcnow()
            return "READ" if rows else "EMPTY"

        rows = q.order_by(Company.security_code, Disclosure.announcement_date, Disclosure.id).all()
        return run("subsidiaries", rows, handle, totals, again, progress, session,
                   parse="ashare.group:parse_subsidiaries_job")
    finally:
        session.close()


def import_subsidiaries_csv(path: str, source: str = "CSV_IMPORT") -> dict:
    """Columns: security_code, observation_date, entity_name, relationship
    (SUBSIDIARY/ASSOCIATE/JOINT_VENTURE or 子公司/联营企业/合营企业),
    principal_place, registered_place, business_nature, direct_pct,
    indirect_pct, acquisition_method, consolidated, registered_capital,
    total_assets, net_assets, revenue, net_profit."""
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
                name = (r.get("entity_name") or "").strip()
                if not d or not name:
                    raise ValueError("observation_date and entity_name are required")
                row = session.query(SubsidiaryObservation).filter_by(
                    company_id=c.id, observation_date=d, entity_name=name, source=source).one_or_none()
                if row is None:
                    row = SubsidiaryObservation(company_id=c.id, observation_date=d, entity_name=name, source=source,
                                                extraction_method="CSV_IMPORT")
                    session.add(row)
                    inserted += 1
                else:
                    updated += 1
                rel = (r.get("relationship") or "SUBSIDIARY").strip()
                row.relationship = RELATIONSHIPS.get(rel, rel.upper())

                def num(k):
                    v = (r.get(k) or "").replace(",", "").replace("%", "").strip()
                    return float(v) if v not in ("", "-") else None
                row.direct_pct, row.indirect_pct = num("direct_pct"), num("indirect_pct")
                row.total_pct = num("total_pct") if r.get("total_pct") else (
                    (row.direct_pct or 0) + (row.indirect_pct or 0) if (row.direct_pct is not None or row.indirect_pct is not None) else None)
                for k in ("registered_capital", "total_assets", "net_assets", "revenue", "net_profit"):
                    setattr(row, k, num(k))
                row.principal_place, row.registered_place = r.get("principal_place"), r.get("registered_place")
                row.business_nature = r.get("business_nature")
                row.acquisition_method = _acq(r.get("acquisition_method") or "") or (r.get("acquisition_method") or None)
                cons = (r.get("consolidated") or "").strip().lower()
                row.consolidated = True if cons in ("1", "true", "yes", "是") else (False if cons in ("0", "false", "no", "否")
                                                                                   else row.relationship == "SUBSIDIARY")
                row.jurisdiction_class = jurisdiction_class(row.registered_place, row.principal_place) or jurisdiction_class(name)
                row.source_document = r.get("source_document")
                row.confidence = float(r["confidence"]) if r.get("confidence") else None
                session.flush()
            except Exception as exc:
                errors.append({"row": i, "error": str(exc)})
        session.commit()
        return {"inserted": inserted, "updated": updated, "errors": errors}
    finally:
        session.close()


def _company(session, code):
    return session.query(Company).filter_by(security_code=str(code).strip().zfill(6)).first()


def _dates(session, company_id, as_of=None):
    dates = sorted({o.observation_date for o in session.query(SubsidiaryObservation).filter_by(company_id=company_id)})
    return [d for d in dates if not as_of or d <= as_of]


def subsidiaries(security_code: str, as_of: str | None = None, date: str | None = None) -> dict:
    """Group structure at one reporting date (default: latest on or before ``as_of``)."""
    init_db()
    session = SessionLocal()
    try:
        c = _company(session, security_code)
        if not c:
            return {"error": "company not found"}
        dates = _dates(session, c.id, as_of)
        date = date or (dates[-1] if dates else None)
        if not date:
            return {"code": c.security_code, "date": None, "entities": []}
        from .review import reviewed_rows
        rows = reviewed_rows(session, "subsidiary_observations",
                             session.query(SubsidiaryObservation).filter_by(company_id=c.id, observation_date=date).all())
        ents = [{"id": r.id, "name": r.entity_name, "relationship": r.relationship, "pct": r.total_pct,
                 "direct": r.direct_pct, "indirect": r.indirect_pct, "jurisdiction": r.jurisdiction_class,
                 "registered": r.registered_place, "business": r.business_nature,
                 "acquired_by": r.acquisition_method, "consolidated": r.consolidated,
                 "net_assets": r.net_assets, "net_profit": r.net_profit}
                for r in sorted(rows, key=lambda r: (r.relationship or "", -(r.total_pct or 0), r.entity_name))]
        subs = [e for e in ents if e["relationship"] == "SUBSIDIARY"]
        summary = {
            "subsidiaries": len(subs),
            "wholly_owned": sum(1 for e in subs if e["pct"] is not None and e["pct"] >= 99.995),
            "associates_and_jvs": sum(1 for e in ents if e["relationship"] in ("ASSOCIATE", "JOINT_VENTURE")),
            "by_jurisdiction": dict(Counter(e["jurisdiction"] or "UNKNOWN" for e in subs)),
            "offshore_entities": [e["name"] for e in ents if e["jurisdiction"] == "OFFSHORE"],
            "consolidated_below_50pct": [e["name"] for e in subs if e["consolidated"] and e["pct"] is not None and e["pct"] < 50],
            "by_acquisition": dict(Counter(e["acquired_by"] or "UNKNOWN" for e in subs)),
        }
        return {"code": c.security_code, "date": date, "as_of": as_of, "summary": summary, "entities": ents,
                "notes": ["Consolidation with 50% or less can rest on control by agreement (for example VIE "
                          "arrangements or acting-in-concert), board control or potential voting rights; it is "
                          "listed for review, not treated as an error."]}
    finally:
        session.close()


def scope_changes(security_code: str, date_from: str | None = None, date_to: str | None = None) -> dict:
    """Entities added to or removed from the group, and stake changes,
    between two reporting dates (default: the last two)."""
    init_db()
    session = SessionLocal()
    try:
        c = _company(session, security_code)
        if not c:
            return {"error": "company not found"}
        dates = _dates(session, c.id)
        if len(dates) < 2 and not (date_from and date_to):
            return {"code": c.security_code, "error": "need subsidiary observations at two dates"}
        date_to = date_to or dates[-1]
        date_from = date_from or max(d for d in dates if d < date_to)

        def snap(d):
            return {r.entity_name: r for r in session.query(SubsidiaryObservation).filter_by(company_id=c.id, observation_date=d)}
        a, b = snap(date_from), snap(date_to)
        added = [{"name": n, "relationship": b[n].relationship, "pct": b[n].total_pct, "acquired_by": b[n].acquisition_method,
                  "jurisdiction": b[n].jurisdiction_class} for n in sorted(set(b) - set(a))]
        removed = [{"name": n, "relationship": a[n].relationship, "pct": a[n].total_pct} for n in sorted(set(a) - set(b))]
        changed = [{"name": n, "from_pct": a[n].total_pct, "to_pct": b[n].total_pct,
                    "from_relationship": a[n].relationship, "to_relationship": b[n].relationship}
                   for n in sorted(set(a) & set(b))
                   if (a[n].total_pct or 0) != (b[n].total_pct or 0) or a[n].relationship != b[n].relationship]
        return {"code": c.security_code, "from": date_from, "to": date_to, "added": added, "removed": removed,
                "stake_or_status_changed": changed,
                "note": "Entities are matched by exact name; a renamed entity appears as removed and added."}
    finally:
        session.close()
