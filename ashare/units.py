"""Shared detection of declared table units (v1.4).

Annual reports state the unit of each table in a line such as "单位：元",
"金额单位：万元 币种：人民币" or "单位：人民币万元". A unit mentioned in a
sentence ("实现营业收入1,500亿元") is not a declaration.
"""
from __future__ import annotations

import re

UNIT_DECL = re.compile(r"(?:金额)?单位\s*[:：]\s*(?:人民币)?\s*(亿元|百万元|万元|千元|元)")
UNIT_CODES = {"亿元": ("CNY_100M", 1e8), "百万元": ("CNY_1M", 1e6), "万元": ("CNY_10K", 1e4),
              "千元": ("CNY_1K", 1e3), "元": ("CNY", 1.0)}


def first_declared(text: str) -> tuple[str, float] | None:
    m = UNIT_DECL.search(text or "")
    return UNIT_CODES[m.group(1)] if m else None


def last_declared(text: str) -> tuple[str, float] | None:
    found = list(UNIT_DECL.finditer(text or ""))
    return UNIT_CODES[found[-1].group(1)] if found else None
