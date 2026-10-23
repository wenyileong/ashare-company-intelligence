"""Licence-aware, optionally pseudonymised dataset releases (v2.0).

A release is built in four steps:

1. every row of every research table is copied into a fresh SQLite snapshot,
   unless its licence class is excluded (LICENSED by default; see
   :mod:`ashare.licences`) or it falls outside the release scope;
2. with ``pseudonymise=True``, personal names of natural persons (directors,
   supervisors and officers, natural-person shareholders, pledgors and
   controllers) are replaced with stable keyed identifiers, raw-text
   columns are dropped and names in free-text columns are replaced;
3. one CSV per table (and optionally Parquet) is written from the snapshot,
   with a data-quality report (:mod:`ashare.quality`);
4. a manifest records the software version, schema revision, database
   fingerprint, row counts, the licence classes included and excluded (with
   the number of rows excluded), the pseudonymisation settings, file hashes
   and a suggested citation; a ``CITATION.cff`` is written beside it.

Pseudonyms are HMAC-SHA256 of the normalised name under a secret key, so the
same name receives the same identifier in every release made with the same
key, and the identifier cannot be reversed without the key. The key lives in
the data folder (``pseudonym.key``) and is never written into a release.
Identical names map to the same identifier, so pseudonymisation neither adds
nor removes linkage relative to the names themselves; the resolved person
register (``persons``) is kept for disambiguation.

Pseudonymised data remain personal information under the PIPL (art. 73(3)
distinguishes de-identification from anonymisation). See
``docs/compliance.md``.
"""
from __future__ import annotations

import csv
import hashlib
import hmac
import json
import platform
import re
import secrets
from pathlib import Path

from sqlalchemy import create_engine, select

from . import __version__
from .licences import CLASSES, row_licence, _overrides
from .models import Base, Company, SessionLocal, engine, init_db
from .timeutil import utcnow

# Operational tables: never part of a release.
OPERATIONAL = {"jobs", "job_items", "high_water_marks", "raw_records", "research_queries", "review_items"}
# Reference tables kept in a single-company release.
GLOBAL_TABLES = {"trading_calendar", "parser_calibration", "sources", "persons", "entities", "entity_aliases"}
# Columns that hold the researcher's own file paths or raw provider payloads.
LOCAL_COLUMNS = {"local_path", "payload_path", "raw_json"}

# Columns holding a name that may be a natural person's.
PERSON_ALWAYS = {("management_events", "person_name"), ("management_observations", "person_name"),
                 ("persons", "name")}
PERSON_IF_NATURAL = {("ownership_observations", "shareholder_name"), ("pledge_events", "pledgor"),
                     ("control_observations", "controlling_shareholder"),
                     ("control_observations", "actual_controller"), ("control_edges", "parent_name"),
                     ("control_edges", "child_name"), ("transaction_events", "counterparty"),
                     ("entities", "name"), ("entities", "normalised_name"), ("entity_aliases", "alias"),
                     ("entity_aliases", "normalised_alias")}
NATURE_COLUMN = {("ownership_observations", "shareholder_name"): ("shareholder_nature", "shareholder_type"),
                 ("control_observations", "controlling_shareholder"): ("controlling_nature",),
                 ("control_observations", "actual_controller"): ("controller_nature",),
                 ("entities", "name"): ("entity_type",), ("entities", "normalised_name"): ("entity_type",)}
# Raw-text columns dropped from a pseudonymised release.
RAW_TEXT = {"raw_value", "raw_text", "extraction_note", "text"}
RAW_TEXT_TABLES = {"document_pages"}
# Free-text columns in which known personal names are replaced.
FREE_TEXT = {"title_cn", "reason_text", "sanctions", "normalised_value", "subject", "proposal", "notes",
             "source_context", "link_basis", "ownership_basis", "basis", "relationship", "resolution"}
QUASI = {("management_observations", "age"): 5, ("persons", "birth_year"): 5}


# ---------------------------------------------------------------------------
# Pseudonymisation
# ---------------------------------------------------------------------------

def key_path() -> Path:
    from .config import db_path
    return Path(db_path()).resolve().parent / "pseudonym.key"


