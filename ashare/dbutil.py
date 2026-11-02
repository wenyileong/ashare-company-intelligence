"""Database helpers (v2.1.2).

SQLite accepts a limited number of values in one statement (32,766 in current versions, 999 in older ones). A
catalogue refresh over ten months queued more document IDs than that for one ``IN (...)`` query and failed after
thirteen hours (finding 120). ``in_chunks`` runs such queries a few hundred values at a time.
"""
from __future__ import annotations

from typing import Iterable, Iterator, Sequence

CHUNK = 500


def chunks(values: Sequence, size: int = CHUNK) -> Iterator[list]:
    values = list(values)
    for i in range(0, len(values), size):
        yield values[i:i + size]


def in_chunks(query, column, values: Iterable, size: int = CHUNK) -> list:
    """The rows of ``query.filter(column.in_(chunk))`` for every chunk of ``values``, in one list.

    The caller orders the result itself if order matters: each chunk is a separate query."""
    out: list = []
    for part in chunks(list(values), size):
        out.extend(query.filter(column.in_(part)).all())
    return out


def delete_in_chunks(query, column, values: Iterable, size: int = CHUNK) -> int:
    """``query.filter(column.in_(chunk)).delete()`` for every chunk; returns the rows deleted."""
    n = 0
    for part in chunks(list(values), size):
        n += query.filter(column.in_(part)).delete(synchronize_session=False) or 0
    return n
