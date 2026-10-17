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


def acquire_market_data(security_code: str | None, start: str, end: str, provider: str = "eastmoney", adjust: str = "none") -> dict:
    session = SessionLocal()
    totals = {"companies": 0, "bars_inserted": 0, "bars_updated": 0, "errors": []}
    try:
        q = session.query(Company)
        if security_code:
            q = q.filter(Company.security_code == security_code.zfill(6))
        companies = q.order_by(Company.security_code).all()
        for company in companies:
            totals["companies"] += 1
            try:
                if provider == "eastmoney":
                    bars = fetch_eastmoney_bars(company, start, end, adjust)
                else:
                    raise ValueError(f"Unknown market provider: {provider}")
                result = persist_bars(company, bars)
                totals["bars_inserted"] += result["inserted"]
                totals["bars_updated"] += result["updated"]
            except Exception as exc:
                totals["errors"].append((company.security_code, str(exc)))
        return totals
    finally:
        session.close()


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

    Run after the close: the values are the day's final prices only then. The
    endpoint and field codes follow Eastmoney's public list API and are
    UNVERIFIED against the live site; the self-test checks them.
    """
    client = RateLimitedClient(USER_AGENT, MARKET_RPS)
    out = []
    try:
        for pn in range(1, max_pages + 1):
            params = {"pn": pn, "pz": page_size, "po": 1, "np": 1, "fltt": 2, "invt": 2, "fid": "f12",
                      "fs": EASTMONEY_LIST_FS, "fields": "f2,f3,f4,f5,f6,f8,f12,f13,f14,f15,f16,f17,f18",
                      "ut": "bd1d9ddb04089700cf9c27f6f7426281"}
            payload = client.get(EASTMONEY_LIST_URL, params=params).json()
            data = (payload or {}).get("data") or {}
            rows = data.get("diff") or []
            if isinstance(rows, dict):
                rows = list(rows.values())
            for r in rows:
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
            total = data.get("total") or 0
            if not rows or pn * page_size >= total:
                break
    finally:
        client.close()
    return out


def fetch_listing_info(page_size: int = 100, max_pages: int = 100) -> dict[str, dict]:
    """Listing date and current name of every security in the public quote list
    (v2.0.2; field f26 is the listing date as YYYYMMDD). About 60 requests.
    UNVERIFIED against the live site; the self-test's quote-list check covers
    the endpoint."""
    client = RateLimitedClient(USER_AGENT, MARKET_RPS)
    out: dict[str, dict] = {}
    try:
        for pn in range(1, max_pages + 1):
            params = {"pn": pn, "pz": page_size, "po": 1, "np": 1, "fltt": 2, "invt": 2, "fid": "f12",
                      "fs": EASTMONEY_LIST_FS, "fields": "f12,f14,f26", "ut": "bd1d9ddb04089700cf9c27f6f7426281"}
            payload = client.get(EASTMONEY_LIST_URL, params=params).json()
            data = (payload or {}).get("data") or {}
            rows = data.get("diff") or []
            if isinstance(rows, dict):
                rows = list(rows.values())
            for r in rows:
                code = str(r.get("f12") or "").zfill(6)
                raw = str(r.get("f26") or "").strip()
                ld = f"{raw[:4]}-{raw[4:6]}-{raw[6:8]}" if len(raw) == 8 and raw.isdigit() and raw != "00000000" \
                    else None
                out[code] = {"name": r.get("f14"), "listing_date": ld}
            total = data.get("total") or 0
            if not rows or pn * page_size >= total:
                break
    finally:
        client.close()
    return out


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
