"""The graph snapshot: the contract between the data and every display (v2.1, visualisation V0).

A snapshot describes, for a list of companies and a span of fiscal years, as known at a date (``as_of``):
* **nodes**: companies, their reported observations in the five NVF layers, shareholders, controllers, sectors,
  regulatory events, and the gaps where a layer has no data;
* **edges**: each with a relation and an evidential status (DOCUMENTED_FACT, OBSERVED_ASSOCIATION,
  ESTIMATED_RELATIONSHIP, THEORETICAL_PROPOSITION) and the basis for it;
* the coverage of each layer, the chart series, and the policy it was built under (pseudonymisation, licences).

Every value, date, position and status is decided here; a display only draws it (design principle 1). The same
parameters on the same database give the same file, byte for byte. Names that a release would mask are masked with
the release's own rule (:mod:`ashare.release`), imported rather than copied (review round 3).

Version 1 builds only DOCUMENTED_FACT edges: what a document, a classification or a market feed states. Associations,
estimates and the NVF's propositions are reserved in the schema for the measures of V4.
"""
from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from datetime import date

from ..nvf.layers import LAYERS, BY_ID

SCHEMA_VERSION = 1
EVIDENCE = ("DOCUMENTED_FACT", "OBSERVED_ASSOCIATION", "ESTIMATED_RELATIONSHIP", "THEORETICAL_PROPOSITION")
RELATIONS = ("REPORTS", "HOLDS_SHARES", "CONTROLS", "SUBJECT_OF", "GUIDES", "PRICED_AT", "IN_SECTOR",
             "NAMES_POLICY", "RECEIVES_GRANT", "PRECEDES", "ASSOCIATED_WITH", "NVF_PROPOSITION")
NODE_KINDS = ("company", "institution", "policy_event", "regulatory_event", "observation", "measure", "shareholder",
              "controller", "sector", "data_gap")
BASIS_KINDS = ("page", "xbrl", "title", "feed", "classification")
DATE_BASES = ("published", "observed")

FUNDAMENTALS = (("revenue", "Revenue"), ("net_profit_parent", "Net profit attributable"))
CAPABILITY_FACTS = (("rd_expense", "R&D expense"), ("capex", "Capital expenditure"))
CAPABILITY_ITEMS = (("rd_investment", "R&D investment"), ("rd_staff", "R&D staff"),
                    ("rd_ratio", "R&D investment to revenue"))
EXPECTATION_MEASURES = (("net_profit_parent", "Net profit attributable"), ("revenue", "Revenue"))
SERIES = ("revenue", "net_profit_parent")

LANE = 220
YEAR_DEPTH = 190
YEAR_GAP_2D = 26


class SnapshotError(ValueError):
    pass


def _hid(*parts) -> str:
    return hashlib.sha1("|".join(str(p) for p in parts).encode("utf-8")).hexdigest()[:12]


def _fy_periods(start: str, end: str) -> list[str]:
    return [f"{y}-12-31" for y in range(int(start[:4]), int(end[:4]) + 1) if start <= f"{y}-12-31" <= end]


def _licence_ok(table: str, row: dict, include_licensed: bool, overrides: dict) -> bool:
    from ..licences import row_licence
    return include_licensed or row_licence(table, row, overrides) != "LICENSED"


class _Builder:
    def __init__(self, params: dict, session, key: bytes):
        from ..release import Pseudonymiser
        self.p = params
        self.s = session
        self.nodes: dict[str, dict] = {}
        self.edges: dict[str, dict] = {}
        self.masker = Pseudonymiser(key)
        self.masked_originals: set[str] = set()
        self.lanes: dict[str, float] = {}
        self.years = [int(p[:4]) for p in params["periods"]]

    # --- positions ----------------------------------------------------------------------------------------------

    def z(self, when: str | None) -> float:
        if not when or not self.years:
            return 0.0
        y = int(when[:4])
        mid = (self.years[0] + self.years[-1]) / 2
        return round((y - mid) * YEAR_DEPTH, 2)

    def pos(self, layer: str, code: str | None, dx: float = 0, dy: float = 0, when: str | None = None) -> dict:
        """x: the layer; y: the company's lane; z: the year. ``y2`` is the lane in the 2D slice, where the years,
        having no axis, are set apart within the lane instead."""
        x = BY_ID[layer].x + dx if layer in BY_ID else 0
        y = (self.lanes.get(code, 0.0) if code else 0.0) + dy
        z = self.z(when)
        y2 = y + (z / YEAR_DEPTH) * YEAR_GAP_2D
        return {"x": round(x, 2), "y": round(y, 2), "z": z, "y2": round(y2, 2)}

    # --- graph --------------------------------------------------------------------------------------------------

    def node(self, n: dict) -> dict:
        n.setdefault("dates", {})
        n.setdefault("flags", [])
        n.setdefault("masked", False)
        n.setdefault("provenance", None)
        self.nodes[n["id"]] = n
        return n

    def edge(self, source: str, target: str, relation: str, basis: dict, dates: dict | None = None,
             label: str | None = None, status: str = "DOCUMENTED_FACT", value=None) -> None:
        eid = f"e:{relation}:{source}>{target}"
        self.edges[eid] = {"id": eid, "source": source, "target": target, "relation": relation,
                           "evidence_status": status, "basis": basis, "dates": dates or {}, "label": label,
                           "value": value}

    def mask(self, table: str, row: dict, col: str) -> tuple[str, bool]:
        original = row.get(col) or ""
        self.masker.learn(table, row)
        shown = self.masker.apply(table, row).get(col) or ""
        if shown != original:
            from ..release import strip_nature
            self.masked_originals.update(x for x in (original, strip_nature(original)[0]) if x and len(x) >= 2)
            return shown, True
        return shown, False


