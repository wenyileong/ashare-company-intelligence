from __future__ import annotations
from .timeutil import utcnow

import json
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable

from bs4 import BeautifulSoup
from lxml import etree
from pypdf import PdfReader

from .models import SessionLocal, Company, Disclosure, FinancialFact
from .disclosures import REPORT_KINDS

_KIND_ALIASES = {"annual": "annual_report", "interim": "interim_report", "quarterly": "quarterly_report"}

# Canonical metrics. XBRL local-name aliases are deliberately broad because
# Chinese annual-report taxonomies differ across reporting years.
METRICS: dict[str, dict[str, object]] = {
    "revenue": {"cn": "营业收入", "aliases": {"Revenue", "OperatingRevenue", "OperatingIncome", "营业收入", "营业总收入"}},
    "cost_of_revenue": {"cn": "营业成本", "aliases": {"OperatingCosts", "OperatingCost", "CostOfRevenue", "营业成本"}},
    "operating_profit": {"cn": "营业利润", "aliases": {"OperatingProfit", "OperatingProfitLoss", "营业利润"}},
    "profit_before_tax": {"cn": "利润总额", "aliases": {"ProfitBeforeTax", "ProfitLossBeforeTax", "利润总额"}},
    "income_tax": {"cn": "所得税费用", "aliases": {"IncomeTaxExpense", "IncomeTax", "所得税费用", "所得税"}},
    "net_profit": {"cn": "净利润", "aliases": {"NetProfit", "NetProfitLoss", "ProfitLoss", "净利润"}},
    "net_profit_parent": {"cn": "归属于母公司所有者的净利润", "aliases": {"NetProfitAttributableToOwnersOfParent", "NetProfitAttributableToParent", "ProfitLossAttributableToOwnersOfParent", "归属于母公司所有者的净利润", "归属于母公司股东的净利润", "归属于上市公司股东的净利润"}},
    "total_assets": {"cn": "资产总计", "aliases": {"Assets", "TotalAssets", "资产总计"}},
    "total_liabilities": {"cn": "负债合计", "aliases": {"Liabilities", "TotalLiabilities", "负债合计"}},
    "equity": {"cn": "所有者权益合计", "aliases": {"Equity", "OwnersEquity", "TotalEquity", "所有者权益合计", "所有者权益（或股东权益）合计", "所有者权益(或股东权益)合计", "股东权益合计"}},
    "cash": {"cn": "货币资金", "aliases": {"CashAndCashEquivalents", "Cash", "MonetaryFunds", "货币资金", "现金及现金等价物"}},
    "accounts_receivable": {"cn": "应收账款", "aliases": {"AccountsReceivable", "TradeReceivables", "应收账款"}},
    "inventory": {"cn": "存货", "aliases": {"Inventories", "Inventory", "存货"}},
    "operating_cash_flow": {"cn": "经营活动产生的现金流量净额", "aliases": {"NetCashFlowsFromOperatingActivities", "NetCashProvidedByUsedInOperatingActivities", "经营活动产生的现金流量净额"}},
    "investing_cash_flow": {"cn": "投资活动产生的现金流量净额", "aliases": {"NetCashFlowsFromInvestingActivities", "NetCashProvidedByUsedInInvestingActivities", "投资活动产生的现金流量净额"}},
    "financing_cash_flow": {"cn": "筹资活动产生的现金流量净额", "aliases": {"NetCashFlowsFromFinancingActivities", "NetCashProvidedByUsedInFinancingActivities", "筹资活动产生的现金流量净额"}},
    "rd_expense": {"cn": "研发费用", "aliases": {"ResearchAndDevelopmentExpense", "ResearchAndDevelopmentCosts", "研发费用"}},
    "net_profit_parent_ex_nonrecurring": {"cn": "归属于上市公司股东的扣除非经常性损益的净利润", "aliases": {
        "NetProfitAttributableToOwnersOfParentExcludingNonRecurringGainsAndLosses",
        "NetProfitAfterDeductingNonRecurringProfitAndLoss",
        "归属于上市公司股东的扣除非经常性损益的净利润", "扣除非经常性损益后归属于母公司股东的净利润",
        "归属于母公司所有者的扣除非经常性损益后的净利润"}},
    "employees": {"cn": "员工人数", "aliases": {"NumberOfEmployees", "Employees", "员工人数", "在职员工"}},
}

