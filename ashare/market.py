from __future__ import annotations
from .timeutil import utcnow

import csv
import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Iterable

from .config import market_raw_dir, MARKET_RPS, USER_AGENT
from .http import RateLimitedClient
from .models import SessionLocal, Company, MarketBar, MarketSnapshot


def _num(value):
    if value is None or value == "":
        return None
    s = str(value).strip().replace(",", "").replace("，", "")
    if s in {"-", "--", "null", "None"}:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _normalise_date(value):
    if not value:
        return None
    value = str(value).strip().replace("/", "-")
    if len(value) >= 10:
        return value[:10]
    return value


def _secid(company: Company) -> str:
    market = "1" if company.exchange == "SSE" else "0"
    return f"{market}.{company.security_code}"


def fetch_eastmoney_bars(company: Company, start: str, end: str, adjust: str = "none") -> list[dict]:
    """Optional public-feed adapter. It is not represented as exchange-authoritative data."""
    fqt = {"none": "0", "forward": "1", "backward": "2"}.get(adjust, "0")
    url = "https://push2his.eastmoney.com/api/qt/stock/kline/get"
    params = {
        "secid": _secid(company),
        "klt": "101",
        "fqt": fqt,
        "beg": start.replace("-", ""),
        "end": end.replace("-", ""),
        "fields1": "f1,f2,f3,f4,f5,f6",
        "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61",
        "ut": "7eea3edcaed734bea9cbfc24409ed989",
    }
    client = RateLimitedClient(USER_AGENT, MARKET_RPS)
    try:
        response = client.get(url, params=params)
        payload = response.json()
    finally:
        client.close()
    base = market_raw_dir()
    base.mkdir(parents=True, exist_ok=True)
    raw_bytes = response.content
    digest = hashlib.sha256(raw_bytes).hexdigest()
    raw_path = base / f"{digest}.json"
    if not raw_path.exists():
        raw_path.write_bytes(raw_bytes)
    from .storage import register_raw
    register_raw("EASTMONEY_PUBLIC", str(response.url), digest, raw_path, {
        "content_type": "application/json", "company_id": company.id,
        "security_code": company.security_code, "start": start, "end": end,
        "adjustment": adjust,
    })

    data = (payload.get("data") or {}).get("klines") or []
    bars = []
    for row in data:
        parts = row.split(",")
        if len(parts) < 7:
            continue
        bars.append({
            "trade_date": _normalise_date(parts[0]),
            "open": _num(parts[1]),
            "close": _num(parts[2]),
            "high": _num(parts[3]),
            "low": _num(parts[4]),
            "volume": _num(parts[5]),
            "amount": _num(parts[6]),
            "pct_change": _num(parts[8]) if len(parts) > 8 else None,
            "change": _num(parts[9]) if len(parts) > 9 else None,
            "prev_close": (_num(parts[2]) - _num(parts[9])) if len(parts) > 9 and _num(parts[2]) is not None and _num(parts[9]) is not None else None,
            "turnover_rate": _num(parts[10]) if len(parts) > 10 else None,
            "adjustment": adjust,
            # Eastmoney daily volume is reported in lots (手) of 100 shares.
            "volume_unit": "LOTS_100_SHARES",
            "source": "EASTMONEY_PUBLIC",
            "raw_json": json.dumps({"provider": "EASTMONEY_PUBLIC", "raw_record": parts, "raw_sha256": digest, "raw_path": str(raw_path)}, ensure_ascii=False),
        })
    return bars


def persist_bars(company: Company, bars: Iterable[dict]) -> dict:
    session = SessionLocal()
    inserted = updated = 0
    try:
        for b in bars:
            if not b.get("trade_date"):
                continue
            row = session.query(MarketBar).filter_by(
                company_id=company.id,
                trade_date=b["trade_date"],
                adjustment=b.get("adjustment", "none"),
                source=b.get("source", "UNKNOWN"),
            ).one_or_none()
            if row is None:
                row = MarketBar(
                    company_id=company.id,
                    trade_date=b["trade_date"],
                    adjustment=b.get("adjustment", "none"),
                    source=b.get("source", "UNKNOWN"),
                )
                session.add(row)
                inserted += 1
            else:
                updated += 1
            for field in ("open", "high", "low", "close", "prev_close", "volume", "amount", "pct_change", "change", "turnover_rate", "status", "volume_unit", "raw_json"):
                if field in b:
                    setattr(row, field, b[field])
            row.retrieved_at = utcnow()
        session.commit()
        return {"inserted": inserted, "updated": updated}
    finally:
        session.close()


