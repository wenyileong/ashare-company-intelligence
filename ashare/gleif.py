"""Entity identifiers from GLEIF, the Global Legal Entity Identifier Foundation (v2.3.0, plan section B7; switch
``gleif``, off by default because it is a network source the author chooses to use).

GLEIF's API (api.gleif.org/api/v1) is public and needs no key. It gives each entity holding a Legal Entity Identifier
(LEI) its legal name, register and registration number, and its direct and ultimate parents.

* **Matching.** An LEI is accepted automatically only when GLEIF's registration number equals the entity's unified
  social credit code (an exact identifier match). A match by name is stored as a candidate, for the author to accept
  or reject; nothing is merged by guesswork.
* **Parents.** GLEIF's direct and ultimate parents go into ``external_relationships``, never into ``control_edges``,
  so the control chains read from reports are unchanged.
* Each response is archived like any other source response. GLEIF's terms of reuse are recorded in
  ``docs/compliance.md``; the identifiers are left out of releases until those terms are settled.
"""
from __future__ import annotations

import json

API = "https://api.gleif.org/api/v1"
RECORD = "https://search.gleif.org/#/record/{}"


def _client():
    from .http import RateLimitedClient
    from .config import USER_AGENT, REQUESTS_PER_SECOND
    return RateLimitedClient(USER_AGENT, REQUESTS_PER_SECOND, server_patience=True)


def _get(client, path: str, params: dict | None = None) -> dict:
    from .storage import store_raw
    url = f"{API}{path}"
    r = client.get(url, params=params or {}, headers={"Accept": "application/vnd.api+json"})
    data = r.json()
    try:
        store_raw("GLEIF", str(r.request.url), data, {"content_type": "application/json"})
    except Exception:                                             # noqa: BLE001  archiving never stops a lookup
        pass
    return data


def summarise(record: dict) -> dict:
    a = record.get("attributes") or {}
    e = a.get("entity") or {}
    return {"lei": a.get("lei") or record.get("id"), "name": (e.get("legalName") or {}).get("name"),
            "registered_as": e.get("registeredAs"), "jurisdiction": e.get("jurisdiction"),
            "status": e.get("status"), "registration_status": (a.get("registration") or {}).get("status"),
            "register": (e.get("registeredAt") or {}).get("id"), "url": RECORD.format(a.get("lei") or record.get("id"))}


def by_registration_number(client, number: str) -> list[dict]:
    data = _get(client, "/lei-records", {"filter[entity.registeredAs]": number, "page[size]": 5})
    return [summarise(x) for x in data.get("data") or []]


def by_name(client, name: str, size: int = 5) -> list[dict]:
    data = _get(client, "/lei-records", {"filter[entity.legalName]": name, "page[size]": size})
    hits = data.get("data") or []
    if not hits:
        data = _get(client, "/lei-records", {"filter[fulltext]": name, "page[size]": size})
        hits = data.get("data") or []
    return [summarise(x) for x in hits]


def parents(client, lei: str) -> list[tuple[str, dict]]:
    out = []
    for rel, path in (("DIRECT_PARENT", "direct-parent"), ("ULTIMATE_PARENT", "ultimate-parent")):
        try:
            data = _get(client, f"/lei-records/{lei}/{path}")
        except Exception:                                         # noqa: BLE001  (404: no parent reported)
            continue
        rec = data.get("data")
        if rec:
            out.append((rel, summarise(rec)))
    return out