def _provenance(fact, disclosure) -> dict:
    from ..crossvalidation import confidence_class
    return {"disclosure_id": fact.disclosure_id, "document_hash": getattr(disclosure, "sha256", None),
            "document_title": getattr(disclosure, "title_cn", None),
            "source_url": getattr(disclosure, "document_url", None), "page": fact.source_page,
            "method": fact.extraction_method, "confidence_class": confidence_class(fact.confidence,
                                                                                   fact.validation_status),
            "validation": fact.validation_status}


def _basis_for(prov: dict) -> dict:
    if (prov.get("method") or "").startswith("XBRL"):
        return {"kind": "xbrl", "disclosure_id": prov["disclosure_id"], "page": prov.get("page"),
                "method": prov["method"]}
    return {"kind": "page", "disclosure_id": prov["disclosure_id"], "page": prov.get("page"), "method": prov["method"]}


def build_snapshot(codes: list[str], start: str, end: str, as_of: str | None = None, date_basis: str = "published",
                   expectations: str = "MANAGEMENT_GUIDANCE", top_holders: int = 5, include_licensed: bool = False,
                   key: bytes | None = None, episode: str | None = None) -> dict:
    """Build a snapshot (a JSON-ready dict). Raises :class:`SnapshotError` for bad parameters."""
    from ..models import SessionLocal, Company, init_db
    from ..release import load_key, PERSON_RULE
    from ..expectations import SOURCE_KINDS
    from .. import __version__
    codes = sorted({str(c).strip().zfill(6) for c in codes if str(c).strip()})
    if not codes:
        raise SnapshotError("name at least one company")
    for d in (start, end) + ((as_of,) if as_of else ()):
        try:
            date.fromisoformat(d)
        except (TypeError, ValueError):
            raise SnapshotError(f"not a date (YYYY-MM-DD): {d!r}")
    if start > end:
        raise SnapshotError("the start is after the end")
    if date_basis not in DATE_BASES:
        raise SnapshotError(f"date basis must be one of {', '.join(DATE_BASES)}")
    if expectations not in SOURCE_KINDS:
        raise SnapshotError(f"expectations must be one of {', '.join(SOURCE_KINDS)}")
    as_of = as_of or date.today().isoformat()
    periods = _fy_periods(start, end)
    if not periods:
        raise SnapshotError("the span holds no fiscal year end (31 December)")
    init_db()
    s = SessionLocal()
    try:
        found = {c.security_code: c for c in s.query(Company).filter(Company.security_code.in_(codes))}
        unknown = [c for c in codes if c not in found]
        if unknown:
            raise SnapshotError(f"not in the company list: {', '.join(unknown)}")
        params = {"companies": codes, "start": start, "end": end, "as_of": as_of, "date_basis": date_basis,
                  "periods": periods, "expectations": expectations, "top_holders": top_holders,
                  "include_licensed": include_licensed, "episode": episode}
        b = _Builder(params, s, key if key is not None else load_key())
        spacing = min(LANE, 1200 / max(len(codes) - 1, 1)) if len(codes) > 1 else 0
        for i, code in enumerate(codes):
            b.lanes[code] = round((i - (len(codes) - 1) / 2) * spacing, 2)
        from ..licences import _overrides
        overrides = _overrides(s)
        for code in codes:
            _company(b, found[code])
            _fundamentals(b, found[code])
            _capability(b, found[code])
            _expectations(b, found[code], overrides)
            _valuation(b, found[code], overrides)
            _institutional(b, found[code])
            _ownership(b, found[code])
        coverage = _coverage(b, codes)
        snap = {
            "schema_version": SCHEMA_VERSION,
            "software": f"ashare {__version__}",
            "parameters": params,
            "policy": {"pseudonymisation": PERSON_RULE,
                       "licences": "all classes" if include_licensed else "LICENSED rows excluded, as in releases",
                       "expectations_source": expectations,
                       "point_in_time": f"only what was published on or before {as_of}",
                       "evidence_statuses_built": ["DOCUMENTED_FACT"], "measures": []},
            "layers": [{"id": layer.id, "label": layer.label, "label_zh": layer.label_zh, "x": layer.x,
                        "colour": layer.colour} for layer in LAYERS],
            "coverage": coverage,
            "nodes": [b.nodes[k] for k in sorted(b.nodes)],
            "edges": [b.edges[k] for k in sorted(b.edges)],
            "series": _series(b),
            "summary": _summary(b, codes, periods, coverage),
            "notes": _notes(expectations, coverage),
        }
        problems = validate_snapshot(snap, b.masked_originals)
        if problems:
            raise SnapshotError("the snapshot breaks its rules: " + "; ".join(problems[:10]))
        return snap
    finally:
        s.close()


