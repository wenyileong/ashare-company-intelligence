"""The topology view (v2.1), registered in the Visualise section (v2.2). It keeps its own command (``topology``),
snapshot (schema version 1) and viewer; the registry lists it with its readiness."""
from __future__ import annotations

from ..registry import register
from ..view import View
from . import _checks


@register
class TopologyView(View):
    id = "topology"
    family = "topology"
    title = "Topology view"
    intro = ("The five links of the Nested Valuation Framework for a set of companies or a CSRC industry over a span "
             "of years, with the document behind every item and the gaps shown.")
    evidence = "DOCUMENTED_FACT"
    requires = [_checks.periodic_figures(), _checks.guidance(), _checks.holders(), _checks.control(),
                _checks.industry()]

    def command(self) -> str:
        return "topology"