PERIOD_RE = re.compile(r"(?<!\d)(20\d{2})(?:年|[-/]年?)(?:12月31日|12-31|12/31)?")
NUM_RE = re.compile(r"[-−]?\(?\s*\d[\d,，]*(?:\.\d+)?\s*\)?")


def _normalise_number(raw: str) -> float | None:
    if not raw:
        return None
    s = raw.strip().replace(",", "").replace("，", "").replace("−", "-")
    negative = s.startswith("(") and s.endswith(")")
    s = s.strip("() ")
    try:
        value = float(s)
        return -value if negative else value
    except ValueError:
        return None


_PERIOD_END = {"FY": "12-31", "H1": "06-30", "Q1": "03-31", "Q3": "09-30"}


def _period_type_of(value: str) -> str | None:
    if "半年" in value:
        return "H1"
    if "第三季度" in value or "三季度" in value or "三季报" in value:
        return "Q3"
    if "第一季度" in value or "一季度" in value or "一季报" in value:
        return "Q1"
    if "年度" in value or "年报" in value:
        return "FY"
    return None


def infer_period_type(title: str, text: str = "") -> str:
    """Infer FY/H1/Q1/Q3, deciding on the title before the body text.

    v0.7 scanned title and body together, so an annual report whose body
    contains a quarterly breakdown (分季度主要财务指标) could be misread.
    """
    return _period_type_of(title or "") or _period_type_of((text or "")[:3000]) or "UNKNOWN"


def infer_period(title: str, text: str = "", announcement_date: str | None = None) -> tuple[str | None, str]:
    """Return (reporting_period_end, period_type) consistently.

    The fiscal year is taken from the title, then the document head, then the
    announcement date (an annual report announced in year N covers N-1).
    """
    ptype = infer_period_type(title, text)
    year = None
    for sample in (title or "", (text or "")[:3000]):
        m = re.search(r"(20\d{2})\s*年", sample)
        if m:
            year = int(m.group(1))
            break
    if year is None and announcement_date and announcement_date[:4].isdigit():
        year = int(announcement_date[:4]) - (1 if ptype in ("FY", "UNKNOWN") else 0)
    if year is None:
        return None, ptype
    end = _PERIOD_END.get(ptype, "12-31")
    return f"{year}-{end}", ptype


def comparative_periods(period: str | None, ptype: str) -> list[tuple[str, str]]:
    """Comparative reporting periods disclosed alongside ``period``."""
    if not period or ptype == "UNKNOWN":
        return []
    y = int(period[:4])
    out = [(f"{y - 1}{period[4:]}", ptype)]
    if ptype != "FY":
        out.append((f"{y - 1}-12-31", "FY"))
    return out


def infer_reporting_period(text: str, fallback: str | None = None) -> str | None:
    """Backwards-compatible wrapper: treats the first line as the title."""
    title, _, body = (text or "").partition("\n")
    period, _ = infer_period(title, body)
    return period or fallback


STATEMENT_TYPES = {
    "net_profit_parent_ex_nonrecurring": "INCOME_STATEMENT",
    "revenue": "INCOME_STATEMENT",
    "cost_of_revenue": "INCOME_STATEMENT",
    "operating_profit": "INCOME_STATEMENT",
    "profit_before_tax": "INCOME_STATEMENT",
    "income_tax": "INCOME_STATEMENT",
    "net_profit": "INCOME_STATEMENT",
    "net_profit_parent": "INCOME_STATEMENT",
    "total_assets": "BALANCE_SHEET",
    "total_liabilities": "BALANCE_SHEET",
    "equity": "BALANCE_SHEET",
    "cash": "BALANCE_SHEET",
    "accounts_receivable": "BALANCE_SHEET",
    "inventory": "BALANCE_SHEET",
    "operating_cash_flow": "CASH_FLOW",
    "investing_cash_flow": "CASH_FLOW",
    "financing_cash_flow": "CASH_FLOW",
    "rd_expense": "INCOME_STATEMENT",
    "employees": "NON_FINANCIAL",
}

def metric_unit(metric: str, default_unit: str) -> str:
    return "PERSON" if metric == "employees" else default_unit


def _unit_multiplier(text: str) -> tuple[str, float]:
    sample = text[:5000]
    if "亿元" in sample:
        return "CNY_100M", 100_000_000.0
    if "百万元" in sample or "百万" in sample:
        return "CNY_1M", 1_000_000.0
    if "万元" in sample:
        return "CNY_10K", 10_000.0
    if "千元" in sample:
        return "CNY_1K", 1_000.0
    return "CNY", 1.0


