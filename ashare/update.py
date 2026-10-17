"""Update check (v2.0).

The program never contacts an update server unless one is configured, either
with the ``ASHARE_UPDATE_URL`` environment variable or under Settings in the
desktop application. The URL must use HTTPS and return JSON of the form::

    {"version": "2.0.1",
     "url": "https://example.org/AShareScraper-2.0.1-setup.exe",
     "sha256": "<hash of the installer>",
     "notes": "What changed"}

The check only reports; it never downloads or installs anything. The user
downloads the installer and can compare its SHA-256 hash with the one given.
"""
from __future__ import annotations

import os
import re

from . import __version__


def _parse(v: str) -> tuple:
    nums = [int(x) for x in re.findall(r"\d+", v or "")[:3]]
    return tuple(nums + [0] * (3 - len(nums)))


def newer(candidate: str, current: str = __version__) -> bool:
    return _parse(candidate) > _parse(current)


def configured_url(url: str | None = None) -> str | None:
    if url:
        return url
    if os.environ.get("ASHARE_UPDATE_URL"):
        return os.environ["ASHARE_UPDATE_URL"]
    try:
        from .gui import load_settings
        return load_settings().get("update_url") or None
    except Exception:
        return None


def check_for_update(url: str | None = None) -> dict:
    """Compare the running version with the one published at the update URL."""
    url = configured_url(url)
    base = {"current": __version__}
    if not url:
        return {**base, "status": "NOT_CONFIGURED",
                "message": "No update URL is set (Settings, or ASHARE_UPDATE_URL); nothing was contacted."}
    if not url.lower().startswith("https://"):
        return {**base, "status": "ERROR", "message": "The update URL must use HTTPS."}
    from .config import USER_AGENT
    from .http import RateLimitedClient
    client = RateLimitedClient(USER_AGENT, 1.0, retries=1)
    try:
        info = client.get(url).json()
    except Exception as exc:                          # network, HTTP or JSON errors
        return {**base, "status": "ERROR", "message": f"Could not read the update information: {exc}"}
    finally:
        client.close()
    latest = str(info.get("version") or "") if isinstance(info, dict) else ""
    if not latest:
        return {**base, "status": "ERROR", "message": "The update information has no version."}
    if newer(latest):
        dl = str(info.get("url") or "")
        return {**base, "status": "UPDATE_AVAILABLE", "latest": latest,
                "url": dl if dl.lower().startswith("https://") else None,
                "sha256": info.get("sha256"), "notes": info.get("notes"),
                "message": f"Version {latest} is available (you have {__version__})."}
    return {**base, "status": "UP_TO_DATE", "latest": latest,
            "message": f"You have the latest version ({__version__})."}
