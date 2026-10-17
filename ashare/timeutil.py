from datetime import datetime, timezone


def utcnow() -> datetime:
    """Naive UTC timestamp (SQLite stores naive datetimes); replaces the
    deprecated ``datetime.datetime.utcnow``."""
    return datetime.now(timezone.utc).replace(tzinfo=None)