_UNIT_DECL = re.compile(r"(?:金额)?单位\s*[:：]\s*(?:人民币)?\s*(亿元|百万元|万元|千元|元)")
_UNIT_CODES = {"亿元": ("CNY_100M", 1e8), "百万元": ("CNY_1M", 1e6), "万元": ("CNY_10K", 1e4),
               "千元": ("CNY_1K", 1e3), "元": ("CNY", 1.0)}


def declared_unit(pages: list[str], page_no: int, pos: int) -> tuple[str, float] | None:
    """Unit declared by the nearest preceding '单位：…' line (v1.4).

    Searches the page up to ``pos``, then earlier pages from the end. A
    figure mentioned in narrative ("营业收入1,500亿元") is not a declaration,
    which is why v1.3's whole-document scan could scale tables by the wrong
    factor.
    """
    for i in range(page_no - 1, -1, -1):
        text = re.sub(r"[ \t]+", " ", pages[i])
        if i == page_no - 1:
            text = text[:pos]
        found = list(_UNIT_DECL.finditer(text))
        if found:
            return _UNIT_CODES[found[-1].group(1)]
    return None


def _metric_from_label(label: str) -> str | None:
    clean = re.sub(r"\s+", "", label)
    for key, spec in METRICS.items():
        if clean in {re.sub(r"\s+", "", str(a)) for a in spec["aliases"]}:
            return key
    return None


def _metric_for_concept(local: str) -> str | None:
    return next((k for k, v in METRICS.items() if local in v["aliases"]), None)


def _xbrl_contexts(soup) -> dict[str, dict]:
    contexts: dict[str, dict] = {}
    for ctx in soup.find_all("context"):
        cid = ctx.get("id")
        if not cid:
            continue
        def _txt(name):
            node = ctx.find(name)
            return node.get_text(strip=True) if node else None
        members = [m.get_text(strip=True) for m in ctx.find_all("explicitMember")]
        contexts[cid] = {
            "start": _txt("startDate"),
            "end": _txt("endDate") or _txt("instant"),
            "instant": bool(ctx.find("instant")),
            "dimensions": members,
        }
    return contexts


def _xbrl_facts(data: bytes, suffix: str) -> list[dict]:
    """Extract XBRL / inline-XBRL numeric facts with their contexts.

    v0.8 fixes: honours ix ``scale`` and ``sign`` attributes, and returns the
    context period and dimensions of every fact so that the caller can select
    the current-period, default-scope value instead of whichever duplicate
    (often the prior-year comparative) happened to be read last.
    """
    facts: list[dict] = []
    try:
        soup = BeautifulSoup(data, "lxml-xml")
        contexts = _xbrl_contexts(soup)
        for node in soup.find_all(attrs={"contextRef": True}):
            if node.name == "nonNumeric":
                continue
            concept = node.get("name") or (f"{node.prefix}:{node.name}" if node.prefix else node.name)
            local = concept.split(":")[-1]
            metric = _metric_for_concept(local)
            if not metric:
                continue
            raw = node.get_text(" ", strip=True)
            value = _normalise_number(raw)
            if value is None and raw in ("-", "—", "–") and "zero" in (node.get("format") or ""):
                value = 0.0
            if value is None:
                continue
            if node.get("scale"):
                try:
                    value *= 10 ** int(node.get("scale"))
                except ValueError:
                    pass
            if node.get("sign") == "-":
                value = -value
            ctx_id = node.get("contextRef")
            ctx = contexts.get(ctx_id, {})
            facts.append({
                "metric": metric, "raw_value": raw, "value": value,
                "xbrl_tag": concept, "context": ctx_id,
                "context_start": ctx.get("start"), "context_end": ctx.get("end"),
                "dimensions": ctx.get("dimensions") or [],
                "unit_ref": node.get("unitRef"),
            })
    except Exception:
        return []
    return facts


