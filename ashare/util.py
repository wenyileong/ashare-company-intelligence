"""Small helpers shared by the commands (v2.3.0)."""
from __future__ import annotations


def parse_codes(raw) -> tuple[list[str], list[str]]:
    """Security codes from a comma-separated string or a list: zero-padded to six digits, in the order given, with
    duplicates dropped (v2.3.0, finding 142). Returns (codes, dropped duplicates)."""
    items = raw if isinstance(raw, (list, tuple, set)) else str(raw or "").replace("，", ",").split(",")
    seen, codes, dropped = set(), [], []
    for c in items:
        c = str(c).strip()
        if not c:
            continue
        c = c.zfill(6)
        if c in seen:
            dropped.append(c)
            continue
        seen.add(c)
        codes.append(c)
    return codes, dropped


def plural(n: int, one: str, many: str | None = None) -> str:
    """'1 announcement', '2 announcements' (v2.3.0, finding 146)."""
    return f"{n:,} {one if n == 1 else (many or one + 's')}"


def span(a: str, b: str) -> str:
    """'2020-12-30', or '2020-12-30 to 2020-12-31' (v2.3.0, finding 146)."""
    return a if a == b else f"{a} to {b}"
