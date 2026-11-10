"""Ownership and board network measures (v2.3.0, plan section B8).

Built from what is known on a date: each company's latest top-10 holders table published by then, and the directors
and officers seen in a roster within ``ROLE_WINDOW_DAYS`` before it.

* :func:`holder_network` links two listed companies when a holder (other than a nominee account,
  ``rules/nominee_holders.json``) is among the top ten of both.
* :func:`interlock_network` links two listed companies when a person serves both.
* :func:`mhhi_delta` is O'Brien and Salop's modified Herfindahl increment for a set of companies (an industry): with
  market shares s and holders' stakes b (control taken as proportional to stake),
  ΔMHHI = Σ_j Σ_{k≠j} s_j s_k (Σ_i b_ij b_ik) / (Σ_i b_ij²).
  Top-10 tables omit smaller holders, so this is a lower bound; the codebook says so.

Network observations are not independent: use clustered or network-robust standard errors.
"""
from __future__ import annotations

import json
import re
from collections import defaultdict
from datetime import date, timedelta
from functools import lru_cache
from pathlib import Path

ROLE_WINDOW_DAYS = 450
NOMINEES_FILE = Path(__file__).resolve().parent / "rules" / "nominee_holders.json"     # the bundled pack


def _norm(name: str | None) -> str:
    t = (name or "").strip().upper()
    t = t.replace("（", "(").replace("）", ")")
    return re.sub(r"\s+", "", t)


def nominees() -> frozenset:
    """The nominee and custody accounts in use (v2.4.0: a swappable pack, see ``rulepacks``)."""
    from .rulepacks import data
    return _nominee_set(tuple(data("nominees")["names"]))


@lru_cache(maxsize=8)
def _nominee_set(names: tuple) -> frozenset:
    return frozenset(_norm(n) for n in names)


def latest_holders(session, as_of: str, company_ids=None) -> dict[int, dict[str, float]]:
    """{company: {holder key: stake %}} from each company's latest top-10 table published by ``as_of``."""
    from .models import OwnershipObservation, Disclosure
    q = (session.query(OwnershipObservation, Disclosure.announcement_date)
         .outerjoin(Disclosure, Disclosure.id == OwnershipObservation.disclosure_id)
         .filter(OwnershipObservation.rank.isnot(None)))
    if company_ids is not None:
        q = q.filter(OwnershipObservation.company_id.in_(list(company_ids)))
    best: dict[int, str] = {}
    rows = []
    for o, pub in q:
        known = (pub or o.observation_date or "9999")[:10]
        if known > as_of:
            continue
        rows.append(o)
        if o.observation_date > best.get(o.company_id, ""):
            best[o.company_id] = o.observation_date
    out: dict[int, dict[str, float]] = defaultdict(dict)
    nom = nominees()
    for o in rows:
        if o.observation_date != best[o.company_id]:
            continue
        key = f"E{o.entity_id}" if getattr(o, "entity_id", None) else _norm(o.shareholder_name)
        if not key or _norm(o.shareholder_name) in nom:
            continue
        out[o.company_id][key] = max(out[o.company_id].get(key, 0.0), float(o.ownership_pct or 0.0))
    return dict(out)


def holder_network(session, as_of: str) -> dict[int, set[int]]:
    """{company: companies sharing at least one top-10 holder}."""
    holders = latest_holders(session, as_of)
    by_holder: dict[str, set[int]] = defaultdict(set)
    for cid, hs in holders.items():
        for h in hs:
            by_holder[h].add(cid)
    links: dict[int, set[int]] = defaultdict(set)
    for cids in by_holder.values():
        if len(cids) > 1:
            for c in cids:
                links[c] |= cids - {c}
    return dict(links)


def interlock_network(session, as_of: str) -> dict[int, set[int]]:
    """{company: companies sharing a director or officer in office (seen within ROLE_WINDOW_DAYS)}."""
    from .models import PersonRole
    lo = (date.fromisoformat(as_of) - timedelta(days=ROLE_WINDOW_DAYS)).isoformat()
    by_person: dict[int, set[int]] = defaultdict(set)
    for r in session.query(PersonRole):
        last, first = (r.last_date or r.first_date or ""), (r.first_date or r.last_date or "")
        if first and first <= as_of and last >= lo:
            by_person[r.person_id].add(r.company_id)
    links: dict[int, set[int]] = defaultdict(set)
    for cids in by_person.values():
        if len(cids) > 1:
            for c in cids:
                links[c] |= cids - {c}
    return dict(links)


def mhhi_delta(shares: dict[int, float], holders: dict[int, dict[str, float]]) -> float | None:
    """ΔMHHI (in HHI points, shares in per cent) for the companies in ``shares`` (market shares that sum to 1)."""
    firms = [f for f in shares if holders.get(f)]
    if len(firms) < 2:
        return None
    total = 0.0
    for j in firms:
        bj = holders[j]
        own = sum(v * v for v in bj.values())
        if own <= 0:
            continue
        for k in firms:
            if k == j:
                continue
            bk = holders[k]
            cross = sum(v * bk.get(h, 0.0) for h, v in bj.items())
            total += shares[j] * shares[k] * cross / own
    return total * 10000.0


def industry_mhhi(session, as_of: str, year: int) -> dict[str, float | None]:
    """{CSRC industry code: ΔMHHI} for ``year``, with revenue shares from the annual reports published by ``as_of``
    and the top-10 stakes known then."""
    from .models import IndustryClassification, FinancialFact, Disclosure
    ind: dict[int, str] = {}
    for r in session.query(IndustryClassification).order_by(IndustryClassification.effective_date):
        if (r.effective_date or "") <= as_of:
            ind[r.company_id] = r.level2_code or r.level1_code
    rev: dict[int, float] = {}
    for f, pub in (session.query(FinancialFact, Disclosure.announcement_date)
                   .outerjoin(Disclosure, Disclosure.id == FinancialFact.disclosure_id)
                   .filter(FinancialFact.metric == "revenue", FinancialFact.reporting_period == f"{year}-12-31")):
        if (pub or "9999")[:10] <= as_of and f.value and f.value > 0:
            rev[f.company_id] = max(rev.get(f.company_id, 0.0), f.value)
    holders = latest_holders(session, as_of)
    groups: dict[str, dict[int, float]] = defaultdict(dict)
    for cid, v in rev.items():
        if cid in ind:
            groups[ind[cid]][cid] = v
    out = {}
    for code, revs in groups.items():
        tot = sum(revs.values())
        out[code] = mhhi_delta({c: v / tot for c, v in revs.items()}, holders) if tot else None
    return out
