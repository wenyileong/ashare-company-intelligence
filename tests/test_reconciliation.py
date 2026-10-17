import json


def _caps(tmp_path, rows):
    from ashare.ownership import import_capital_csv
    p = tmp_path / "cap.csv"
    p.write_text("security_code,observation_date,total_shares\n" +
                 "".join(f"600519,{d},{n}\n" for d, n in rows), encoding="utf-8")
    import_capital_csv(str(p), source="CAPITAL_SRC")


def _actions(tmp_path, rows, name="ca.csv"):
    from ashare.corporate_actions import import_corporate_actions_csv
    p = tmp_path / name
    header = "security_code,action_id,action_type,status,ex_date,listing_date,effective_date,ratio,share_delta,shares_affected\n"
    p.write_text(header + "".join("600519," + ",".join(str(x) for x in r) + "\n" for r in rows), encoding="utf-8")
    r = import_corporate_actions_csv(str(p), source="ACTION_SRC")
    assert not r["errors"], r


def test_reconciliation_end_to_end(company, tmp_path):
    from ashare.reconciliation import reconcile_capital
    from ashare.models import SessionLocal, CapitalReconciliation, CorporateAction
    _caps(tmp_path, [("2026-03-31", 500_000_000), ("2026-06-30", 697_000_000),
                     ("2026-09-30", 747_000_500), ("2026-12-31", 760_000_000)])
    _actions(tmp_path, [
        # window 1: capitalisation 10转4 (delta from ratio), cancellation
        ("a1", "CAPITALISATION_ISSUE", "IMPLEMENTATION_ANNOUNCED", "2026-05-21", "", "", 0.4, "", ""),
        ("a2", "SHARE_CANCELLATION", "COMPLETED", "", "", "2026-06-10", "", "", 3_000_000),
        ("a3", "CASH_DIVIDEND", "COMPLETED", "2026-05-21", "", "", "", "", ""),
        ("a4", "SHARE_BUYBACK", "COMPLETED", "", "", "2026-06-01", "", 0, 3_000_000),
        ("a5", "PRIVATE_PLACEMENT", "PROPOSED", "", "", "2026-06-15", "", 99_000_000, ""),  # not effective
        # window 2: placement captured twice + conversion
        ("a6", "PRIVATE_PLACEMENT", "COMPLETED", "", "2026-08-10", "", "", 50_000_000, ""),
        ("a7", "PRIVATE_PLACEMENT", "COMPLETED", "", "", "2026-08-05", "", 50_000_000, ""),
        ("a8", "CONVERTIBLE_CONVERSION", "COMPLETED", "", "", "2026-09-30", "", 500, ""),
        # window 3: issuance with no quantity
        ("a9", "SHARE_ISSUANCE", "COMPLETED", "", "", "2026-11-01", "", "", ""),
    ])
    r = reconcile_capital("600519")
    status = {(x["t0"], x["t1"]): x for x in r["results"]}
    w1 = status[("2026-03-31", "2026-06-30")]
    assert w1["status"] == "RECONCILED" and w1["expected_t1"] == 697_000_000
    assert any("buyback" in n for n in w1["notes"])
    w2 = status[("2026-06-30", "2026-09-30")]
    assert w2["status"] == "RECONCILED" and w2["expected_t1"] == 747_000_500
    assert any("duplicate PRIVATE_PLACEMENT" in n for n in w2["notes"])
    w3 = status[("2026-09-30", "2026-12-31")]
    assert w3["status"] == "INSUFFICIENT_DATA"
    # Idempotent re-run; derived rows replaced, observations untouched.
    reconcile_capital("600519")
    s = SessionLocal()
    assert s.query(CapitalReconciliation).count() == 3
    a6 = s.query(CorporateAction).filter(CorporateAction.share_delta == 50_000_000).all()
    assert all(a.share_delta == 50_000_000 for a in a6)
    statuses = {a.action_type: a.validation_status for a in s.query(CorporateAction).all()}
    s.close()
    assert statuses["CAPITALISATION_ISSUE"] == "RECONCILED_CAPITAL"


def test_unexplained_difference(company, tmp_path):
    from ashare.reconciliation import reconcile_capital
    _caps(tmp_path, [("2026-03-31", 500_000_000), ("2026-06-30", 510_000_000)])
    r = reconcile_capital("600519")
    [w] = r["results"]
    assert w["status"] == "UNEXPLAINED_DIFFERENCE" and w["residual"] == 10_000_000
    assert any("no eligible corporate action" in n for n in w["notes"])
