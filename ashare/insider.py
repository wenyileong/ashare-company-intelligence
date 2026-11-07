"""Directors', supervisors' and senior managers' share dealings (v2.3.0, plan section B6; experimental, switch
``insider``, off by default).

* :func:`dealing_announcements` finds the announcements of such dealings by their titles.
* :func:`extract_dealings` reads the rows of their tables where the text layer has them (name, date, direction,
  shares, price) into ``insider_dealings``. Persons are stored by name like the roster, and leave the program only
  under pseudonyms; the table is left out of releases.
* :func:`flags` applies the rules in ``rules/insider_rules.json``: late report, sale without a prior plan, dealing in
  a window. **A rule is applied only once it is verified** (its article and effective date confirmed); until then
  the flags say so and nothing is flagged. A flag is a fact to examine, not a finding of breach.
"""
from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

RULES_FILE = Path(__file__).resolve().parent / "rules" / "insider_rules.json"
TITLE = re.compile(r"(董事|监事|高级管理人员|董监高|高管).{0,20}(增持|减持|买卖|持股变动|股份变动|权益变动)|"
                   r"(增持|减持).{0,12}(董事|监事|高级管理人员|董监高|高管)")
ROW = re.compile(
    r"(?P<name>[\u4e00-\u9fff]{2,4})\s+(?:(?P<role>[\u4e00-\u9fff、]{2,20})\s+)?"
    r"(?P<y>20\d{2})[-/.年](?P<m>\d{1,2})[-/.月](?P<d>\d{1,2})日?\s*"
    r"(?:(?P<dir>增持|减持|买入|卖出)\s*)?"
    r"(?P<shares>[\d,]+(?:\.\d+)?)(?:\s*股)?"
    r"(?:\s+(?P<price>\d+(?:\.\d+)?)(?:\s*元)?)?")


@lru_cache(maxsize=1)
def rules() -> dict:
    return json.loads(RULES_FILE.read_text(encoding="utf-8"))


def verified(rule_id: str) -> dict | None:
    for r in rules()["rules"]:
        if r["id"] == rule_id and r.get("verified"):
            return r
    return None


def is_dealing_title(title: str | None) -> bool:
    return bool(title and TITLE.search(title))


def parse_rows(text: str, title: str = "") -> list[dict]:
    """Dealing rows from a page's text: a name, a date, a number of shares and, where given, a price. The direction
    comes from the row, or else from the title (增持 or 减持)."""
    default = "BUY" if "增持" in (title or "") else "SELL" if "减持" in (title or "") else None
    out = []
    for m in ROW.finditer(text or ""):
        try:
            shares = float(m.group("shares").replace(",", ""))
        except (TypeError, ValueError):
            continue
        if shares < 100:                       # a day or a percentage, not a number of shares
            continue
        price = m.group("price")
        d = m.group("dir")
        out.append({"person_name": m.group("name"), "role": (m.group("role") or "").strip() or None,
                    "deal_date": f"{int(m.group('y')):04d}-{int(m.group('m')):02d}-{int(m.group('d')):02d}",
                    "direction": {"增持": "BUY", "买入": "BUY", "减持": "SELL", "卖出": "SELL"}.get(d, default),
                    "shares": shares, "price": float(price.replace(",", "")) if price else None,
                    "raw_text": m.group(0)[:300]})
    return out


def dealing_announcements(session, company_ids=None):
    from .models import Disclosure, Company
    q = session.query(Disclosure, Company).join(Company, Company.id == Disclosure.company_id)
    if company_ids is not None:
        q = q.filter(Disclosure.company_id.in_(list(company_ids)))
    return [(d, c) for d, c in q if is_dealing_title(d.title_cn)]