def match_entities(names: bool = False, limit: int | None = None, progress=None, client=None) -> dict:
    """Look up LEIs: by credit code (accepted when exact), and, with ``names``, by name (candidates for review);
    then the parents of every accepted LEI."""
    from .features import require
    from .models import SessionLocal, Entity, init_db
    from .models_v23 import EntityIdentifier, ExternalRelationship
    from .timeutil import utcnow
    require("gleif")
    init_db()
    say = progress or (lambda m: None)
    client = client or _client()
    s = SessionLocal()
    totals = {"looked_up": 0, "accepted": 0, "candidates": 0, "parents": 0, "errors": 0}
    today = utcnow().date().isoformat()
    try:
        have = {(i.entity_id, i.scheme) for i in s.query(EntityIdentifier).filter(EntityIdentifier.status != "REJECTED")}
        rejected = {(i.entity_id, i.value) for i in s.query(EntityIdentifier).filter(EntityIdentifier.status == "REJECTED")}
        q = s.query(Entity).order_by(Entity.id)
        ents = [e for e in q if (e.id, "LEI") not in have and (e.credit_code or names)]
        if limit:
            ents = ents[:limit]
        say(f"{len(ents):,} entities to look up")
        for e in ents:
            totals["looked_up"] += 1
            try:
                hits = []
                if e.credit_code:
                    hits = [h for h in by_registration_number(client, e.credit_code)
                            if (h["registered_as"] or "").upper() == e.credit_code.upper()]
                    for h in hits[:1]:
                        s.add(EntityIdentifier(entity_id=e.id, scheme="LEI", value=h["lei"], source="GLEIF",
                                               status="ACCEPTED", confidence="HIGH", observed_date=today,
                                               detail_json=json.dumps(h, ensure_ascii=False)))
                        totals["accepted"] += 1
                if not hits and names:
                    for h in by_name(client, e.name)[:3]:
                        if (e.id, h["lei"]) in rejected:          # a rejected match is not offered again
                            continue
                        s.add(EntityIdentifier(entity_id=e.id, scheme="LEI", value=h["lei"], source="GLEIF",
                                               status="CANDIDATE", confidence="LOW", observed_date=today,
                                               detail_json=json.dumps(h, ensure_ascii=False)))
                        totals["candidates"] += 1
                s.commit()
            except Exception as exc:                              # noqa: BLE001
                s.rollback()
                totals["errors"] += 1
                say(f"  {e.name}: {exc}")
        lei_of = {i.value: i.entity_id for i in s.query(EntityIdentifier).filter(EntityIdentifier.scheme == "LEI",
                                                                                    EntityIdentifier.status == "ACCEPTED")}
        known = {(r.child_lei, r.parent_lei, r.relation) for r in s.query(ExternalRelationship)}
        for lei, eid in lei_of.items():
            try:
                for rel, p in parents(client, lei):
                    if (lei, p["lei"], rel) in known:
                        continue
                    s.add(ExternalRelationship(child_lei=lei, parent_lei=p["lei"], relation=rel, child_entity_id=eid,
                                               parent_entity_id=lei_of.get(p["lei"]), parent_name=p["name"],
                                               source="GLEIF", observed_date=today))
                    totals["parents"] += 1
                s.commit()
            except Exception as exc:                              # noqa: BLE001
                s.rollback()
                totals["errors"] += 1
                say(f"  parents of {lei}: {exc}")
        return totals
    finally:
        s.close()


def candidates() -> list[dict]:
    from .models import SessionLocal, Entity, init_db
    from .models_v23 import EntityIdentifier
    init_db()
    s = SessionLocal()
    try:
        out = []
        for i, e in (s.query(EntityIdentifier, Entity).join(Entity, Entity.id == EntityIdentifier.entity_id)
                     .filter(EntityIdentifier.status == "CANDIDATE").order_by(Entity.name)):
            d = json.loads(i.detail_json or "{}")
            out.append({"id": i.id, "entity": e.name, "credit_code": e.credit_code, "lei": i.value,
                        "gleif_name": d.get("name"), "registered_as": d.get("registered_as"),
                        "jurisdiction": d.get("jurisdiction"), "url": d.get("url")})
        return out
    finally:
        s.close()


def decide(identifier_id: int, accept: bool) -> dict:
    """Accept or reject a candidate; accepting one rejects the entity's other LEI candidates."""
    from .models import SessionLocal, init_db
    from .models_v23 import EntityIdentifier
    init_db()
    s = SessionLocal()
    try:
        i = s.get(EntityIdentifier, identifier_id)
        if i is None or i.status != "CANDIDATE":
            return {"error": f"no candidate {identifier_id}"}
        i.status = "ACCEPTED" if accept else "REJECTED"
        if accept:
            i.confidence = "MEDIUM"
            for o in s.query(EntityIdentifier).filter(EntityIdentifier.entity_id == i.entity_id,
                                                      EntityIdentifier.scheme == i.scheme,
                                                      EntityIdentifier.status == "CANDIDATE",
                                                      EntityIdentifier.id != i.id):
                o.status = "REJECTED"
        s.commit()
        return {"id": identifier_id, "status": i.status, "lei": i.value}
    finally:
        s.close()
