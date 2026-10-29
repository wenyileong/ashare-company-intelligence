"""Parser registry (v1.5).

Every document parser is registered here with the fields it produces, the
key that identifies one record, the input it reads ('text' or 'layout') and
a version. Table parsers have a layout variant (``segments@layout``) that
runs the same rules on rows rebuilt from character positions
(:mod:`ashare.layout`). The evaluation harness scores each variant
separately, calibration is stored per variant, and extractors run both
variants and compare them (:func:`dual_run`).

Additional parsers can be added with :func:`register`, for instance from a
module that handles a new report layout.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

PARSER_VERSION = "1.8"
TABLE_FAMILIES = ("financials", "statements", "segments", "subsidiaries", "human_capital", "roster", "top10",
                  "top10_tradable")


@dataclass
class ParserSpec:
    name: str
    run: Callable[[list[str], dict], list[dict]]
    key: tuple[str, ...]
    fields: tuple[str, ...]
    method: str
    version: str = PARSER_VERSION
    description: str = ""
    doc_kinds: tuple[str, ...] = ("annual_report", "interim_report")
    input: str = "text"          # 'text' (pypdf order) or 'layout' (rows rebuilt from positions)
    family: str = ""             # parsers that produce the same records share a family
    prior: float = 0.55          # confidence used until the variant is calibrated

    def __post_init__(self):
        self.family = self.family or self.name.split("@")[0]


# --- parser adapters ------------------------------------------------------------

def _run_financials(pages, meta):
    from ..financials import pdf_facts_from_pages
    return pdf_facts_from_pages(pages, meta.get("title") or "", meta.get("fallback_period"),
                                meta.get("announcement_date"))


def _run_statements(pages, meta):
    from ..cas import parse_statement_items
    return parse_statement_items(pages)


def _run_top10(pages, meta):
    from ..control import parse_top10_pages
    return parse_top10_pages(pages)


def _run_top10_tradable(pages, meta):
    from ..control import parse_top10_tradable_pages
    return parse_top10_tradable_pages(pages)


def _run_control(pages, meta):
    from ..control import parse_control_text, classify_ownership
    r = parse_control_text(pages)
    if not any(r[k] for k in ("controlling_shareholder", "actual_controller", "no_actual_controller")):
        return []
    r["ownership_type"] = classify_ownership(r["actual_controller"], r["controller_nature"],
                                             bool(r["no_actual_controller"]))[0]
    r["record"] = "control"
    return [r]


def _run_pledges(pages, meta):
    from ..control import parse_pledge_text, classify_pledge_title
    typ = classify_pledge_title(meta.get("title"))
    if not typ:
        return []
    out = parse_pledge_text("\n".join(pages), typ)
    for r in out:
        r["event_type"] = typ
    return out


def _run_segments(pages, meta):
    from ..segments import parse_segment_pages, _merge
    return _merge(parse_segment_pages(pages))


def _run_subsidiaries(pages, meta):
    from ..group import parse_group_pages
    return parse_group_pages(pages)


def _run_human_capital(pages, meta):
    from ..human_capital import parse_human_capital_pages
    return parse_human_capital_pages(pages)


def _run_roster(pages, meta):
    from ..management import parse_roster_pages
    rows = parse_roster_pages(pages)
    for r in rows:
        r["role_codes"] = "|".join(sorted({c for c, _ in r.get("roles") or []}))
    return rows


def _run_esg(pages, meta):
    from ..esg import parse_esg_text
    return parse_esg_text(pages)


def _run_corporate_actions(pages, meta):
    from ..corporate_actions import parse_action_text, classify_action_title, classify_action_status
    title = meta.get("title") or ""
    types = classify_action_title(title)
    if not types:
        return []
    out = []
    for p in parse_action_text(title + "\n" + "\n".join(pages), types, classify_action_status(title)):
        rec = {"action_type": p.action_type, "status": p.status}
        rec.update(p.fields)
        out.append(rec)
    return out


def _run_regulatory(pages, meta):
    from ..regulatory import classify_event_title, parse_event_text
    out = []
    text = "\n".join(pages)
    for ev in classify_event_title(meta.get("title") or ""):
        rec = {"event_type": ev["event_type"], "legal_classification": ev["legal_classification"]}
        f = parse_event_text(text, ev)
        if f.get("violation_categories") is not None:
            f["violation_categories"] = "|".join(sorted(f["violation_categories"]))
        f.pop("sanctions", None)
        f.pop("cited_provisions", None)
        rec.update(f)
        out.append(rec)
    return out


_BUILTIN = (
    ParserSpec("financials", _run_financials, ("metric",), ("value",), "PDF_TEXT_HEURISTIC",
               description="Headline statement items read from PDF text"),
    ParserSpec("statements", _run_statements, ("metric",), ("value",), "PDF_STATEMENT_TABLE",
               description="Consolidated statement line items (CAS chart, about 130 items)", prior=0.6),
    ParserSpec("top10", _run_top10, ("shareholder_name",),
               ("rank", "shares", "ownership_pct", "change_shares", "restricted_shares", "pledged_shares",
                "shareholder_nature"), "PDF_TABLE_HEURISTIC", description="Top-10 shareholders table"),
    ParserSpec("top10_tradable", _run_top10_tradable, ("shareholder_name",), ("rank", "tradable_shares"),
               "PDF_TABLE_HEURISTIC", description="Top-10 holders of tradable shares"),
    ParserSpec("control", _run_control, ("record",),
               ("controlling_shareholder", "actual_controller", "controller_nature", "ownership_type"),
               "DOCUMENT_TEXT_REGEX", description="Controlling shareholder, actual controller, ownership type"),
    ParserSpec("pledges", _run_pledges, ("pledgor",), ("shares", "pledgee", "pct_of_holding", "pct_of_total",
                                                       "start_date", "event_type"),
               "DOCUMENT_TEXT_REGEX", description="Share pledge and release announcements",
               doc_kinds=("announcement",)),
    ParserSpec("segments", _run_segments, ("dimension", "segment_name"),
               ("revenue", "revenue_share", "revenue_prior", "cost", "gross_margin"), "PDF_TABLE_HEURISTIC",
               description="Revenue composition and segment margin tables"),
    ParserSpec("subsidiaries", _run_subsidiaries, ("entity_name",),
               ("relationship", "registered_place", "principal_place", "jurisdiction_class", "direct_pct",
                "indirect_pct", "total_pct", "acquisition_method", "registered_capital", "total_assets",
                "net_assets", "revenue", "net_profit"), "PDF_TABLE_HEURISTIC",
               description="Group composition and major subsidiaries tables"),
    ParserSpec("human_capital", _run_human_capital, ("item",), ("value",), "PDF_TEXT_HEURISTIC",
               description="R&D, workforce composition, education and patents"),
    ParserSpec("roster", _run_roster, ("person_name",),
               ("role_codes", "gender", "age", "status", "tenure_start", "tenure_end", "remuneration"),
               "PDF_TABLE_HEURISTIC", description="Directors, supervisors and officers table"),
    ParserSpec("esg", _run_esg, ("item",), ("value",), "PDF_TEXT_HEURISTIC",
               description="Environmental and social disclosures"),
    ParserSpec("corporate_actions", _run_corporate_actions, ("action_type",),
               ("record_date", "ex_date", "payment_date", "listing_date", "effective_date", "base_share_count",
                "old_share_count", "new_share_count", "share_delta", "shares_affected", "ratio", "cash_amount",
                "total_cash_amount", "subscription_price", "issue_price", "tax_basis"),
               "DOCUMENT_TEXT_REGEX", description="Distribution, issue and buyback announcements",
               doc_kinds=("announcement",)),
    ParserSpec("regulatory", _run_regulatory, ("event_type",),
               ("legal_classification", "authority", "authority_name", "event_date", "document_number",
                "case_number", "fine_amount_total", "fine_amount_company", "confiscation_amount",
                "amount_in_dispute", "company_role", "violation_categories"),
               "DOCUMENT_TEXT_REGEX", description="Penalties, measures, litigation and audit opinions",
               doc_kinds=("announcement",)),
)


PARSERS: dict[str, ParserSpec] = {}


def register(spec: ParserSpec) -> ParserSpec:
    PARSERS[spec.name] = spec
    return spec


for _s in _BUILTIN:
    register(_s)
for _fam in TABLE_FAMILIES:
    _base = PARSERS[_fam]
    register(ParserSpec(f"{_fam}@layout", _base.run, _base.key, _base.fields, _base.method.replace("HEURISTIC", "LAYOUT"),
                        description=_base.description + " (layout extractor)", doc_kinds=_base.doc_kinds,
                        input="layout", family=_fam, prior=_base.prior + 0.05))


def variants(family: str) -> list[ParserSpec]:
    return [s for s in PARSERS.values() if s.family == family]


# --- page loading ---------------------------------------------------------------

def load_pages(path: Path, input: str = "text") -> list[str]:
    from ..http import check_cancel
    check_cancel()
    path = Path(path)
    if path.suffix.lower() == ".txt":
        return path.read_text(encoding="utf-8").split("\f")
    if input == "layout" and path.suffix.lower() == ".pdf":
        from ..layout import available, layout_text_pages
        if available():
            return layout_text_pages(path)
        return []
    from ..corporate_actions import _document_pages
    return _document_pages(path)


def pages_for(path: Path, input: str, cache: dict | None = None) -> list[str]:
    if cache is None:
        return load_pages(path, input)
    key = (str(path), input)
    if key not in cache:
        cache[key] = load_pages(path, input)
    return cache[key]


# --- dual run ---------------------------------------------------------------------

def _norm(v):
    from ..evaluation import _norm as n
    return n(v)


def _same(a, b) -> bool:
    from ..evaluation import values_equal
    return values_equal(a, b)


def dual_run(family: str, path: Path, meta: dict | None = None, text_pages: list[str] | None = None,
             cache: dict | None = None, reader=None, sections=None) -> tuple[list[dict], dict]:
    """Run the text and layout variants of a parser family and reconcile them.

    The variant with the higher (calibrated) confidence is primary and its
    records are returned. Each record gets ``_variant``, ``_agreement``
    ('AGREE', 'DISAGREE' or 'SINGLE') and, on disagreement, ``_alternative``
    (the other variant's differing values). Records found only by the other
    variant are dropped and counted, because a key the primary did not
    produce is usually a fragment of a broken row.
    """
    from ..evaluation import calibrated_confidence
    meta = meta or {}
    path = Path(path)
    runs = {}
    for spec in variants(family):
        if spec.input == "text" and text_pages is not None:
            pages = text_pages
        elif reader is not None:          # v2.0.8: only the pages of the sections sought (ashare.reportreader)
            pages = reader.pages(spec.input, sections or [family])
        else:
            pages = pages_for(path, spec.input, cache)
        if not pages:
            continue
        try:
            runs[spec.name] = (spec, spec.run(pages, meta))
        except Exception as exc:  # one variant failing must not stop the other
            runs[spec.name] = (spec, [])
            meta.setdefault("_errors", []).append(f"{spec.name}: {exc!r}")
    info = {"variants": sorted(runs), "agree": 0, "disagree": 0, "single": 0, "secondary_only": 0,
            "glue_resolved": 0}
    import re as _re
    texts = [text_pages] if text_pages is not None else \
        [reader.pages("text", sections or [family])] if reader is not None else [pages_for(path, "text", cache)]
    info["scanned"] = path.suffix.lower() == ".pdf" and all(len(_re.sub(r"\s+", "", "".join(t or []))) < 20 for t in texts)
    if not runs:
        return [], info
    ranked = sorted(runs.values(), key=lambda sr: calibrated_confidence(sr[0].name, sr[0].prior), reverse=True)
    primary, records = ranked[0]
    info["primary"] = primary.name
    if len(ranked) == 1:
        for r in records:
            r.update(_variant=primary.name, _agreement="SINGLE")
        info["single"] = len(records)
        return records, info
    secondary, other = ranked[1]
    key = lambda r: tuple(_norm(r.get(k)) for k in primary.key)  # noqa: E731
    by_key = {key(r): r for r in other}
    seen = set()
    for r in records:
        k = key(r)
        seen.add(k)
        alt = by_key.get(k)
        r["_variant"] = primary.name
        if alt is None:
            r["_agreement"] = "SINGLE"
            info["single"] += 1
            continue
        # v2.0.8 (finding 85): a note reference glued to the amount in one reading ("1" + "1,791,960,892.40") gives
        # a well-formed but wrong number; when the other reading is the same figure without those digits, it wins.
        if r.get("raw_value") and alt.get("raw_value"):
            from ..numbers import glue_split
            if glue_split(r["raw_value"], alt["raw_value"]):
                r["_glue"], r["raw_value"], r["value"] = r["raw_value"], alt["raw_value"], alt.get("value")
                info["glue_resolved"] += 1
            elif glue_split(alt["raw_value"], r["raw_value"]):
                info["glue_resolved"] += 1
                alt = {**alt, "value": r.get("value")}
        diff = {f: alt.get(f) for f in primary.fields
                if _norm(r.get(f)) is not None and _norm(alt.get(f)) is not None and not _same(r.get(f), alt.get(f))}
        if diff:
            r["_agreement"], r["_alternative"] = "DISAGREE", {"variant": secondary.name, "values": diff}
            info["disagree"] += 1
        else:
            r["_agreement"] = "AGREE"
            info["agree"] += 1
    info["secondary_only"] = sum(1 for k in by_key if k not in seen)
    return records, info


def record_confidence(record: dict, default: float) -> float:
    """Confidence for a dual-run record: calibrated per variant, +0.05 when both agree."""
    from ..evaluation import calibrated_confidence, HEURISTIC_CAP
    spec = PARSERS.get(record.get("_variant") or "")
    base = calibrated_confidence(spec.name, max(default, spec.prior) if spec.input == "layout" else default) \
        if spec else default
    if record.get("_agreement") == "AGREE":
        base += 0.05
    elif record.get("_agreement") == "DISAGREE":
        base = min(base, 0.4)
    return round(min(base, HEURISTIC_CAP), 3)


def extraction_note(record: dict) -> str | None:
    import json
    if not record.get("_variant"):
        return None
    note = {"variant": record["_variant"], "agreement": record.get("_agreement")}
    if record.get("_glue"):
        note["glued_note_removed"] = record["_glue"]
    if record.get("_alternative"):
        note["alternative"] = record["_alternative"]
    return json.dumps(note, ensure_ascii=False, default=str)


def tally_dual(totals: dict, info: dict, disclosure_id) -> None:
    """Accumulate dual-run counts (v1.5)."""
    for k in ("agree", "disagree", "single", "secondary_only"):
        totals.setdefault("dual_run", {}).setdefault(k, 0)
        totals["dual_run"][k] += info.get(k, 0)
    if info.get("scanned"):
        totals.setdefault("scanned_documents", []).append(disclosure_id)