def import_bars_csv(path: str, security_code: str | None = None, source: str = "CSV_IMPORT") -> dict:
    """Import a normalised CSV. Required: date/open/high/low/close; code is required for whole-universe files."""
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(path)
    session = SessionLocal()
    inserted = updated = skipped = 0
    errors = []
    try:
        with p.open("r", encoding="utf-8-sig", newline="") as fh:
            reader = csv.DictReader(fh)
            for row in reader:
                code = str(security_code or row.get("security_code") or row.get("code") or "").strip().zfill(6)
                company = session.query(Company).filter_by(security_code=code).first()
                if not company:
                    skipped += 1
                    errors.append((code, "company not found"))
                    continue
                b = {
                    "trade_date": _normalise_date(row.get("trade_date") or row.get("date")),
                    "open": _num(row.get("open")),
                    "high": _num(row.get("high")),
                    "low": _num(row.get("low")),
                    "close": _num(row.get("close")),
                    "prev_close": _num(row.get("prev_close")),
                    "volume": _num(row.get("volume")),
                    "amount": _num(row.get("amount") or row.get("turnover")),
                    "pct_change": _num(row.get("pct_change") or row.get("change_pct")),
                    "turnover_rate": _num(row.get("turnover_rate")),
                    "volume_unit": row.get("volume_unit") or None,
                    "adjustment": row.get("adjustment") or "none",
                    "source": source,
                }
                if not b["trade_date"] or b["close"] is None:
                    skipped += 1
                    errors.append((code, "missing date/close"))
                    continue
                existing = session.query(MarketBar).filter_by(
                    company_id=company.id, trade_date=b["trade_date"],
                    adjustment=b["adjustment"], source=source,
                ).one_or_none()
                if existing is None:
                    session.add(MarketBar(company_id=company.id, **b))
                    inserted += 1
                else:
                    for k, v in b.items():
                        setattr(existing, k, v)
                    existing.retrieved_at = utcnow()
                    updated += 1
        session.commit()
        return {"inserted": inserted, "updated": updated, "skipped": skipped, "errors": errors}
    finally:
        session.close()


# --- v2.0.8 (finding 73): a second public source, and the author's choice ------------------------------------------

TENCENT_KLINE_URL = "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get"
_TENCENT_FQ = {"none": "", "forward": "qfq", "backward": "hfq"}


def _tencent_symbol(company: Company) -> str:
    prefix = {"SSE": "sh", "SZSE": "sz", "BSE": "bj"}.get(company.exchange or "", "sh" if
                                                            str(company.security_code).startswith("6") else "sz")
    return f"{prefix}{company.security_code}"


def _windows(start: str, end: str, years: int = 2):
    from datetime import date
    a, b = date.fromisoformat(start), date.fromisoformat(end)
    while a <= b:
        c = min(b, date(a.year + years, a.month, min(a.day, 28)))
        yield a.isoformat(), c.isoformat()
        a = date.fromordinal(c.toordinal() + 1)


