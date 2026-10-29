"""Ownership and control (v1.8, build plan section 18.8).

* Top-10 shareholders and top-10 holders of tradable shares, read from the
  periodic reports' 前十名股东持股情况 tables (plain and layout text, compared).
* Pledge and release announcements (质押 / 解除质押).
* Controlling shareholder and actual controller from 控股股东情况 /
  实际控制人情况, with the ownership type (central SOE, local SOE, private,
  foreign, collective, none) and the basis of the classification.
* Control chains: listed company ← controlling shareholder ← … ← actual
  controller, with percentages where disclosed or imported.
* Entity register (organisations by unified social credit code or normalised
  name) and person register (directors and officers resolved across companies
  by name, gender and birth year), interlocks and common controllers.
"""
from __future__ import annotations

import csv
import json
import re
from collections import defaultdict
from pathlib import Path

from .timeutil import utcnow
from .models import (SessionLocal, init_db, Company, Disclosure, OwnershipObservation, PledgeEvent,
                     ControlObservation, ControlEdge, Entity, EntityAlias, Person, PersonRole,
                     ManagementObservation, SubsidiaryObservation, ReviewItem)
from .corporate_actions import parse_cn_date, _DATE, _clean, _document_pages
from .ownership import normalise_date

NATURES = ("国有法人", "国有股", "国家", "境内非国有法人", "境内一般法人", "境外法人", "境内自然人", "境外自然人",
           "国有独资", "基金、理财产品等", "其他")
NATURE_TYPES = {"国有法人": "STATE_LEGAL_PERSON", "国有股": "STATE", "国家": "STATE", "国有独资": "STATE_LEGAL_PERSON",
                "境内非国有法人": "DOMESTIC_NON_STATE_LEGAL_PERSON", "境内一般法人": "DOMESTIC_NON_STATE_LEGAL_PERSON",
                "境外法人": "FOREIGN_LEGAL_PERSON", "境内自然人": "DOMESTIC_NATURAL_PERSON",
                "境外自然人": "FOREIGN_NATURAL_PERSON", "基金、理财产品等": "FUND_OR_PRODUCT", "其他": "OTHER"}
_NUM = r"-?\d[\d,]*(?:\.\d+)?"
_STATES = ("质押", "冻结", "标记", "无", "未知", "-")


def _f(tok: str | None) -> float | None:
    if tok in (None, "", "-", "－", "—"):
        return None
    try:
        return float(tok.replace(",", "").rstrip("%"))
    except ValueError:
        return None


# --- top-10 tables ---------------------------------------------------------------------

_NUM_PCT = _NUM + r"%?"
# A well-formed figure: thousands grouped in threes, or no grouping. PDF text sometimes runs two cells together
# ("833,820,000200,000"); such a token is not a figure, and the row is not read rather than misread.
_WELL_FORMED = re.compile(r"-?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?%?")


def _is_num(tok: str) -> bool:
    return bool(re.fullmatch(_NUM_PCT, tok))
# Natures, longest first, for finding one glued to the end of a name (v2.0.7).
_NATURES_LONGEST = tuple(sorted(NATURES, key=len, reverse=True))


def split_nature(name: str) -> tuple[str, str | None]:
    """(name, nature) for a name with a shareholder nature glued to its end, as PDF text often gives it
    ("西安投资控股有限公司国有法人"); otherwise (name, None). v2.0.7 (finding 68)."""
    n = (name or "").strip()
    for nat in _NATURES_LONGEST:
        if n.endswith(nat) and len(n) > len(nat):
            return n[: -len(nat)].strip(), nat
    return n, None


def _close(a: float | None, b: float | None) -> bool:
    return a is not None and b is not None and abs(a - b) <= max(1.0, abs(b) * 1e-6)


def parse_top10_pages(pages: list[str]) -> list[dict]:
    """Rows of 前十名股东持股情况 (rank order).

    v2.0.7 (finding 68): two column orders are read.
    * Layout A (the older order, still used in many reports): name, change in the period, shares held,
      percentage, restricted shares, pledge state and number, nature at the end.
    * Layout B (the order with the nature after the name, as in the Shenzhen templates): name, nature,
      percentage, shares held, then [change in the period,] restricted [and unrestricted] shares, pledge state.
    The layout is taken from the header when it names the columns, otherwise from where the nature stands. The
    columns after the shares in layout B are placed by checking that restricted and unrestricted shares add up
    to the shares held. A row whose figures fail the checks (percentage outside 0 to 100, no shares) is left out.
    """
    from .units import first_declared  # noqa: F401 (share counts carry no currency unit)
    out, seen = [], set()
    mode = None
    header_layout, header_change = None, None
    pending = ""                     # the first line of a name wrapped onto two lines
    for pno, page in enumerate(pages, start=1):
        for raw in page.splitlines():
            line = raw.replace("　", " ").strip()
            if re.search(r"前十名股东持股情况|前10名股东持股情况", line) and "无限售" not in line:
                mode = "top10"
                header_layout, header_change, pending = None, None, ""
                continue
            if re.search(r"前十名无限售条件股东持股情况|前10名无限售条件股东持股情况|前十名流通股东", line):
                mode = None
                continue
            if mode and re.search(r"上述股东关联关系|一致行动|表决权恢复的优先股", line):
                mode = None
                continue
            if mode != "top10":
                continue
            if "股东名称" in line or ("股东性质" in line and not re.search(_NUM, line)):
                # A header: which column comes first, the nature or the figures?
                pos_nat = line.find("股东性质")
                pos_pct = min([p for p in (line.find("持股比例"), line.find("比例")) if p >= 0], default=-1)
                if pos_nat >= 0 and pos_pct >= 0:
                    header_layout = "B" if pos_nat < pos_pct else "A"
                if "增减" in line:
                    header_change = True
                elif header_layout == "B" and pos_pct >= 0:
                    header_change = False
                continue
            toks = line.split()
            k = 0
            while k < len(toks) and not _is_num(toks[k]):
                k += 1
            if k >= len(toks):
                # no figure: the first part of a wrapped name (kept for the next line), unless it is a note
                pending = "" if re.search(r"单位|说明|注|股东名称", line) else (pending + line)[-60:]
                continue
            if k == 0:
                pending = ""
                continue
            head = " ".join(toks[:k]) if re.search(r"[A-Za-z]", "".join(toks[:k])) else "".join(toks[:k])
            if pending:
                head = pending + ("" if not re.search(r"[A-Za-z]$", pending) else " ") + head
                pending = ""
            if re.search(r"股东名称|报告期|期末持股|比例|数量|单位", head):
                continue
            name, lead_nature = split_nature(head)
            rest = toks[k:]
            nums = []
            i = 0
            while i < len(rest) and _is_num(rest[i]):
                nums.append(rest[i])
                i += 1
            tail = rest[i:]
            if any(not _WELL_FORMED.fullmatch(x) for x in nums[:5]):
                continue                     # two cells run together: not read rather than misread
            if len(nums) < 3 and not (lead_nature and len(nums) >= 2):
                continue
            layout = header_layout or ("B" if lead_nature else "A")
            vals = [_f(x) for x in nums]
            change = restricted = None
            if layout == "B":
                pct, shares = vals[0], vals[1]
                r = vals[2:]
                if len(r) >= 3 and _close((r[1] or 0) + (r[2] or 0), shares):
                    change, restricted = r[0], r[1]
                elif len(r) >= 2 and _close((r[0] or 0) + (r[1] or 0), shares):
                    restricted = r[0]
                elif len(r) >= 2:
                    if header_change is False:
                        restricted = r[0]
                    else:
                        change, restricted = r[0], r[1]
                elif len(r) == 1:
                    if header_change:
                        change = r[0]
                    else:
                        restricted = r[0]
            else:
                change, shares, pct = vals[0], vals[1], vals[2]
                restricted = vals[3] if len(vals) > 3 else None
            if pct is None or not (0 <= pct <= 100) or shares is None or shares <= 0:
                continue
            if restricted is not None and (restricted < 0 or restricted > shares + 1):
                restricted = None
            state, pledged, nature = None, None, lead_nature
            j = 0
            if j < len(tail) and any(tail[j].startswith(s) for s in _STATES):
                state = tail[j]
                j += 1
                if j < len(tail) and re.fullmatch(_NUM + "|-", tail[j]):
                    pledged = _f(tail[j])
                    j += 1
            rest_text = "".join(tail[j:])
            if nature is None:
                nature = next((n for n in NATURES if n in rest_text), rest_text or None)
            if name in seen:
                continue
            seen.add(name)
            out.append({"shareholder_name": name, "rank": len(out) + 1, "change_shares": change, "shares": shares,
                        "ownership_pct": pct, "restricted_shares": restricted, "pledge_state": state,
                        "pledged_shares": pledged if state and ("质押" in state or "冻结" in state or "标记" in state) else None,
                        "shareholder_nature": nature, "shareholder_type": NATURE_TYPES.get(nature or ""),
                        "page": pno, "raw": line, "layout": layout})
            if len(out) >= 10:
                mode = None
    total = sum(r["ownership_pct"] for r in out)
    if total > 100.5:          # the figures cannot all be percentages: do not keep a misread table
        return []
    return out


