import pytest


@pytest.fixture
def db(tmp_path, monkeypatch):
    """Isolated database and archive directories for integration tests."""
    monkeypatch.setenv("ASHARE_DB", str(tmp_path / "test.db"))
    monkeypatch.setenv("ASHARE_RAW_DIR", str(tmp_path / "raw"))
    monkeypatch.setenv("ASHARE_DISCLOSURE_DIR", str(tmp_path / "disclosures"))
    monkeypatch.setenv("ASHARE_MARKET_RAW_DIR", str(tmp_path / "market_raw"))
    import os
    url = os.environ.get("ASHARE_TEST_DB_URL")       # v1.9: run the suite against another back end
    if url:
        monkeypatch.setenv("ASHARE_DB_URL", url)
        from ashare.models import engine, Base
        from ashare import transactions  # noqa: F401
        from sqlalchemy import text
        eng = engine()
        with eng.begin() as conn:
            conn.execute(text("DROP SCHEMA public CASCADE"))
            conn.execute(text("CREATE SCHEMA public"))
    from ashare.models import init_db, reset_init_cache
    reset_init_cache()
    init_db()
    return tmp_path


@pytest.fixture
def company(db):
    from ashare.storage import upsert_ashares
    from ashare.models import SessionLocal, Company
    upsert_ashares([{"code": "600519", "exchange": "SSE", "legal_name_cn": "贵州茅台酒股份有限公司",
                     "short_name_cn": "贵州茅台", "org_id": "gssh0600519"}])
    s = SessionLocal()
    try:
        return s.query(Company).filter_by(security_code="600519").one()
    finally:
        s.close()
