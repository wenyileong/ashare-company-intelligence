from bs4 import BeautifulSoup
from .base import SourceAdapter
from ..http import RateLimitedClient
from ..config import USER_AGENT, REQUESTS_PER_SECOND

class SSEAdapter(SourceAdapter):
    name = "SSE"

    def __init__(self):
        self.http = RateLimitedClient(USER_AGENT, REQUESTS_PER_SECOND)
        self.url = "https://www.sse.com.cn/assortment/stock/list/share/"

    def get_universe(self):
        r = self.http.get(self.url)
        soup = BeautifulSoup(r.text, "lxml")
        rows = []
        for tr in soup.find_all("tr"):
            cells = [c.get_text(" ", strip=True) for c in tr.find_all(["td", "th"])]
            if len(cells) >= 4 and cells[0].isdigit():
                code = cells[0].zfill(6)
                if code.startswith(("600", "601", "603", "605", "688")):
                    rows.append({
                        "code": code,
                        "exchange": "SSE",
                        "short_name_cn": cells[1],
                        "legal_name_cn": cells[3],
                    })
        return rows

    def close(self):
        self.http.close()

class SZSEAdapter(SourceAdapter):
    name = "SZSE"

    def __init__(self):
        self.http = RateLimitedClient(USER_AGENT, REQUESTS_PER_SECOND)
        self.url = "https://www.szse.cn/market/product/stock/list/index.html"

    def get_universe(self):
        # SZSE's public frontend is dynamic. We retain this adapter as a
        # validation hook rather than guessing its internal AJAX endpoint.
        r = self.http.get(self.url)
        return {
            "status": r.status_code,
            "url": str(r.url),
            "content_type": r.headers.get("content-type"),
        }

    def close(self):
        self.http.close()