def parse_top10_tradable_pages(pages: list[str]) -> list[dict]:
    """Rows of 前十名无限售条件股东持股情况: name, tradable shares, share class."""
    out, seen, mode = [], set(), False
    pending = ""                     # v2.0.7: the first line of a wrapped name
    for pno, page in enumerate(pages, start=1):
        for raw in page.splitlines():
            line = raw.replace("　", " ").strip()
            if re.search(r"前十名无限售条件股东持股情况|前10名无限售条件股东持股情况", line):
                mode, pending = True, ""
                continue
            if mode and re.search(r"上述股东关联关系|一致行动|前十名股东参与融资融券|前十名有限售条件", line):
                mode = False
                continue
            if not mode:
                continue
            m = re.match(r"^(.+?)\s+(" + _NUM + r")\s*(人民币普通股|境内上市外资股|境外上市外资股)(?:\s+(" + _NUM + r"))?\s*$", line)
            if not m:
                pending = "" if (re.search(r"\d", line) or re.search(r"股东名称|数量", line)) else (pending + line)[-60:]
                continue
            if not _WELL_FORMED.fullmatch(m.group(2)):
                pending = ""
                continue
            head = (pending + m.group(1)) if pending else m.group(1)
            pending = ""
            name = re.sub(r"\s+", "" if not re.search(r"[A-Za-z]", head) else " ", head).strip()
            if name in seen or re.search(r"股东名称|数量", name):
                continue
            seen.add(name)
            out.append({"shareholder_name": name, "rank": len(out) + 1, "tradable_shares": _f(m.group(2)),
                        "share_class": m.group(3), "page": pno, "raw": line})
            if len(out) >= 10:
                mode = False
    return out


def extract_top_holders(security_code: str | None = None, again: bool = False, progress=None) -> dict:
    """Top-10 and top-10 tradable holders from downloaded periodic reports.

    v2.0.8 (findings 76, 77 and 79): each report is opened once, and only the pages of the two shareholder tables
    are read (:mod:`ashare.reportreader`); progress is shown in documents, and a stopped run continues with the
    next report (:mod:`ashare.extractstate`). The extractor's version is new, so the first run re-reads every
    report and completes the re-extraction that v2.0.7's layout fix needs."""
    from .parsers import dual_run, record_confidence, extraction_note, tally_dual, PARSERS
    from .extractstate import run
    init_db()
    s = SessionLocal()
    totals = {"reports": 0, "holders": 0, "inserted": 0, "updated": 0, "errors": []}
    sections = ["top10", "top10_tradable"]
    try:
        q = s.query(Disclosure, Company).join(Company, Disclosure.company_id == Company.id).filter(
            Disclosure.kind.in_(("annual_report", "interim_report", "quarterly_report")),
            Disclosure.local_path.isnot(None))
        if security_code:
            q = q.filter(Company.security_code == str(security_code).zfill(6))
        from .financials import infer_period

        def handle(d, c, reader):
            path = Path(d.local_path)
            period, _ = infer_period(d.title_cn or "", "", d.announcement_date)
            if not period:
                return None
            rows, info = dual_run("top10", path, {"title": d.title_cn}, reader=reader, sections=sections)
            tradable, _ = dual_run("top10_tradable", path, {"title": d.title_cn}, reader=reader, sections=sections)
            tally_dual(totals, info, d.id)
            # v2.0.7 (finding 68): rows an earlier parser read from this document, and that the current one
            # does not, are removed (with their review items), so a misread table does not linger.
            keep = {r["shareholder_name"] for r in rows}
            stale = [o for o in s.query(OwnershipObservation).filter_by(company_id=c.id, disclosure_id=d.id)
                     if o.shareholder_name not in keep]
            if stale:
                ids = [o.id for o in stale]
                s.query(ReviewItem).filter(ReviewItem.table_name == "ownership_observations",
                                           ReviewItem.row_id.in_(ids)).delete(synchronize_session=False)
                for o in stale:
                    s.delete(o)
                totals["removed"] = totals.get("removed", 0) + len(stale)
            if not rows:
                return "EMPTY"
            totals["reports"] += 1
            tmap = {t["shareholder_name"]: t for t in tradable}
            for r in rows:
                row = s.query(OwnershipObservation).filter_by(
                    company_id=c.id, observation_date=period, shareholder_name=r["shareholder_name"],
                    source=d.source or "CNINFO").one_or_none()
                if row is None:
                    row = OwnershipObservation(company_id=c.id, observation_date=period,
                                               shareholder_name=r["shareholder_name"], source=d.source or "CNINFO")
                    s.add(row)
                    totals["inserted"] += 1
                else:
                    totals["updated"] += 1
                for k in ("rank", "shares", "ownership_pct", "restricted_shares", "pledged_shares",
                          "change_shares", "shareholder_type", "shareholder_nature"):
                    setattr(row, k, r.get(k))
                t = tmap.get(r["shareholder_name"])
                row.tradable_shares = t["tradable_shares"] if t else None
                row.disclosure_id, row.source_document = d.id, d.local_path or d.document_url
                row.source_page, row.raw_text = r.get("page"), r.get("raw")
                row.extraction_method = PARSERS[r["_variant"]].method
                row.confidence = record_confidence(r, 0.55)
                row.extraction_note = extraction_note(r)
                row.retrieved_at = utcnow()
                totals["holders"] += 1
            return "READ"

        rows = q.order_by(Company.security_code, Disclosure.announcement_date, Disclosure.id).all()
        return run("top_holders", rows, handle, totals, again, progress, s)
    finally:
        s.close()


