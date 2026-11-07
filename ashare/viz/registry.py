"""The views of the Visualise section (v2.2, plan section B4.1). The desktop pages and the ``viz-*`` commands are
generated from this list, so a view added here appears in both."""
from __future__ import annotations

_VIEWS: dict = {}
_LOADED = False


def register(view_cls):
    v = view_cls()
    _VIEWS[v.id] = v
    return view_cls


def _load() -> None:
    global _LOADED
    if not _LOADED:
        from .views import topology, coverage, ego_map, guidance_outcome  # noqa: F401  (registration)
        from .views import market_map, common_ownership, sectors, timeliness_view  # noqa: F401  (v2.3.0)
        _LOADED = True


def views() -> list:
    _load()
    return list(_VIEWS.values())


def get(view_id: str):
    _load()
    key = view_id.replace("-", "_")
    if key not in _VIEWS:
        raise KeyError(f"no view {view_id!r}; known: {', '.join(sorted(_VIEWS))}")
    return _VIEWS[key]