def codes_in_industry(code: str, as_of: str, scheme: str = "CSRC_2012") -> list[str]:
    """Companies classified in an industry (a CSRC division such as C39, or a section such as C) on ``as_of``, by
    their latest classification on or before that date."""
    from ..models import SessionLocal, Company, IndustryClassification, init_db
    init_db()
    s = SessionLocal()
    try:
        latest: dict[int, IndustryClassification] = {}
        for r in s.query(IndustryClassification).filter(IndustryClassification.scheme == scheme,
                                                        IndustryClassification.effective_date <= as_of):
            if r.company_id not in latest or (r.effective_date, r.id) > (latest[r.company_id].effective_date,
                                                                          latest[r.company_id].id):
                latest[r.company_id] = r
        code = code.strip().upper()
        ids = [cid for cid, r in latest.items() if code in (r.level1_code, r.level2_code, r.level3_code)]
        return sorted(c.security_code for c in s.query(Company).filter(Company.id.in_(ids)))
    finally:
        s.close()


# --- the parts ------------------------------------------------------------------------------------------------------

def _company(b: _Builder, c) -> None:
    from ..models import IndustryClassification
    code = c.security_code
    b.node({"id": f"company:{code}", "kind": "company", "layer": "fundamentals",
            "label": f"{c.short_name_cn or c.legal_name_cn or code} · {code}", "label_zh": c.short_name_cn,
            "company_code": code, "sector": None, "dates": {"valid_from": c.listing_date},
            "position": b.pos("fundamentals", code, dx=0, dy=0, when=None),
            "description": f"{c.legal_name_cn or ''}. Board: {c.board or 'unknown'}; status: {c.status or 'unknown'}."})
    rows = [r for r in b.s.query(IndustryClassification).filter_by(company_id=c.id, scheme="CSRC_2012")
            if r.effective_date and r.effective_date <= b.p["as_of"]]
    if rows:
        r = max(rows, key=lambda r: (r.effective_date, r.id))
        code2 = r.level2_code or r.level1_code
        sid = f"sector:CSRC_2012:{code2}"
        b.nodes[f"company:{code}"]["sector"] = code2
        if sid not in b.nodes:
            b.node({"id": sid, "kind": "sector", "layer": "institutional",
                    "label": f"CSRC {code2} {r.level2_name or r.level1_name or ''}".strip(), "label_zh": r.level2_name,
                    "position": {"x": BY_ID["institutional"].x + 60, "y": 0.0, "z": 0.0, "y2": 0.0},
                    "description": "Industry under the CSRC classification. A sector grouping is not evidence that a "
                                   "policy applies to each company in it."})
        b.edge(f"company:{code}", sid, "IN_SECTOR", {"kind": "classification", "scheme": "CSRC_2012",
                                                    "code": code2, "source": r.source,
                                                    "effective_date": r.effective_date},
               dates={"valid_from": r.effective_date}, label="classified in")


