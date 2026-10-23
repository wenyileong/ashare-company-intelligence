from __future__ import annotations
from .timeutil import utcnow

import hashlib
import html
import json
import re
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Iterable

from .config import disclosure_dir, CNINFO_QUERY_URL, CNINFO_STATIC_BASE, USER_AGENT, REQUESTS_PER_SECOND
from .http import RateLimitedClient
from .models import SessionLocal, Company, Disclosure
from .storage import store_raw

# CNINFO category codes. The four periodic-report codes were used in v0.4-0.7.
# NB: category_yjdbg_szsh is the *first-quarter* report (一季报), not an
# earnings preview; the legacy key "quarterly_preview" is retained as an alias
# of "q1" for backwards compatibility. The corporate-action codes added in
# v0.8 follow CNINFO's announcement-category filter and must be confirmed on
# the first live run (see README, "Live-source status").
REPORT_CATEGORIES = {
    "annual": "category_ndbg_szsh;",
    "interim": "category_bndbg_szsh;",
    "quarterly": "category_sjdbg_szsh;",
    "q1": "category_yjdbg_szsh;",
    "quarterly_preview": "category_yjdbg_szsh;",
    "reports": "category_ndbg_szsh;category_bndbg_szsh;category_sjdbg_szsh;category_yjdbg_szsh;",
    "earnings_forecast": "category_yjygjxz_szsh;",
    "distributions": "category_qyfpxzcs_szsh;",
    "corporate_actions": (
        "category_qyfpxzcs_szsh;category_zf_szsh;category_pg_szsh;"
        "category_kzzq_szsh;category_gqjl_szsh;category_jj_szsh;category_gqbd_szsh;"
    ),
    # v0.9: risk warnings / special treatment and delisting / delisting
    # consolidation / clarifications. Penalties, litigation and suspensions
    # are frequently filed under other categories, so for full regulatory
    # coverage catalogue with kind "all" and let extract-regulatory-events
    # classify by title.
    "regulatory": (
        "category_fxts_szsh;category_tbclts_szsh;category_tszlq_szsh;category_cqdq_szsh;"
    ),
    "all": "",
}

PLATE_MAP = {
    "SSE_MAIN": ("sse", "sh"),
    "STAR": ("sse", "shkcp"),
    "SZSE_MAIN": ("szse", "sz"),
    "CHINEXT": ("szse", "szcy"),
    # v1.6 optional boards; parameters UNVERIFIED against the live endpoint
    "BSE": ("bj", "bj"),
    "SSE_B": ("sse", "sh"),
    "SZSE_B": ("szse", "sz"),
}


def clean_title(value: str | None) -> str | None:
    if value is None:
        return None
    value = html.unescape(str(value))
    return re.sub(r"<[^>]+>", "", value).strip()


def announcement_date(value) -> str | None:
    if value in (None, ""):
        return None
    if value in (0, "0"):
        return None
    try:
        # CNINFO returns announcementTime as epoch milliseconds; normalise to China Standard Time.
        ts = int(value) / 1000
        return datetime.fromtimestamp(ts, tz=timezone.utc).astimezone(CHINA_TZ).date().isoformat()
    except (TypeError, ValueError, OverflowError):
        return str(value)[:10]


# China Standard Time, UTC+8 with no daylight saving since 1991. A fixed
# offset avoids zoneinfo, which needs the separate tzdata package on Windows.
CHINA_TZ = timezone(timedelta(hours=8))

# v1.3: corporate social responsibility, sustainability and ESG reports
SUSTAINABILITY_RE = re.compile(r"(社会责任报告|可持续发展报告|ESG报告|ESG 报告|环境、社会及(?:公司)?治理(?:\(ESG\)|（ESG）)?报告|环境、社会和(?:公司)?治理报告)")

REPORT_KINDS = ("annual_report", "interim_report", "quarterly_report")


