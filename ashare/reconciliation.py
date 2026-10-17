"""v0.8 capital reconciliation.

    Capital structure at t0 + corporate actions in (t0, t1] = capital at t1

Reconciliation results are *derived* records stored in
``capital_reconciliations``. Observed capital and corporate-action values are
never modified; only their ``validation_status`` is updated, and every
discrepancy is reported with the actions and assumptions used.
"""
from __future__ import annotations

from .timeutil import utcnow

import json
from datetime import datetime

from .models import (
    SessionLocal, Company, CorporateAction, CapitalStructureObservation,
    CapitalReconciliation, init_db,
)
from .corporate_actions import (
    RATIO_TYPES, ISSUE_TYPES, REDUCTION_TYPES, NON_CAPITAL_TYPES,
    capital_effective_date,
)

#: Only actions that have taken (or are announced as taking) effect count.
ELIGIBLE_STATUSES = {"IMPLEMENTATION_ANNOUNCED", "COMPLETED"}


def _dedupe(actions: list) -> tuple[list, list[str]]:
    """Collapse the same event captured from several disclosures.

    An issuance is often reported in a 发行情况报告书 and again in a
    上市公告书; a distribution in a 实施公告 and a 提示性公告. Records of
    the same type are merged when they share the capital-effective date, or
    (for issuances and cancellations) the same signed share change. The
    record with quantities and the highest confidence is kept.
    """
    notes = []
    kept: dict[tuple, object] = {}

    def score(a):
        has_q = a.share_delta is not None or a.ratio is not None
        return (has_q, a.confidence or 0.0, a.status == "COMPLETED")

    for a in actions:
        keys = [(a.action_type, "date", capital_effective_date(a))]
        if a.action_type in ISSUE_TYPES | REDUCTION_TYPES and a.share_delta:
            keys.append((a.action_type, "delta", round(a.share_delta)))
        match = next((k for k in keys if k in kept), None)
        if match is None:
            for k in keys:
                kept[k] = a
            continue
        current = kept[match]
        winner = a if score(a) > score(current) else current
        loser = current if winner is a else a
        notes.append(f"duplicate {loser.action_type} (id {loser.id}) merged into id {winner.id}")
        for k, v in list(kept.items()):
            if v is current:
                kept[k] = winner
        for k in keys:
            kept[k] = winner
    unique, seen = [], set()
    for v in kept.values():
        if id(v) not in seen:
            seen.add(id(v))
            unique.append(v)
    return unique, notes


def apply_actions(t0_total: float, actions: list) -> tuple[float, list[str], list[str]]:
    """Roll issued share capital forward through ``actions`` (in date order).

    Returns (expected_total, missing, notes). ``missing`` lists actions whose
    effect on capital could not be quantified from the stored observation.
    """
    expected = float(t0_total)
    missing: list[str] = []
    notes: list[str] = []
    for a in sorted(actions, key=lambda x: (capital_effective_date(x) or "", x.id or 0)):
        label = f"{a.action_type} id {a.id} on {capital_effective_date(a)}"
        if a.old_share_count is not None and abs(a.old_share_count - expected) > max(10.0, expected * 1e-5):
            notes.append(f"{label}: disclosed pre-event total {a.old_share_count:,.0f} differs from rolled-forward {expected:,.0f}")
        if a.action_type in RATIO_TYPES:
            if a.action_type in ("STOCK_SPLIT", "SHARE_CONSOLIDATION"):
                if a.ratio:
                    expected *= a.ratio
                else:
                    missing.append(label)
            elif a.share_delta is not None:
                expected += a.share_delta
            elif a.ratio is not None:
                expected += expected * a.ratio
                notes.append(f"{label}: delta derived from ratio on rolled-forward total "
                             "(distribution base may exclude treasury shares)")
            elif a.old_share_count is not None and a.new_share_count is not None:
                expected += a.new_share_count - a.old_share_count
            else:
                missing.append(label)
        elif a.action_type in ISSUE_TYPES:
            if a.share_delta is not None:
                expected += a.share_delta
            elif a.old_share_count is not None and a.new_share_count is not None:
                expected += a.new_share_count - a.old_share_count
            else:
                missing.append(label)
        elif a.action_type in REDUCTION_TYPES:
            if a.share_delta is not None:
                expected += a.share_delta if a.share_delta <= 0 else -a.share_delta
            elif a.shares_affected is not None:
                expected -= a.shares_affected
            elif a.old_share_count is not None and a.new_share_count is not None:
                expected += a.new_share_count - a.old_share_count
            else:
                missing.append(label)
    return expected, missing, notes


#: Issues whose new shares are listed as tradable on issue (A-share practice):
#: public follow-on offerings, rights issues and conversions. Private
#: placements, share-for-asset issues and incentive grants are locked up
#: (restricted) until a later unlock announcement.
TRADABLE_ON_ISSUE = {"PUBLIC_OFFERING", "RIGHTS_ISSUE", "CONVERTIBLE_CONVERSION", "WARRANT_CONVERSION"}