def _fact_nodes(b: _Builder, c, metrics, layer: str, dxs) -> None:
    from ..intelligence import financial_series
    from ..models import FinancialFact, Disclosure, ValidationFlag
    code = c.security_code
    flags = defaultdict(list)
    for f in b.s.query(ValidationFlag).filter_by(company_id=c.id, table_name="financial_facts"):
        try:
            for rid in json.loads(f.row_ids or "[]"):
                flags[rid].append(f.rule)
        except ValueError:
            pass
    for (metric, label), dx in zip(metrics, dxs):
        for k, pt in enumerate(financial_series(code, metric, b.p["as_of"], "FY")):
            if pt["period"] not in b.p["periods"]:
                continue
            fact = b.s.get(FinancialFact, pt["fact_id"])
            d = b.s.get(Disclosure, fact.disclosure_id) if fact.disclosure_id else None
            prov = _provenance(fact, d)
            prov["review"] = pt.get("review")
            prov["confidence_class"] = pt.get("confidence_class") or prov["confidence_class"]
            nid = f"obs:{code}:{metric}:{pt['period']}"
            when = pt["published"] if b.p["date_basis"] == "published" else pt["period"]
            b.node({"id": nid, "kind": "observation", "layer": layer, "label": f"{label} {pt['period'][:4]}",
                    "company_code": code, "metric": metric, "period": pt["period"], "value": pt["value"],
                    "unit": pt.get("unit") or "CNY",
                    "dates": {"published_date": pt["published"], "observed_date": pt["period"]},
                    "provenance": prov, "flags": sorted(set(flags.get(fact.id, []))),
                    "restated": bool(pt.get("restated")),
                    "position": b.pos(layer, code, dx=dx, dy=0, when=when),
                    "description": f"{label} for the fiscal year ending {pt['period']}, as published on "
                                   f"{pt['published'] or 'an unknown date'}."})
            if prov.get("disclosure_id") is None:
                continue                     # no document: shown, but not linked as a documented fact
            b.edge(f"company:{code}", nid, "REPORTS", _basis_for(prov), {"published_date": pt["published"]},
                   label="reported in")


def _fundamentals(b: _Builder, c) -> None:
    _fact_nodes(b, c, FUNDAMENTALS, "fundamentals", (-22, 22))


def _capability(b: _Builder, c) -> None:
    from ..models import HumanCapitalObservation, Disclosure
    _fact_nodes(b, c, CAPABILITY_FACTS, "capability", (-40, -20))
    code = c.security_code
    best = {}
    for r, pub, title, sha, url in (b.s.query(HumanCapitalObservation, Disclosure.announcement_date, Disclosure.title_cn,
                                              Disclosure.sha256, Disclosure.document_url)
                                    .outerjoin(Disclosure, HumanCapitalObservation.disclosure_id == Disclosure.id)
                                    .filter(HumanCapitalObservation.company_id == c.id,
                                            HumanCapitalObservation.item.in_([i for i, _ in CAPABILITY_ITEMS]))):
        if r.value is None or r.reporting_period not in b.p["periods"] or not pub or pub > b.p["as_of"]:
            continue
        k = (r.item, r.reporting_period)
        if k not in best or (pub, r.id) > (best[k][1], best[k][0].id):
            best[k] = (r, pub, title, sha, url)
    labels = dict(CAPABILITY_ITEMS)
    for (item, period), (r, pub, title, sha, url) in sorted(best.items()):
        from ..crossvalidation import confidence_class
        prov = {"disclosure_id": r.disclosure_id, "document_hash": sha, "document_title": title, "source_url": url,
                "page": r.source_page, "method": r.extraction_method,
                "confidence_class": confidence_class(r.confidence, r.validation_status), "validation": r.validation_status}
        nid = f"obs:{code}:{item}:{period}"
        dx = {"rd_investment": 0, "rd_staff": 20, "rd_ratio": 40}[item]
        when = pub if b.p["date_basis"] == "published" else period
        b.node({"id": nid, "kind": "observation", "layer": "capability", "label": f"{labels[item]} {period[:4]}",
                "company_code": code, "metric": item, "period": period, "value": r.value, "unit": r.unit,
                "dates": {"published_date": pub, "observed_date": period}, "provenance": prov,
                "position": b.pos("capability", code, dx=dx, when=when),
                "description": f"{labels[item]} for {period[:4]}, from the R&D and workforce pages of the report."})
        if r.disclosure_id:
            b.edge(f"company:{code}", nid, "REPORTS", _basis_for(prov), {"published_date": pub}, label="reported in")