def select_xbrl_facts(facts: list[dict], period: str | None) -> list[dict]:
    """Choose one fact per (metric, scope) for the reporting period.

    Preference: context ending on the reporting period; for durations, the
    year-to-date context (starting 1 January); default (dimensionless) scope
    labelled CONSOLIDATED_DEFAULT. Facts whose context cannot be resolved are
    retained only when nothing better exists, at reduced confidence.
    """
    chosen: dict[tuple[str, str], dict] = {}
    year_start = f"{period[:4]}-01-01" if period else None
    for f in facts:
        dims = f.get("dimensions") or []
        scope = "CONSOLIDATED_DEFAULT" if not dims else "DIM:" + "|".join(dims)[:40]
        end = f.get("context_end")
        if end and period:
            if end != period:
                continue
            start = f.get("context_start")
            score = 3 if (start is None or start == year_start) else 2
            confidence = 0.98 if not dims else 0.9
        else:
            score, confidence = 1, 0.75
        key = (f["metric"], scope)
        prior = chosen.get(key)
        if prior is None or score > prior["_score"]:
            chosen[key] = {**f, "consolidation_scope": scope if end else None,
                           "confidence": confidence, "_score": score}
    out = []
    for f in chosen.values():
        f.pop("_score", None)
        out.append(f)
    return out


def _pdf_text_pages(path: Path) -> list[str]:
    from .http import document_heartbeat
    document_heartbeat(path)
    reader = PdfReader(str(path))
    pages = []
    for page in reader.pages:
        try:
            pages.append(page.extract_text() or "")
        except Exception:
            pages.append("")
    return pages


_CJK = "\u4e00-\u9fff"
_PDF_NUM = r"[-−]?\(?\s*\d[\d,，]*(?:\.\d+)?\s*\)?(?![\d.]*\s*[年月日%％])"


def _pdf_facts(path: Path, title: str, fallback_period: str | None, announcement_date: str | None = None) -> list[dict]:
    """Heuristic text extraction.

    v0.8 fixes: labels must stand alone (so 净利润 no longer matches inside
    归属于母公司股东的净利润, and 营业利润 not inside 营业利润率); years,
    dates and percentages are not captured as values; formatted amounts
    (with thousands separators or decimals) are preferred over bare
    integers such as note references.
    """
    return pdf_facts_from_pages(_pdf_text_pages(path), title, fallback_period, announcement_date)


def pdf_facts_from_pages(pages: list[str], title: str, fallback_period: str | None,
                         announcement_date: str | None = None) -> list[dict]:
    """Text-level core of :func:`_pdf_facts` (used by the evaluation harness)."""
    full = "\n".join(pages)
    period, period_type = infer_period(title, full, announcement_date)
    period = period or fallback_period
    any_declared = any(_UNIT_DECL.search(p) for p in pages)
    legacy_unit = _unit_multiplier(full)
    facts = []

    for metric, spec in METRICS.items():
        labels = sorted((str(a) for a in spec["aliases"] if any("中" <= c <= "鿿" for c in str(a))), key=len, reverse=True)
        if not labels:
            continue
        label_pattern = "|".join(re.escape(x) for x in labels)
        rx = re.compile(rf"(?<![{_CJK}])({label_pattern})(?![{_CJK}])([^\n]{{0,100}})")
        found = None
        for page_no, text in enumerate(pages, start=1):
            compact = re.sub(r"[ \t]+", " ", text)
            for m in rx.finditer(compact):
                nums = [n.group(0) for n in re.finditer(_PDF_NUM, m.group(2))]
                nums = [n for n in nums if _normalise_number(n) is not None]
                if not nums:
                    continue
                formatted = [n for n in nums if "," in n or "，" in n or "." in n]
                raw = (formatted or nums)[0]
                found = (page_no, m.group(1), raw, 0.60 if formatted else 0.40, m.start())
                break
            if found:
                break
        if not found:
            continue
        page_no, label, raw, confidence, pos = found
        unit_mult = declared_unit(pages, page_no, pos)
        if unit_mult is None:
            if any_declared:
                unit_mult = ("CNY", 1.0)
            else:  # no table declares a unit: fall back to a document scan, less confidently
                unit_mult = legacy_unit
                confidence *= 0.75
        unit, multiplier = unit_mult
        from .evaluation import calibrated_confidence
        confidence = round(calibrated_confidence("financials", 0.60) * confidence / 0.60, 3)
        value = _normalise_number(raw)
        facts.append({
            "metric": metric,
            "metric_cn": str(spec["cn"]),
            "value": value if metric == "employees" else value * multiplier,
            "raw_value": raw,
            "label": label,
            "unit": metric_unit(metric, unit),
            "period": period,
            "statement_type": STATEMENT_TYPES.get(metric),
            "period_type": period_type,
            "page": page_no,
            "method": "PDF_TEXT_HEURISTIC",
            "confidence": confidence,
        })
    return facts


def _find_disclosure(session, company: Company, path: Path) -> Disclosure | None:
    name = path.name
    return session.query(Disclosure).filter(
        Disclosure.company_id == company.id,
        Disclosure.local_path == str(path),
    ).one_or_none()