def apply_tradable(t0_tradable: float, t0_total: float, actions: list) -> tuple[float | None, list[str], list[str]]:
    """Roll *tradable* shares forward. Returns (expected, missing, notes).

    Assumptions (each recorded in the notes where it is used):
    - bonus and capitalisation shares accrue pro rata to tradable and
      restricted holdings;
    - cancellations of repurchased restricted (incentive) shares reduce
      restricted shares; other cancellations reduce tradable shares;
    - unlocks move ``shares_affected`` from restricted to tradable.
    """
    tradable, total = float(t0_tradable), float(t0_total)
    missing, notes = [], []
    for a in sorted(actions, key=lambda x: (capital_effective_date(x) or "", x.id or 0)):
        label = f"{a.action_type} id {a.id}"
        share = tradable / total if total else 0.0
        if a.action_type in ("STOCK_SPLIT", "SHARE_CONSOLIDATION"):
            if not a.ratio:
                missing.append(label); continue
            tradable *= a.ratio; total *= a.ratio
        elif a.action_type in ("BONUS_SHARES", "CAPITALISATION_ISSUE"):
            if a.ratio is not None:
                delta_total = a.share_delta if a.share_delta is not None else total * a.ratio
                tradable += tradable * a.ratio if a.share_delta is None else a.share_delta * share
                total += delta_total
            elif a.share_delta is not None:
                tradable += a.share_delta * share; total += a.share_delta
            else:
                missing.append(label); continue
            notes.append(f"{label}: allocated pro rata to tradable shares")
        elif a.action_type in ISSUE_TYPES:
            if a.share_delta is None:
                missing.append(label); continue
            total += a.share_delta
            if a.action_type in TRADABLE_ON_ISSUE:
                tradable += a.share_delta
        elif a.action_type in REDUCTION_TYPES:
            n = abs(a.share_delta) if a.share_delta is not None else a.shares_affected
            if n is None:
                missing.append(label); continue
            total -= n
            if "限制性股票" in (a.raw_value or ""):
                notes.append(f"{label}: cancellation of restricted incentive shares; tradable unchanged")
            else:
                tradable -= n
        elif a.action_type == "RESTRICTED_SHARE_UNLOCK":
            if a.shares_affected is None:
                missing.append(label); continue
            tradable += a.shares_affected
    return tradable, missing, notes


