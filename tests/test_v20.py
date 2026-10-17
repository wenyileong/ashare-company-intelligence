"""v2.0: schema migrations, licence-aware and pseudonymised releases, quality report, update check."""
import csv
import json
import sqlite3
from pathlib import Path

import httpx
import pytest

FIXTURES = Path(__file__).parent / "fixtures"


def _restore(sql_name, db_file):
    c = sqlite3.connect(db_file)
    c.executescript((FIXTURES / sql_name).read_text(encoding="utf-8"))
    c.commit()
    c.close()


@pytest.mark.parametrize("fixture", ["schema_v07.sql", "schema_v13.sql", "schema_v19.sql"])
def test_old_databases_upgrade_to_head(tmp_path, monkeypatch, fixture):
    import os
    if os.environ.get("ASHARE_TEST_DB_URL"):
        pytest.skip("SQLite fixtures")
    db = tmp_path / "old.db"
    _restore(fixture, db)
    monkeypatch.setenv("ASHARE_DB", str(db))
    monkeypatch.delenv("ASHARE_DB_URL", raising=False)
    from ashare.models import reset_init_cache, init_db, Base, engine
    from ashare.migrate import current, head, upgrade
    from sqlalchemy import inspect, select, func
    reset_init_cache()
    assert current() is None
    init_db()
    assert current() == head()
    assert list(tmp_path.glob("old.db.bak-*")), "a backup copy is taken before upgrading"
    insp = inspect(engine())
    for t in Base.metadata.sorted_tables:            # every model table and column exists and is readable
        have = {c["name"] for c in insp.get_columns(t.name)}
        assert set(t.c.keys()) <= have, (t.name, set(t.c.keys()) - have)
    with engine().connect() as c:
        assert c.execute(select(func.count()).select_from(Base.metadata.tables["companies"])).scalar() == 1
    from ashare.storage import upsert_ashares
    upsert_ashares([{"code": "600519", "exchange": "SSE", "legal_name_cn": "贵州茅台酒股份有限公司",
                     "short_name_cn": "贵州茅台", "org_id": "gssh0600519"}])
    assert upgrade()["changed"] is False                 # idempotent


def test_new_database_is_at_head(db):
    from ashare.migrate import status
    st = status()
    assert st["up_to_date"] and [h["revision"] for h in st["history"]][0] == "0001_baseline_v19"


def test_licence_classes():
    from ashare.licences import classify_source, row_licence
    assert classify_source("CNINFO") == classify_source("cninfo") == "PUBLIC_DISCLOSURE"
    assert classify_source("EASTMONEY_PUBLIC") == "PUBLIC_FEED"
    assert classify_source("OWN") == classify_source("DERIVED_FROM_BARS") == "DERIVED"
    assert classify_source("MANUAL_REVIEW") == "MANUAL"
    assert classify_source("CSV_IMPORT") == classify_source("WIND_2026") == "LICENSED"
    assert row_licence("esg_ratings", {"source": "CNINFO"}) == "LICENSED"
    assert row_licence("industry_classifications", {"scheme": "SW_2021", "source": "CSV_IMPORT"}) == "LICENSED"
    assert row_licence("industry_classifications", {"scheme": "CSRC_2012", "source": "CSV_IMPORT"}) == \
        "PUBLIC_DISCLOSURE"
    assert row_licence("financial_facts", {"extraction_method": "PDF_TEXT_HEURISTIC"}) == "PUBLIC_DISCLOSURE"
    assert row_licence("financial_facts", {"extraction_method": "CSV_IMPORT"}) == "LICENSED"
    assert row_licence("ownership_observations", {"source": "MY_HAND_CODING"}, {"MY_HAND_CODING": "MANUAL"}) == \
        "MANUAL"


