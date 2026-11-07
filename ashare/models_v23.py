"""Tables added in v2.3.0 (plan ``docs/plan_v2.3.md``).

All are new: no table of v2.2 changes shape. They are created empty by migration 0008, and each is used only by the
feature named beside it, behind that feature's switch (``ashare/features.py``).
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import String, Integer, DateTime, Text, Float, ForeignKey, UniqueConstraint, Index
from sqlalchemy.orm import Mapped, mapped_column

from .models import Base
from .timeutil import utcnow


class WorkRecord(Base):
    """B3: one unit of work of a run (a company, a document, a day), with its outcome. Records only; the extraction
    state stays the authority on what has been read. (The v1.9 ``jobs`` and ``job_items`` tables, for queued jobs run
    by 'job-run', are unchanged.)"""
    __tablename__ = "work_ledger"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[str] = mapped_column(String(40), index=True)
    job: Mapped[str] = mapped_column(String(60), index=True)
    item: Mapped[str] = mapped_column(String(200), index=True)
    state: Mapped[str] = mapped_column(String(20), index=True)          # DONE / SKIPPED / FAILED / NOT_READ
    reason: Mapped[str | None] = mapped_column(String(60), index=True)
    detail: Mapped[str | None] = mapped_column(Text)
    attempts: Mapped[int] = mapped_column(Integer, default=1)
    seconds: Mapped[float | None] = mapped_column(Float)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    __table_args__ = (Index("ix_work_ledger_job_item", "job", "item"),)


class OutputRecord(Base):
    """B11: one output the program wrote (a view, panel, release, export ...)."""
    __tablename__ = "outputs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    kind: Mapped[str] = mapped_column(String(40), index=True)
    command: Mapped[str | None] = mapped_column(String(80))
    params_json: Mapped[str | None] = mapped_column(Text)
    path: Mapped[str] = mapped_column(String(2000))
    is_folder: Mapped[int] = mapped_column(Integer, default=1)
    files: Mapped[int | None] = mapped_column(Integer)
    bytes: Mapped[int | None] = mapped_column(Integer)
    manifest_sha256: Mapped[str | None] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(20), default="PRESENT", index=True)   # PRESENT / MISSING / REMOVED
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    removed_at: Mapped[datetime | None] = mapped_column(DateTime)


class PathRewrite(Base):
    """B1 phase 4: each stored path changed by 'Normalise paths' or a move, so that the change can be undone."""
    __tablename__ = "path_rewrites"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[str] = mapped_column(String(40), index=True)
    table_name: Mapped[str] = mapped_column(String(60))
    row_id: Mapped[int] = mapped_column(Integer)
    column_name: Mapped[str] = mapped_column(String(40))
    old_value: Mapped[str | None] = mapped_column(String(2000))
    new_value: Mapped[str | None] = mapped_column(String(2000))
    undone_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class EntityIdentifier(Base):
    """B7: an external identifier of an entity (LEI, ISIN, a register number); ``entities.credit_code`` stays the
    authority for the credit code."""
    __tablename__ = "entity_identifiers"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    entity_id: Mapped[int] = mapped_column(ForeignKey("entities.id"), index=True)
    scheme: Mapped[str] = mapped_column(String(20), index=True)          # LEI / USCC / ISIN / REGISTRY
    value: Mapped[str] = mapped_column(String(100), index=True)
    source: Mapped[str] = mapped_column(String(60))
    status: Mapped[str] = mapped_column(String(20), default="ACCEPTED")  # ACCEPTED / CANDIDATE / REJECTED
    confidence: Mapped[str | None] = mapped_column(String(10))
    observed_date: Mapped[str | None] = mapped_column(String(20))
    detail_json: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    __table_args__ = (UniqueConstraint("entity_id", "scheme", "value", name="uq_entity_identifier"),)


class ExternalRelationship(Base):
    """B7: a relationship from an outside register (GLEIF direct or ultimate parent). Kept apart from
    ``control_edges``, so the chains read from reports are never changed (review V8)."""
    __tablename__ = "external_relationships"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    child_lei: Mapped[str] = mapped_column(String(20), index=True)
    parent_lei: Mapped[str] = mapped_column(String(20), index=True)
    relation: Mapped[str] = mapped_column(String(30))                    # DIRECT_PARENT / ULTIMATE_PARENT
    child_entity_id: Mapped[int | None] = mapped_column(Integer, index=True)
    parent_entity_id: Mapped[int | None] = mapped_column(Integer, index=True)
    parent_name: Mapped[str | None] = mapped_column(String(300))
    source: Mapped[str] = mapped_column(String(30), default="GLEIF")
    observed_date: Mapped[str | None] = mapped_column(String(20))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    __table_args__ = (UniqueConstraint("child_lei", "parent_lei", "relation", "source", name="uq_external_rel"),)


class InsiderDealing(Base):
    """B6: a director's, supervisor's or senior manager's dealing in the company's shares, as disclosed."""
    __tablename__ = "insider_dealings"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), index=True)
    person_id: Mapped[int | None] = mapped_column(Integer, index=True)
    person_name: Mapped[str | None] = mapped_column(String(100))
    role: Mapped[str | None] = mapped_column(String(100))
    relation: Mapped[str | None] = mapped_column(String(20))             # SELF / SPOUSE / PARENT / CHILD / OTHER
    deal_date: Mapped[str | None] = mapped_column(String(20), index=True)
    direction: Mapped[str | None] = mapped_column(String(10))            # BUY / SELL
    shares: Mapped[float | None] = mapped_column(Float)
    price: Mapped[float | None] = mapped_column(Float)
    amount: Mapped[float | None] = mapped_column(Float)
    holding_after: Mapped[float | None] = mapped_column(Float)
    method: Mapped[str | None] = mapped_column(String(30))
    disclosure_id: Mapped[int | None] = mapped_column(Integer, index=True)
    published_date: Mapped[str | None] = mapped_column(String(20), index=True)
    source_page: Mapped[int | None] = mapped_column(Integer)
    extraction_method: Mapped[str | None] = mapped_column(String(40))
    raw_text: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Watchlist(Base):
    """B9: a named set of companies and kinds of item to watch."""
    __tablename__ = "watchlists"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    codes: Mapped[str] = mapped_column(Text)                             # comma-separated
    kinds: Mapped[str] = mapped_column(Text)                             # comma-separated
    baseline_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Alert(Base):
    """B9: one new item found by a watchlist run."""
    __tablename__ = "alerts"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    watchlist_id: Mapped[int] = mapped_column(ForeignKey("watchlists.id"), index=True)
    key: Mapped[str] = mapped_column(String(200), index=True)
    kind: Mapped[str] = mapped_column(String(40))
    security_code: Mapped[str | None] = mapped_column(String(12))
    title: Mapped[str | None] = mapped_column(String(500))
    item_date: Mapped[str | None] = mapped_column(String(20))
    reference: Mapped[str | None] = mapped_column(String(500))
    baseline: Mapped[int] = mapped_column(Integer, default=0)
    seen_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    __table_args__ = (UniqueConstraint("watchlist_id", "key", name="uq_alert"),)


V23_TABLES = ("work_ledger", "outputs", "path_rewrites", "entity_identifiers", "external_relationships",
              "insider_dealings", "watchlists", "alerts")