# --- pledges -----------------------------------------------------------------------------

def classify_pledge_title(title: str | None) -> str | None:
    t = re.sub(r"\s+", "", title or "")
    if "质押" not in t or any(k in t for k in ("股票质押式回购交易业务", "风险提示", "可能")):
        return None
    if re.search(r"解除质押|解押|质押解除", t) and not re.search(r"(?<!解除)质押(?!解除|式)[^及]*及", t):
        return "RELEASE"
    return "PLEDGE"


def parse_pledge_text(text: str, event_type: str) -> list[dict]:
    t = _clean(text or "")
    out = []
    # narrative: "股东A将其持有的本公司10,000,000股质押给B"
    for m in re.finditer(r"(?:控股股东|股东|实际控制人)?([^，,。；;：:\s]{2,40}?)(?:先生|女士)?将其(?:所)?持有的(?:本)?公司"
                         r"(?:无限售条件流通股|限售股|股份)?\s*(" + _NUM + r")\s*(万)?\s*股(?:[^。]{0,20}?)?(质押给|解除质押|办理了?解除质押)"
                         r"(?:([^，,。；;]{2,60}))?", t):
        shares = _f(m.group(2)) * (1e4 if m.group(3) else 1)
        pledgor = re.sub(r"^(?:.*?(?:获悉|告知|通知))?(?:本公司|公司)?(?:控股股东|实际控制人|持股5%以上(?:的)?股东|股东)?(?:及其一致行动人)?",
                         "", m.group(1)) or m.group(1)
        out.append({"pledgor": pledgor, "shares": shares,
                    "pledgee": m.group(5).strip() if m.group(5) and m.group(4) == "质押给" else None})
    if not out:
        # table row: name, is-controlling, shares, …, dates, pledgee, pct of holding, pct of total
        for line in (text or "").splitlines():
            toks = line.split()
            nums = [x for x in toks if re.fullmatch(_NUM, x)]
            dates = re.findall(_DATE, line)
            pcts = re.findall(r"(\d+(?:\.\d+)?)%", line)
            if len(toks) >= 5 and nums and (dates or pcts) and re.match(r"^[一-鿿A-Za-z]", toks[0]) \
                    and not re.search(r"股东名称|合计|数量", toks[0]):
                rec = {"pledgor": toks[0], "shares": _f(nums[0]),
                       "is_controlling_shareholder": {"是": True, "否": False}.get(toks[1]) if len(toks) > 1 else None}
                if dates:
                    rec["start_date"] = parse_cn_date(dates[0])
                    rec["end_date"] = parse_cn_date(dates[1]) if len(dates) > 1 else None
                if len(pcts) >= 2:
                    rec["pct_of_holding"], rec["pct_of_total"] = float(pcts[-2]) / 100, float(pcts[-1]) / 100
                pl = re.search(r"([一-鿿（）()]{4,40}(?:公司|银行|信托|证券|资产管理|合伙企业))", line[len(toks[0]):])
                if pl and event_type == "PLEDGE":
                    rec["pledgee"] = pl.group(1)
                out.append(rec)
    for rec in out:
        m = re.search(r"占其所持(?:有)?(?:公司)?股份(?:总数)?(?:的)?比例(?:为)?\s*(\d+(?:\.\d+)?)%", t)
        if m and rec.get("pct_of_holding") is None:
            rec["pct_of_holding"] = float(m.group(1)) / 100
        m = re.search(r"占(?:本)?公司(?:总股本|股份总数)(?:的)?(?:比例)?(?:为)?\s*(\d+(?:\.\d+)?)%", t)
        if m and rec.get("pct_of_total") is None:
            rec["pct_of_total"] = float(m.group(1)) / 100
        if not rec.get("start_date"):
            m = re.search(r"质押(?:起始|开始)日(?:期)?[:：为]?\s*" + _DATE, t)
            rec["start_date"] = parse_cn_date(m.group(1)) if m else None
        if not rec.get("end_date"):
            m = re.search(r"(?:解除质押|解押|质押到期)日(?:期)?[:：为]?\s*" + _DATE, t)
            rec["end_date"] = parse_cn_date(m.group(1)) if m else None
        m = re.search(r"累计(?:质押|被质押)(?:股份|股数)?(?:数量)?(?:为)?\s*(" + _NUM + r")\s*(万)?\s*股", t)
        rec["cumulative_pledged"] = _f(m.group(1)) * (1e4 if m.group(2) else 1) if m else None
        if rec.get("is_controlling_shareholder") is None and re.search(r"控股股东", t[:200]):
            rec["is_controlling_shareholder"] = True
    return out


