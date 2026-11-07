"""Stored file paths (v2.3.0, plan section B1, finding 145).

Every read of a stored document or archive path goes through this module, so that a data folder can be moved without
losing the links to its files. The rules:

* **Reading** (phase 2). A relative path is read against the data root (and, for paths written by the command line
  before v2.3, against the working folder). An absolute path that exists is used as it is. An absolute path that
  does not exist is looked for at the same place under the current folders: the part after the last ``disclosures``,
  ``raw`` or ``market_raw`` is joined to the folder now configured for it, and the file is accepted only when its
  SHA-256 matches the stored hash. A path that cannot be resolved is returned unchanged, so callers see exactly the
  missing file they saw before v2.3.
* **Writing** (phase 3, switch ``storage.relative_paths``). New paths under the data root are stored relative to it,
  with forward slashes (``disclosures/600519/<sha256>.pdf``); others, or with the switch off, as before.

Nothing here writes to the database. The tests forbid building a path from ``local_path`` or ``payload_path`` anywhere
else.
"""
from __future__ import annotations

import hashlib
from pathlib import Path, PurePosixPath, PureWindowsPath

from .config import disclosure_dir, raw_dir, market_raw_dir
from .features import data_root, enabled

_ANCHORS = ("disclosures", "raw", "market_raw")
_recovered: dict[tuple[str, str | None], Path | None] = {}
_stats = {"recovered": 0, "refused": 0}


def _anchor_dir(name: str) -> Path:
    return {"disclosures": disclosure_dir, "raw": raw_dir, "market_raw": market_raw_dir}[name]().resolve()


def _parts(value: str) -> tuple[bool, list[str]]:
    """(absolute, parts) of a stored path, written on Windows or elsewhere."""
    if "\\" in value or (len(value) > 1 and value[1] == ":"):
        p = PureWindowsPath(value)
        return p.is_absolute() or bool(p.drive), list(p.parts[1:] if p.drive or p.root else p.parts)
    p = PurePosixPath(value)
    return p.is_absolute(), list(p.parts[1:] if p.root else p.parts)


def sha256_file(path: Path) -> str | None:
    try:
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(1 << 20), b""):
                h.update(chunk)
        return h.hexdigest()
    except OSError:
        return None


def _tail_candidate(parts: list[str]) -> Path | None:
    low = [p.lower() for p in parts]
    for i in range(len(low) - 1, -1, -1):
        if low[i] in _ANCHORS and i < len(parts) - 1:
            return _anchor_dir(low[i]).joinpath(*parts[i + 1:])
    return None


def resolve_stored(value: str | None, sha256: str | None = None) -> Path | None:
    """The file a stored path names now, or the stored path unchanged if it cannot be found; ``None`` for none."""
    if not value:
        return None
    absolute, parts = _parts(value)
    if not absolute:
        rel = Path(*parts) if parts else Path(value)
        for base in (data_root(), Path.cwd()):
            cand = base / rel
            if cand.exists():
                return cand
        found = _recover(value, parts, sha256)
        return found or data_root() / rel
    own = Path(value)
    if own.exists():
        return own
    return _recover(value, parts, sha256) or own


def _recover(value: str, parts: list[str], sha256: str | None) -> Path | None:
    key = (value, sha256)
    if key in _recovered:
        return _recovered[key]
    found = None
    cand = _tail_candidate(parts)
    if cand is not None and cand.exists():
        # the content-addressed name is itself the hash; anything else must match the stored hash
        if sha256 is None or cand.stem.lower() == sha256.lower() or sha256_file(cand) == sha256:
            found = cand
            _stats["recovered"] += 1
        else:
            _stats["refused"] += 1
    _recovered[key] = found
    return found


def clear_cache() -> None:
    _recovered.clear()
    _stats.update(recovered=0, refused=0)


def recovery_stats() -> dict:
    return dict(_stats)


def document_path(d) -> Path | None:
    """The file of a disclosure (``disclosures.local_path``), wherever the data folder now is."""
    return resolve_stored(getattr(d, "local_path", None), getattr(d, "sha256", None))


def has_document(d) -> bool:
    p = document_path(d)
    return p is not None and p.exists()


def raw_path(value: str | None, sha256: str | None = None) -> Path | None:
    """The file of an archived source response (``raw_records.payload_path``)."""
    return resolve_stored(value, sha256)


def to_stored(path: Path | str) -> str:
    """The form in which a new path is written: relative to the data root (forward slashes) when the switch is on and
    the file lies under the root; otherwise exactly as before v2.3."""
    p = Path(path)
    if enabled("storage.relative_paths"):
        try:
            return p.resolve().relative_to(data_root()).as_posix()
        except ValueError:
            pass
    return str(p)


def stored_forms(path: Path | str) -> list[str]:
    """The forms in which a file's path may be stored, for an exact lookup."""
    p = Path(path)
    forms = {str(p)}
    try:
        r = p.resolve()
        forms.add(str(r))
        forms.add(r.relative_to(data_root()).as_posix())
    except (OSError, ValueError):
        pass
    return sorted(forms)


def same_file(a, b) -> bool:
    try:
        return Path(a).resolve() == Path(b).resolve()
    except OSError:
        return str(a) == str(b)


def display_source(text: str | None, sha256: str | None = None) -> str | None:
    """A ``source_document`` value for display: a local path resolved to where the file is now; an address as it is."""
    if not text or "://" in text:
        return text
    absolute, parts = _parts(text)
    if absolute or (parts and parts[0].lower() in _ANCHORS):
        p = resolve_stored(text, sha256)
        if p is not None and p.exists():
            return str(p)
    return text


def classify(value: str | None) -> str:
    """For the paths report: none, relative, inside (absolute under the root), outside (absolute elsewhere)."""
    if not value:
        return "none"
    absolute, _ = _parts(value)
    if not absolute:
        return "relative"
    try:
        Path(value).resolve().relative_to(data_root())
        return "inside"
    except (ValueError, OSError):
        return "outside"
