"""Directors', supervisors' and senior managers' share dealings (v2.3.0, plan section B6; experimental, switch
``insider``, off by default).

* :func:`dealing_announcements` finds the announcements of such dealings by their titles.
* :func:`extract_dealings` reads the rows of their tables where the text layer has them (name, date, direction,
  shares, price) into ``insider_dealings``. Persons are stored by name like the roster, and leave the program only
  under pseudonyms; the table is left out of releases.
* :func:`flags` applies the rules of the ``insider`` rule pack: late report, sale without an announced plan, dealing
  in a window. Since v2.4.0 the pack is swappable (``rulepacks``; Check > Rules) and its rules are applied while
  *provisional*: every flag a provisional rule raises is marked "(provisional rule)", and ``confirmed_only`` applies
  only the rules the author has confirmed against the official text. A withdrawn rule is never applied. A flag is a
  fact to examine, not a finding of breach.
"""
from __future__ import annotations

import re
from pathlib import Path

RULES_FILE = Path(__file__).resolve().parent / "rules" / "insider_rules.json"     # the bundled pack
TITLE = re.compile(r"(董事|监事|高级管理人员|董监高|高管).{0,20}(增持|减持|买卖|持股变动|股份变动|权益变动)|"
                   r"(增持|减持).{0,12}(董事|监事|高级管理人员|董监高|高管)")
ROW = re.compile(
    r"(?P<name>[\u4e00-\u9fff]{2,4})\s+(?:(?P<role>[\u4e00-\u9fff、]{2,20})\s+)?"
    r"(?P<y>20\d{2})[-/.年](?P<m>\d{1,2})[-/.月](?P<d>\d{1,2})日?\s*"
    r"(?:(?P<dir>增持|减持|买入|卖出)\s*)?"
    r"(?P<shares>[\d,]+(?:\.\d+)?)(?:\s*股)?"
    r"(?:\s+(?P<price>\d+(?:\.\d+)?)(?:\s*元)?)?")


PLAN_TITLE = re.compile(r"减持(股份)?计划|拟减持|减持.{0,6}预披露|预披露.{0,10}减持")
# v2.4.1: a notice that a plan has ended, progressed or been dropped announces no new plan
NOT_A_PLAN = re.compile(r"完毕|完成|结果|进展|过半|届满|期满|终止|实施情况|提前结束|未减持")
METHODS = (("AUCTION", re.compile(r"集中竞价|竞价交易|二级市场")), ("BLOCK", re.compile(r"大宗交易")),
           ("AGREEMENT", re.compile(r"协议转让")), ("OTHER", re.compile(r"司法|继承|赠与|非交易过户|股权激励|行权")))
METHOD_LABEL = {"AUCTION": "sale by auction", "BLOCK": "block trade", "AGREEMENT": "transfer by agreement",
                "OTHER": "other transfer"}


def read_method(row_text: str, page_text: str = "") -> str | None:
    """The method of a dealing (v2.4.1): from the row's own line, or else from the page when it names exactly one."""
    for name, rx in METHODS:
        if rx.search(row_text or ""):
            return name
    found = [name for name, rx in METHODS if rx.search(page_text or "")]
    return found[0] if len(found) == 1 else None
PLAN_LOOKBACK_DAYS = 200            # a reduction plan older than this is not taken to cover a sale


def rules() -> dict:
    """The share-dealing rules in use (v2.4.0: the swappable ``insider`` pack)."""
    from .rulepacks import data
    return data("insider")


def rule(rule_id: str, confirmed_only: bool = False, on: str | None = None) -> dict | None:
    """The rule if it is applied (provisional or confirmed; only confirmed with ``confirmed_only``) and, when ``on``
    is given, in force on that date."""
    from .rulepacks import load
    r = load("insider").rule(rule_id, confirmed_only)
    if r is None or on is None:
        return r
    if r.get("effective_from") and on < r["effective_from"]:
        return None
    if r.get("effective_to") and on > r["effective_to"]:
        return None
    return r


def verified(rule_id: str) -> dict | None:
    """v2.3 name, kept: the rule only once it is confirmed."""
    return rule(rule_id, confirmed_only=True)


def _tag(r: dict, when: str | None = None) -> str:
    """What is said after a flag: that the rule is provisional, and (v2.4.1) that the dealing predates the rule's
    present form, when an earlier version, which may differ, applied."""
    from .rulepacks import rule_status
    s = ""
    since = r.get("in_this_form_from")
    if when and since and when < since:
        s += f" (before {since}: an earlier version of the rule applied, which may differ)"
    return s + (" (provisional rule)" if rule_status(r) == "provisional" else "")