def classify_title(title: str | None) -> str:
    """Classify a CNINFO announcement title.

    Periodic reports are separated from their summaries (摘要), English
    versions and enquiry letters about them, so that financial extraction
    targets the full Chinese report only.
    """
    title = title or ""
    if any(k in title for k in ("问询函", "关注函", "监管工作函", "回复")):
        return "regulatory_enquiry"
    if SUSTAINABILITY_RE.search(title) and "摘要" not in title:
        return "sustainability_report"
    base = None
    if "半年度报告" in title or "半年报" in title:
        base = "interim_report"
    elif "季度报告" in title or "季报" in title:
        base = "quarterly_report"
    elif "年度报告" in title or "年报" in title:
        base = "annual_report"
    if base:
        if "摘要" in title:
            return base + "_summary"
        if "英文" in title or "English" in title:
            return base + "_english"
        return base
    if "业绩预告" in title or "业绩快报" in title:
        return "earnings_forecast_or_flash"
    keywords = (
        "重大资产重组", "重大合同", "关联交易", "对外担保", "对外投资",
        "收购", "出售资产", "股权激励", "回购", "增持", "减持",
        "分红", "利润分配", "权益分派", "送股", "转增", "配股",
        "非公开发行", "向特定对象发行", "可转债", "转股", "注销", "股份变动",
        "诉讼", "仲裁", "监管", "纪律处分", "行政处罚", "立案", "警示函", "会计差错", "审计意见",
        "风险提示", "退市", "停牌", "复牌", "控制权", "实际控制人",
    )
    if any(k in title for k in keywords):
        return "material_or_risk_announcement"
    return "other_announcement"


def document_url(adjunct_url: str | None) -> str | None:
    if not adjunct_url:
        return None
    if adjunct_url.startswith("http://") or adjunct_url.startswith("https://"):
        return adjunct_url
    return CNINFO_STATIC_BASE.rstrip("/") + "/" + adjunct_url.lstrip("/")