def _populate(company, tmp_path):
    from ashare.models import (SessionLocal, EsgRating, ManagementObservation, OwnershipObservation,
                               ControlObservation, DocumentPage, Disclosure)
    from helpers import add_disclosure
    d = add_disclosure(company, "关于董事张伟辞职的公告", "2026-03-01", tmp_path / "secret" / "a.pdf", ann_id="A1")
    s = SessionLocal()
    s.add(EsgRating(company_id=company.id, provider="VENDOR", rating_date="2026-01-01", rating="AA",
                    source="CSV_IMPORT"))
    s.add(ManagementObservation(company_id=company.id, observation_date="2025-12-31", person_name="张伟",
                                role="DIRECTOR", gender="男", age=53, source="CNINFO", raw_value="张伟 董事 男 53",
                                extraction_method="PDF_TABLE_HEURISTIC", disclosure_id=d.id,
                                source_document=str(tmp_path / "secret" / "a.pdf")))
    s.add(ManagementObservation(company_id=company.id, observation_date="2025-12-31", person_name="李和平",
                                role="CFO", source="CNINFO", extraction_method="PDF_TABLE_HEURISTIC"))
    s.add(OwnershipObservation(company_id=company.id, observation_date="2025-12-31", shareholder_name="王芳",
                               shareholder_nature="境内自然人", shares=1e6, source="CNINFO", rank=2,
                               raw_text="王芳 境内自然人 1,000,000"))
    s.add(OwnershipObservation(company_id=company.id, observation_date="2025-12-31",
                               shareholder_name="张伟投资有限公司", shareholder_nature="境内非国有法人", shares=5e6,
                               source="CNINFO", rank=1))
    s.add(OwnershipObservation(company_id=company.id, observation_date="2025-12-31", shareholder_name="某基金",
                               shares=1e5, source="CSV_IMPORT", rank=3))
    s.add(ControlObservation(company_id=company.id, observation_date="2025-12-31",
                             controlling_shareholder="张伟投资有限公司", actual_controller="张伟、王芳",
                             controller_nature="境内自然人", source="CNINFO"))
    s.add(DocumentPage(disclosure_id=d.id, company_id=company.id, page=1, text="张伟 董事长致辞"))
    s.commit()
    s.close()


def _csv(rel, table):
    with (Path(rel) / "csv" / f"{table}.csv").open(encoding="utf-8-sig") as fh:
        return list(csv.DictReader(fh))


def test_release_excludes_licensed_and_local_paths(company, tmp_path):
    from ashare.release import build_release
    _populate(company, tmp_path)
    r = build_release(str(tmp_path / "rel"), name="r1")
    m = json.loads((tmp_path / "rel" / "r1" / "manifest.json").read_text(encoding="utf-8"))
    assert "LICENSED" in m["licence"]["excluded"]
    assert m["licence"]["excluded_rows"]["esg_ratings"]["LICENSED"] == 1
    assert m["licence"]["excluded_rows"]["ownership_observations"]["LICENSED"] == 1
    assert r["row_counts"]["esg_ratings"] == 0 and r["row_counts"]["ownership_observations"] == 2
    assert all(not row["local_path"] for row in _csv(r["release"], "disclosures"))
    mo = _csv(r["release"], "management_observations")
    assert {x["source_document"] for x in mo} == {"https://static.cninfo.com.cn/A1.PDF", ""}
    assert str(tmp_path) not in "".join(p.read_text(encoding="utf-8-sig") for p in (Path(r["release"]) / "csv").glob("*.csv"))
    assert "jobs" not in r["row_counts"] and "research_queries" not in r["row_counts"]
    for f in ("CITATION.cff", "quality_report.md", "quality_report.html", "quality_report.json",
              "ashares_snapshot.db"):
        assert (Path(r["release"]) / f).exists(), f
    assert m["schema_revision"] and m["citation"].startswith("A-share Company Intelligence dataset release 'r1'")
    assert "sha256:" + m["database_fingerprint"] in (Path(r["release"]) / "CITATION.cff").read_text(encoding="utf-8")
    snap = sqlite3.connect(Path(r["release"]) / "ashares_snapshot.db")
    assert snap.execute("select count(*) from esg_ratings").fetchone()[0] == 0
    snap.close()
    r2 = build_release(str(tmp_path / "rel"), name="r2", include_licensed=True, exclude=("PUBLIC_FEED",))
    assert r2["row_counts"]["esg_ratings"] == 1 and r2["row_counts"]["ownership_observations"] == 3
    with pytest.raises(ValueError):
        build_release(str(tmp_path / "rel"), name="r3", exclude=("NOPE",))


def test_set_licence_overrides_default(company, tmp_path):
    from ashare.licences import set_licence, licence_summary
    from ashare.release import build_release
    _populate(company, tmp_path)
    set_licence("CSV_IMPORT", "MANUAL")
    r = build_release(str(tmp_path / "rel"), name="r", quality=False)
    assert r["row_counts"]["ownership_observations"] == 3 and r["row_counts"]["esg_ratings"] == 1
    assert any(x["table"] == "esg_ratings" and x["licence"] == "MANUAL" for x in licence_summary())


