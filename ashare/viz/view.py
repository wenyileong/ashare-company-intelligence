"""The View contract (v2.2, plan section B4.2).

Every view in the Visualise section is one :class:`View`, registered in :mod:`ashare.viz.registry`. A view declares
its parameters once (the desktop form and the command-line options are generated from them), the data it needs (with
a readiness check that names the action filling each gap), its evidential status and its outputs; ``build`` returns
a snapshot (graph or series) and the figures drawn from it.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

FAMILIES = ("topology", "company", "relational", "sector", "econometric", "coverage")
EVIDENCE = {
    "DOCUMENTED_FACT": "Every item is a documented fact: a report, announcement, classification or price states it.",
    "OBSERVED_ASSOCIATION": "An observed association between documented values; not evidence of cause.",
    "DESCRIPTIVE_PROXY": "A descriptive proxy for a concept of the paper, under the definition named; not the "
                         "paper's measure.",
}
MET, PARTLY, MISSING = "MET", "PARTLY", "MISSING"


@dataclass
class Requirement:
    """One kind of data a view needs. ``check(params)`` returns (status, detail, action)."""
    key: str
    label: str
    check: Callable[[dict], tuple[str, str, str | None]]


@dataclass
class Built:
    """What ``View.build`` returns: the snapshot and the figures (chart specifications) drawn from it."""
    snapshot: dict
    figures: list = field(default_factory=list)        # [(name, ChartSpec)]


class View:
    id: str = ""
    family: str = ""
    title: str = ""
    intro: str = ""
    evidence: str = "DOCUMENTED_FACT"
    outputs: tuple[str, ...] = ("html", "svg", "csv")
    params: list[dict] = []
    requires: list[Requirement] = []

    def readiness(self, params: dict | None = None) -> list[dict]:
        out = []
        for r in self.requires:
            try:
                status, detail, action = r.check(params or {})
            except Exception as exc:                    # a check never stops a view
                status, detail, action = MISSING, f"could not be checked ({exc!r})", None
            out.append({"requirement": r.label, "status": status, "detail": detail, "action": action})
        return out

    def build(self, params: dict) -> Built:            # pragma: no cover - each view implements it
        raise NotImplementedError

    def command(self) -> str:
        return "viz-" + self.id.replace("_", "-")


def readiness_line(rows: list[dict]) -> str:
    if not rows:
        return "Data: nothing required."
    parts = []
    for r in rows:
        mark = {"MET": "ready", "PARTLY": "partly", "MISSING": "missing"}[r["status"]]
        part = f"{r['requirement']}: {mark}" + (f" ({r['detail']})" if r.get("detail") else "")
        if r["status"] != MET and r.get("action"):
            part += f"; run '{r['action']}'"
        parts.append(part)
    return "Data: " + "; ".join(parts) + "."