def extract_document(company: Company, disclosure: Disclosure) -> list[dict]:
    if not disclosure.local_path:
        return []
    path = Path(disclosure.local_path)
    if not path.exists():
        return []
    data = path.read_bytes()
    suffix = path.suffix.lower()
    title = disclosure.title_cn or ""
    ann = disclosure.announcement_date
    period, ptype = infer_period(title, "", ann)

    facts = _xbrl_facts(data, suffix) if suffix in {".xml", ".xbrl", ".html", ".htm"} else []
    if facts:
        selected = select_xbrl_facts(facts, period)
        for f in selected:
            f.update({"metric_cn": METRICS[f["metric"]]["cn"], "period": period,
                      "period_type": ptype, "unit": metric_unit(f["metric"], "CNY"),
                      "statement_type": STATEMENT_TYPES.get(f["metric"]), "method": "XBRL",
                      "page": None})
        # v1.0: also keep the comparatives the report discloses (same period
        # of the prior year; prior year-end for balance-sheet items). They
        # are what cross-document validation compares against the earlier
        # report, so restatements become visible.
        for cperiod, cptype in comparative_periods(period, ptype):
            for f in select_xbrl_facts(facts, cperiod):
                if f.get("consolidation_scope") is None:
                    continue  # context unresolved; cannot be a comparative
                f.update({"metric_cn": METRICS[f["metric"]]["cn"], "period": cperiod,
                          "period_type": cptype, "unit": metric_unit(f["metric"], "CNY"),
                          "statement_type": STATEMENT_TYPES.get(f["metric"]),
                          "method": "XBRL_COMPARATIVE", "page": None,
                          "confidence": min(f.get("confidence") or 0.95, 0.95)})
                selected.append(f)
        return selected
    if suffix == ".pdf":
        # v1.5: run the plain and layout extractors and compare them. The
        # method stays PDF_TEXT_HEURISTIC (it is part of the vintage key);
        # the variant and agreement are kept in extraction_note.
        from .parsers import dual_run, extraction_note
        facts, info = dual_run("financials", path, {"title": title, "announcement_date": ann,
                                                    "fallback_period": period})
        for f in facts:
            conf = f.get("confidence") or 0.4
            if f.get("_agreement") == "AGREE":
                conf = min(conf + 0.05, 0.9)
            elif f.get("_agreement") == "DISAGREE":
                conf = min(conf, 0.4)
            f["confidence"] = round(conf, 3)
            f["extraction_note"] = extraction_note(f)
            f["method"] = "PDF_TEXT_HEURISTIC"
        # v1.7: line items of the consolidated statements (CAS chart)
        from .cas import CHART, CHART_VERSION
        from .parsers import record_confidence
        if facts:
            period, ptype = facts[0]["period"], facts[0]["period_type"]
        items, _ = dual_run("statements", path, {"title": title, "announcement_date": ann})
        for it in items:
            facts.append({
                "metric": it["metric"], "metric_cn": CHART[it["metric"]]["labels"][0], "value": it["value"],
                "raw_value": it["raw_value"], "label": it["label"], "unit": it["unit"], "period": period,
                "period_type": ptype, "statement_type": {"BS": "BALANCE_SHEET", "IS": "INCOME_STATEMENT",
                                                         "CF": "CASH_FLOW"}[it["statement"]],
                "page": it["page"], "method": "PDF_STATEMENT_TABLE", "context": CHART_VERSION,
                "confidence": record_confidence(it, 0.65), "extraction_note": extraction_note(it)})
        return facts
    return []