def _expectations(b: _Builder, c, overrides) -> None:
    from ..models import ExpectationObservation, Disclosure
    code = c.security_code
    best = {}
    for r in b.s.query(ExpectationObservation).filter_by(company_id=c.id, source_kind=b.p["expectations"]):
        if r.measure not in dict(EXPECTATION_MEASURES) or r.reporting_period not in b.p["periods"]:
            continue
        if not r.published_date or r.published_date > b.p["as_of"]:
            continue
        if not _licence_ok("expectation_observations", {"source": r.source}, b.p["include_licensed"], overrides):
            continue
        k = (r.measure, r.reporting_period)
        best.setdefault(k, []).append(r)
    labels = dict(EXPECTATION_MEASURES)
    for (measure, period), rows in sorted(best.items()):
        rows.sort(key=lambda r: (r.published_date, r.id))
        r = rows[-1]
        d = b.s.get(Disclosure, r.disclosure_id) if r.disclosure_id else None
        guided = r.source_kind == "MANAGEMENT_GUIDANCE"
        nid = f"exp:{code}:{measure}:{period}:{r.source_kind}"
        when = r.published_date if b.p["date_basis"] == "published" else period
        kind_label = {"FLASH": "flash report", "FORECAST": "earnings forecast", "IMPORT": "analyst forecast"}.get(
            r.document_kind or "", "expectation")
        prov = {"disclosure_id": r.disclosure_id, "document_hash": getattr(d, "sha256", None),
                "document_title": getattr(d, "title_cn", None), "source_url": getattr(d, "document_url", None),
                "page": r.source_page, "method": r.extraction_method, "confidence_class": None,
                "issuer": r.issuer if not guided else None, "licence": r.licence, "source_kind": r.source_kind,
                "revisions": len(rows)}
        b.node({"id": nid, "kind": "observation", "layer": "expectations",
                "label": f"{labels[measure]} {period[:4]} ({kind_label})", "company_code": code, "metric": measure,
                "period": period, "value": None, "low": r.low, "high": r.high, "unit": r.unit,
                "source_kind": r.source_kind,
                "dates": {"published_date": r.published_date, "observed_date": period},
                "provenance": prov, "position": b.pos("expectations", code, dx=-20 if measure == "revenue" else 20,
                                                      when=when),
                "description": ("Management guidance, a disclosed proxy for expectations, not investors' "
                                "expectations. " if guided else
                                f"An analyst forecast imported under the licence: {r.licence}. ")
                + (f"{len(rows)} statements for this period; the latest published is shown." if len(rows) > 1
                   else "")})
        if guided and r.disclosure_id:
            b.edge(f"company:{code}", nid, "GUIDES", {"kind": "page", "disclosure_id": r.disclosure_id,
                                                      "page": r.source_page, "method": r.extraction_method},
                   {"published_date": r.published_date}, label="guided in")
        elif not guided:
            b.edge(f"company:{code}", nid, "GUIDES", {"kind": "feed", "source": r.source, "date": r.published_date,
                                                      "issuer": r.issuer, "licence": r.licence},
                   {"published_date": r.published_date}, label="forecast by " + (r.issuer or "an analyst"))


def _valuation(b: _Builder, c, overrides) -> None:
    from ..models import MarketBar
    code = c.security_code
    for period in b.p["periods"]:
        cutoff = min(period, b.p["as_of"])
        bars = [m for m in b.s.query(MarketBar).filter(MarketBar.company_id == c.id, MarketBar.adjustment == "none",
                                                      MarketBar.trade_date <= cutoff,
                                                      MarketBar.trade_date >= f"{period[:4]}-01-01",
                                                      MarketBar.close.isnot(None))
                if _licence_ok("market_bars", {"source": m.source}, b.p["include_licensed"], overrides)]
        if not bars:
            continue
        last = max(m.trade_date for m in bars)
        m = sorted((x for x in bars if x.trade_date == last), key=lambda x: x.source)[0]
        nid = f"obs:{code}:close:{period}"
        b.node({"id": nid, "kind": "observation", "layer": "valuation", "label": f"Close {m.trade_date}",
                "company_code": code, "metric": "close", "period": period, "value": m.close, "unit": "CNY_PER_SHARE",
                "dates": {"published_date": m.trade_date, "observed_date": m.trade_date},
                "provenance": {"source": m.source, "trade_date": m.trade_date, "method": "MARKET_FEED",
                               "adjustment": "none"},
                "position": b.pos("valuation", code, when=m.trade_date),
                "description": f"Closing price on the last trading day on or before {cutoff}, unadjusted, from "
                               f"{m.source}. A price, not a valuation ratio."})
        b.edge(f"company:{code}", nid, "PRICED_AT", {"kind": "feed", "source": m.source, "date": m.trade_date},
               {"observed_date": m.trade_date}, label="closing price")