def reconcile_capital(security_code: str | None = None, capital_source: str | None = None,
                      relative_tolerance: float = 1e-5, absolute_tolerance: float = 10.0) -> dict:
    """Reconcile consecutive capital observations against corporate actions."""
    init_db()
    session = SessionLocal()
    summary = {"companies": 0, "windows": 0, "RECONCILED": 0, "UNEXPLAINED_DIFFERENCE": 0,
               "INSUFFICIENT_DATA": 0, "action_consistency_flags": 0,
               "tradable": {"RECONCILED": 0, "UNEXPLAINED_DIFFERENCE": 0, "INSUFFICIENT_DATA": 0},
               "results": []}
    try:
        cq = session.query(Company)
        if security_code:
            cq = cq.filter(Company.security_code == str(security_code).zfill(6))
        for company in cq.order_by(Company.security_code).all():
            caps_q = session.query(CapitalStructureObservation).filter(
                CapitalStructureObservation.company_id == company.id,
                CapitalStructureObservation.total_shares.isnot(None),
            )
            if capital_source:
                caps_q = caps_q.filter(CapitalStructureObservation.source == capital_source)
            caps = caps_q.order_by(CapitalStructureObservation.observation_date).all()
            all_actions = session.query(CorporateAction).filter(CorporateAction.company_id == company.id).all()
            for a in all_actions:  # reconciliation is the sole writer of these statuses
                a.validation_status = "UNVALIDATED"

            # Action-level internal check: disclosed before/after totals vs delta.
            # Issuances and cancellations disclose one event's before/after
            # totals; check them against the stated share change. (Combined
            # bonus + capitalisation schemes report one aggregate change, so
            # ratio actions are not checked individually.)
            for a in all_actions:
                if a.action_type in ISSUE_TYPES | REDUCTION_TYPES and \
                        None not in (a.old_share_count, a.new_share_count, a.share_delta):
                    if abs((a.new_share_count - a.old_share_count) - a.share_delta) > absolute_tolerance:
                        a.validation_status = "FAILED_INTERNAL_SHARE_COUNT"
                        summary["action_consistency_flags"] += 1

            if not caps and not all_actions:
                continue
            summary["companies"] += 1
            by_source: dict[str, list] = {}
            for c in caps:
                by_source.setdefault(c.source, []).append(c)
            eligible = [a for a in all_actions
                        if a.status in ELIGIBLE_STATUSES and a.action_type not in NON_CAPITAL_TYPES]
            informational = [a for a in all_actions if a.action_type in NON_CAPITAL_TYPES]

            for source, series in by_source.items():
                for c0, c1 in zip(series, series[1:]):
                    window = [a for a in eligible
                              if capital_effective_date(a) and c0.observation_date < capital_effective_date(a) <= c1.observation_date]
                    window, notes = _dedupe(window)
                    expected, missing, roll_notes = apply_actions(c0.total_shares, window)
                    notes += roll_notes
                    undated = [a for a in eligible if not capital_effective_date(a)]
                    if undated:
                        notes.append(f"{len(undated)} eligible action(s) have no usable date and were not placed in any window")
                    buybacks = [a for a in informational if a.action_type == "SHARE_BUYBACK"
                                and (capital_effective_date(a) or "") > c0.observation_date
                                and (capital_effective_date(a) or "") <= c1.observation_date]
                    if buybacks:
                        notes.append(f"{len(buybacks)} buyback observation(s) in window: treasury shares, "
                                     "no change to issued capital until cancellation")
                    # Tradable-share roll-forward (v1.0), where both ends report it.
                    t_status = t_expected = t_residual = None
                    if c0.tradable_shares is not None and c1.tradable_shares is not None:
                        unlocks = [a for a in all_actions if a.action_type == "RESTRICTED_SHARE_UNLOCK"
                                   and a.status in ELIGIBLE_STATUSES and capital_effective_date(a)
                                   and c0.observation_date < capital_effective_date(a) <= c1.observation_date]
                        unlocks, _ = _dedupe(unlocks)
                        t_expected, t_missing, t_notes = apply_tradable(c0.tradable_shares, c0.total_shares, window + unlocks)
                        t_residual = c1.tradable_shares - t_expected
                        t_tol = max(absolute_tolerance, abs(c1.tradable_shares) * relative_tolerance)
                        if t_missing:
                            t_status = "INSUFFICIENT_DATA"
                            t_notes.append("unquantified: " + "; ".join(t_missing))
                        elif abs(t_residual) <= t_tol:
                            t_status = "RECONCILED"
                        else:
                            t_status = "UNEXPLAINED_DIFFERENCE"
                        notes += ["tradable: " + n for n in t_notes]
                        summary["tradable"][t_status] += 1
                    tolerance = max(absolute_tolerance, abs(c1.total_shares) * relative_tolerance)
                    residual = c1.total_shares - expected
                    if missing:
                        status = "INSUFFICIENT_DATA"
                        notes.append("unquantified: " + "; ".join(missing))
                    elif abs(residual) <= tolerance:
                        status = "RECONCILED"
                    else:
                        status = "UNEXPLAINED_DIFFERENCE"
                        if not window:
                            notes.append("total shares changed but no eligible corporate action is recorded in the window")

                    row = session.query(CapitalReconciliation).filter_by(
                        company_id=company.id, capital_source=source,
                        t0_date=c0.observation_date, t1_date=c1.observation_date,
                    ).one_or_none()
                    if row is None:
                        row = CapitalReconciliation(company_id=company.id, capital_source=source,
                                                    t0_date=c0.observation_date, t1_date=c1.observation_date,
                                                    status=status)
                        session.add(row)
                    row.t0_total_shares = c0.total_shares
                    row.t1_total_shares = c1.total_shares
                    row.expected_t1_total_shares = expected
                    row.residual = residual
                    row.tolerance = tolerance
                    row.status = status
                    row.t0_tradable_shares = c0.tradable_shares
                    row.t1_tradable_shares = c1.tradable_shares
                    row.expected_t1_tradable_shares = t_expected
                    row.tradable_residual = t_residual
                    row.tradable_status = t_status
                    row.action_ids = json.dumps([a.id for a in window])
                    row.notes = json.dumps(notes, ensure_ascii=False)
                    row.run_at = utcnow()

                    for a in window:
                        if a.validation_status == "FAILED_INTERNAL_SHARE_COUNT":
                            continue
                        a.validation_status = {"RECONCILED": "RECONCILED_CAPITAL",
                                               "UNEXPLAINED_DIFFERENCE": "IN_UNRECONCILED_WINDOW",
                                               "INSUFFICIENT_DATA": "INSUFFICIENT_DATA"}[status]
                    summary["windows"] += 1
                    summary[status] += 1
                    summary["results"].append({
                        "code": company.security_code, "source": source,
                        "t0": c0.observation_date, "t1": c1.observation_date,
                        "t0_total": c0.total_shares, "t1_total": c1.total_shares,
                        "expected_t1": expected, "residual": residual,
                        "status": status, "actions": [a.id for a in window], "notes": notes,
                        "tradable_status": t_status, "expected_t1_tradable": t_expected,
                        "tradable_residual": t_residual,
                    })
        session.commit()
        return summary
    finally:
        session.close()
