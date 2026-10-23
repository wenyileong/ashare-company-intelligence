"""The exchanges' own stock lists, as a source of listing dates (v2.0.7, findings 58 and 66).

In October 2026 Eastmoney's public quote list, the only source of listing
dates until v2.0.6, refused every request from the author's network for hours
at a time. The Shanghai and Shenzhen stock exchanges publish their own lists
of listed companies, with each company's listing date, on their websites:

* Shanghai: the query behind the exchange's stock-list page
  (``query.sse.com.cn/sseQuery/commonQuery.do``), one request for the main
  board and one for STAR, answered in JSON (``LIST_DATE``);
* Shenzhen: the A-share list offered for download on the exchange's
  stock-list page (``www.szse.cn/api/report/ShowReport``, an Excel file with
  the column ``A股上市日期``), one request for the main board and ChiNext.

These are the exchanges' own records, so they are preferred to the quote
list: three requests in all. Every response is kept in the raw archive with
its hash. The parameters are those the exchanges' pages send; they are not
documented as an interface and are checked live by "Update the company list",
which reports what each list returned. The Excel file is read with a small
reader here (an .xlsx file is a zip of XML), so no new dependency is needed.
"""
from __future__ import annotations

import io
import re
import zipfile
from datetime import date, timedelta

from lxml import etree

from .config import USER_AGENT, REQUESTS_PER_SECOND
from .http import RateLimitedClient

SSE_URL = "https://query.sse.com.cn/sseQuery/commonQuery.do"
SSE_REFERER = "https://www.sse.com.cn/assortment/stock/list/share/"
SZSE_URL = "https://www.szse.cn/api/report/ShowReport"
SZSE_REFERER = "https://www.szse.cn/market/product/stock/list/index.html"
# (key, name, minimum rows for the list to count as whole)
LISTS = (("sse_main", "Shanghai main board", 1000), ("sse_star", "STAR Market", 300),
         ("szse_a", "Shenzhen A shares (main board and ChiNext)", 2000))
_NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}


def normalise_listing_date(v) -> str | None:
    """YYYY-MM-DD from '20010827', '2001-08-27', '2001/08/27' or an Excel day number."""
    if v is None:
        return None
    t = str(v).strip()
    if not t or t in ("-", "--", "0", "00000000"):
        return None
    m = re.fullmatch(r"(\d{4})[-/.]?(\d{2})[-/.]?(\d{2})(?:[ T].*)?", t)
    if m:
        y, mo, d = (int(x) for x in m.groups())
        try:
            return date(y, mo, d).isoformat()
        except ValueError:
            return None
    try:
        n = float(t)
    except ValueError:
        return None
    if 10000 < n < 80000:                      # an Excel serial day (1927 to 2119)
        return (date(1899, 12, 30) + timedelta(days=int(n))).isoformat()
    return None


def read_xlsx(content: bytes) -> list[list[str]]:
    """The first worksheet of an .xlsx file as rows of cell texts (shared strings, inline strings, numbers)."""
    z = zipfile.ZipFile(io.BytesIO(content))
    shared: list[str] = []
    if "xl/sharedStrings.xml" in z.namelist():
        root = etree.fromstring(z.read("xl/sharedStrings.xml"))
        for si in root.findall("m:si", _NS):
            shared.append("".join(t.text or "" for t in si.iter("{%s}t" % _NS["m"])))
    sheets = sorted(n for n in z.namelist() if re.fullmatch(r"xl/worksheets/sheet\d+\.xml", n))
    if not sheets:
        return []
    root = etree.fromstring(z.read(sheets[0]))
    rows = []
    for r in root.iter("{%s}row" % _NS["m"]):
        cells: dict[int, str] = {}
        for c in r.findall("m:c", _NS):
            ref = c.get("r") or ""
            letters = re.match(r"[A-Z]+", ref)
            col = 0
            for ch in (letters.group(0) if letters else ""):
                col = col * 26 + ord(ch) - 64
            col = col - 1 if col else len(cells)
            typ = c.get("t")
            if typ == "inlineStr":
                val = "".join(t.text or "" for t in c.iter("{%s}t" % _NS["m"]))
            else:
                v = c.find("m:v", _NS)
                val = v.text if v is not None and v.text is not None else ""
                if typ == "s" and val.isdigit() and int(val) < len(shared):
                    val = shared[int(val)]
            cells[col] = val.strip()
        if cells:
            rows.append([cells.get(i, "") for i in range(max(cells) + 1)])
    return rows


