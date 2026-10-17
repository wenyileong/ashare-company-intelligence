"""v1.1 industry classification, peer groups and industry statistics.

Schemes
-------
CSRC_2012   CSRC Guidelines on Industry Classification of Listed Companies
            (上市公司行业分类指引, 2012 revision): 19 sections (门类, A–S) and
            90 divisions (大类, two digits), aligned with GB/T 4754-2011.
SW_2021     Shenwan Hongyuan industry classification, 2021 revision (31
            level-1 industries). Commercial; import from a licensed export.
CSRC_OTHER / CNINFO / CUSTOM   Any other scheme, imported as-is.

Classifications are point-in-time observations (``effective_date``). Peer
groups and statistics use the classification in force at ``as_of``.

The section/division ranges below are used only to *validate* imported
codes; names always come from the imported source.
"""
from __future__ import annotations

import csv
import re
import statistics
from collections import defaultdict
from pathlib import Path

from .models import SessionLocal, Company, IndustryClassification, init_db
from .ownership import normalise_date

#: CSRC 2012 section letter -> (first division, last division, name)
CSRC_2012_SECTIONS = {
    "A": (1, 5, "农、林、牧、渔业"), "B": (6, 12, "采矿业"), "C": (13, 43, "制造业"),
    "D": (44, 46, "电力、热力、燃气及水生产和供应业"), "E": (47, 50, "建筑业"),
    "F": (51, 52, "批发和零售业"), "G": (53, 60, "交通运输、仓储和邮政业"),
    "H": (61, 62, "住宿和餐饮业"), "I": (63, 65, "信息传输、软件和信息技术服务业"),
    "J": (66, 69, "金融业"), "K": (70, 70, "房地产业"), "L": (71, 72, "租赁和商务服务业"),
    "M": (73, 75, "科学研究和技术服务业"), "N": (76, 78, "水利、环境和公共设施管理业"),
    "O": (79, 81, "居民服务、修理和其他服务业"), "P": (82, 82, "教育"),
    "Q": (83, 84, "卫生和社会工作"), "R": (85, 89, "文化、体育和娱乐业"), "S": (90, 90, "综合"),
}

#: SW 2021 level-1 industry names (31), used to validate imported names.
SW_2021_LEVEL1 = {
    "农林牧渔", "基础化工", "钢铁", "有色金属", "电子", "汽车", "家用电器", "食品饮料", "纺织服饰",
    "轻工制造", "医药生物", "公用事业", "交通运输", "房地产", "商贸零售", "社会服务", "银行",
    "非银金融", "综合", "建筑材料", "建筑装饰", "电力设备", "机械设备", "国防军工", "计算机",
    "传媒", "通信", "煤炭", "石油石化", "环保", "美容护理",
}

SCHEMES = ("CSRC_2012", "SW_2021", "CNINFO", "CSRC_OTHER", "CUSTOM")


def parse_csrc_code(code: str | None) -> tuple[str | None, str | None]:
    """Split a CSRC 2012 code such as 'C27' or 'C-27' into ('C', 'C27')."""
    if not code:
        return None, None
    m = re.match(r"^\s*([A-Sa-s])\s*-?\s*(\d{1,2})?\s*$", str(code))
    if not m:
        return None, None
    sec = m.group(1).upper()
    return sec, (f"{sec}{int(m.group(2)):02d}" if m.group(2) else None)


def validate_classification(scheme: str, level1_code=None, level1_name=None, level2_code=None) -> list[str]:
    """Problems with an imported classification (empty list = valid)."""
    problems = []
    if scheme == "CSRC_2012":
        sec = (level1_code or "").strip().upper()
        if sec not in CSRC_2012_SECTIONS:
            problems.append(f"unknown CSRC 2012 section {level1_code!r}")
        elif level2_code:
            s2, div = parse_csrc_code(level2_code)
            if div is None or s2 != sec:
                problems.append(f"division {level2_code!r} does not belong to section {sec}")
            else:
                lo, hi, _ = CSRC_2012_SECTIONS[sec]
                n = int(div[1:])
                if not lo <= n <= hi:
                    problems.append(f"division {div} outside section {sec} range {lo:02d}-{hi:02d}")
    elif scheme == "SW_2021" and level1_name and level1_name.strip() not in SW_2021_LEVEL1:
        problems.append(f"{level1_name!r} is not an SW 2021 level-1 industry")
    return problems