def extract_pledges(security_code: str | None = None, use_documents: bool = True) -> dict:
    init_db()
    s = SessionLocal()
    totals = {"announcements": 0, "events": 0, "inserted": 0, "title_only": 0}
    try:
        q = s.query(Disclosure, Company).join(Company, Disclosure.company_id == Company.id)
        if security_code:
            q = q.filter(Company.security_code == str(security_code).zfill(6))
        for d, c in q.all():
            typ = classify_pledge_title(d.title_cn)
            if not typ:
                continue
            totals["announcements"] += 1
            text, method, conf = d.title_cn or "", "TITLE_ONLY", 0.3
            if use_documents and d.local_path and Path(d.local_path).exists():
                pages = _document_pages(Path(d.local_path))
                if any(p.strip() for p in pages):
                    text, method, conf = "\n".join(pages), "DOCUMENT_TEXT_REGEX", 0.6
            recs = parse_pledge_text(text, typ) if method != "TITLE_ONLY" else []
            if not recs:
                recs = [{"pledgor": None, "shares": None}]
                totals["title_only"] += 1
            for r in recs:
                row = s.query(PledgeEvent).filter_by(company_id=c.id, disclosure_id=d.id, event_type=typ,
                                                     pledgor=r.get("pledgor"), shares=r.get("shares"),
                                                     source=d.source or "CNINFO").one_or_none()
                if row is None:
                    row = PledgeEvent(company_id=c.id, disclosure_id=d.id, event_type=typ, pledgor=r.get("pledgor"),
                                      shares=r.get("shares"), source=d.source or "CNINFO")
                    s.add(row)
                    totals["inserted"] += 1
                for k in ("pledgee", "is_controlling_shareholder", "pct_of_holding", "pct_of_total", "start_date",
                          "end_date", "cumulative_pledged"):
                    setattr(row, k, r.get(k))
                row.announcement_date, row.raw_value = d.announcement_date, (d.title_cn or "")[:300]
                row.extraction_method, row.confidence, row.retrieved_at = method, conf if r.get("shares") else 0.3, utcnow()
                totals["events"] += 1
        s.commit()
        return totals
    finally:
        s.close()


# --- controller and ownership type -----------------------------------------------------

CENTRAL = ("国务院国有资产监督管理委员会", "国务院国资委", "中华人民共和国财政部", "财政部", "中央汇金", "国务院",
           "中国投资有限责任公司", "全国社会保障基金理事会", "教育部", "中国科学院")
LOCAL_GOV = re.compile(r"(省|市|自治区|区|县|州|盟|旗)(?:人民政府)?(?:国有资产监督管理委员会|国资委|国有资产管理(?:委员会|局|办公室)|"
                       r"人民政府|财政(?:厅|局))")
_INSTITUTION = re.compile(r"公司|集团|委员会|政府|财政|大学|研究院|研究所|基金|合伙|银行|中心|协会|学院|局|厅|部")


def classify_ownership(controller: str | None, nature: str | None = None, no_controller: bool = False) -> tuple[str, str]:
    """(ownership type, basis): CENTRAL_SOE, LOCAL_SOE, PRIVATE, FOREIGN, COLLECTIVE, NO_CONTROLLER or UNKNOWN."""
    name = re.sub(r"\s+", "", controller or "")
    nat = re.sub(r"\s+", "", nature or "")
    if no_controller and not name:
        return "NO_CONTROLLER", "report states there is no actual controller"
    if not name and not nat:
        return "UNKNOWN", "no controller disclosed in the text read"
    if "中央" in nat or any(k in name for k in CENTRAL):
        return "CENTRAL_SOE", f"controller {name or nat} is a central-government body"
    if "地方" in nat and ("国资" in nat or "国有" in nat) or LOCAL_GOV.search(name):
        return "LOCAL_SOE", f"controller {name or nat} is a local-government body"
    if "集体" in nat or "集体" in name or "村民委员会" in name or "经济合作社" in name:
        return "COLLECTIVE", f"controller {name or nat} is a collective organisation"
    if "境外" in nat or "外资" in nat or re.search(r"国籍[:：]?(?!中国)[一-鿿]{2,6}", name):
        return "FOREIGN", f"controller nature '{nat or name}' is foreign"
    if "国有" in nat or "国资" in name:
        return "LOCAL_SOE", f"controller nature '{nat or name}' is state-owned (level not stated; local assumed)"
    if "自然人" in nat or "民营" in nat or "个人" in nat or (re.fullmatch(r"[一-鿿·]{2,8}(?:、[一-鿿·]{2,8})*", name)
                                                           and not _INSTITUTION.search(name)):
        return "PRIVATE", f"controller {name or nat} is a natural person"
    return "UNKNOWN", f"controller '{name}' with nature '{nat}' not classified; review"


_CTRL_HEADINGS = {
    "与本公司的关系", "与公司的关系", "与实际控制人关系", "与实际控制人的关系", "国籍", "是否取得其他国家或地区居留权",
    "法定代表人", "单位负责人", "法定代表人/单位负责人", "单位负责人或法定代表人", "成立日期", "组织机构代码",
    "统一社会信用代码", "主要经营业务", "主要职业及职务", "名称", "姓名", "控股股东名称", "控股股东姓名",
    "实际控制人名称", "实际控制人姓名", "注册资本", "不适用", "无", "/", "-", "适用", "√适用", "□适用"}
_CTRL_FIELD = re.compile(r"(?:法定代表人|单位负责人|成立日期|组织机构代码|统一社会信用代码|主要经营业务|国籍|"
                         r"是否取得|与(?:本公司|公司|实际控制人)的?关系|主要职业)")
_CTRL_STOP = re.compile(r"^(?:主要职业|报告期内|过去10年|过去十年|其他|公司与实际控制人|实际控制人通过|"
                        r"[（(]?[一二三四五六七八九十\d]+[)）、.]|第[一二三四五六七八九十]+节|\d+\s|"
                        r"控股股东|实际控制人|一致行动人|公司最终控制|报告期)")
_NO_CTRL = re.compile(r"^(?:无|不存在|无实际控制人|无控股股东|无控股主体|不适用)$")


def _ctrl_name(token: str) -> str | None:
    t = token.strip(" ：:；;，,。")
    if not t or t in _CTRL_HEADINGS or _CTRL_FIELD.match(t) or re.search(r"[:：]", t) or len(t) < 2:
        return None
    if re.fullmatch(r"[\d\-./年月日%（）()A-Z]+", t):
        return None
    return t


def _section(lines: list[str], start: int, limit: int = 40) -> list[str]:
    out = []
    for ln in lines[start + 1:start + 1 + limit]:
        if re.search(r"(?:控股股东|实际控制人)(?:情况|及其一致行动人)\s*$", ln) and out:
            break
        out.append(ln)
    return out


