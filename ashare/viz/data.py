"""The data layer shared by the views of the Visualise section (v2.2, plan section B4.2).

A view reads the database only through a :class:`Context`, which applies in one place the rules every view must keep:

* **point in time**: only what was published on or before ``as_of`` (``published`` gives a row's publication date);
* **persons**: natural persons are shown under the same pseudonyms as in releases (``mask``);
* **licences**: licensed rows are left out unless ``include_licensed`` (``licence_ok``).
"""
from __future__ import annotations

from datetime import date


class ParamError(ValueError):
    """A parameter a view cannot use; the message says what to give instead."""


def check_date(value: str | None, label: str) -> str | None:
    if value in (None, ""):
        return None
    try:
        date.fromisoformat(str(value))
    except ValueError:
        raise ParamError(f"{label} is not a date (YYYY-MM-DD): {value!r}")
    return str(value)


class Context:
    def __init__(self, as_of: str | None = None, include_licensed: bool = False, key: bytes | None = None):
        from ..models import SessionLocal, init_db
        from ..release import load_key, Pseudonymiser
        init_db()
        self.as_of = check_date(as_of, "As of") or date.today().isoformat()
        self.include_licensed = bool(include_licensed)
        self.s = SessionLocal()
        self.masker = Pseudonymiser(key if key is not None else load_key())
        self.masked_originals: set[str] = set()
        self._published: dict[int, str | None] = {}
        self._overrides = None

    def close(self) -> None:
        self.s.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    # --- point in time --------------------------------------------------------------------------------------------

    def published(self, disclosure_id: int | None) -> str | None:
        """The announcement date of a document (None when the row has no document)."""
        if disclosure_id is None:
            return None
        if disclosure_id not in self._published:
            from ..models import Disclosure
            d = self.s.get(Disclosure, disclosure_id)
            self._published[disclosure_id] = d.announcement_date if d else None
        return self._published[disclosure_id]

    def known(self, published: str | None, observed: str | None = None) -> bool:
        """Whether a row is known on ``as_of``: published by then (or, without a publication date, observed by
        then)."""
        when = published or observed
        return bool(when) and when <= self.as_of

    # --- persons and licences -------------------------------------------------------------------------------------

    def mask(self, table: str, row: dict, col: str) -> tuple[str, bool]:
        """A column's value as shown: a natural person's name is replaced by its pseudonym, as in releases."""
        original = row.get(col) or ""
        self.masker.learn(table, row)
        shown = self.masker.apply(table, row).get(col) or ""
        if shown != original:
            from ..release import strip_nature
            self.masked_originals.update(x for x in (original, strip_nature(original)[0]) if x and len(x) >= 2)
            return shown, True
        return shown, False

    def person(self, name: str) -> str:
        """A natural person (directors and officers) always under a pseudonym."""
        shown, _ = self.mask("persons", {"name": name}, "name")
        return shown

    def licence_ok(self, table: str, row: dict) -> bool:
        from ..licences import row_licence, _overrides
        if self.include_licensed:
            return True
        if self._overrides is None:
            self._overrides = _overrides(self.s)
        return row_licence(table, row, self._overrides) != "LICENSED"

    def policy(self) -> dict:
        from ..release import PERSON_RULE
        return {"point_in_time": f"only what was published on or before {self.as_of}",
                "pseudonymisation": PERSON_RULE,
                "licences": "all classes" if self.include_licensed else "LICENSED rows excluded, as in releases"}

    def leaks(self, text: str) -> list[str]:
        """Names of persons that appear unmasked in ``text`` (for the snapshot's own check)."""
        return sorted(n for n in self.masked_originals if n in text)

    # --- companies ------------------------------------------------------------------------------------------------

    def company(self, code: str):
        from ..models import Company
        code = str(code or "").strip().zfill(6)
        c = self.s.query(Company).filter_by(security_code=code).first()
        if c is None:
            raise ParamError(f"not in the company list: {code}")
        return c

    def label(self, c) -> str:
        return f"{c.security_code} {c.short_name_cn or c.legal_name_cn or ''}".strip()