_COLS = {
    "security_code": ("security_code", "code", "证券代码", "股票代码"),
    "effective_date": ("effective_date", "date", "observation_date", "日期", "生效日期"),
    "level1_code": ("level1_code", "section_code", "门类代码", "一级行业代码"),
    "level1_name": ("level1_name", "section_name", "门类名称", "一级行业名称", "一级行业"),
    "level2_code": ("level2_code", "division_code", "大类代码", "二级行业代码", "行业代码"),
    "level2_name": ("level2_name", "division_name", "大类名称", "二级行业名称", "二级行业", "行业名称"),
    "level3_code": ("level3_code", "三级行业代码"),
    "level3_name": ("level3_name", "三级行业名称", "三级行业"),
    "level4_code": ("level4_code",),
    "level4_name": ("level4_name",),
}


def _col(row: dict, key: str):
    for name in _COLS[key]:
        if row.get(name) not in (None, ""):
            return str(row[name]).strip()
    return None


def import_industry_csv(path: str, scheme: str, source: str = "CSV_IMPORT", effective_date: str | None = None) -> dict:
    """Import classifications. English or Chinese column headers are accepted
    (e.g. 证券代码, 门类代码, 大类代码, 行业名称). A CSRC file that gives only
    the division code (C27) has its section derived from it."""
    scheme = scheme.upper()
    init_db()
    session = SessionLocal()
    inserted = updated = 0
    errors, invalid = [], 0
    try:
        with Path(path).open("r", encoding="utf-8-sig", newline="") as fh:
            rows = list(csv.DictReader(fh))
        for i, r in enumerate(rows, 1):
            try:
                code = _col(r, "security_code")
                c = session.query(Company).filter_by(security_code=str(code or "").zfill(6)).first() if code else None
                if not c:
                    raise ValueError("company not found")
                date = normalise_date(_col(r, "effective_date") or effective_date)
                if not date:
                    raise ValueError("effective_date missing (column or --effective-date)")
                v = {k: _col(r, k) for k in _COLS if k not in ("security_code", "effective_date")}
                if scheme == "CSRC_2012":
                    sec, div = parse_csrc_code(v["level2_code"] or v["level1_code"])
                    if sec and not v["level1_code"]:
                        v["level1_code"] = sec
                    if sec and v["level1_code"] and len(v["level1_code"]) > 1:
                        v["level1_code"] = sec
                    if div:
                        v["level2_code"] = div
                    if v["level1_code"] in CSRC_2012_SECTIONS and not v["level1_name"]:
                        v["level1_name"] = CSRC_2012_SECTIONS[v["level1_code"]][2]
                problems = validate_classification(scheme, v["level1_code"], v["level1_name"], v["level2_code"])
                row = session.query(IndustryClassification).filter_by(
                    company_id=c.id, scheme=scheme, effective_date=date, source=source).one_or_none()
                if row is None:
                    row = IndustryClassification(company_id=c.id, scheme=scheme, effective_date=date, source=source)
                    session.add(row)
                    inserted += 1
                else:
                    updated += 1
                for k, val in v.items():
                    setattr(row, k, val)
                row.source_document = r.get("source_document")
                row.extraction_method = r.get("extraction_method") or "CSV_IMPORT"
                row.confidence = float(r["confidence"]) if r.get("confidence") else None
                row.validation_status = "FAILED_CODE_CHECK" if problems else "VALIDATED_CODE_CHECK"
                row.raw_text = "; ".join(problems) if problems else None
                invalid += bool(problems)
                session.flush()
            except Exception as exc:
                errors.append({"row": i, "error": str(exc)})
        session.commit()
        return {"inserted": inserted, "updated": updated, "invalid_codes": invalid, "errors": errors}
    finally:
        session.close()


def classification_at(session, company_id: int, scheme: str, as_of: str | None = None):
    """The classification in force at ``as_of`` (latest effective on/before)."""
    q = session.query(IndustryClassification).filter(
        IndustryClassification.company_id == company_id, IndustryClassification.scheme == scheme)
    if as_of:
        q = q.filter(IndustryClassification.effective_date <= as_of)
    return q.order_by(IndustryClassification.effective_date.desc(), IndustryClassification.id.desc()).first()


def _level_key(cls, level: int):
    return getattr(cls, f"level{level}_code") or getattr(cls, f"level{level}_name")


def industry_history(security_code: str):
    init_db()
    session = SessionLocal()
    try:
        c = session.query(Company).filter_by(security_code=str(security_code).zfill(6)).first()
        if not c:
            return []
        return (session.query(IndustryClassification).filter_by(company_id=c.id)
                .order_by(IndustryClassification.scheme, IndustryClassification.effective_date).all())
    finally:
        session.close()