class CNInfoDisclosureAdapter:
    name = "CNINFO"

    def __init__(self):
        self.http = RateLimitedClient(USER_AGENT, REQUESTS_PER_SECOND)

    def query_pages(
        self,
        company: Company,
        since: str,
        until: str,
        kind: str = "reports",
        page_size: int = 30,
        max_pages: int = 10000,
    ) -> Iterable[tuple[int, dict, bytes]]:
        if company.board not in PLATE_MAP:
            raise ValueError(f"Unsupported board for CNINFO disclosure query: {company.board}")
        if not company.org_id:
            raise ValueError(f"Company {company.security_code} has no CNINFO org_id")
        if kind not in REPORT_CATEGORIES:
            raise ValueError(f"Unknown disclosure kind: {kind}")

        column, plate = PLATE_MAP[company.board]
        stock = f"{company.security_code},{company.org_id}"
        category = REPORT_CATEGORIES[kind]

        for page in range(1, max_pages + 1):
            payload = {
                "pageNum": str(page),
                "pageSize": str(min(page_size, 30)),
                "tabName": "fulltext",
                "column": column,
                "stock": stock,
                "searchkey": "",
                "secid": "",
                "plate": plate,
                "category": category,
                "trade": "",
                "seDate": f"{since}~{until}",
                "sortName": "",
                "sortType": "",
                "isHLtitle": "true",
            }
            response = self.http.post(
                CNINFO_QUERY_URL,
                data=payload,
                headers={
                    "Referer": "https://www.cninfo.com.cn/new/commonUrl?url=disclosure/list/notice",
                    "Origin": "https://www.cninfo.com.cn",
                    "X-Requested-With": "XMLHttpRequest",
                    "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                },
            )
            data = response.json()
            yield page, data, response.content
            announcements = data.get("announcements") or []
            if not announcements or not data.get("hasMore"):
                break

    def query_market_pages(self, since: str, until: str, column: str = "szse", kind: str = "all",
                           page_size: int = 30, max_pages: int = 2000) -> Iterable[tuple[int, dict, bytes]]:
        """All companies' announcements in a date range for one exchange column (v1.9).

        Same endpoint and form as the per-company query, with the stock field
        left empty. The parameters follow CNINFO's announcement search; they are
        UNVERIFIED against the live site and are checked by the self-test.
        """
        if kind not in REPORT_CATEGORIES:
            raise ValueError(f"Unknown disclosure kind: {kind}")
        for page in range(1, max_pages + 1):
            payload = {"pageNum": str(page), "pageSize": str(min(page_size, 30)), "tabName": "fulltext",
                       "column": column, "stock": "", "searchkey": "", "secid": "", "plate": "",
                       "category": REPORT_CATEGORIES[kind], "trade": "", "seDate": f"{since}~{until}",
                       "sortName": "", "sortType": "", "isHLtitle": "true"}
            response = self.http.post(CNINFO_QUERY_URL, data=payload, headers={
                "Referer": "https://www.cninfo.com.cn/new/commonUrl?url=disclosure/list/notice",
                "Origin": "https://www.cninfo.com.cn", "X-Requested-With": "XMLHttpRequest",
                "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8"})
            data = response.json()
            yield page, data, response.content
            if not (data.get("announcements") or []) or not data.get("hasMore"):
                break

    def close(self):
        self.http.close()


def _safe_filename(value: str, limit: int = 120) -> str:
    value = re.sub(r"[\\/:*?\"<>|\r\n]+", "_", value)
    return value.strip(" ._")[:limit] or "document"


def persist_disclosures(
    company: Company,
    pages: Iterable[tuple[int, dict, bytes]],
    kind: str,
    download_documents: bool = False,
) -> dict:
    base_dir = disclosure_dir()
    base_dir.mkdir(parents=True, exist_ok=True)
    session = SessionLocal()
    adapter = CNInfoDisclosureAdapter() if download_documents else None
    inserted = updated = downloaded = 0
    raw_pages = 0
    try:
        for page_num, data, raw_bytes in pages:
            raw_pages += 1
            store_raw(
                "CNINFO",
                CNINFO_QUERY_URL,
                raw_bytes,
                {
                    "content_type": "application/json",
                    "company_id": company.id,
                    "security_code": company.security_code,
                    "board": company.board,
                    "kind": kind,
                    "page_num": page_num,
                },
            )
            for item in data.get("announcements") or []:
                row, created = persist_announcement(session, company, item)
                if row is None:
                    continue
                inserted += created
                updated += not created
                if download_documents and row.document_url and not (row.local_path and Path(row.local_path).exists()):
                    store_downloaded(adapter, company, row)
                    downloaded += 1

                session.commit()
    finally:
        session.close()
        if adapter:
            adapter.close()
    return {"inserted": inserted, "updated": updated, "downloaded": downloaded, "raw_pages": raw_pages}


def persist_announcement(session, company: Company, item: dict):
    """Upsert one announcement record; returns (row, created) or (None, False)."""
    ann_id = str(item.get("announcementId") or item.get("announcementID") or "").strip()
    adjunct = item.get("adjunctUrl") or ""
    if not ann_id and adjunct:
        ann_id = hashlib.sha256(adjunct.encode()).hexdigest()[:40]
    if not ann_id:
        return None, False
    title = clean_title(item.get("announcementTitle")) or ""
    row = session.query(Disclosure).filter_by(company_id=company.id, announcement_id=ann_id).one_or_none()
    created = row is None
    if created:
        row = Disclosure(company_id=company.id, announcement_id=ann_id)
        session.add(row)
    row.announcement_date = announcement_date(item.get("announcementTime"))
    row.title_cn = title
    row.announcement_type_cn = item.get("announcementTypeName") or item.get("announcementType")
    row.kind = classify_title(title)
    row.adjunct_url = adjunct
    row.document_url = document_url(adjunct)
    row.sec_code = item.get("secCode") or company.security_code
    row.sec_name = item.get("secName") or company.short_name_cn
    row.raw_json = json.dumps(item, ensure_ascii=False)
    row.source = "CNINFO"
    row.retrieved_at = utcnow()
    return row, created


def store_downloaded(adapter, company: Company, row) -> str:
    """Download a disclosure's document into the content-addressed archive (v1.9: shared helper)."""
    base_dir = disclosure_dir()
    response = adapter.http.get(row.document_url)
    content = response.content
    digest = hashlib.sha256(content).hexdigest()
    adjunct = row.adjunct_url or row.document_url or ""
    ext = ".pdf" if ("pdf" in (response.headers.get("content-type") or "").lower() or adjunct.lower().endswith(".pdf")) \
        else Path(adjunct).suffix or ".bin"
    target_dir = base_dir / company.security_code
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / f"{digest}{ext}"
    if not target.exists():
        target.write_bytes(content)
    if row.sha256 != digest:
        row.extracted_version = None        # v2.0.6: a new or changed document is read again
    row.local_path = str(target)
    row.sha256 = digest
    row.content_type = response.headers.get("content-type")
    row.file_size = len(content)
    return str(target)