def load_key(path: str | None = None, create: bool = True) -> bytes:
    """Read the pseudonymisation key, creating a random one on first use."""
    p = Path(path) if path else key_path()
    if p.exists():
        return bytes.fromhex(p.read_text(encoding="ascii").strip())
    if not create:
        raise FileNotFoundError(p)
    key = secrets.token_bytes(32)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(key.hex(), encoding="ascii")
    return key


def pseudonym(name: str, key: bytes) -> str:
    from .control import normalise_name
    digest = hmac.new(key, ("person:" + normalise_name(name)).encode("utf-8"), hashlib.sha256).hexdigest()
    return "P" + digest[:12].upper()


_ORG = re.compile(r"公司|集团|银行|基金|计划|信托|证券|保险|资产|合伙|中心|委员会|政府|国资|财政|大学|学院|研究|协会|"
                  r"商会|工会|事务所|产品|账户|专户|组合|企业|厂$|局$|部$|社$|LIMITED|LTD|INC|CORP|LLC|GMBH|PLC|"
                  r"AG\b|SA\b|N\.?V\.?\b|B\.?V\.?\b|FUND|TRUST|BANK|HOLDING|CAPITAL|PARTNERS|AUTHORITY|INVESTMENT|ASSET|"
                  r"MANAGEMENT|SECURITIES|GROUP|COMPANY|\bCO\.|NOMINEES|株式会社", re.I)
# A shareholder nature glued to a name by the PDF text ("张三境内自然人"; finding 69).
_NATURE_SUFFIX = re.compile(r"(境内自然人|境外自然人|自然人|国有法人|国有股|境内非国有法人|境内一般法人|境外法人|国有独资|"
                            r"基金、理财产品等|其他)$")


def strip_nature(name: str) -> tuple[str, str | None]:
    """(name, nature) with a shareholder nature glued to the end of the name taken off."""
    n = (name or "").strip()
    m = _NATURE_SUFFIX.search(n)
    if m and m.start() > 0:
        return n[:m.start()].strip(), m.group(1)
    return n, None


# v2.0.7: recorded in each release's manifest, so that a release made under the earlier rule can be recognised.
PERSON_RULE = ("fail-safe v2.0.7: a name is masked unless a legal-person nature or an organisation word shows "
               "it to be an organisation's; a nature glued to the name is taken off first")


def is_natural_person(name: str | None, nature: str | None = None) -> bool:
    """Whether a name is to be treated as a natural person's in a pseudonymised release.

    v2.0.7 (finding 69): fail-safe. A name is a person's unless it is shown to be an organisation's: by a
    legal-person nature, or by a word that only organisations use (公司, 基金, LIMITED ...). Before, a name had
    to look like a two-to-five-character Chinese name to be masked, so a name with its nature glued on
    ("张三境内自然人") or written in Latin letters ("JOHN SMITH") was released as it stood. Masking an
    organisation by mistake loses a little information; leaving a person unmasked is a privacy failure."""
    if not name or not str(name).strip():
        return False
    base, glued = strip_nature(str(name))
    nat = (nature or "") + (glued or "")
    if "自然人" in nat or nat.upper() in ("PERSON", "DOMESTIC_NATURAL_PERSON", "FOREIGN_NATURAL_PERSON"):
        return True
    if _ORG.search(base):
        return False
    if nat and ("法人" in nat or "国有" in nat or "基金" in nat or nat.upper() in (
            "COMPANY", "FUND", "GOVERNMENT", "PARTNERSHIP", "STATE", "STATE_LEGAL_PERSON",
            "DOMESTIC_NON_STATE_LEGAL_PERSON", "FOREIGN_LEGAL_PERSON", "FUND_OR_PRODUCT")):
        return False
    if re.fullmatch(r"[\d\s.,%()（）\-]+", base):
        return False                      # a stray figure, not a name
    return True


_SPLIT = re.compile(r"[、,，;；/]")   # not 和/与/及: they occur inside names (张和平)
_SPLIT_KEEP = re.compile(r"([、,，;；/])")


def _person_parts(value: str, nature: str | None, always: bool) -> list[str]:
    parts = [p.strip() for p in _SPLIT.split(value)] if not always else [value.strip()]
    return [p for p in parts if p and (always or is_natural_person(p, nature))]