def _names_in(body: list[str], several: bool) -> list[str]:
    """Names from a controller section, in either layout:

    * label and value (Shanghai): "名称 中国贵州茅台酒厂（集团）有限责任公司", "姓名 李四";
    * header row, then value rows (Shenzhen): "实际控制人姓名 与实际控制人关系 国籍 …" / "王传福 本人 中国 否".
    """
    names: list[str] = []
    k = 0
    while k < len(body):
        ln = body[k].strip()
        head = re.match(r"^(?:控股股东|实际控制人)?(?:名称|姓名)(?=\s|[:：]|$)\s*[:：]?\s*(.*)$", ln)
        if head:
            rest = head.group(1).strip()
            if not rest or _CTRL_FIELD.match(rest) or rest.split()[0] in _CTRL_HEADINGS:
                # a header row: the values are on the rows below, one row per person or entity
                k += 1
                while k < len(body):
                    row = body[k].strip()
                    if not row:
                        k += 1
                        continue
                    if _CTRL_STOP.match(row) or re.match(r"^(?:控股股东|实际控制人)?(?:名称|姓名)(?=\s|[:：]|$)", row):
                        break
                    name = _ctrl_name(row.split()[0])
                    if name and name not in names:
                        names.append(name)
                    if not several:
                        break
                    k += 1
                continue
            value = re.split(r"\s{2,}|\s(?=单位负责人|法定代表人|成立日期|国籍|是否取得|统一社会信用代码)", rest)[0]
            name = _ctrl_name(value)
            if name and name not in names:
                names.append(name)
        k += 1
    return names if several else names[:1]


def parse_control_text(pages: list[str]) -> dict:
    """Controlling shareholder and actual controller from the share-capital section.

    v2.0.8 (findings 78 and 89): reads both exchanges' layouts. Shenzhen reports head the section
    "公司实际控制人及其一致行动人" and give the values on the row after a header row ("实际控制人姓名 与本公司的关系
    国籍 …"); v2.0.7 looked only for "实际控制人情况" and took the word after 姓名, which there is a heading. A
    heading is never taken as a name, and several natural persons acting together are kept together ("王传福、吕向阳")."""
    text = "\n".join(pages)
    t = re.sub(r"[ \t　]+", " ", text)
    lines = [ln.strip() for ln in t.splitlines()]
    out = {"controlling_shareholder": None, "controlling_nature": None, "actual_controller": None,
           "controller_nature": None, "no_controlling_shareholder": None, "no_actual_controller": None, "page": None}

    def heading(ln: str, which: str) -> bool:
        if which == "holder":
            return bool(re.search(r"控股股东情况\s*$", ln)) and "实际控制人" not in ln
        return bool(re.search(r"实际控制人(?:情况|及其一致行动人)\s*$", ln)) and "控股股东" not in ln

    for which, key, nkey, several in (("holder", "controlling_shareholder", "controlling_nature", False),
                                      ("actual", "actual_controller", "controller_nature", True)):
        for idx, ln in enumerate(lines):
            if not heading(ln, which):
                continue
            body = _section(lines, idx)
            names = _names_in(body, several)
            if names:
                out[key] = "、".join(names)
                break
    m = re.search(r"控股股东(?:性质|类型)\s*[:：]\s*([^\n]{1,30})", t)
    if m:
        out["controlling_nature"] = m.group(1).strip()
    m = re.search(r"实际控制人性质\s*[:：]\s*([^\n]{1,30})", t) or re.search(r"实际控制人类型\s*[:：]\s*([^\n]{1,30})", t)
    if m:
        out["controller_nature"] = m.group(1).strip()
    if re.search(r"(?:公司|本公司)(?:不存在|无|没有)控股股东|控股股东(?:报告期内)?变更.{0,6}无控股股东", t) or \
            (out["controlling_nature"] and _NO_CTRL.match(out["controlling_nature"])):
        out["no_controlling_shareholder"] = True
    if re.search(r"(?:公司|本公司)(?:不存在|无|没有)实际控制人|实际控制人.{0,4}[:：]?\s*无(?:\s|$)|无实际控制人", t):
        out["no_actual_controller"] = True
    for k in ("controlling_nature", "controller_nature"):
        if out[k] and _NO_CTRL.match(out[k]):
            out[k] = None
    if out["no_actual_controller"] and out["actual_controller"]:
        out["no_actual_controller"] = None          # a name was read; the phrase was about something else
    for pno, p in enumerate(pages, start=1):
        if "实际控制人" in p or "控股股东情况" in p:
            out["page"] = pno
            break
    return out


def extract_control(security_code: str | None = None, again: bool = False, progress=None) -> dict:
    """Controlling shareholder, actual controller and ownership type from annual and interim reports.

    v2.0.8: only the control section's pages are read, in both the layout and the plain text, and the reading
    that names more parties is kept; progress and resume as for the other extractors."""
    from .extractstate import run
    from .financials import infer_period
    init_db()
    s = SessionLocal()
    totals = {"reports": 0, "with_controller": 0, "types": defaultdict(int), "errors": []}
    try:
        q = s.query(Disclosure, Company).join(Company, Disclosure.company_id == Company.id).filter(
            Disclosure.kind.in_(("annual_report", "interim_report")), Disclosure.local_path.isnot(None))
        if security_code:
            q = q.filter(Company.security_code == str(security_code).zfill(6))

        def score(r):
            return (bool(r["actual_controller"]) + bool(r["controlling_shareholder"])
                    + bool(r["no_actual_controller"]) * 0.5)

        def handle(d, c, reader):
            period, _ = infer_period(d.title_cn or "", "", d.announcement_date)
            if not period:
                return None
            readings = [parse_control_text(p) for p in (reader.pages("layout", ["control"]),
                                                         reader.pages("text", ["control"])) if p]
            if not readings:
                return "EMPTY"
            r = max(readings, key=score)          # stable: the layout reading wins a tie
            if not any(r[k] for k in ("controlling_shareholder", "actual_controller", "no_actual_controller")):
                return "EMPTY"
            totals["reports"] += 1
            typ, basis = classify_ownership(r["actual_controller"], r["controller_nature"],
                                            bool(r["no_actual_controller"]))
            row = s.query(ControlObservation).filter_by(company_id=c.id, observation_date=period,
                                                        source=d.source or "CNINFO").one_or_none()
            if row is None:
                row = ControlObservation(company_id=c.id, observation_date=period, source=d.source or "CNINFO")
                s.add(row)
            row.disclosure_id = d.id
            for k in ("controlling_shareholder", "controlling_nature", "actual_controller", "controller_nature",
                      "no_controlling_shareholder", "no_actual_controller"):
                setattr(row, k, r[k])
            row.ownership_type, row.ownership_basis, row.source_page = typ, basis, r["page"]
            row.extraction_method, row.confidence, row.retrieved_at = "DOCUMENT_TEXT_REGEX", \
                0.6 if typ != "UNKNOWN" else 0.4, utcnow()
            totals["types"][typ] += 1
            if r["actual_controller"]:
                totals["with_controller"] += 1
            _chain_from(s, c, period, r, d.source or "CNINFO")
            return "READ"

        rows = q.order_by(Company.security_code, Disclosure.announcement_date, Disclosure.id).all()
        run("control", rows, handle, totals, again, progress, s)
        totals["types"] = dict(totals["types"])
        return totals
    finally:
        s.close()