def test_pseudonymised_release(company, tmp_path):
    from ashare.release import build_release, pseudonym, load_key
    _populate(company, tmp_path)
    keyf = tmp_path / "k.key"
    r = build_release(str(tmp_path / "rel"), name="p1", pseudonymise=True, key_file=str(keyf), coarsen=True)
    rel = Path(r["release"])
    key = load_key(str(keyf))
    pz, pw, ph = pseudonym("张伟", key), pseudonym("王芳", key), pseudonym("李和平", key)
    mo = {row["role"]: row for row in _csv(rel, "management_observations")}
    assert mo["DIRECTOR"]["person_name"] == pz and mo["CFO"]["person_name"] == ph
    assert mo["DIRECTOR"]["raw_value"] == "" and mo["DIRECTOR"]["age"] == "50"
    own = {row["rank"]: row for row in _csv(rel, "ownership_observations")}
    assert own["2"]["shareholder_name"] == pw and own["2"]["raw_text"] == ""
    assert own["1"]["shareholder_name"] == "张伟投资有限公司"      # organisations are left alone
    ctl = _csv(rel, "control_observations")[0]
    assert ctl["actual_controller"] == f"{pz}、{pw}" and ctl["controlling_shareholder"] == "张伟投资有限公司"
    assert _csv(rel, "disclosures")[0]["title_cn"] == f"关于董事{pz}辞职的公告"
    assert not (rel / "csv" / "document_pages.csv").exists()
    everything = "".join(p.read_text(encoding="utf-8-sig") for p in (rel / "csv").glob("*.csv"))
    everything += (rel / "quality_report.json").read_text(encoding="utf-8")
    assert "王芳" not in everything and "李和平" not in everything
    assert key.hex() not in everything and not list(rel.rglob("*.key"))
    m = json.loads((rel / "manifest.json").read_text(encoding="utf-8"))
    assert m["pseudonymisation"]["applied"] and m["pseudonymisation"]["names_replaced"] == 3
    # stable across releases with the same key; different with another key
    r2 = build_release(str(tmp_path / "rel"), name="p2", pseudonymise=True, key_file=str(keyf), quality=False)
    assert {x["person_name"] for x in _csv(r2["release"], "management_observations")} == {pz, ph}
    r3 = build_release(str(tmp_path / "rel"), name="p3", pseudonymise=True, key_file=str(tmp_path / "other.key"),
                       quality=False)
    assert pz not in {x["person_name"] for x in _csv(r3["release"], "management_observations")}


def test_natural_person_heuristic():
    from ashare.release import is_natural_person
    assert is_natural_person("张伟") and is_natural_person("欧阳娜娜") and is_natural_person("王会")
    assert is_natural_person("JOHN SMITH", "境外自然人")
    assert not is_natural_person("香港中央结算有限公司") and not is_natural_person("中央汇金资产管理有限责任公司")
    assert not is_natural_person("某某计划") and not is_natural_person("财政局")
    assert not is_natural_person("张伟", "境内非国有法人")


def test_quality_report(company, tmp_path):
    from ashare.quality import write_quality_report
    _populate(company, tmp_path)
    r = write_quality_report(tmp_path / "q")
    md = (tmp_path / "q" / "quality_report.md").read_text(encoding="utf-8")
    assert "## 1. Coverage" in md and "Shareholders" in md and "## 6. Known gaps" in md
    rep = r["report"]
    own = rep["coverage"]["layers"]["ownership"]
    assert own["rows"] == 3 and list(own["by_year"]["2025"].values()) == [1.0]
    assert "No rows for daily prices." in rep["known_gaps"]["computed"]
    assert "<table>" in (tmp_path / "q" / "quality_report.html").read_text(encoding="utf-8")


def test_update_check(monkeypatch):
    from ashare import update
    from ashare.http import set_default_transport
    monkeypatch.delenv("ASHARE_UPDATE_URL", raising=False)
    monkeypatch.setattr(update, "configured_url", lambda url=None: url)
    assert update.check_for_update()["status"] == "NOT_CONFIGURED"
    assert update.check_for_update("http://example.org/u.json")["status"] == "ERROR"
    payload = {"version": "9.0.0", "url": "https://example.org/setup.exe", "sha256": "ab" * 32}
    set_default_transport(httpx.MockTransport(lambda req: httpx.Response(200, json=payload)))
    try:
        r = update.check_for_update("https://example.org/u.json")
        assert r["status"] == "UPDATE_AVAILABLE" and r["latest"] == "9.0.0" and r["url"].endswith("setup.exe")
        payload["version"] = "1.0.0"
        assert update.check_for_update("https://example.org/u.json")["status"] == "UP_TO_DATE"
    finally:
        set_default_transport(None)
    assert update.newer("2.0.1", "2.0.0") and not update.newer("2.0", "2.0.0")


def test_docs_and_citation_files_present():
    root = Path(__file__).resolve().parents[1]
    for f in ("docs/user_guide.md", "docs/methods.md", "docs/developer_guide.md", "docs/compliance.md",
              "docs/codebook.md", "CITATION.cff", "packaging/installer.nsi"):
        assert (root / f).exists(), f
    for f in root.joinpath("docs").glob("*.md"):
        assert "—" not in f.read_text(encoding="utf-8"), f"em dash in {f.name}"