def _institutional(b: _Builder, c) -> None:
    from ..models import RegulatoryEvent
    code = c.security_code
    lo, hi = b.p["start"], min(b.p["end"], b.p["as_of"])
    for e in b.s.query(RegulatoryEvent).filter_by(company_id=c.id):
        when = e.event_date or e.announcement_date
        pub = e.announcement_date or e.event_date
        if not when or not (lo <= when <= hi) or not pub or pub > b.p["as_of"]:
            continue
        nid = f"reg:{code}:{e.event_id}"
        title = b.masker._replace_text(e.title_cn or "") if e.title_cn else None
        b.node({"id": nid, "kind": "regulatory_event", "layer": "institutional",
                "label": f"{(e.event_type or '').replace('_', ' ').lower()} {when}",
                "company_code": code, "dates": {"event_date": e.event_date, "published_date": pub},
                "provenance": {"disclosure_id": e.disclosure_id, "page": e.source_page, "method": e.extraction_method,
                               "document_title": title, "source_url": e.primary_source_url,
                               "document_hash": e.document_hash,
                               "legal_classification": e.legal_classification, "authority": e.authority},
                "position": b.pos("institutional", code, dx=-30, when=pub if b.p["date_basis"] == "published"
                                  else when),
                "description": f"{e.legal_classification or ''} ({e.authority or 'authority not stated'}); "
                               "read from the announcement's title."})
        if e.disclosure_id:
            b.edge(f"company:{code}", nid, "SUBJECT_OF", {"kind": "title", "disclosure_id": e.disclosure_id,
                                                          "method": e.extraction_method},
                   {"event_date": e.event_date, "published_date": pub}, label="subject of")


def _ownership(b: _Builder, c) -> None:
    from ..models import OwnershipObservation, ControlObservation, Disclosure
    code = c.security_code
    hi = min(b.p["end"], b.p["as_of"])
    rows = []
    for o, pub in (b.s.query(OwnershipObservation, Disclosure.announcement_date)
                   .join(Disclosure, OwnershipObservation.disclosure_id == Disclosure.id)
                   .filter(OwnershipObservation.company_id == c.id, OwnershipObservation.rank.isnot(None))):
        if pub and pub <= b.p["as_of"] and b.p["start"] <= o.observation_date <= hi:
            rows.append((o, pub))
    if rows:
        latest = max(o.observation_date for o, _ in rows)
        top = sorted((x for x in rows if x[0].observation_date == latest), key=lambda x: (x[0].rank, x[0].id))
        for o, pub in top[:b.p["top_holders"]]:
            row = {"shareholder_name": o.shareholder_name, "shareholder_nature": getattr(o, "shareholder_nature", None),
                   "shareholder_type": o.shareholder_type}
            shown, masked = b.mask("ownership_observations", row, "shareholder_name")
            hid = f"holder:{_hid(shown)}"
            if hid not in b.nodes:
                b.node({"id": hid, "kind": "shareholder", "layer": "fundamentals", "label": shown, "masked": masked,
                        "position": b.pos("fundamentals", code, dx=-85, dy=(o.rank - 1) * 22 - 44, when=latest),
                        "description": "A natural person, shown under a pseudonym as in releases." if masked else
                        "A shareholder named in the top-10 table."})
            b.edge(hid, f"company:{code}", "HOLDS_SHARES",
                   {"kind": "page", "disclosure_id": o.disclosure_id, "page": o.source_page,
                    "method": o.extraction_method},
                   {"observed_date": latest, "published_date": pub},
                   label=f"holds {o.ownership_pct}%" if o.ownership_pct is not None else "holds shares",
                   value=o.ownership_pct)
    ctl = []
    for o, pub in (b.s.query(ControlObservation, Disclosure.announcement_date)
                   .join(Disclosure, ControlObservation.disclosure_id == Disclosure.id)
                   .filter(ControlObservation.company_id == c.id)):
        if pub and pub <= b.p["as_of"] and b.p["start"] <= o.observation_date <= hi and o.actual_controller:
            ctl.append((o, pub))
    if ctl:
        o, pub = max(ctl, key=lambda x: (x[0].observation_date, x[0].id))
        row = {"actual_controller": o.actual_controller, "controller_nature": o.controller_nature}
        shown, masked = b.mask("control_observations", row, "actual_controller")
        cid = f"controller:{_hid(shown)}"
        if cid not in b.nodes:
            b.node({"id": cid, "kind": "controller", "layer": "fundamentals", "label": shown, "masked": masked,
                    "position": b.pos("fundamentals", code, dx=-140, when=o.observation_date),
                    "description": "The actual controller named in the report"
                                   + (" (a natural person, shown under a pseudonym)." if masked else ".")})
        b.edge(cid, f"company:{code}", "CONTROLS", {"kind": "page", "disclosure_id": o.disclosure_id,
                                                    "page": o.source_page, "method": o.extraction_method},
               {"observed_date": o.observation_date, "published_date": pub}, label="actual controller")


