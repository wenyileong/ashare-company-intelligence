from ..timeutil import utcnow
from datetime import datetime
from .base import SourceAdapter, SourceRecord
from ..http import RateLimitedClient
from ..config import USER_AGENT, REQUESTS_PER_SECOND

class CNInfoAdapter(SourceAdapter):
    name = "CNINFO"

    # v2.0.1: CNINFO publishes ONE code-to-orgId list for all mainland
    # listed shares (Shanghai, Shenzhen and Beijing), despite its file name.
    # The former separate Shanghai list (sse_stock.json) now returns 404,
    # which broke "Update the company list" on the first live run. The
    # exchange is inferred from each security code. ASHARE_CNINFO_STOCK_LIST_URL
    # overrides the address if CNINFO moves it again.
    STOCK_LIST_URL = "https://www.cninfo.com.cn/new/data/szse_stock.json"
    # Kept for reference and for the self-test's diagnostic only.
    LEGACY_SSE_URL = "https://www.cninfo.com.cn/new/data/sse_stock.json"

    @classmethod
    def stock_list_url(cls) -> str:
        import os
        return os.environ.get("ASHARE_CNINFO_STOCK_LIST_URL") or cls.STOCK_LIST_URL

    def __init__(self):
        self.http = RateLimitedClient(USER_AGENT, REQUESTS_PER_SECOND)
        self.last_source_records = []

    def _fetch(self, url: str):
        r = self.http.get(url)
        return r, r.json()

    @staticmethod
    def _value(item, *keys):
        for key in keys:
            value = item.get(key)
            if value not in (None, ""):
                return str(value).strip()
        return None

    def get_stock_mappings(self):
        from ..universe import infer_exchange
        url = self.stock_list_url()
        response, data = self._fetch(url)
        stock_list = (data.get("stockList") or data.get("data") or []) if isinstance(data, dict) else []
        counts: dict[str, int] = {}
        for item in stock_list:
            code = self._value(item, "code", "securityCode", "stockCode")
            if code and code.isdigit():
                ex = infer_exchange(code.zfill(6)) or "OTHER"
                counts[ex] = counts.get(ex, 0) + 1
        self.last_source_records.append(SourceRecord(
            source=self.name, url=url, company_key=None,
            content_type=response.headers.get("content-type"), payload=response.content,
            metadata={"exchange": "ALL", "retrieved_at": utcnow().isoformat(),
                      "record_count": len(stock_list), "by_exchange": counts},
        ))
        for item in stock_list:
            code = self._value(item, "code", "securityCode", "stockCode")
            if not code or not code.isdigit():
                continue
            code = code.zfill(6)
            yield {
                "exchange": infer_exchange(code) or "OTHER",
                "code": code,
                "org_id": self._value(item, "orgId", "orgID"),
                "short_name_cn": self._value(item, "zwjc", "shortName", "secName", "name"),
                "legal_name_cn": self._value(item, "gsqc", "companyName", "fullName", "orgName"),
                "listing_date": self._value(item, "listingDate", "listDate"),
                "status": self._value(item, "status", "state"),
                "category": self._value(item, "category"),
                "raw": item,
            }

    def get_universe(self):
        # Convert the official mappings into source records.
        yield from self.get_stock_mappings()

    def close(self):
        self.http.close()