def _bare(name: str) -> str:
    """The name without a glued nature, for the pseudonym and for finding it in free text."""
    return strip_nature(name)[0] or name


class Pseudonymiser:
    def __init__(self, key: bytes, coarsen: bool = False, drop_free_text: bool = False):
        self.key, self.coarsen, self.drop_free_text = key, coarsen, drop_free_text
        self.names: dict[str, str] = {}
        self.fields: set[str] = set()
        self._pattern = None

    def learn(self, table: str, row: dict) -> None:
        for col in [c for (t, c) in PERSON_ALWAYS | PERSON_IF_NATURAL if t == table]:
            v = row.get(col)
            if not v:
                continue
            always = (table, col) in PERSON_ALWAYS
            nature = next((row.get(n) for n in NATURE_COLUMN.get((table, col), ()) if row.get(n)), None)
            for part in _person_parts(str(v), nature, always):
                if len(part) >= 2:
                    bare = _bare(part)
                    p = self.names.setdefault(bare, pseudonym(bare, self.key))
                    self.names.setdefault(part, p)          # the glued form maps to the same identifier

    def _replace_text(self, text: str) -> str:
        if self._pattern is None:
            names = sorted(self.names, key=len, reverse=True)
            self._pattern = re.compile("|".join(map(re.escape, names))) if names else False
        if not self._pattern:
            return text
        return self._pattern.sub(lambda m: self.names[m.group(0)], text)

    def apply(self, table: str, row: dict) -> dict:
        out = dict(row)
        for col, v in row.items():
            key = (table, col)
            if v is None:
                continue
            if col in RAW_TEXT:
                out[col] = None
                self.fields.add(f"{table}.{col} (dropped)")
            elif key in PERSON_ALWAYS or key in PERSON_IF_NATURAL:
                always = key in PERSON_ALWAYS
                nature = next((row.get(n) for n in NATURE_COLUMN.get(key, ()) if row.get(n)), None)
                if always:
                    new = self.names.get(str(v).strip(), str(v))
                else:               # whole tokens only, so an organisation's name is never altered
                    new = "".join(self.names.get(tok.strip(), tok)
                                  if tok.strip() in self.names and is_natural_person(tok.strip(), nature) else tok
                                  for tok in _SPLIT_KEEP.split(str(v)))
                if new != v:
                    self.fields.add(f"{table}.{col}")
                out[col] = new
            elif col in FREE_TEXT and isinstance(v, str):
                if self.drop_free_text:
                    out[col] = None
                    self.fields.add(f"{table}.{col} (dropped)")
                else:
                    new = self._replace_text(v)
                    if new != v:
                        self.fields.add(f"{table}.{col} (names replaced)")
                    out[col] = new
            elif self.coarsen and key in QUASI and isinstance(v, (int, float)):
                band = QUASI[key]
                out[col] = int(v) // band * band
                self.fields.add(f"{table}.{col} (coarsened to {band})")
        return out


# ---------------------------------------------------------------------------
# Release
# ---------------------------------------------------------------------------

def _sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def suggested_citation(name: str, fingerprint: str, created: str, pseudonymised: bool) -> str:
    year = created[:4]
    return (f"A-share Company Intelligence dataset release '{name}' ({year}), built with A-share Company "
            f"Intelligence v{__version__}; database fingerprint {fingerprint[:16]}"
            f"{'; pseudonymised' if pseudonymised else ''}. Created {created[:10]}.")


def _citation_cff(name: str, fingerprint: str, created: str, author: str | None) -> str:
    return "\n".join([
        "cff-version: 1.2.0",
        "message: If you use this dataset, please cite it as below.",
        "type: dataset",
        f'title: "A-share Company Intelligence dataset release {name}"',
        f"version: \"{name}\"",
        f"date-released: {created[:10]}",
        "authors:",
        f'  - name: "{author or "Dataset author (edit before publication)"}"',
        "identifiers:",
        "  - type: other",
        f'    value: "sha256:{fingerprint}"',
        '    description: "Database fingerprint at release time"',
        "references:",
        "  - type: software",
        '    title: "A-share Company Intelligence"',
        f'    version: "{__version__}"',
        "",
    ])