def _supervisor_only(role: str | None) -> bool:
    return bool(role) and "监事" in role and "董事" not in role and not re.search(r"经理|总裁|财务|秘书|高级管理", role)


def is_plan_title(title: str | None) -> bool:
    return bool(title and PLAN_TITLE.search(title) and not NOT_A_PLAN.search(title))


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
        a, b = (text.rfind("\n", 0, m.start()) + 1), text.find("\n", m.end())
        line = text[a:b if b != -1 else len(text)]
        out.append({"person_name": m.group("name"), "role": (m.group("role") or "").strip() or None,
                    "deal_date": f"{int(m.group('y')):04d}-{int(m.group('m')):02d}-{int(m.group('d')):02d}",
                    "direction": {"增持": "BUY", "买入": "BUY", "减持": "SELL", "卖出": "SELL"}.get(d, default),
                    "shares": shares, "price": float(price.replace(",", "")) if price else None,
                    "method": read_method(line, text), "raw_text": m.group(0)[:300]})
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
            from .progressbar import count                   # v2.4.1 (R3)
            for d, c in count(dealing_announcements(s, ids), unit="announcements"):
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


def _covers(session, exchange: str, start: str, end: str) -> bool:
    """Whether the trading calendar covers the span (without it, trading days cannot be counted)."""
    from sqlalchemy import func
    from .models import TradingDay
    lo, hi = session.query(func.min(TradingDay.trade_date), func.max(TradingDay.trade_date)).filter(
        TradingDay.exchange == (exchange or "SSE").upper()).one()
    return bool(lo and hi and lo <= start and hi >= end)


def dealing_flags(session, x, company, confirmed_only: bool = False, cache: dict | None = None) -> tuple[list, dict]:
    """The flags for one dealing ``x`` of ``company``: ([(rule id, text)], {rule id: why it could not be checked})."""
    from datetime import date, timedelta
    from .models import Disclosure
    from .security_master import trading_days
    cache = {} if cache is None else cache
    out, unchecked = [], {}
    when = x.deal_date
    exch = company.exchange or "SSE"
    # v2.4.1: supervisors left the Rules on the date the pack gives (CSRC Announcement [2025] No 5)
    for r0 in rules().get("rules", []):
        until = r0.get("supervisors_until")
        if when and until and when >= until and _supervisor_only(getattr(x, "role", None)):
            return [], {"all rules": f"a supervisor's dealing on or after {until}, when supervisors left the Rules"}
    rep = rule("report_within", confirmed_only, when) if when else None
    if rep and x.published_date:
        pub = x.published_date[:10]
        if not _covers(session, exch, when, pub):
            unchecked["report_within"] = "no trading calendar for the span (run build-calendar)"
        else:
            n = len(trading_days(when, pub, exch)) - 1
            if n > rep["trading_days"]:
                out.append(("report_within", f"reported {n} trading days after the dealing (rule: within "
                                             f"{rep['trading_days']}){_tag(rep, when)}"))
    win = rule("blackout", confirmed_only, when) if when else None
    if win:
        for w in win["windows"]:
            kinds = ("earnings_forecast_or_flash", "earnings_forecast", "earnings_flash") \
                if w["before"].startswith("earnings_") else (w["before"],)
            later = (session.query(Disclosure).filter(Disclosure.company_id == company.id,
                                                      Disclosure.kind.in_(kinds),
                                                      Disclosure.announcement_date > when)
                     .order_by(Disclosure.announcement_date).first())
            if later is not None:
                gap = (date.fromisoformat(later.announcement_date[:10]) - date.fromisoformat(when)).days
                if gap <= w["calendar_days"]:
                    out.append(("blackout", f"{gap} day(s) before a {w['before'].replace('_', ' ')} (window: "
                                            f"{w['calendar_days']} days){_tag(win, when)}"))
    plan = rule("plan_before_sale", confirmed_only, when) if when and x.direction == "SELL" else None
    covered = set((plan or {}).get("methods") or ["AUCTION"])
    method = {"集中竞价": "AUCTION", "大宗交易": "BLOCK"}.get(x.method or "", x.method or None)
    if plan and (method is None or method in covered):       # v2.4.1: only the methods the rule covers
        key = ("plans", company.id)
        if key not in cache:
            cache[key] = sorted(d.announcement_date[:10] for d in session.query(Disclosure).filter(
                Disclosure.company_id == company.id, Disclosure.announcement_date.isnot(None))
                if is_plan_title(d.title_cn))
        start = (date.fromisoformat(when) - timedelta(days=PLAN_LOOKBACK_DAYS)).isoformat()
        plans = [p for p in cache[key] if start <= p <= when]
        unknown = "" if method else "; method not given, taken as a sale the rule covers"
        if not plans:
            out.append(("plan_before_sale", f"no reduction plan announced in the {PLAN_LOOKBACK_DAYS} days before "
                                            f"the sale{unknown}{_tag(plan, when)}"))
        elif not _covers(session, exch, plans[0], when):
            unchecked["plan_before_sale"] = "no trading calendar for the span (run build-calendar)"
        else:
            best = max(len(trading_days(p, when, exch)) - 1 for p in plans)
            if best < plan["trading_days"]:
                out.append(("plan_before_sale", f"reduction plan announced {best} trading days before the sale (rule: "
                                                f"at least {plan['trading_days']}){unknown}{_tag(plan, when)}"))
    return out, unchecked


