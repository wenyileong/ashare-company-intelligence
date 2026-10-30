"""The five NVF layers, and the panel variables that belong to each (v2.1, plan E1).

The layers are the columns of the topology view: what institutions do, what companies can produce, what they report,
what is expected of them, and how the market values them. Every panel variable is assigned to one layer, or to none
(identifiers, listing status, index membership), so that the coverage of a layer can be counted from the panel's own
registry rather than from a second list.

The Chinese labels are proposals for the glossary (``docs/glossary_zh_CN.md``, part 11), to stand until reviewed.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Layer:
    id: str
    label: str
    label_zh: str
    x: int            # fixed coordinate of the layer in the topology view
    colour: str       # Okabe-Ito, as the other charts


LAYERS = (
    Layer("institutional", "Institutional coordination", "制度协调", -760, "#0072B2"),
    Layer("capability", "Productive capability", "生产能力", -380, "#009E73"),
    Layer("fundamentals", "Corporate fundamentals", "公司基本面", 0, "#CC79A7"),
    Layer("expectations", "Investor expectations", "投资者预期", 380, "#E69F00"),
    Layer("valuation", "Market valuation", "市场估值", 760, "#D55E00"),
)
LAYER_IDS = tuple(layer.id for layer in LAYERS)
BY_ID = {layer.id: layer for layer in LAYERS}

# panel variable group -> layer (None: not a layer of the NVF)
GROUP_LAYER = {
    "financial": "fundamentals", "derived": "fundamentals", "ratio": "fundamentals", "segments": "fundamentals",
    "ownership": "fundamentals", "control": "fundamentals", "governance": "fundamentals",
    "human_capital": "capability",
    "market": "valuation",
    "regulatory": "institutional", "industry": "institutional",
    "index": None, "listing": None,
}
# single variables that the group would place elsewhere
VARIABLE_LAYER = {
    "rd_expense": "capability", "rd_intensity": "capability", "capex": "capability",
    "development_expenditure": "capability", "employees": "capability",
    "construction_in_progress": "capability", "fixed_assets": "capability",
}


def layer_of(variable: str) -> str | None:
    """The NVF layer of a panel variable, or None."""
    from ..panel import variables
    if variable in VARIABLE_LAYER:
        return VARIABLE_LAYER[variable]
    v = variables().get(variable)
    if v is None:
        raise KeyError(f"unknown panel variable {variable!r}")
    return GROUP_LAYER.get(v.group)


def variables_by_layer() -> dict[str, list[str]]:
    from ..panel import variables
    out: dict[str, list[str]] = {lid: [] for lid in LAYER_IDS}
    for name in sorted(variables()):
        lid = layer_of(name)
        if lid:
            out[lid].append(name)
    return out
