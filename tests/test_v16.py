"""v1.6: point-in-time security master, index membership, calendar, optional boards."""
import json

import pytest

from ashare.security_master import (classify_listing_title, parse_listing_text, import_listing_events_csv,
                                    import_security_history_csv, rebuild_security_history, universe_at, name_at,
                                    security_history, extract_listing_events, import_index_csv, index_members,
                                    company_indices, sustainability_mandate, build_trading_calendar, suspensions,
                                    import_calendar_csv)


def test_listing_titles_and_texts():
    assert classify_listing_title("贵州茅台首次公开发行A股股票上市公告书") == ["IPO"]
    assert classify_listing_title("关于公司股票终止上市暨摘牌的公告") == ["DELISTING"]
    assert classify_listing_title("关于公司股票可能被终止上市的风险提示公告") == []
    assert classify_listing_title("关于进入退市整理期交易的公告") == []
    assert classify_listing_title("关于变更证券简称的公告") == ["NAME_CHANGE"]
    assert classify_listing_title("关于变更公司名称及证券简称的公告") == ["NAME_CHANGE", "LEGAL_NAME_CHANGE"]
    [r] = parse_listing_text("经公司申请，公司证券简称由“甲科技”变更为“乙科技”，证券代码不变。"
                             "自2018年7月1日起启用新的证券简称。", ["NAME_CHANGE"])
    assert (r["old_value"], r["new_value"], r["event_date"], r["date_basis"]) == ("甲科技", "乙科技", "2018-07-01", "EFFECTIVE")
    [r] = parse_listing_text("变更后的证券简称：新名字\n变更前的证券简称：旧名字", ["NAME_CHANGE"])
    assert (r["old_value"], r["new_value"]) == ("旧名字", "新名字")
    [r] = parse_listing_text("本所决定公司股票终止上市。公司股票将于2020年6月1日被本所予以摘牌。", ["DELISTING"])
    assert r["event_date"] == "2020-06-01"
    [r] = parse_listing_text("本公司股票将于2021年1月5日在深圳证券交易所创业板上市。", ["IPO"])
    assert r["event_date"] == "2021-01-05"
    [r] = parse_listing_text("证券代码由“600004”变更为“601004”，自2019年3月1日起生效。", ["CODE_CHANGE"])
    assert (r["old_value"], r["new_value"], r["event_date"]) == ("600004", "601004", "2019-03-01")


@pytest.fixture
def history_db(db, tmp_path):
    ev = tmp_path / "ev.csv"
    ev.write_text(
        "security_code,event_type,event_date,old_value,new_value\n"
        "600001,IPO,2010-03-01,,\n600001,DELISTING,2020-06-01,,\n"
        "000002,IPO,2015-05-05,,\n000002,NAME_CHANGE,2018-07-01,甲科技,乙科技\n"
        "300003,IPO,2021-01-05,,\n"
        "601004,IPO,2012-01-10,,\n601004,CODE_CHANGE,2019-03-01,600004,601004\n", encoding="utf-8")
    r = import_listing_events_csv(str(ev))
    assert r["inserted"] == 7 and not r["errors"]
    from ashare.models import SessionLocal, Company
    s = SessionLocal()
    names = {"600001": "退市公司", "000002": "乙科技", "300003": "新上市", "601004": "改码公司"}
    for c in s.query(Company):
        c.short_name_cn = names.get(c.security_code, c.short_name_cn)
    s.commit()
    s.close()
    assert rebuild_security_history()["companies"] == 4
    return tmp_path


REFERENCE = {   # who was listed, under which code and name
    "2009-12-31": set(),
    "2011-01-01": {("600001", "退市公司")},
    "2017-01-01": {("600001", "退市公司"), ("000002", "甲科技"), ("600004", "改码公司")},
    "2019-01-01": {("600001", "退市公司"), ("000002", "乙科技"), ("600004", "改码公司")},
    "2020-06-01": {("000002", "乙科技"), ("601004", "改码公司")},
    "2022-01-01": {("000002", "乙科技"), ("300003", "新上市"), ("601004", "改码公司")},
}