def _chain_from(s, company, period, r, source):
    """Edges: controlling shareholder -> listed company (pct from the top-10 table), and
    actual controller -> controlling shareholder when they differ (pct unknown)."""
    listed = company.legal_name_cn or company.short_name_cn or company.security_code
    edges = []
    if r.get("controlling_shareholder"):
        holder = s.query(OwnershipObservation).filter_by(company_id=company.id, observation_date=period,
                                                         shareholder_name=r["controlling_shareholder"]).first()
        edges.append((r["controlling_shareholder"], listed, holder.ownership_pct if holder else None,
                      "top-10 table" if holder else "controlling shareholder (stake not matched)"))
        if r.get("actual_controller") and r["actual_controller"] != r["controlling_shareholder"]:
            edges.append((r["actual_controller"], r["controlling_shareholder"], None, "actual controller (stake not disclosed in text)"))
    elif r.get("actual_controller"):
        edges.append((r["actual_controller"], listed, None, "actual controller"))
    for parent, child, pct, basis in edges:
        e = s.query(ControlEdge).filter_by(company_id=company.id, observation_date=period, parent_name=parent,
                                           child_name=child, source=source).one_or_none()
        if e is None:
            e = ControlEdge(company_id=company.id, observation_date=period, parent_name=parent, child_name=child,
                            source=source)
            s.add(e)
        e.pct, e.basis, e.retrieved_at = pct, basis, utcnow()


def import_control_edges_csv(path: str, source: str = "CSV_IMPORT") -> dict:
    """Columns: security_code, observation_date, parent_name, child_name, pct (percent). Use for chains
    read from the 方框图 or from licensed datasets."""
    init_db()
    s = SessionLocal()
    n, errors = 0, []
    try:
        for i, r in enumerate(csv.DictReader(open(path, encoding="utf-8-sig")), 1):
            c = s.query(Company).filter_by(security_code=str(r.get("security_code", "")).zfill(6)).first()
            if not c:
                errors.append({"row": i, "error": "company not found"})
                continue
            d = normalise_date(r.get("observation_date"))
            e = s.query(ControlEdge).filter_by(company_id=c.id, observation_date=d, parent_name=r["parent_name"],
                                               child_name=r["child_name"], source=source).one_or_none()
            if e is None:
                e = ControlEdge(company_id=c.id, observation_date=d, parent_name=r["parent_name"],
                                child_name=r["child_name"], source=source)
                s.add(e)
                n += 1
            e.pct = _f(r.get("pct"))
            e.basis = "imported"
        s.commit()
        return {"inserted": n, "errors": errors}
    finally:
        s.close()


def import_control_csv(path: str, source: str = "CSV_IMPORT") -> dict:
    """Columns: security_code, observation_date, controlling_shareholder, actual_controller,
    [controller_nature, ownership_type]. A given ownership_type is kept; otherwise it is classified."""
    init_db()
    s = SessionLocal()
    n, errors = 0, []
    try:
        for i, r in enumerate(csv.DictReader(open(path, encoding="utf-8-sig")), 1):
            c = s.query(Company).filter_by(security_code=str(r.get("security_code", "")).zfill(6)).first()
            if not c:
                errors.append({"row": i, "error": "company not found"})
                continue
            d = normalise_date(r.get("observation_date"))
            row = s.query(ControlObservation).filter_by(company_id=c.id, observation_date=d, source=source).one_or_none()
            if row is None:
                row = ControlObservation(company_id=c.id, observation_date=d, source=source)
                s.add(row)
                n += 1
            row.controlling_shareholder = r.get("controlling_shareholder") or None
            row.actual_controller = r.get("actual_controller") or None
            row.controller_nature = r.get("controller_nature") or None
            if r.get("ownership_type"):
                row.ownership_type, row.ownership_basis = r["ownership_type"].strip().upper(), "imported"
            else:
                row.ownership_type, row.ownership_basis = classify_ownership(row.actual_controller, row.controller_nature)
            row.extraction_method, row.confidence = "CSV_IMPORT", 0.9
        s.commit()
        return {"inserted": n, "errors": errors}
    finally:
        s.close()


def control_at(security_code: str, as_of: str | None = None) -> dict:
    """Controller, ownership type and chain known at a date (reports published by then)."""
    init_db()
    s = SessionLocal()
    try:
        c = s.query(Company).filter_by(security_code=str(security_code).zfill(6)).first()
        if not c:
            return {"error": "company not found"}
        obs = []
        for o in s.query(ControlObservation).filter_by(company_id=c.id):
            d = s.get(Disclosure, o.disclosure_id) if o.disclosure_id else None
            pub = d.announcement_date if d else o.observation_date
            if not as_of or (pub or "") <= as_of:
                obs.append((o.observation_date, 1 if o.source == "CSV_IMPORT" else 0, pub, o))
        if not obs:
            return {"code": c.security_code, "control": None, "chain": []}
        date_, _, pub, o = max(obs, key=lambda x: (x[0], x[1]))
        chain = [{"parent": e.parent_name, "child": e.child_name, "pct": e.pct, "basis": e.basis, "source": e.source}
                 for e in s.query(ControlEdge).filter_by(company_id=c.id, observation_date=date_)]
        return {"code": c.security_code, "name": c.legal_name_cn,
                "control": {"date": date_, "published": pub, "controlling_shareholder": o.controlling_shareholder,
                            "controlling_nature": o.controlling_nature, "actual_controller": o.actual_controller,
                            "controller_nature": o.controller_nature, "ownership_type": o.ownership_type,
                            "basis": o.ownership_basis, "source": o.source, "confidence": o.confidence},
                "chain": chain}
    finally:
        s.close()


