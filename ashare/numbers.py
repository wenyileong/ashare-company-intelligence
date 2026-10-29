"""Checks on amounts read from report text (v2.0.8, finding 85).

Two faults in the live data could not be caught by looking at one number alone:

* a note reference glued to an amount ("七、1" + "1,791,960,892.40" read as "11,791,960,892.40") gives a
  well-formed number, so only another reading of the same figure can show the extra digits;
* an amount cut at a separator or a line break ("22,103" for "22,103,629.82", "1,355.2") is caught by the
  number of decimals: statement amounts in yuan carry two.
"""
from __future__ import annotations

import re

_YUAN = re.compile(r"^\(?-?\d{1,3}(?:,\d{3})*\.\d{2}\)?$|^\(?-?\d+\.\d{2}\)?$")
_LARGER = re.compile(r"^\(?-?\d{1,3}(?:,\d{3})*(?:\.\d{1,4})?\)?$|^\(?-?\d+(?:\.\d{1,4})?\)?$")


def _bare(raw: str) -> str:
    return re.sub(r"[\s,，()（）]", "", str(raw or "")).replace("−", "-").lstrip("-")


def well_formed_amount(raw: str | None, multiplier: float = 1.0) -> bool:
    """True when ``raw`` looks like a whole amount for its unit: two decimals in yuan; up to four decimals,
    or none, in thousands, ten-thousands, millions or hundred-millions. Dashes are not amounts."""
    t = str(raw or "").strip().replace("，", ",").replace("−", "-").replace(" ", "")
    if not t or not re.search(r"\d", t):
        return False
    return bool((_YUAN if multiplier == 1.0 else _LARGER).match(t))


def glue_split(longer: str | None, shorter: str | None) -> str | None:
    """If ``longer`` is ``shorter`` with one or two digits in front (a glued note reference), return
    ``shorter``; otherwise None. Both are raw texts of one figure from two readings."""
    a, b = _bare(longer), _bare(shorter)
    if not a or not b or a == b or not a.endswith(b):
        return None
    extra = a[: len(a) - len(b)]
    if 1 <= len(extra) <= 2 and extra.isdigit() and re.search(r"\d", b):
        return shorter
    return None


def power_of_ten(a: float | None, b: float | None) -> int | None:
    """The exponent k when a = b × 10^k exactly (to 0.1%) for k in ±3, ±4, ±6, ±8; else None."""
    import math
    if not a or not b or (a > 0) != (b > 0):
        return None
    k = math.log10(abs(a) / abs(b))
    for p in (3, 4, 6, 8, -3, -4, -6, -8):
        if abs(k - p) < 0.0005:
            return p
    return None