def _coverage(b: _Builder, codes: list[str]) -> list[dict]:
    out = []
    reasons = {
        "institutional": "No regulatory event or classification in the span. Policy events are imported from V3 on.",
        "capability": "No R&D, capital expenditure or R&D staff figure read. Run 'Extract figures from reports' "
                      "and 'Read R&D and workforce'.",
        "fundamentals": "No financial figure read for these years. Download periodic reports and run 'Extract "
                        "figures from reports'.",
        "expectations": ("No management guidance read. Run 'Read guidance' (it downloads the earnings forecasts "
                         "and flash reports first)." if b.p["expectations"] == "MANAGEMENT_GUIDANCE" else
                         "No analyst forecast imported, or the imported rows are licensed and excluded."),
        "valuation": "No price on or before the year ends. Choose a price source (Market data) or import prices.",
    }
    for layer in LAYERS:
        obs = [n for n in b.nodes.values() if n["layer"] == layer.id and n["kind"] in
               ("observation", "regulatory_event", "sector")]
        covered = sorted({n.get("company_code") for n in obs if n.get("company_code")})
        if layer.id == "institutional":
            covered = sorted(set(covered) | {e["source"].split(":", 1)[1] for e in b.edges.values()
                                             if e["relation"] == "IN_SECTOR"})
        status = "GAP" if not obs else "COMPLETE" if len(covered) == len(codes) else "PARTIAL"
        note = reasons[layer.id] if status == "GAP" else (
            f"{len(covered)} of {len(codes)} companies have data in this layer." if status == "PARTIAL"
            else "Every company has data in this layer.")
        if layer.id == "expectations" and status != "GAP" and b.p["expectations"] == "MANAGEMENT_GUIDANCE":
            note += " Management guidance is a disclosed proxy, not investors' expectations."
        out.append({"layer": layer.id, "status": status, "observations": len(obs), "companies_covered": len(covered),
                    "companies": len(codes), "note": note})
        if status == "GAP":
            b.node({"id": f"gap:{layer.id}", "kind": "data_gap", "layer": layer.id,
                    "label": f"No data: {layer.label.lower()}", "position": {"x": layer.x, "y": 0.0, "z": 0.0, "y2": 0.0},
                    "description": reasons[layer.id]})
    return out


def _series(b: _Builder) -> list[dict]:
    out = []
    for metric in SERIES:
        pts = sorted(({"company": n["company_code"], "period": n["period"], "value": n["value"],
                       "display_value": None if n["value"] is None else round(n["value"] / 1e9, 6)}
                      for n in b.nodes.values() if n["kind"] == "observation" and n.get("metric") == metric
                      and n["layer"] == "fundamentals"), key=lambda p: (p["company"], p["period"]))
        out.append({"metric": metric, "label": dict(FUNDAMENTALS)[metric], "unit": "CNY", "display_unit": "CNY bn",
                    "points": pts})
    return out


def _summary(b: _Builder, codes, periods, coverage) -> list[dict]:
    obs = sum(1 for n in b.nodes.values() if n["kind"] == "observation")
    gaps = [c["layer"] for c in coverage if c["status"] == "GAP"]
    return [
        {"label": "Companies", "value": str(len(codes)), "note": ", ".join(codes[:6]) + (" …" if len(codes) > 6 else "")},
        {"label": "Fiscal years", "value": f"{periods[0][:4]}–{periods[-1][:4]}" if len(periods) > 1
         else periods[0][:4], "note": f"as published by {b.p['as_of']}"},
        {"label": "Observations", "value": f"{obs:,}", "note": f"{len(b.edges):,} documented links"},
        {"label": "Layers without data", "value": str(len(gaps)),
         "note": ", ".join(BY_ID[g].label for g in gaps) if gaps else "every layer has data"},
    ]