def fetch_tencent_bars(company: Company, start: str, end: str, adjust: str = "none") -> list[dict]:
    """Daily bars from Tencent's public quote service (labelled TENCENT_PUBLIC).

    Like Eastmoney's, this is an unofficial public feed, not exchange-authoritative, and its terms are the user's
    to check. The request is the one its public pages send: ``param=sh600519,day,START,END,640,FQ`` (FQ empty,
    ``qfq`` or ``hfq``), answered with rows ``[date, open, close, high, low, volume in lots]``. At most 640 rows come
    back per request, so long periods are asked for two years at a time."""
    fq = _TENCENT_FQ.get(adjust, "")
    sym = _tencent_symbol(company)
    key = {"": "day", "qfq": "qfqday", "hfq": "hfqday"}[fq]
    client = RateLimitedClient(USER_AGENT, MARKET_RPS)
    bars: dict[str, dict] = {}
    try:
        for a, b in _windows(start, end):
            r = client.get(TENCENT_KLINE_URL, params={"param": f"{sym},day,{a},{b},640,{fq}"})
            raw_bytes = r.content
            payload = r.json()
            digest = hashlib.sha256(raw_bytes).hexdigest()
            base = market_raw_dir()
            base.mkdir(parents=True, exist_ok=True)
            raw_path = base / f"{digest}.json"
            if not raw_path.exists():
                raw_path.write_bytes(raw_bytes)
            from .storage import register_raw
            register_raw("TENCENT_PUBLIC", str(r.url), digest, raw_path, {
                "content_type": "application/json", "company_id": company.id, "security_code": company.security_code,
                "start": a, "end": b, "adjustment": adjust})
            node = ((payload or {}).get("data") or {}).get(sym) or {}
            rows = node.get(key) or node.get("day") or []
            for row in rows:
                if not isinstance(row, list) or len(row) < 6:
                    continue
                d = _normalise_date(row[0])
                bars[d] = {"trade_date": d, "open": _num(row[1]), "close": _num(row[2]), "high": _num(row[3]),
                           "low": _num(row[4]), "volume": _num(row[5]), "amount": None, "adjustment": adjust,
                           "volume_unit": "LOTS_100_SHARES", "source": "TENCENT_PUBLIC",
                           "raw_json": json.dumps({"provider": "TENCENT_PUBLIC", "raw_record": row,
                                                   "raw_sha256": digest, "raw_path": str(raw_path)},
                                                  ensure_ascii=False)}
    finally:
        client.close()
    out = [bars[k] for k in sorted(bars)]
    for prev, cur in zip(out, out[1:]):
        cur["prev_close"] = prev["close"]
        if prev["close"] and cur["close"] is not None:
            cur["change"] = round(cur["close"] - prev["close"], 4)
            cur["pct_change"] = round((cur["close"] / prev["close"] - 1) * 100, 4)
    return out


PROVIDERS = {"eastmoney": ("EASTMONEY_PUBLIC", "fetch_eastmoney_bars"),
             "tencent": ("TENCENT_PUBLIC", "fetch_tencent_bars")}
PRICE_SOURCES = tuple(PROVIDERS) + ("none",)


def price_source() -> str:
    """The author's chosen price source (Settings; ASHARE_PRICE_SOURCE): eastmoney, tencent or none."""
    import os
    v = (os.environ.get("ASHARE_PRICE_SOURCE") or "eastmoney").strip().lower()
    return v if v in PRICE_SOURCES else "eastmoney"


def _fetcher(provider: str):
    if provider not in PROVIDERS:
        raise ValueError(f"Unknown price source: {provider} (choose {', '.join(PROVIDERS)}; or import a CSV)")
    return globals()[PROVIDERS[provider][1]]


def acquire_market_data(security_code: str | None, start: str, end: str, provider: str | None = None,
                        adjust: str = "none", raise_errors: bool = False) -> dict:
    """Daily bars from the chosen public source (v2.0.8: eastmoney or tencent; default from Settings)."""
    provider = (provider or price_source()).lower()
    if provider == "none":
        raise ValueError("The price source is 'none': import prices from a CSV file instead ('Import prices').")
    fetch = _fetcher(provider)
    session = SessionLocal()
    totals = {"provider": provider, "companies": 0, "bars_inserted": 0, "bars_updated": 0, "errors": []}
    try:
        q = session.query(Company)
        if security_code:
            q = q.filter(Company.security_code == security_code.zfill(6))
        companies = q.order_by(Company.security_code).all()
        for company in companies:
            totals["companies"] += 1
            try:
                bars = fetch(company, start, end, adjust)
                result = persist_bars(company, bars)
                totals["bars_inserted"] += result["inserted"]
                totals["bars_updated"] += result["updated"]
            except Exception as exc:
                if raise_errors:
                    raise
                totals["errors"].append((company.security_code, str(exc)))
        return totals
    finally:
        session.close()


def diagnose_prices(security_code: str, days: int = 30) -> dict:
    """'Test price sources': ask each public source for one company's last ``days`` days, store nothing, and
    report what each returned, so that the author can choose (finding 73)."""
    from datetime import date, timedelta
    from .models import init_db
    init_db()
    s = SessionLocal()
    try:
        c = s.query(Company).filter_by(security_code=str(security_code).zfill(6)).first()
    finally:
        s.close()
    if c is None:
        raise ValueError(f"no company {security_code}")
    end = date.today()
    start = (end - timedelta(days=days)).isoformat()
    out = []
    for name in PROVIDERS:
        try:
            bars = _fetcher(name)(c, start, end.isoformat())
            out.append({"provider": name, "ok": bool(bars), "bars": len(bars),
                        "last": bars[-1]["trade_date"] if bars else None, "last_close": bars[-1]["close"] if bars else None,
                        "error": None if bars else "answered, but with no prices"})
        except Exception as exc:
            from .quotelist import _describe
            out.append({"provider": name, "ok": False, "bars": 0, "last": None, "last_close": None,
                        "error": _describe(exc)})
    ok = [x["provider"] for x in out if x["ok"]]
    return {"security_code": c.security_code, "from": start, "to": end.isoformat(), "providers": out,
            "suggestion": ok[0] if ok else "none", "current": price_source()}


