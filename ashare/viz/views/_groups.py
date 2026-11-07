"""Groups of companies for the views (v2.3.0): CSRC sections (level 1) or industries (level 2) once classifications
are imported, boards otherwise; and the companies listed at a date."""
from __future__ import annotations


def csrc(session, as_of: str, level: int = 1) -> dict[int, str]:
    from ...models import IndustryClassification
    out: dict[int, tuple] = {}
    for r in session.query(IndustryClassification).filter(IndustryClassification.scheme == "CSRC_2012"):
        code = r.level1_code if level == 1 else (r.level2_code or r.level1_code)
        if (r.effective_date or "") <= as_of and code:
            if r.company_id not in out or ((r.effective_date or ""), r.id) > out[r.company_id][0]:
                out[r.company_id] = (((r.effective_date or ""), r.id), code)
    return {cid: v[1] for cid, v in out.items()}


def groups(session, comps: dict, as_of: str, group_by: str = "auto") -> tuple[dict[int, str], str]:
    """({company: group}, 'csrc' or 'board')."""
    cs = csrc(session, as_of)
    use = group_by == "csrc" or (group_by == "auto" and len(cs) >= 0.5 * max(len(comps), 1))
    if use:
        return {cid: cs.get(cid, "unclassified") for cid in comps}, "csrc"
    return {cid: (c.board or c.exchange or "unknown") for cid, c in comps.items()}, "board"


def listed_on(session, comps: dict, day: str) -> set[int]:
    from ...models import ListingEvent
    delisted: dict[int, str] = {}
    for e in session.query(ListingEvent).filter(ListingEvent.event_type == "DELISTING"):
        if (e.event_date or "9999") <= day:
            delisted[e.company_id] = min(delisted.get(e.company_id, "9999"), e.event_date)
    return {cid for cid, c in comps.items() if c.listing_date and c.listing_date <= day
            and delisted.get(cid, "9999") > day}