def extract_dealings(security_code: str | None = None, progress=None) -> dict:
    from .features import require
    from .models import SessionLocal, Company, init_db
    from .models_v23 import InsiderDealing
    from .storepaths import document_path
    from .ledger import Ledger, DONE, EMPTY, NOT_READ, FAILED
    require("insider")
    init_db()
    s = SessionLocal()
    totals = {"announcements": 0, "read": 0, "rows": 0, "missing_files": 0, "errors": 0}
    try:
        ids = None
        if security_code:
            ids = [c.id for c in s.query(Company).filter(Company.security_code == str(security_code).zfill(6))]
        with Ledger("insider") as led:
            for d, c in dealing_announcements(s, ids):
                totals["announcements"] += 1
                p = document_path(d)
                if p is None or not p.exists():
                    totals["missing_files"] += 1
                    led.record(d.id, NOT_READ, "MISSING_FILE")
                    continue
                try:
                    from .reportreader import ReportReader
                    r = ReportReader(p)
                    rows = []
                    try:
                        for i in range(r.n):
                            for row in parse_rows(r.fast_text(i), d.title_cn):
                                rows.append({**row, "source_page": i + 1})
                    finally:
                        r.close()
                    s.query(InsiderDealing).filter(InsiderDealing.disclosure_id == d.id).delete()
                    for row in rows:
                        s.add(InsiderDealing(company_id=c.id, disclosure_id=d.id, published_date=d.announcement_date,
                                             extraction_method="PDF_TEXT_EXPERIMENTAL", **row))
                    s.commit()
                    totals["read"] += 1
                    totals["rows"] += len(rows)
                    led.record(d.id, DONE if rows else EMPTY, None if rows else "NO_VALUES")
                except Exception as exc:                          # noqa: BLE001
                    s.rollback()
                    totals["errors"] += 1
                    led.record(d.id, FAILED, "PARSE_ERROR", repr(exc))
        return totals
    finally:
        s.close()


def flags(security_code: str | None = None) -> dict:
    """The rules' flags for each dealing; only verified rules are applied."""
    from .features import require
    from .models import SessionLocal, Company, Disclosure, init_db
    from .models_v23 import InsiderDealing
    require("insider")
    init_db()
    applied = [r["id"] for r in rules()["rules"] if r.get("verified")]
    s = SessionLocal()
    try:
        q = s.query(InsiderDealing, Company).join(Company, Company.id == InsiderDealing.company_id)
        if security_code:
            q = q.filter(Company.security_code == str(security_code).zfill(6))
        rows = []
        for x, c in q.order_by(Company.security_code, InsiderDealing.deal_date):
            f = []
            rep = verified("report_within")
            if rep and x.deal_date and x.published_date:
                from .security_master import trading_days
                days = trading_days(x.deal_date, x.published_date[:10], c.exchange)
                if days and len(days) - 1 > rep["trading_days"]:
                    f.append(f"reported {len(days) - 1} trading days after the dealing (rule {rep['trading_days']})")
            win = verified("blackout")
            if win and x.deal_date:
                for w in win["windows"]:
                    later = (s.query(Disclosure).filter(Disclosure.company_id == c.id,
                                                        Disclosure.kind == w["before"],
                                                        Disclosure.announcement_date > x.deal_date)
                             .order_by(Disclosure.announcement_date).first())
                    if later is not None:
                        from datetime import date
                        gap = (date.fromisoformat(later.announcement_date[:10]) - date.fromisoformat(x.deal_date)).days
                        if gap <= w["calendar_days"]:
                            f.append(f"{gap} day(s) before a {w['before'].replace('_', ' ')}")
            rows.append({"code": c.security_code, "deal_date": x.deal_date, "direction": x.direction,
                         "shares": x.shares, "published": x.published_date, "flags": "; ".join(f)})
        note = ("No rule is verified yet, so nothing is flagged: confirm each rule's article and effective date in "
                "rules/insider_rules.json." if not applied else f"Rules applied: {', '.join(applied)}.")
        return {"rows": rows, "applied_rules": applied, "note": note + " A flag is a fact to examine, not a "
                                                                      "finding of breach."}
    finally:
        s.close()