def test_universe_at_reproduces_reference_lists(history_db):
    for on, expected in REFERENCE.items():
        got = {(r["code"], r["name"]) for r in universe_at(on)}
        assert got == expected, on
    # one identity across the code change
    [r] = [r for r in universe_at("2018-06-30") if r["code"] == "600004"]
    assert r["current_code"] == "601004"
    assert name_at("000002", "2018-06-30")["short_name_cn"] == "甲科技"
    assert name_at("600001", "2021-01-01")["listing_status"] == "DELISTED"
    h = security_history("000002")
    assert [x["name"] for x in h["history"]] == ["甲科技", "乙科技"] and h["history"][0]["to"] == "2018-07-01"
    assert {r["code"] for r in universe_at("2019-01-01", ["CHINEXT"])} == set()


def test_imported_history_takes_precedence_and_risk_warnings(history_db, tmp_path):
    from ashare.models import SessionLocal, RegulatoryEvent, Company
    s = SessionLocal()
    c = s.query(Company).filter_by(security_code="000002").first()
    s.add(RegulatoryEvent(event_id="st1", company_id=c.id, event_type="DELISTING_RISK", legal_classification="LISTING_STATUS",
                          event_subtype="OTHER_RISK_WARNING", status="IMPOSED", event_date="2019-04-30", source="CNINFO", extraction_method="TITLE_ONLY"))
    s.add(RegulatoryEvent(event_id="st2", company_id=c.id, event_type="DELISTING_RISK", legal_classification="LISTING_STATUS",
                          event_subtype="OTHER_RISK_WARNING", status="LIFTED", event_date="2020-05-06", source="CNINFO", extraction_method="TITLE_ONLY"))
    s.commit()
    s.close()
    rebuild_security_history("000002")
    assert name_at("000002", "2019-12-31")["risk_warning"] == "ST"
    assert name_at("000002", "2020-12-31")["risk_warning"] is None
    hist = tmp_path / "h.csv"
    hist.write_text("security_code,valid_from,valid_to,short_name_cn,listing_status\n"
                    "300003,2021-01-06,,授权名称,LISTED\n", encoding="utf-8")
    assert import_security_history_csv(str(hist))["inserted"] == 1
    rebuild_security_history()
    assert {r["name"] for r in universe_at("2022-01-01") if r["code"] == "300003"} == {"授权名称"}
    assert not [r for r in universe_at("2021-01-05") if r["code"] == "300003"]   # the imported list wins


def test_listing_events_from_announcements_and_snapshots(db, company, tmp_path):
    from helpers import make_pdf, add_disclosure
    from ashare.storage import upsert_ashares
    pdf = make_pdf(tmp_path / "n.pdf", ["关于变更证券简称的公告", "公司证券简称由“贵州茅台”变更为“茅台股份”，",
                                        "自2026年8月1日起启用新的证券简称。"])
    add_disclosure(company, "关于变更证券简称的公告", "2026-07-28", pdf, ann_id="N1")
    r = extract_listing_events("600519")
    assert r["by_type"] == {"NAME_CHANGE": 1}
    upsert_ashares([{"code": "600519", "exchange": "SSE", "legal_name_cn": "贵州茅台酒股份有限公司",
                     "short_name_cn": "茅台新名"}])
    ev = security_history("600519")["events"]
    assert {(e["type"], e["basis"]) for e in ev} >= {("NAME_CHANGE", "EFFECTIVE"), ("NAME_CHANGE", "DETECTED")}