def build_release(out_dir: str = "releases", name: str | None = None, security_code: str | None = None,
                  formats: tuple[str, ...] = ("csv", "sqlite"), include_licensed: bool = False,
                  exclude: tuple[str, ...] = (), pseudonymise: bool = False, key_file: str | None = None,
                  coarsen: bool = False, drop_free_text: bool = False, quality: bool = True,
                  author: str | None = None) -> dict:
    """Write a licence-aware dataset release; see the module docstring."""
    from .research import database_fingerprint, _write_parquet
    from .migrate import current
    from . import transactions  # noqa: F401
    init_db()
    excluded = {c.upper() for c in exclude}
    if not include_licensed:
        excluded.add("LICENSED")
    bad = excluded - set(CLASSES)
    if bad:
        raise ValueError(f"unknown licence classes {sorted(bad)}; choose from {CLASSES}")
    stamp = utcnow().strftime("%Y%m%dT%H%M%SZ")
    code = str(security_code).zfill(6) if security_code else None
    rel = Path(out_dir) / (name or f"ashare_release_{stamp}{'_' + code if code else ''}")
    rel.mkdir(parents=True, exist_ok=True)
    snap = rel / "ashares_snapshot.db"
    for p in (snap, Path(str(snap) + "-wal"), Path(str(snap) + "-shm")):
        if p.exists():
            p.unlink()
    dst = create_engine(f"sqlite:///{snap}", future=True)
    md = Base.metadata
    tables = [t for t in md.sorted_tables if t.name not in OPERATIONAL
              and not (pseudonymise and t.name in RAW_TEXT_TABLES)]
    md.create_all(dst, tables=tables)
    key = load_key(key_file) if pseudonymise else None
    ps = Pseudonymiser(key, coarsen, drop_free_text) if pseudonymise else None
    session = SessionLocal()
    counts, dropped = {}, {}
    try:
        ov = _overrides(session)
        company_id = None
        if code:
            c = session.query(Company).filter_by(security_code=code).first()
            company_id = c.id if c else -1

        def rows_of(t):
            stmt = select(t)
            if company_id is not None:
                if "company_id" in t.c:
                    stmt = stmt.where(t.c.company_id == company_id)
                elif t.name == "companies":
                    stmt = stmt.where(t.c.id == company_id)
                elif t.name not in GLOBAL_TABLES:
                    return
            for r in session.execute(stmt).mappings():
                yield dict(r)

        from .models import Disclosure
        doc_urls = {i: u for i, u in session.query(Disclosure.id, Disclosure.document_url)}

        def public_document(r):
            """Replace a local file path in source_document with the document's URL (or its file name)."""
            v = r.get("source_document")
            if v and not str(v).lower().startswith(("http://", "https://")):
                r["source_document"] = doc_urls.get(r.get("disclosure_id")) or re.split(r"[\\/]", str(v))[-1]

        if ps:                          # first pass: collect every personal name
            for t in tables:
                if any((t.name, c) in PERSON_ALWAYS | PERSON_IF_NATURAL for c in t.c.keys()):
                    for r in rows_of(t):
                        ps.learn(t.name, r)
        with dst.begin() as conn:
            for t in tables:
                batch, n = [], 0
                for r in rows_of(t) or ():
                    lic = row_licence(t.name, r, ov)
                    if lic in excluded:
                        dropped.setdefault(t.name, {}).setdefault(lic, 0)
                        dropped[t.name][lic] += 1
                        continue
                    for col in LOCAL_COLUMNS & r.keys():
                        r[col] = None
                    if "source_document" in r:
                        public_document(r)
                    if ps:
                        r = ps.apply(t.name, r)
                    batch.append(r)
                    n += 1
                    if len(batch) >= 2000:
                        conn.execute(t.insert(), batch)
                        batch = []
                if batch:
                    conn.execute(t.insert(), batch)
                counts[t.name] = n
    finally:
        session.close()
    files = []
    if "csv" in formats:
        (rel / "csv").mkdir(exist_ok=True)
        with dst.connect() as conn:
            for t in tables:
                p = rel / "csv" / f"{t.name}.csv"
                res = conn.execute(select(t))
                with p.open("w", encoding="utf-8-sig", newline="") as fh:
                    w = csv.writer(fh)
                    w.writerow(list(res.keys()))
                    w.writerows(list(r) for r in res)
                files.append(p)
    if "parquet" in formats:
        (rel / "parquet").mkdir(exist_ok=True)
        with dst.connect() as conn:
            for t in tables:
                res = conn.execute(select(t))
                p = rel / "parquet" / f"{t.name}.parquet"
                _write_parquet(p, list(res.keys()), [tuple(r) for r in res])
                files.append(p)
    report = None
    if quality:
        from .quality import write_quality_report
        report = write_quality_report(rel, data_engine=dst, scope_company=company_id)
        files += [rel / f for f in report["files"]]
    dst.dispose()
    if "sqlite" in formats:
        files.append(snap)
    else:
        snap.unlink()
    created = utcnow().isoformat(timespec="seconds")
    fp = database_fingerprint()
    cite = suggested_citation(rel.name, fp, created, pseudonymise)
    (rel / "CITATION.cff").write_text(_citation_cff(rel.name, fp, created, author), encoding="utf-8")
    files.append(rel / "CITATION.cff")
    flags = {}
    with engine().connect() as conn:
        from .models import ValidationFlag
        for sev, rule in conn.execute(select(ValidationFlag.severity, ValidationFlag.rule)):
            flags[f"{sev}:{rule}"] = flags.get(f"{sev}:{rule}", 0) + 1
    manifest = {
        "name": rel.name, "created_utc": created,
        "software": {"name": "A-share Company Intelligence", "version": __version__,
                     "python": platform.python_version(), "platform": platform.platform()},
        "schema_revision": current(),
        "scope": {"security_code": code or "ALL"},
        "database_fingerprint": fp,
        "row_counts": counts,
        "licence": {"included": [c for c in CLASSES if c not in excluded], "excluded": sorted(excluded),
                    "excluded_rows": dropped,
                    "note": "Rows are classed by source; tag an import with set-licence to change its class."},
        "pseudonymisation": ({"applied": True, "method": "HMAC-SHA256 of the normalised name, 12 hex digits",
                              "rule": PERSON_RULE,
                              "key_fingerprint": hashlib.sha256(key).hexdigest()[:16],
                              "names_replaced": len(ps.names), "fields": sorted(ps.fields),
                              "coarsened": coarsen, "free_text_dropped": drop_free_text,
                              "tables_dropped": sorted(RAW_TEXT_TABLES)}
                             if ps else {"applied": False}),
        "validation_flags": flags,
        "quality_report": report["summary"] if report else None,
        "citation": cite,
        "files": [{"path": str(f.relative_to(rel)).replace("\\", "/"), "bytes": f.stat().st_size,
                   "sha256": _sha256_file(f)} for f in files],
        "notes": [
            "Every observation retains its source, extraction method, confidence and validation status.",
            "Public market feeds (EASTMONEY_PUBLIC) are not exchange-authoritative; the provider's terms apply.",
            "Local file paths (replaced by the document URL) and raw provider payloads are removed from every release.",
            "Operational tables (jobs, high-water marks, raw records, query log, review queue) are not released.",
        ],
    }
    (rel / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    _log_release(rel, manifest, formats)
    return {"release": str(rel), "files": len(files), "row_counts": counts, "excluded_rows": dropped,
            "pseudonymised": bool(ps), "citation": cite}


def _log_release(rel: Path, manifest: dict, formats) -> None:
    from .models import ResearchQuery
    s = SessionLocal()
    try:
        s.add(ResearchQuery(kind="RELEASE", name=rel.name,
                            query_text=json.dumps({"formats": list(formats),
                                                   "licence": manifest["licence"]["excluded"],
                                                   "pseudonymised": manifest["pseudonymisation"]["applied"]}),
                            query_sha256=hashlib.sha256(rel.name.encode()).hexdigest(),
                            parameters=json.dumps(manifest["scope"]),
                            database_sha256=manifest["database_fingerprint"],
                            row_count=sum(manifest["row_counts"].values()), output_path=str(rel),
                            output_sha256=_sha256_file(rel / "manifest.json"),
                            software_version=__version__, run_at=utcnow()))
        s.commit()
    finally:
        s.close()