def show_market(security_code: str, start: str | None = None, end: str | None = None):
    session = SessionLocal()
    try:
        company = session.query(Company).filter_by(security_code=security_code.zfill(6)).first()
        if not company:
            return []
        q = session.query(MarketBar).filter(MarketBar.company_id == company.id)
        if start:
            q = q.filter(MarketBar.trade_date >= start)
        if end:
            q = q.filter(MarketBar.trade_date <= end)
        return q.order_by(MarketBar.trade_date).all()
    finally:
        session.close()


# --- v1.9: whole-market daily snapshot ------------------------------------------------------

EASTMONEY_LIST_URL = "https://push2.eastmoney.com/api/qt/clist/get"
EASTMONEY_LIST_FS = "m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23"   # SZSE main, ChiNext, SSE main, STAR


def fetch_eastmoney_snapshot(trade_date: str, page_size: int = 100, max_pages: int = 100) -> list[dict]:
    """Today's bar for every listed A-share from the public quote list (one request per 100 securities).

    Run after the close: the values are the day's final prices only then.
    v2.0.3: uses the quote-list variant that answers (see ``quotelist``)."""
    from .quotelist import fetch_pages
    # v2.0.6: read through fetch_pages, so that a list longer than one query returns is read board by board
    # (findings 50 and 57). Not cached: prices change during the day.
    r = fetch_pages("f2,f3,f4,f5,f6,f8,f12,f13,f14,f15,f16,f17,f18", "snapshot", max_pages=max_pages,
                    use_cache=False, min_rows=0)
    if not r["complete"]:
        detail = r.get("refused") or r.get("error") or "; ".join(f"{b['name']}: {b.get('error')}" for b in r["parts"].values()
                                             if b.get("error"))
        raise RuntimeError(f"quote list incomplete ({len(r['rows']):,} securities): {detail or 'no answer'}")
    out = []
    for r in r["rows"]:
        close = _num(r.get("f2"))
        if close is None:          # suspended or no trade today
            continue
        out.append({"code": str(r.get("f12")).zfill(6), "trade_date": trade_date, "close": close,
                    "open": _num(r.get("f17")), "high": _num(r.get("f15")), "low": _num(r.get("f16")),
                    "prev_close": _num(r.get("f18")), "pct_change": _num(r.get("f3")),
                    "change": _num(r.get("f4")), "volume": _num(r.get("f5")), "amount": _num(r.get("f6")),
                    "turnover_rate": _num(r.get("f8")), "adjustment": "none", "volume_unit": "LOTS_100_SHARES",
                    "source": "EASTMONEY_PUBLIC",
                    "raw_json": json.dumps({"provider": "EASTMONEY_PUBLIC", "endpoint": "clist", "raw_record": r},
                                           ensure_ascii=False)})
    return out


def fetch_listing_info(page_size: int = 100, max_pages: int = 100, progress=None):
    """Listing date and current name of every security in the public quote list
    (field f26, YYYYMMDD). v2.0.3: resumable, tries several request variants,
    and says how complete the result is (``.complete``, ``.note``)."""
    from .quotelist import listing_info
    return listing_info(progress=progress)


def persist_snapshot(bars: list[dict]) -> dict:
    """Store snapshot bars for the companies in the database."""
    session = SessionLocal()
    try:
        by_code = {c.security_code: c for c in session.query(Company)}
    finally:
        session.close()
    groups: dict[str, list] = {}
    for b in bars:
        if b["code"] in by_code:
            groups.setdefault(b["code"], []).append(b)
    ins = upd = 0
    for code, bs in groups.items():
        r = persist_bars(by_code[code], bs)
        ins += r["inserted"]
        upd += r["updated"]
    return {"securities": len(groups), "inserted": ins, "updated": upd, "unknown": len(bars) - sum(map(len, groups.values()))}
