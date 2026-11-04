"""Versioned definitions of the descriptive proxies for the paper's concepts (v2.2, plan section B6).

Views that stand in for Institutional Visibility or the Fractal Investment Clock read their definitions from here,
and every snapshot records the version it used, so that a figure can always be traced to the definition behind it.
Version 0 is provisional: labelled proxies, to be replaced by the paper's operational definitions as version 1.
"""
from __future__ import annotations

DEFINITIONS = {
    "nvf-0": {
        "status": "provisional descriptive proxies, not the paper's measures",
        "capability": "R&D expense and capital expenditure, each over revenue",
        "fundamentals": "revenue; net profit attributable to the parent",
        "expectations": "management guidance (业绩预告, 业绩快报), a disclosed proxy",
        "valuation": "market value at the year end",
        "growth": "year on year",
    },
}
CURRENT = "nvf-0"


def current() -> dict:
    return {"version": CURRENT, **DEFINITIONS[CURRENT]}