# --- entities --------------------------------------------------------------------------------

_CREDIT_CHARS = "0123456789ABCDEFGHJKLMNPQRTUWXY"
_CREDIT_W = (1, 3, 9, 27, 19, 26, 16, 17, 20, 29, 25, 13, 8, 24, 10, 30, 28)
CREDIT_RE = re.compile(r"(?<![0-9A-Z])([0-9A-HJ-NPQRTUWXY]{2}\d{6}[0-9A-HJ-NPQRTUWXY]{10})(?![0-9A-Z])")


def valid_credit_code(code: str) -> bool:
    """Unified social credit code check digit (GB 32100-2015)."""
    code = (code or "").upper()
    if len(code) != 18 or any(ch not in _CREDIT_CHARS for ch in code):
        return False
    total = sum(_CREDIT_CHARS.index(ch) * w for ch, w in zip(code[:17], _CREDIT_W))
    return _CREDIT_CHARS[(31 - total % 31) % 31] == code[17]


def find_credit_codes(text: str) -> list[str]:
    return [m for m in CREDIT_RE.findall(text or "") if valid_credit_code(m)]


def normalise_name(name: str) -> str:
    s = (name or "").strip()
    s = s.translate(str.maketrans("（）［］【】，。：；", "()[][],.:;"))
    s = re.sub(r"[！-～]", lambda m: chr(ord(m.group(0)) - 0xFEE0), s)   # full-width ASCII
    s = re.sub(r"\s+", "", s).upper()
    s = re.sub(r"[－—]", "-", s)
    return s


def _entity_type(name: str) -> str:
    name, nature = split_nature(name)          # v2.0.7: a nature glued to the name (finding 68)
    if nature and "自然人" in nature:
        return "PERSON"
    if re.search(r"国有资产监督管理|国资委|人民政府|财政|管理委员会$", name):
        return "GOVERNMENT"
    if re.search(r"合伙企业|有限合伙", name):
        return "PARTNERSHIP"
    if re.search(r"基金|资产管理计划|理财|信托计划|社保", name):
        return "FUND"
    if re.search(r"公司|LIMITED|LTD|INC|CORP|GMBH|株式会社|集团|银行", name, re.I):
        return "COMPANY"
    if re.fullmatch(r"[一-鿿·]{2,4}", name):
        return "PERSON"
    return "OTHER"


def resolve_entities() -> dict:
    """Build the entity register from shareholders, subsidiaries, controllers and listed companies,
    and link the observations to it."""
    from .places import jurisdiction_class
    init_db()
    s = SessionLocal()
    totals = {"entities": 0, "new": 0, "links": 0, "listed_matches": 0}
    try:
        by_norm: dict[str, Entity] = {}
        for e in s.query(Entity).all():
            by_norm[e.normalised_name] = e
        for a in s.query(EntityAlias).all():
            e = s.get(Entity, a.entity_id)
            if e:
                by_norm.setdefault(a.normalised_alias, e)

        def get(name, source, jurisdiction=None):
            if not name or _entity_type(name) == "PERSON":
                return None
            n = normalise_name(name)
            e = by_norm.get(n)
            if e is None:
                e = Entity(name=name, normalised_name=n, entity_type=_entity_type(name),
                           jurisdiction=jurisdiction or jurisdiction_class(name), sources=source)
                s.add(e)
                s.flush()
                by_norm[n] = e
                totals["new"] += 1
            elif source not in (e.sources or "").split(","):
                e.sources = ",".join(filter(None, [e.sources, source]))
            return e
        for c in s.query(Company).all():
            for nm in filter(None, (c.legal_name_cn, c.legal_name_en)):
                e = get(nm, "listed")
                if e and e.listed_company_id != c.id:
                    e.listed_company_id = c.id
                    totals["listed_matches"] += 1
        for o in s.query(OwnershipObservation).all():
            e = get(o.shareholder_name, "shareholder")
            if e and o.entity_id != e.id:
                o.entity_id = e.id
                totals["links"] += 1
        for sub in s.query(SubsidiaryObservation).all():
            e = get(sub.entity_name, "subsidiary", sub.jurisdiction_class)
            if e and sub.entity_id != e.id:
                sub.entity_id = e.id
                totals["links"] += 1
        for ed in s.query(ControlEdge).all():
            p, ch = get(ed.parent_name, "controller"), get(ed.child_name, "controller")
            ed.parent_entity_id, ed.child_entity_id = (p.id if p else None), (ch.id if ch else None)
        for co in s.query(ControlObservation).all():
            get(co.actual_controller, "controller")
            get(co.controlling_shareholder, "controller")
        s.flush()
        # v2.0.7 (finding 68): entities known only as shareholders, which no shareholder row names any more (rows
        # misread by an earlier parser and since removed), are removed with their aliases.
        linked = {eid for (eid,) in s.query(OwnershipObservation.entity_id).filter(
            OwnershipObservation.entity_id.isnot(None)).distinct()}
        pruned = 0
        for e in s.query(Entity).all():
            if (e.sources or "") == "shareholder" and not e.credit_code and e.id not in linked:
                s.query(EntityAlias).filter_by(entity_id=e.id).delete(synchronize_session=False)
                s.delete(e)
                pruned += 1
        totals["removed"] = pruned
        s.commit()
        totals["entities"] = s.query(Entity).count()
        return totals
    finally:
        s.close()


def import_entities_csv(path: str) -> dict:
    """Columns: name, [credit_code, aliases ('|'-separated), entity_type]. Credit codes are checked."""
    init_db()
    s = SessionLocal()
    n, errors = 0, []
    try:
        for i, r in enumerate(csv.DictReader(open(path, encoding="utf-8-sig")), 1):
            name = (r.get("name") or "").strip()
            code = (r.get("credit_code") or "").strip().upper() or None
            if code and not valid_credit_code(code):
                errors.append({"row": i, "error": f"invalid credit code {code}"})
                code = None
            e = (s.query(Entity).filter_by(credit_code=code).first() if code else None) or \
                s.query(Entity).filter_by(normalised_name=normalise_name(name)).first()
            if e is None:
                e = Entity(name=name, normalised_name=normalise_name(name), entity_type=r.get("entity_type") or _entity_type(name),
                           sources="import")
                s.add(e)
                s.flush()
                n += 1
            e.credit_code = code or e.credit_code
            for alias in filter(None, (a.strip() for a in (r.get("aliases") or "").split("|"))):
                na = normalise_name(alias)
                if not s.query(EntityAlias).filter_by(entity_id=e.id, normalised_alias=na).first():
                    s.add(EntityAlias(entity_id=e.id, alias=alias, normalised_alias=na))
        s.commit()
        return {"inserted": n, "errors": errors}
    finally:
        s.close()


