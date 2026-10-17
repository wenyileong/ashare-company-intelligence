"""Runtime configuration.

Paths are resolved at call time (not import time) so that environment
overrides such as ``ASHARE_DB`` take effect in tests and in scripted runs.
The module-level constants are retained for backwards compatibility.
"""
from pathlib import Path
import os


def db_path() -> Path:
    return Path(os.getenv("ASHARE_DB", "ashares.db"))


def raw_dir() -> Path:
    return Path(os.getenv("ASHARE_RAW_DIR", "raw"))


def disclosure_dir() -> Path:
    return Path(os.getenv("ASHARE_DISCLOSURE_DIR", "disclosures"))


def market_raw_dir() -> Path:
    return Path(os.getenv("ASHARE_MARKET_RAW_DIR", "market_raw"))


DB_PATH = db_path()
RAW_DIR = raw_dir()
DISCLOSURE_DIR = disclosure_dir()
MARKET_RAW_DIR = market_raw_dir()

USER_AGENT = os.getenv(
    "ASHARE_USER_AGENT",
    "AshareResearchDataCollector/2.0.2 (research use; replace-contact-before-production)",
)
REQUEST_TIMEOUT = float(os.getenv("ASHARE_TIMEOUT", "30"))
REQUESTS_PER_SECOND = float(os.getenv("ASHARE_RPS", "1"))

CNINFO_QUERY_URL = os.getenv(
    "CNINFO_QUERY_URL", "https://www.cninfo.com.cn/new/hisAnnouncement/query"
)
CNINFO_STATIC_BASE = os.getenv("CNINFO_STATIC_BASE", "https://static.cninfo.com.cn/")

MARKET_RPS = float(os.getenv("ASHARE_MARKET_RPS", os.getenv("ASHARE_RPS", "1")))