def flags(security_code: str | None = None, confirmed_only: bool = False) -> dict:
    """Each dealing with the flags of the rules applied: provisional and confirmed rules (flags of a provisional rule
    are marked so), or only confirmed ones with ``confirmed_only``."""
    from .features import require
    from .models import SessionLocal, Company, init_db
    from .models_v23 import InsiderDealing
    from .rulepacks import load
    require("insider")
    init_db()
    pk = load("insider")
    applied = [r["id"] for r in pk.applied(confirmed_only)]
    s = SessionLocal()
    try:
        q = s.query(InsiderDealing, Company).join(Company, Company.id == InsiderDealing.company_id)
        if security_code:
            q = q.filter(Company.security_code == str(security_code).zfill(6))
        rows, cache, unchecked_n = [], {}, {}
        for x, c in q.order_by(Company.security_code, InsiderDealing.deal_date):
            f, unchecked = dealing_flags(s, x, c, confirmed_only, cache) if x.deal_date else ([], {})
            for k, why in unchecked.items():
                unchecked_n[(k, why)] = unchecked_n.get((k, why), 0) + 1
            rows.append({"code": c.security_code, "deal_date": x.deal_date, "direction": x.direction,
                         "shares": x.shares, "method": METHOD_LABEL.get(x.method or "", x.method or ""),
                         "published": x.published_date,
                         "flags": "; ".join(t for _, t in f) if x.deal_date else "no dealing date: not checked",
                         "rules_flagged": ",".join(sorted({k for k, _ in f}))})
        prov = [r for r in applied if r in pk.provisional_ids()]
        if not applied:
            note = ("No rule is applied: " + ("none is confirmed yet." if confirmed_only else
                                              "every rule in the pack is withdrawn."))
        else:
            note = f"Rules applied: {', '.join(applied)} ({pk.describe()})."
            if prov:
                note += (f" Provisional, not yet confirmed against the official text: {', '.join(prov)}; their flags "
                         "are marked '(provisional rule)'.")
        for (k, why), n in unchecked_n.items():
            note += f" {k}: {n:,} dealing(s) not checked ({why})."
        return {"rows": rows, "applied_rules": applied, "provisional_rules": prov, "pack": pk.describe(),
                "note": note + " A flag is a fact to examine, not a finding of breach."}
    finally:
        s.close()


def company_measures(session, company, as_of: str, cache: dict | None = None) -> dict:
    """For the panel (v2.4.0): over the twelve months to ``as_of``, net shares bought by directors, supervisors and
    senior managers, and the sales flagged by the blackout rule, from the dealings published by ``as_of``."""
    from datetime import date
    from .models_v23 import InsiderDealing
    y, mo, dd = int(as_of[:4]) - 1, int(as_of[5:7]), int(as_of[8:10])
    start = (date(y, mo, dd) if not (mo == 2 and dd == 29) else date(y, 2, 28)).isoformat()   # exactly a year
    rows = [x for x in session.query(InsiderDealing).filter(InsiderDealing.company_id == company.id)
            if x.deal_date and start < x.deal_date <= as_of and (x.published_date or "9999")[:10] <= as_of]
    if not rows:
        return {"net_buy": None, "window_sales": None, "n": 0}
    net = sum((x.shares or 0) * (1 if x.direction == "BUY" else -1 if x.direction == "SELL" else 0) for x in rows)
    ws = 0
    for x in rows:
        if x.direction == "SELL":
            f, _ = dealing_flags(session, x, company, False, cache)
            ws += any(k == "blackout" for k, _ in f)
    return {"net_buy": float(net), "window_sales": float(ws), "n": len(rows)}