def persist_facts(company: Company, disclosure: Disclosure, facts: Iterable[dict]) -> dict:
    session = SessionLocal()
    inserted = updated = 0
    try:
        for f in facts:
            query = session.query(FinancialFact).filter_by(
                company_id=company.id,
                disclosure_id=disclosure.id,
                reporting_period=f.get("period"),
                period_type=f.get("period_type"),
                metric=f["metric"],
                consolidation_scope=f.get("consolidation_scope"),
                extraction_method=f.get("method", "UNKNOWN"),
            )
            row = query.one_or_none()
            if row is None:
                row = FinancialFact(
                    company_id=company.id,
                    disclosure_id=disclosure.id,
                    reporting_period=f.get("period"),
                    period_type=f.get("period_type"),
                    statement_type=f.get("statement_type"),
                    metric=f["metric"],
                    metric_cn=f.get("metric_cn"),
                    consolidation_scope=f.get("consolidation_scope"),
                    extraction_method=f.get("method", "UNKNOWN"),
                )
                session.add(row)
                inserted += 1
            else:
                updated += 1
            row.value = f.get("value")
            row.raw_value = f.get("raw_value")
            row.unit = f.get("unit")
            row.currency = "CNY"
            row.source_document = disclosure.document_url or disclosure.local_path
            row.source_page = f.get("page")
            row.source_xbrl_tag = f.get("xbrl_tag")
            row.source_label = f.get("label")
            row.source_context = f.get("context")
            row.confidence = f.get("confidence")
            row.extraction_note = f.get("extraction_note")
            row.validation_status = "UNVALIDATED"
            row.retrieved_at = utcnow()
        session.commit()
        return {"inserted": inserted, "updated": updated}
    finally:
        session.close()


def extract_financials(security_code: str | None = None, kind: str = "reports", limit: int | None = None) -> dict:
    session = SessionLocal()
    totals = {"companies": 0, "documents": 0, "facts_inserted": 0, "facts_updated": 0, "skipped": 0, "errors": []}
    try:
        q = session.query(Company)
        if security_code:
            q = q.filter(Company.security_code == security_code.zfill(6))
        companies = q.order_by(Company.security_code).all()
        for company in companies:
            totals["companies"] += 1
            dq = session.query(Disclosure).filter(Disclosure.company_id == company.id, Disclosure.local_path.isnot(None))
            # v0.7 filtered on kinds ("annual", "interim"...) that the
            # classifier never produces, so no report was ever extracted.
            if kind == "reports":
                dq = dq.filter(Disclosure.kind.in_(REPORT_KINDS))
            elif kind != "all":
                dq = dq.filter(Disclosure.kind == _KIND_ALIASES.get(kind, kind))
            docs = dq.order_by(Disclosure.announcement_date).all()
            if limit:
                docs = docs[:limit]
            for disclosure in docs:
                try:
                    facts = extract_document(company, disclosure)
                    if not facts:
                        totals["skipped"] += 1
                        continue
                    result = persist_facts(company, disclosure, facts)
                    totals["documents"] += 1
                    totals["facts_inserted"] += result["inserted"]
                    totals["facts_updated"] += result["updated"]
                except Exception as exc:
                    totals["errors"].append({"code": company.security_code, "disclosure_id": disclosure.id, "error": repr(exc)})
        return totals
    finally:
        session.close()


def validate_financials(security_code: str | None = None) -> dict:
    """Run conservative internal consistency checks; never overwrite values."""
    session = SessionLocal()
    result = {"groups_checked": 0, "passed": 0, "failed": 0, "insufficient": 0, "errors": []}
    try:
        q = session.query(FinancialFact)
        if security_code:
            q = q.join(Company).filter(Company.security_code == security_code.zfill(6))
        rows = q.all()
        groups: dict[tuple, dict[str, FinancialFact]] = {}
        for row in rows:
            # Group per source document and method: facts from different
            # documents (e.g. a comparative restated later) must not be mixed.
            key = (row.company_id, row.reporting_period, row.consolidation_scope,
                   row.disclosure_id, row.extraction_method)
            groups.setdefault(key, {})[row.metric] = row
        for key, facts in groups.items():
            if not all(k in facts for k in ("total_assets", "total_liabilities", "equity")):
                result["insufficient"] += 1
                continue
            result["groups_checked"] += 1
            assets = facts["total_assets"].value
            liabilities = facts["total_liabilities"].value
            equity = facts["equity"].value
            if assets is None or liabilities is None or equity is None:
                result["insufficient"] += 1
                continue
            residual = abs(assets - liabilities - equity)
            tolerance = max(abs(assets) * 0.005, 1000.0)
            status = "VALIDATED_INTERNAL" if residual <= tolerance else "FAILED_INTERNAL_BALANCE"
            for metric in ("total_assets", "total_liabilities", "equity"):
                facts[metric].validation_status = status
            if status == "VALIDATED_INTERNAL":
                result["passed"] += 1
            else:
                result["failed"] += 1
                result["errors"].append({
                    "company_id": key[0], "reporting_period": key[1], "disclosure_id": key[3],
                    "assets": assets, "liabilities": liabilities, "equity": equity,
                    "residual": residual, "tolerance": tolerance,
                })
        session.commit()
        return result
    finally:
        session.close()