def _code(v) -> str | None:
    t = str(v or "").strip()
    t = re.sub(r"\.0+$", "", t)
    return t.zfill(6) if t.isdigit() and len(t) <= 6 else None


def parse_sse(payload: dict) -> list[dict]:
    out = []
    for r in (payload or {}).get("result") or []:
        code = _code(r.get("A_STOCK_CODE") or r.get("SECURITY_CODE_A") or r.get("COMPANY_CODE"))
        if code:
            out.append({"code": code, "name": r.get("COMPANY_ABBR") or r.get("SEC_NAME_CN"),
                        "listing_date": normalise_listing_date(r.get("LIST_DATE"))})
    return out


def parse_szse(content: bytes) -> list[dict]:
    rows = read_xlsx(content)
    if not rows:
        return []
    head = rows[0]

    def col(*names):
        for n in names:
            if n in head:
                return head.index(n)
        return None
    ci, ni, di = col("A股代码", "证券代码"), col("A股简称", "证券简称"), col("A股上市日期", "上市日期")
    if ci is None or di is None:
        raise ValueError(f"unexpected columns in the Shenzhen list: {head[:8]}")
    out = []
    for r in rows[1:]:
        code = _code(r[ci] if ci < len(r) else None)
        if code:
            out.append({"code": code, "name": r[ni] if ni is not None and ni < len(r) else None,
                        "listing_date": normalise_listing_date(r[di] if di < len(r) else None)})
    return out


class ExchangeListing(dict):
    """code -> {name, listing_date, source}, with what each list returned."""
    lists: dict = {}
    complete = False


def exchange_listing_info(client: RateLimitedClient | None = None, store: bool = True) -> ExchangeListing:
    """Listing dates from the exchanges' stock lists (three requests). A list that fails is reported, not raised."""
    from .storage import store_raw
    own = client is None
    client = client or RateLimitedClient(USER_AGENT, REQUESTS_PER_SECOND, retries=2)
    out = ExchangeListing()
    out.lists = {}

    def keep(key, name, minimum, rows, error=None):
        dated = sum(1 for r in rows if r["listing_date"])
        out.lists[key] = {"name": name, "rows": len(rows), "dated": dated, "error": error,
                          "whole": error is None and len(rows) >= minimum}
        for r in rows:
            if r["code"] not in out:
                out[r["code"]] = {"name": r["name"], "listing_date": r["listing_date"], "source": key}

    try:
        for key, name, minimum in LISTS:
            try:
                if key.startswith("sse"):
                    params = {"STOCK_TYPE": "1" if key == "sse_main" else "8", "REG_PROVINCE": "", "CSRC_CODE": "",
                              "STOCK_CODE": "", "sqlId": "COMMON_SSE_CP_GPJCTPZ_GPLB_GP_L",
                              "COMPANY_STATUS": "2,4,5,7,8", "type": "inParams", "isPagination": "true",
                              "pageHelp.cacheSize": "1", "pageHelp.beginPage": "1", "pageHelp.pageSize": "10000",
                              "pageHelp.pageNo": "1", "pageHelp.endPage": "1"}
                    r = client.get(SSE_URL, params=params, headers={"Referer": SSE_REFERER})
                    if store:
                        store_raw("SSE", str(r.url), r.content, {"content_type": "application/json", "list": key})
                    rows = parse_sse(r.json())
                else:
                    params = {"SHOWTYPE": "xlsx", "CATALOGID": "1110", "TABKEY": "tab1"}
                    r = client.get(SZSE_URL, params=params, headers={"Referer": SZSE_REFERER})
                    if store:
                        store_raw("SZSE", str(r.url), r.content, {"content_type": "application/vnd.openxmlformats-"
                                                                  "officedocument.spreadsheetml.sheet", "list": key})
                    rows = parse_szse(r.content)
                keep(key, name, minimum, rows)
            except Exception as exc:              # a list that fails is reported; the others still count
                from .quotelist import _describe
                keep(key, name, minimum, [], _describe(exc))
    finally:
        if own:
            client.close()
    out.complete = all(v["whole"] for v in out.lists.values())
    return out


def summary(info: ExchangeListing) -> str:
    return "; ".join(f"{v['name']} {v['dated']:,} of {v['rows']:,} dated" + (f" ({v['error']})" if v["error"] else "")
                     for v in info.lists.values())
