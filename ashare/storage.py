from .timeutil import utcnow
import hashlib
import json
from datetime import datetime
from .config import raw_dir
from .models import SessionLocal, Source, RawRecord, Company, Security
from .universe import infer_board, infer_exchange, is_a_share, is_supported, SECURITY_TYPES  # noqa: F401

def _source(session, name, url=None):
    row = session.query(Source).filter_by(name=name).one_or_none()
    if row is None:
        row = Source(
            name=name,
            base_url=url,
            access_type="public",
        )
        session.add(row)
        session.flush()
    elif url and not row.base_url:
        row.base_url = url
    return row

def store_raw(source_name, url, payload, metadata, company_id=None):
    base = raw_dir()
    base.mkdir(parents=True, exist_ok=True)
    if isinstance(payload, bytes):
        data = payload
        ctype = (metadata.get("content_type") or "").lower()
        suffix = ".json" if "json" in ctype else ".bin"
    else:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        suffix = ".json"

    digest = hashlib.sha256(data).hexdigest()
    path = base / f"{digest}{suffix}"
    if not path.exists():
        path.write_bytes(data)

    session = SessionLocal()
    try:
        source = _source(session, source_name, url)
        row = RawRecord(
            source_id=source.id,
            company_id=company_id or metadata.get("company_id"),
            retrieved_at=utcnow(),
            url=url,
            content_type=metadata.get("content_type"),
            sha256=digest,
            payload_path=str(path),
            metadata_json=json.dumps(metadata, ensure_ascii=False),
        )
        session.add(row)
        session.commit()
        return {"sha256": digest, "payload_path": str(path)}
    finally:
        session.close()

def register_raw(source_name, url, digest, payload_path, metadata, company_id=None):
    """Record an already-archived payload in raw_records (provenance index)."""
    session = SessionLocal()
    try:
        source = _source(session, source_name, url)
        session.add(RawRecord(
            source_id=source.id,
            company_id=company_id or metadata.get("company_id"),
            retrieved_at=utcnow(),
            url=url,
            content_type=metadata.get("content_type"),
            sha256=digest,
            payload_path=str(payload_path),
            metadata_json=json.dumps(metadata, ensure_ascii=False),
        ))
        session.commit()
    finally:
        session.close()


def upsert_ashares(items, source_name="CNINFO"):
    session = SessionLocal()
    inserted = updated = rejected = 0
    errors = []
    seen = set()
    seen_ids: set[int] = set()

    try:
        for item in items:
            code = str(item["code"]).zfill(6)
            exchange = item["exchange"].upper()

            if not is_supported(code) or infer_exchange(code) != exchange:
                rejected += 1
                errors.append((code, "not an ordinary A-share (or an optional board that is not enabled)"))
                continue

            board = infer_board(exchange, code)
            if not board:
                rejected += 1
                errors.append((code, "unknown board"))
                continue

            key = (exchange, code)
            if key in seen:
                continue
            seen.add(key)

            company = session.query(Company).filter_by(
                security_code=code, exchange=exchange
            ).one_or_none()
            if company is not None:
                # v1.6: a changed short name or board in the official list is a
                # listing event (dated when detected, not when it took effect)
                from .security_master import record_snapshot_change
                record_snapshot_change(session, company, item, board, source_name)

            if company is None:
                company = Company(
                    security_code=code,
                    exchange=exchange,
                    board=board,
                    legal_name_cn=item.get("legal_name_cn"),
                    short_name_cn=item.get("short_name_cn"),
                    status=item.get("status"),
                    listing_date=item.get("listing_date"),
                    org_id=item.get("org_id"),
                    source_last_seen=source_name,
                )
                session.add(company)
                session.flush()
                inserted += 1
            else:
                for attr in (
                    "legal_name_cn", "short_name_cn", "status",
                    "listing_date", "org_id"
                ):
                    value = item.get(attr)
                    if value:
                        setattr(company, attr, value)
                company.board = board
                company.source_last_seen = source_name
                updated += 1

            seen_ids.add(company.id)
            sec = session.query(Security).filter_by(
                company_id=company.id, security_code=code
            ).one_or_none()
            if sec is None:
                stype, ccy = SECURITY_TYPES.get(board, ("A_SHARE", "CNY"))
                session.add(Security(
                    company_id=company.id,
                    security_code=code,
                    security_type=stype,
                    currency=ccy,
                ))

        session.commit()
        return {
            "inserted": inserted,
            "updated": updated,
            "rejected": rejected,
            "errors": errors,
            "_seen_ids": seen_ids,
        }
    finally:
        session.close()