def peers(security_code: str, scheme: str = "CSRC_2012", level: int = 2, as_of: str | None = None) -> dict:
    """Companies in the same industry (same scheme and level) at ``as_of``."""
    init_db()
    session = SessionLocal()
    try:
        c = session.query(Company).filter_by(security_code=str(security_code).zfill(6)).first()
        if not c:
            return {"error": "company not found"}
        own = classification_at(session, c.id, scheme, as_of)
        if not own or not _level_key(own, level):
            return {"error": f"no {scheme} level-{level} classification for {c.security_code} at {as_of or 'latest'}"}
        key = _level_key(own, level)
        members = []
        for other in session.query(Company).all():
            cl = classification_at(session, other.id, scheme, as_of)
            if cl and _level_key(cl, level) == key:
                members.append({"code": other.security_code, "name": other.short_name_cn,
                                "board": other.board, "since": cl.effective_date})
        return {"code": c.security_code, "scheme": scheme, "level": level, "as_of": as_of,
                "industry_code": getattr(own, f"level{level}_code"), "industry_name": getattr(own, f"level{level}_name"),
                "peers": sorted(members, key=lambda m: m["code"])}
    finally:
        session.close()


RATIOS = {
    "net_margin": ("net_profit", "revenue"),
    "liabilities_to_assets": ("total_liabilities", "total_assets"),
    "rd_intensity": ("rd_expense", "revenue"),
    "roa": ("net_profit", "total_assets"),
    "roe": ("net_profit_parent", "equity"),
}


def _value(code, metric, period, period_type, as_of):
    from .intelligence import financial_series
    if metric in RATIOS:
        num, den = RATIOS[metric]
        a = _value(code, num, period, period_type, as_of)
        b = _value(code, den, period, period_type, as_of)
        if a and b and a[0] is not None and b[0]:
            return a[0] / b[0], min(a[1], b[1], key=lambda x: "HIGH MEDIUM LOW UNVALIDATED".split().index(x))
        return None
    s = financial_series(code, metric, as_of=as_of, period_type=period_type)
    pt = next((p for p in s if p["period"] == period), None) if period else (s[-1] if s else None)
    return (pt["value"], pt["confidence_class"]) if pt else None


def _quantile(xs, q):
    xs = sorted(xs)
    if not xs:
        return None
    k = (len(xs) - 1) * q
    f, c = int(k), min(int(k) + 1, len(xs) - 1)
    return xs[f] + (xs[c] - xs[f]) * (k - f)


def industry_stats(security_code: str, metric: str = "revenue", scheme: str = "CSRC_2012", level: int = 2,
                   period: str | None = None, period_type: str = "FY", as_of: str | None = None,
                   min_class: str = "LOW") -> dict:
    """Distribution of a metric (or ratio) across a company's industry peers,
    and the company's percentile rank within it. Values below
    ``min_class`` confidence are excluded and counted."""
    order = ["HIGH", "MEDIUM", "LOW", "UNVALIDATED"]
    p = peers(security_code, scheme, level, as_of)
    if "error" in p:
        return p
    values, excluded, missing = {}, 0, 0
    for m in p["peers"]:
        v = _value(m["code"], metric, period, period_type, as_of)
        if v is None:
            missing += 1
        elif order.index(v[1]) > order.index(min_class.upper()):
            excluded += 1
        else:
            values[m["code"]] = v[0]
    xs = list(values.values())
    own = values.get(p["code"])
    rank = None
    if own is not None and xs:
        below = sum(1 for x in xs if x < own)
        equal = sum(1 for x in xs if x == own)
        rank = (below + 0.5 * equal) / len(xs)
    return {
        "code": p["code"], "industry": f"{p['industry_code'] or ''} {p['industry_name'] or ''}".strip(),
        "scheme": scheme, "level": level, "metric": metric, "period": period or "latest per company",
        "as_of": as_of, "peers": len(p["peers"]), "with_value": len(xs), "missing": missing,
        "excluded_low_confidence": excluded,
        "min": min(xs) if xs else None, "p25": _quantile(xs, 0.25), "median": statistics.median(xs) if xs else None,
        "mean": statistics.fmean(xs) if xs else None, "p75": _quantile(xs, 0.75), "max": max(xs) if xs else None,
        "company_value": own, "company_percentile": rank,
        "note": "percentile = share of peers below the company (ties count half)",
        "values": values,   # v1.7: per-peer values, for distribution charts
    }


def industry_summary(scheme: str = "CSRC_2012", level: int = 1, as_of: str | None = None) -> list[dict]:
    """Number of companies per industry at ``as_of``."""
    init_db()
    session = SessionLocal()
    try:
        counts = defaultdict(lambda: {"companies": 0, "name": None})
        for c in session.query(Company).all():
            cl = classification_at(session, c.id, scheme, as_of)
            if cl:
                k = _level_key(cl, level)
                counts[k]["companies"] += 1
                counts[k]["name"] = counts[k]["name"] or getattr(cl, f"level{level}_name")
        return [{"code": k, "name": v["name"], "companies": v["companies"]}
                for k, v in sorted(counts.items(), key=lambda kv: (-kv[1]["companies"], str(kv[0])))]
    finally:
        session.close()
