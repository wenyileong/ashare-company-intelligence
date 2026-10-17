"""Minimal Stata .dta writer (format 118, Stata 14 and later) (v1.7).

Writes numeric columns as double and text columns as str# (UTF-8, up to
2,045 bytes), with variable labels and a dataset label. Missing numbers are
written as Stata's system missing (.). This covers research panels without a
dependency on pandas.
"""
from __future__ import annotations

import re
import struct
from datetime import datetime

MISSING_DOUBLE = struct.pack("<d", 2.0 ** 1023)   # Stata '.'
_DOUBLE = 65526


def _name(n: str, used: set) -> str:
    s = re.sub(r"[^A-Za-z0-9_]", "_", n)
    if not s or s[0].isdigit():
        s = "v_" + s
    s = s[:32]
    base, k = s, 1
    while s in used:
        suffix = f"_{k}"
        s = base[:32 - len(suffix)] + suffix
        k += 1
    used.add(s)
    return s


def _fixed(text: str, size: int) -> bytes:
    b = text.encode("utf-8")[:size - 1]
    return b + b"\x00" * (size - len(b))


def write_dta(path: str, rows: list[dict], columns: list[str], labels: dict[str, str] | None = None,
              dataset_label: str = "") -> dict:
    labels = labels or {}
    used: set = set()
    names = [_name(c, used) for c in columns]
    types, widths = [], []
    for c in columns:
        vals = [r.get(c) for r in rows]
        numeric = all(v is None or (isinstance(v, (int, float)) and not isinstance(v, bool)) or isinstance(v, bool)
                      for v in vals)
        if numeric:
            types.append(_DOUBLE)
            widths.append(8)
        else:
            w = max([len(str(v).encode("utf-8")) for v in vals if v is not None] + [1])
            w = min(w, 2045)
            types.append(w)
            widths.append(w)
    K, N = len(columns), len(rows)
    out = bytearray()
    offsets = {}

    def tag(t):
        out.extend(t.encode("ascii"))
    tag("<stata_dta><header><release>118</release><byteorder>LSF</byteorder>")
    tag("<K>")
    out += struct.pack("<H", K)
    tag("</K><N>")
    out += struct.pack("<Q", N)
    tag("</N><label>")
    lab = dataset_label.encode("utf-8")[:80]
    out += struct.pack("<H", len(lab)) + lab
    tag("</label><timestamp>")
    ts = datetime.now().strftime("%d %b %Y %H:%M").encode("ascii")
    out += bytes([len(ts)]) + ts
    tag("</timestamp></header>")
    offsets["map"] = len(out)
    tag("<map>")
    map_pos = len(out)
    out += b"\x00" * (14 * 8)
    tag("</map>")
    offsets["variable_types"] = len(out)
    tag("<variable_types>")
    for t in types:
        out += struct.pack("<H", t)
    tag("</variable_types>")
    offsets["varnames"] = len(out)
    tag("<varnames>")
    for n in names:
        out += _fixed(n, 129)
    tag("</varnames>")
    offsets["sortlist"] = len(out)
    tag("<sortlist>")
    out += b"\x00\x00" * (K + 1)
    tag("</sortlist>")
    offsets["formats"] = len(out)
    tag("<formats>")
    for t, w in zip(types, widths):
        out += _fixed("%10.0g" if t == _DOUBLE else f"%-{min(w, 244)}s", 57)
    tag("</formats>")
    offsets["value_label_names"] = len(out)
    tag("<value_label_names>")
    out += b"\x00" * (129 * K)
    tag("</value_label_names>")
    offsets["variable_labels"] = len(out)
    tag("<variable_labels>")
    for c in columns:
        out += _fixed(labels.get(c, c), 321)
    tag("</variable_labels>")
    offsets["characteristics"] = len(out)
    tag("<characteristics></characteristics>")
    offsets["data"] = len(out)
    tag("<data>")
    for r in rows:
        for c, t, w in zip(columns, types, widths):
            v = r.get(c)
            if t == _DOUBLE:
                if v is None or (isinstance(v, float) and v != v):
                    out += MISSING_DOUBLE
                else:
                    out += struct.pack("<d", float(v))
            else:
                # truncate to the width without cutting a UTF-8 character in half
                b = ("" if v is None else str(v)).encode("utf-8")[:w].decode("utf-8", "ignore").encode("utf-8")
                out += b + b"\x00" * (w - len(b))
    tag("</data>")
    offsets["strls"] = len(out)
    tag("<strls></strls>")
    offsets["value_labels"] = len(out)
    tag("<value_labels></value_labels>")
    offsets["end_tag"] = len(out)
    tag("</stata_dta>")
    offsets["eof"] = len(out)
    order = ["stata_data", "map", "variable_types", "varnames", "sortlist", "formats", "value_label_names",
             "variable_labels", "characteristics", "data", "strls", "value_labels", "end_tag", "eof"]
    offsets["stata_data"] = 0
    out[map_pos:map_pos + 14 * 8] = b"".join(struct.pack("<Q", offsets[k]) for k in order)
    with open(path, "wb") as fh:
        fh.write(out)
    return {"path": path, "variables": dict(zip(columns, names)), "rows": N}