def test_index_membership_and_mandate(db, company, tmp_path):
    from ashare.crossvalidation import cross_validate
    f = tmp_path / "idx.csv"
    f.write_text("index_code,security_code,effective_date,action\n"
                 "000010,600519,2020-06-15,调入\n000300,600519,2005-04-08,ADD\n"
                 "000010,600000,2018-01-01,ADD\n000010,600000,2025-06-16,REMOVE\n", encoding="utf-8")
    r = import_index_csv(str(f))
    assert r["inserted"] == 3 and not r["errors"]
    assert [m["code"] for m in index_members("000010", "2024-12-31")] == ["600000", "600519"]
    assert [m["code"] for m in index_members("000010", "2025-12-31")] == ["600519"]
    assert {m["index_name"] for m in company_indices("600519", "2025-12-31")} == {"SSE 180", "CSI 300"}
    m = sustainability_mandate("600519", 2025)
    assert m["mandatory"] and m["indices"] == ["SSE 180"] and m["deadline"] == "2026-04-30"
    assert sustainability_mandate("600519", 2024)["mandatory"] is False
    flags = cross_validate("600519")["flags"]
    assert flags.get("SUSTAINABILITY_REPORT_NOT_OBSERVED") == 1      # FY2025 report not catalogued by 2026-04-30
    from helpers import add_disclosure
    add_disclosure(company, "2025年度可持续发展报告", "2026-04-25", None, ann_id="SR")
    assert "SUSTAINABILITY_REPORT_NOT_OBSERVED" not in cross_validate("600519")["flags"]


def test_calendar_and_suspensions(db, company, tmp_path):
    from ashare.storage import upsert_ashares
    from ashare.market import persist_bars
    from ashare.models import SessionLocal, Company
    upsert_ashares([{"code": c, "exchange": "SSE", "legal_name_cn": f"公司{c}"} for c in ("600000", "600001")])
    s = SessionLocal()
    comps = {c.security_code: c for c in s.query(Company)}
    s.close()
    days = ["2026-01-05", "2026-01-06", "2026-01-07", "2026-01-08", "2026-01-09"]
    for code, have in (("600000", days), ("600001", days), ("600519", ["2026-01-05", "2026-01-09"])):
        persist_bars(comps[code], [{"trade_date": d, "open": 1, "high": 1, "low": 1, "close": 1, "volume": 1,
                                    "source": "TEST", "adjustment": "none"} for d in have])
    r = build_trading_calendar()
    assert r["days_added"] == 5
    sp = suspensions("600519", "2026-01-01", "2026-01-31")
    assert sp["days_without_trading"] == 3 and sp["spells"] == [{"from": "2026-01-06", "to": "2026-01-08", "trading_days": 3}]
    cal = tmp_path / "cal.csv"
    cal.write_text("trade_date,is_open\n2026-01-07,0\n", encoding="utf-8")
    import_calendar_csv(str(cal), "SSE")
    assert suspensions("600519", "2026-01-01", "2026-01-31")["days_without_trading"] == 2


def test_optional_boards_off_by_default(db, monkeypatch):
    from ashare.universe import infer_exchange, infer_board, is_a_share, is_supported
    from ashare.storage import upsert_ashares
    monkeypatch.delenv("ASHARE_OPTIONAL_BOARDS", raising=False)
    assert infer_exchange("900901") is None and infer_exchange("920001") is None
    r = upsert_ashares([{"code": "920001", "exchange": "BSE", "legal_name_cn": "北交所公司"},
                        {"code": "900901", "exchange": "SSE", "legal_name_cn": "B股公司"}])
    assert r["rejected"] == 2
    monkeypatch.setenv("ASHARE_OPTIONAL_BOARDS", "BSE,B_SHARE")
    assert infer_exchange("920001") == "BSE" and infer_board("BSE", "830001") == "BSE"
    assert infer_board("SZSE", "200001") == "SZSE_B" and not is_a_share("900901") and is_supported("900901")
    r = upsert_ashares([{"code": "920001", "exchange": "BSE", "legal_name_cn": "北交所公司"},
                        {"code": "900901", "exchange": "SSE", "legal_name_cn": "B股公司"}])
    assert r["inserted"] == 2
    from ashare.models import SessionLocal, Security
    s = SessionLocal()
    types = {x.security_code: (x.security_type, x.currency) for x in s.query(Security)}
    s.close()
    assert types["900901"] == ("B_SHARE", "USD") and types["920001"] == ("A_SHARE", "CNY")