def _notes(expectations: str, coverage) -> list[dict]:
    notes = [
        {"title": "What a line means", "text": "Every line in this view is a documented fact: a report, an "
                                               "announcement, a classification or a market feed states it. A line "
                                               "does not establish that one thing caused another."},
        {"title": "Point in time", "text": "Only what was published on or before the view's date is shown. "
                                           "Figures restated later appear as published then."},
        {"title": "Gaps", "text": "A layer without data is shown as a gap, with the reason; nothing is interpolated."},
    ]
    if expectations == "MANAGEMENT_GUIDANCE":
        notes.append({"title": "Expectations", "text": "The expectations layer holds management guidance "
                                                       "(earnings forecasts and flash reports): a disclosed proxy, "
                                                       "not investors' expectations."})
    notes.append({"title": "Measures", "text": "The NVF's measures (Institutional Visibility, the Fractal "
                                               "Investment Clock) are not computed: they are PROPOSED until their "
                                               "variables and falsification conditions are fixed."})
    return notes


# --- rules ----------------------------------------------------------------------------------------------------------

def validate_snapshot(snap: dict, masked_originals: set[str] | None = None) -> list[str]:
    """The rules of plan section 7.3; returns the problems found (none for a valid snapshot)."""
    from .schema import check
    problems = check(snap)
    as_of = snap.get("parameters", {}).get("as_of")
    by_id = {n["id"]: n for n in snap.get("nodes", [])}
    ids = set(by_id)
    for n in snap.get("nodes", []):
        pub = (n.get("dates") or {}).get("published_date")
        if as_of and pub and pub > as_of:
            problems.append(f"node {n['id']} published {pub}, after {as_of}")
    for e in snap.get("edges", []):
        if e["source"] not in ids or e["target"] not in ids:
            problems.append(f"edge {e['id']} joins a node not in the snapshot")
        for k, v in (e.get("dates") or {}).items():
            if k == "published_date" and as_of and v and v > as_of:
                problems.append(f"edge {e['id']} published {v}, after {as_of}")
        if e["evidence_status"] == "DOCUMENTED_FACT":
            bs = e.get("basis") or {}
            kind = bs.get("kind")
            if kind in ("page", "title") and not bs.get("disclosure_id"):
                problems.append(f"edge {e['id']} is a documented fact without its document")
            elif kind == "page" and bs.get("page") is None and not str(bs.get("method") or "").startswith("XBRL"):
                problems.append(f"edge {e['id']} is a documented fact without its page")
            elif kind == "feed" and not (bs.get("source") and bs.get("date")):
                problems.append(f"edge {e['id']} is a feed value without its source and date")
            elif kind == "classification" and not (bs.get("scheme") and bs.get("code")):
                problems.append(f"edge {e['id']} is a classification without its scheme and code")
            elif kind not in BASIS_KINDS:
                problems.append(f"edge {e['id']} has no basis")
        src, tgt = by_id.get(e["source"]), by_id.get(e["target"])
        if src and tgt and src["kind"] == "policy_event" and tgt["kind"] == "company" \
                and e["evidence_status"] == "DOCUMENTED_FACT" and (e.get("basis") or {}).get("kind") != "page":
            problems.append(f"edge {e['id']}: a policy is linked to a company as a fact without the company's "
                            "own document")
        if e["evidence_status"] == "THEORETICAL_PROPOSITION" and "company" in (src or {}).get("kind", "") + \
                (tgt or {}).get("kind", ""):
            problems.append(f"edge {e['id']}: an NVF proposition is attached to a company")
    if masked_originals:
        # A name is masked as a whole value (as in releases), and replaced inside free text; an organisation's name
        # that merely contains a person's is not a leak, so organisations' labels are not searched.
        leaked = set()
        for n in snap.get("nodes", []):
            if n["kind"] in ("shareholder", "controller") and n["label"] in masked_originals:
                leaked.add(n["label"])
            free = " ".join(str(x) for x in (n.get("description"), (n.get("provenance") or {}).get("document_title"))
                            if x)
            if n["kind"] in ("regulatory_event", "policy_event", "shareholder", "controller"):
                leaked.update(m for m in masked_originals if m in free)
        for e in snap.get("edges", []):
            if e.get("label") in masked_originals:
                leaked.add(e["label"])
        if leaked:
            problems.append(f"{len(leaked)} masked name(s) appear in the snapshot")
    return problems


def dumps(snap: dict) -> str:
    """The snapshot's canonical text: the same snapshot always gives the same bytes."""
    return json.dumps(snap, ensure_ascii=False, sort_keys=True, indent=1, allow_nan=False) + "\n"
