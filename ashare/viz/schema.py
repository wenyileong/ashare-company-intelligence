"""The snapshot's JSON Schema (draft 2020-12), and a checker for the subset of it the schema uses.

The schema is published with each export (``snapshot.schema.json``) so that other programs, the research suite among
them, can read snapshots without this code. The checker avoids a dependency on ``jsonschema``: it understands
``type``, ``required``, ``properties``, ``items``, ``enum`` and ``additionalProperties: false``, which is all the
schema uses.
"""
from __future__ import annotations

_DATES = {"type": "object", "properties": {k: {"type": ["string", "null"]} for k in (
    "event_date", "published_date", "observed_date", "valid_from", "valid_to")}, "additionalProperties": False}
_POS = {"type": "object", "required": ["x", "y", "z", "y2"],
        "properties": {"x": {"type": "number"}, "y": {"type": "number"}, "z": {"type": "number"},
                       "y2": {"type": "number"}}}


def schema() -> dict:
    from .snapshot import EVIDENCE, RELATIONS, NODE_KINDS, BASIS_KINDS, SCHEMA_VERSION
    from ..nvf.layers import LAYER_IDS
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": f"https://github.com/wenyileong/ashare-company-intelligence/snapshot/v{SCHEMA_VERSION}",
        "title": "A-share Company Intelligence graph snapshot",
        "type": "object",
        "required": ["schema_version", "software", "parameters", "policy", "layers", "coverage", "nodes", "edges",
                     "series", "summary", "notes"],
        "properties": {
            "schema_version": {"enum": [SCHEMA_VERSION]},
            "software": {"type": "string"},
            "parameters": {"type": "object", "required": ["companies", "start", "end", "as_of", "date_basis",
                                                          "periods", "expectations"]},
            "policy": {"type": "object", "required": ["pseudonymisation", "licences", "point_in_time"]},
            "layers": {"type": "array", "items": {"type": "object", "required": ["id", "label", "label_zh", "x",
                                                                                 "colour"]}},
            "coverage": {"type": "array", "items": {
                "type": "object", "required": ["layer", "status", "observations", "companies_covered", "note"],
                "properties": {"layer": {"enum": list(LAYER_IDS)},
                               "status": {"enum": ["COMPLETE", "PARTIAL", "GAP"]}}}},
            "nodes": {"type": "array", "items": {
                "type": "object", "required": ["id", "kind", "layer", "label", "position", "dates", "masked",
                                               "flags"],
                "properties": {"id": {"type": "string"}, "kind": {"enum": list(NODE_KINDS)},
                               "layer": {"enum": list(LAYER_IDS) + [None]}, "label": {"type": "string"},
                               "position": _POS, "dates": _DATES, "masked": {"type": "boolean"},
                               "flags": {"type": "array", "items": {"type": "string"}},
                               "value": {"type": ["number", "null"]}, "low": {"type": ["number", "null"]},
                               "high": {"type": ["number", "null"]}}}},
            "edges": {"type": "array", "items": {
                "type": "object", "required": ["id", "source", "target", "relation", "evidence_status", "basis",
                                               "dates"],
                "properties": {"relation": {"enum": list(RELATIONS)}, "evidence_status": {"enum": list(EVIDENCE)},
                               "basis": {"type": "object", "required": ["kind"],
                                         "properties": {"kind": {"enum": list(BASIS_KINDS)}}},
                               "dates": _DATES}}},
            "series": {"type": "array"}, "summary": {"type": "array"}, "notes": {"type": "array"},
        },
    }


_TYPES = {"object": dict, "array": list, "string": str, "boolean": bool, "null": type(None)}


def _is(value, t: str) -> bool:
    if t == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if t == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    return isinstance(value, _TYPES[t])


def _check(value, sch: dict, path: str, out: list[str]) -> None:
    if len(out) > 50:
        return
    if "enum" in sch and value not in sch["enum"]:
        out.append(f"{path}: {value!r} is not one of {sch['enum']}")
        return
    if "type" in sch:
        types = sch["type"] if isinstance(sch["type"], list) else [sch["type"]]
        if not any(_is(value, t) for t in types):
            out.append(f"{path}: expected {' or '.join(types)}")
            return
    if isinstance(value, dict):
        for k in sch.get("required", []):
            if k not in value:
                out.append(f"{path}: missing {k}")
        props = sch.get("properties", {})
        for k, v in value.items():
            if k in props:
                _check(v, props[k], f"{path}.{k}", out)
            elif sch.get("additionalProperties") is False:
                out.append(f"{path}: unexpected {k}")
    if isinstance(value, list) and "items" in sch:
        for i, v in enumerate(value):
            _check(v, sch["items"], f"{path}[{i}]", out)


def check(snap: dict) -> list[str]:
    out: list[str] = []
    _check(snap, schema(), "snapshot", out)
    return out