def entity_profile(name_or_id: str) -> dict:
    init_db()
    s = SessionLocal()
    try:
        e = s.get(Entity, int(name_or_id)) if str(name_or_id).isdigit() else \
            s.query(Entity).filter_by(normalised_name=normalise_name(name_or_id)).first()
        if not e:
            return {"error": "entity not found"}
        holdings = defaultdict(dict)
        for o in s.query(OwnershipObservation).filter_by(entity_id=e.id):
            c = s.get(Company, o.company_id)
            holdings[c.security_code][o.observation_date] = o.ownership_pct
        subs = sorted({s.get(Company, x.company_id).security_code for x in
                       s.query(SubsidiaryObservation).filter_by(entity_id=e.id)})
        controls = sorted({s.get(Company, x.company_id).security_code for x in
                           s.query(ControlObservation).filter_by(actual_controller=e.name)})
        return {"id": e.id, "name": e.name, "type": e.entity_type, "credit_code": e.credit_code,
                "jurisdiction": e.jurisdiction, "listed_company": s.get(Company, e.listed_company_id).security_code
                if e.listed_company_id else None,
                "aliases": [a.alias for a in s.query(EntityAlias).filter_by(entity_id=e.id)],
                "shareholdings": {k: dict(sorted(v.items())) for k, v in holdings.items()},
                "subsidiary_of": subs, "actual_controller_of": controls}
    finally:
        s.close()


def common_controllers(as_of: str | None = None) -> list[dict]:
    """Listed companies grouped by the same actual controller (group affiliation)."""
    init_db()
    groups = defaultdict(set)
    s = SessionLocal()
    try:
        codes = [c.security_code for c in s.query(Company)]
    finally:
        s.close()
    for code in codes:
        ctl = (control_at(code, as_of) or {}).get("control")
        if ctl and ctl.get("actual_controller"):
            groups[normalise_name(ctl["actual_controller"])].add((code, ctl["actual_controller"], ctl["ownership_type"]))
    out = []
    for _, members in groups.items():
        if len(members) > 1:
            m = sorted(members)
            out.append({"controller": m[0][1], "ownership_type": m[0][2], "companies": [x[0] for x in m],
                        "count": len(m)})
    return sorted(out, key=lambda r: -r["count"])


# --- persons and interlocks -------------------------------------------------------------------

BOARD = {"CHAIR", "VICE_CHAIR", "DIRECTOR", "INDEPENDENT_DIRECTOR", "EMPLOYEE_DIRECTOR"}


def resolve_persons() -> dict:
    """Group officer observations into persons.

    Same person when the name and gender match and the implied birth years
    (observation year − age) differ by at most one. Observations without an
    age stay separate per company (marked unresolved) rather than being
    merged on name alone."""
    init_db()
    s = SessionLocal()
    try:
        s.query(PersonRole).delete()
        s.query(Person).delete()
        clusters: list[dict] = []
        by_name = defaultdict(list)
        for o in s.query(ManagementObservation).all():
            by_name[o.person_name].append(o)
        unresolved = 0
        for name, obs in by_name.items():
            local: list[dict] = []
            for o in obs:
                by = int(o.observation_date[:4]) - o.age if o.age and o.observation_date else None
                if by is None:
                    match = next((c for c in local if c["birth_year"] is None and o.company_id in c["companies"]), None)
                else:
                    match = next((c for c in local if c["birth_year"] is not None and abs(c["birth_year"] - by) <= 1
                                  and (c["gender"] in (None, o.gender) or o.gender is None)), None)
                if match is None:
                    match = {"name": name, "gender": o.gender, "birth_year": by, "obs": [], "companies": set()}
                    local.append(match)
                    if by is None:
                        unresolved += 1
                match["obs"].append(o)
                match["companies"].add(o.company_id)
                match["gender"] = match["gender"] or o.gender
            clusters += local
        for cl in clusters:
            p = Person(name=cl["name"], gender=cl["gender"], birth_year=cl["birth_year"],
                       resolution="name + gender + birth year (±1)" if cl["birth_year"] else
                       "unresolved: no age disclosed, kept per company")
            s.add(p)
            s.flush()
            roles = defaultdict(list)
            for o in cl["obs"]:
                roles[(o.company_id, o.role)].append(o)
            for (cid, role), os_ in roles.items():
                dates = sorted(o.observation_date for o in os_ if o.observation_date)
                s.add(PersonRole(person_id=p.id, company_id=cid, role=role, first_date=dates[0] if dates else None,
                                 last_date=dates[-1] if dates else None,
                                 tenure_start=min((o.tenure_start for o in os_ if o.tenure_start), default=None),
                                 tenure_end=max((o.tenure_end for o in os_ if o.tenure_end), default=None),
                                 observation_ids=json.dumps([o.id for o in os_])))
        s.commit()
        return {"persons": len(clusters), "unresolved_without_age": unresolved,
                "multi_company": sum(1 for c in clusters if len(c["companies"]) > 1)}
    finally:
        s.close()


def interlocks(as_of: str | None = None, security_code: str | None = None) -> list[dict]:
    """Pairs of companies sharing a board member (directors, incl. independent) at a date
    (the last roster on or before it)."""
    init_db()
    s = SessionLocal()
    try:
        seats = defaultdict(set)     # person -> companies
        for pr in s.query(PersonRole).filter(PersonRole.role.in_(BOARD)):
            if as_of and pr.first_date and pr.first_date > as_of:
                continue
            if as_of and pr.tenure_end and pr.tenure_end < as_of:
                continue
            seats[pr.person_id].add(pr.company_id)
        codes = {c.id: c.security_code for c in s.query(Company)}
        names = {p.id: p.name for p in s.query(Person)}
    finally:
        s.close()
    pairs = defaultdict(list)
    for pid, comps in seats.items():
        cs = sorted(comps)
        for i in range(len(cs)):
            for j in range(i + 1, len(cs)):
                pairs[(cs[i], cs[j])].append(names.get(pid))
    out = [{"company_a": codes[a], "company_b": codes[b], "shared_directors": sorted(p), "count": len(p)}
           for (a, b), p in pairs.items()]
    if security_code:
        code = str(security_code).zfill(6)
        out = [r for r in out if code in (r["company_a"], r["company_b"])]
    return sorted(out, key=lambda r: (-r["count"], r["company_a"]))
