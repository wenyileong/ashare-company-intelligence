from ashare.models import MarketBar


def test_market_model_exists():
    assert MarketBar.__tablename__ == "market_bars"


def test_csv_normalisation_helpers():
    from ashare.market import _normalise_date, _num
    assert _normalise_date("2026/10/08") == "2026-10-08"
    assert _num("1,234.50") == 1234.5
    assert _num("--") is None


def test_market_csv_import_is_idempotent(company, tmp_path):
    from ashare.market import import_bars_csv, show_market
    p = tmp_path / "bars.csv"
    p.write_text("code,date,open,high,low,close,volume,volume_unit\n"
                 "600519,2026-10-08,1500,1520,1490,1510,12345,SHARES\n"
                 "600519,2026-10-09,1510,1530,1500,1525,13000,SHARES\n", encoding="utf-8")
    r1 = import_bars_csv(str(p), source="LICENSED_VENDOR")
    r2 = import_bars_csv(str(p), source="LICENSED_VENDOR")
    assert r1["inserted"] == 2 and r2["updated"] == 2 and r2["inserted"] == 0
    rows = show_market("600519")
    assert [r.close for r in rows] == [1510, 1525]
    assert rows[0].volume_unit == "SHARES" and rows[0].source == "LICENSED_VENDOR"
