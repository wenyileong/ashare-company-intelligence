from .timeutil import utcnow
from datetime import datetime
from sqlalchemy import (
    create_engine, String, Integer, DateTime, Text, ForeignKey,
    UniqueConstraint, Index
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker
from .config import db_path

class Base(DeclarativeBase):
    pass

class Company(Base):
    __tablename__ = "companies"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    security_code: Mapped[str] = mapped_column(String(12), index=True)
    exchange: Mapped[str] = mapped_column(String(8), index=True)
    board: Mapped[str | None] = mapped_column(String(40), index=True)
    legal_name_cn: Mapped[str | None] = mapped_column(String(300))
    short_name_cn: Mapped[str | None] = mapped_column(String(100))
    legal_name_en: Mapped[str | None] = mapped_column(String(300))
    status: Mapped[str | None] = mapped_column(String(50), index=True)
    listing_date: Mapped[str | None] = mapped_column(String(20))
    org_id: Mapped[str | None] = mapped_column(String(100), index=True)
    source_last_seen: Mapped[str | None] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, onupdate=utcnow
    )
    __table_args__ = (
        UniqueConstraint("security_code", "exchange", name="uq_company_security_exchange"),
        Index("ix_company_name_cn", "legal_name_cn"),
    )

class Security(Base):
    __tablename__ = "securities"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), index=True)
    security_code: Mapped[str] = mapped_column(String(12), index=True)
    security_type: Mapped[str] = mapped_column(String(50), default="A_SHARE")
    currency: Mapped[str] = mapped_column(String(8), default="CNY")
    __table_args__ = (
        UniqueConstraint("company_id", "security_code", name="uq_security_company_code"),
    )


class Disclosure(Base):
    __tablename__ = "disclosures"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), index=True)
    announcement_id: Mapped[str] = mapped_column(String(100), index=True)
    announcement_date: Mapped[str | None] = mapped_column(String(20), index=True)
    title_cn: Mapped[str | None] = mapped_column(String(1000))
    announcement_type_cn: Mapped[str | None] = mapped_column(String(200))
    kind: Mapped[str | None] = mapped_column(String(100), index=True)
    sec_code: Mapped[str | None] = mapped_column(String(20), index=True)
    sec_name: Mapped[str | None] = mapped_column(String(100))
    adjunct_url: Mapped[str | None] = mapped_column(String(2000))
    document_url: Mapped[str | None] = mapped_column(String(2000))
    local_path: Mapped[str | None] = mapped_column(String(2000))
    content_type: Mapped[str | None] = mapped_column(String(200))
    file_size: Mapped[int | None] = mapped_column(Integer)
    sha256: Mapped[str | None] = mapped_column(String(64), index=True)
    text_layer: Mapped[str | None] = mapped_column(String(12))  # v1.5: FULL / PARTIAL / NONE (scanned)
    # v2.0.6: the financial extractor version that last read the document (with or without facts), so that a
    # stopped extraction continues with the next document
    extracted_version: Mapped[str | None] = mapped_column(String(40))
    extracted_at: Mapped[datetime | None] = mapped_column(DateTime)
    source: Mapped[str | None] = mapped_column(String(100))
    retrieved_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    raw_json: Mapped[str | None] = mapped_column(Text)
    __table_args__ = (
        UniqueConstraint("company_id", "announcement_id", name="uq_disclosure_company_announcement"),
        Index("ix_disclosure_company_date", "company_id", "announcement_date"),
    )

class FinancialFact(Base):
    __tablename__ = "financial_facts"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), index=True)
    disclosure_id: Mapped[int | None] = mapped_column(ForeignKey("disclosures.id"), index=True)
    reporting_period: Mapped[str | None] = mapped_column(String(20), index=True)
    period_type: Mapped[str | None] = mapped_column(String(30), index=True)
    statement_type: Mapped[str | None] = mapped_column(String(50), index=True)
    metric: Mapped[str] = mapped_column(String(150), index=True)
    metric_cn: Mapped[str | None] = mapped_column(String(300))
    value: Mapped[float | None] = mapped_column()
    raw_value: Mapped[str | None] = mapped_column(String(500))
    unit: Mapped[str | None] = mapped_column(String(50))
    currency: Mapped[str | None] = mapped_column(String(10), default="CNY")
    consolidation_scope: Mapped[str | None] = mapped_column(String(50))
    source_document: Mapped[str | None] = mapped_column(String(2000))
    source_page: Mapped[int | None] = mapped_column(Integer)
    source_xbrl_tag: Mapped[str | None] = mapped_column(String(500))
    source_label: Mapped[str | None] = mapped_column(String(300))
    source_context: Mapped[str | None] = mapped_column(String(300))
    extraction_method: Mapped[str] = mapped_column(String(50))
    confidence: Mapped[float | None] = mapped_column()
    validation_status: Mapped[str] = mapped_column(String(50), default="UNVALIDATED")
    extraction_note: Mapped[str | None] = mapped_column(Text)  # v1.5 dual-run result (JSON)
    retrieved_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)
    __table_args__ = (
        UniqueConstraint(
            "company_id", "disclosure_id", "reporting_period", "period_type",
            "metric", "consolidation_scope", "extraction_method",
            name="uq_financial_fact_identity"
        ),
        Index("ix_financial_fact_company_metric_period", "company_id", "metric", "reporting_period"),
    )

class MarketBar(Base):
    __tablename__ = "market_bars"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), index=True)
    trade_date: Mapped[str] = mapped_column(String(20), index=True)
    open: Mapped[float | None] = mapped_column()
    high: Mapped[float | None] = mapped_column()
    low: Mapped[float | None] = mapped_column()
    close: Mapped[float | None] = mapped_column()
    prev_close: Mapped[float | None] = mapped_column()
    volume: Mapped[float | None] = mapped_column()
    amount: Mapped[float | None] = mapped_column()
    pct_change: Mapped[float | None] = mapped_column()
    change: Mapped[float | None] = mapped_column()
    turnover_rate: Mapped[float | None] = mapped_column()
    adjustment: Mapped[str] = mapped_column(String(20), default="none", index=True)
    status: Mapped[str | None] = mapped_column(String(50))
    volume_unit: Mapped[str | None] = mapped_column(String(30))
    source: Mapped[str] = mapped_column(String(100), index=True)
    raw_json: Mapped[str | None] = mapped_column(Text)
    retrieved_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    __table_args__ = (
        UniqueConstraint("company_id", "trade_date", "adjustment", "source", name="uq_market_bar_identity"),
        Index("ix_market_bar_company_date", "company_id", "trade_date"),
    )

class MarketSnapshot(Base):
    __tablename__ = "market_snapshots"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), index=True)
    trade_date: Mapped[str] = mapped_column(String(20), index=True)
    close: Mapped[float | None] = mapped_column()
    market_cap: Mapped[float | None] = mapped_column()
    float_market_cap: Mapped[float | None] = mapped_column()
    shares_outstanding: Mapped[float | None] = mapped_column()
    float_shares: Mapped[float | None] = mapped_column()
    pe: Mapped[float | None] = mapped_column()
    pb: Mapped[float | None] = mapped_column()
    ps: Mapped[float | None] = mapped_column()                 # v1.7
    ev: Mapped[float | None] = mapped_column()                 # v1.7
    ev_to_ebit: Mapped[float | None] = mapped_column()         # v1.7
    source: Mapped[str] = mapped_column(String(100), index=True)
    raw_json: Mapped[str | None] = mapped_column(Text)
    retrieved_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    __table_args__ = (
        UniqueConstraint("company_id", "trade_date", "source", name="uq_market_snapshot_identity"),
    )


class OwnershipObservation(Base):
    __tablename__ = "ownership_observations"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), index=True)
    disclosure_id: Mapped[int | None] = mapped_column(ForeignKey("disclosures.id"), index=True)
    observation_date: Mapped[str] = mapped_column(String(20), index=True)
    shareholder_name: Mapped[str | None] = mapped_column(String(500), index=True)
    shareholder_type: Mapped[str | None] = mapped_column(String(100))
    relationship: Mapped[str | None] = mapped_column(String(200))
    shares: Mapped[float | None] = mapped_column()
    ownership_pct: Mapped[float | None] = mapped_column()
    tradable_shares: Mapped[float | None] = mapped_column()
    pledged_shares: Mapped[float | None] = mapped_column()
    restricted_shares: Mapped[float | None] = mapped_column()
    change_shares: Mapped[float | None] = mapped_column()
    change_pct: Mapped[float | None] = mapped_column()
    is_controlling_shareholder: Mapped[bool | None] = mapped_column()
    is_actual_controller: Mapped[bool | None] = mapped_column()
    rank: Mapped[int | None] = mapped_column(Integer)
    source_document: Mapped[str | None] = mapped_column(String(2000))
    source_page: Mapped[int | None] = mapped_column(Integer)
    extraction_method: Mapped[str] = mapped_column(String(50), default="CSV_IMPORT")
    confidence: Mapped[float | None] = mapped_column()
    source: Mapped[str] = mapped_column(String(100), index=True)
    raw_text: Mapped[str | None] = mapped_column(Text)
    validation_status: Mapped[str | None] = mapped_column(String(50), default="UNVALIDATED")
    entity_id: Mapped[int | None] = mapped_column(Integer, index=True)              # v1.8
    shareholder_nature: Mapped[str | None] = mapped_column(String(40))              # v1.8: 国有法人 …
    extraction_note: Mapped[str | None] = mapped_column(Text)                       # v1.8
    retrieved_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    __table_args__ = (
        UniqueConstraint("company_id", "observation_date", "shareholder_name", "source", "rank", name="uq_ownership_observation_identity"),
        Index("ix_ownership_company_date", "company_id", "observation_date"),
    )

class CapitalStructureObservation(Base):
    __tablename__ = "capital_structure_observations"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), index=True)
    disclosure_id: Mapped[int | None] = mapped_column(ForeignKey("disclosures.id"), index=True)
    observation_date: Mapped[str] = mapped_column(String(20), index=True)
    total_shares: Mapped[float | None] = mapped_column()
    tradable_shares: Mapped[float | None] = mapped_column()
    restricted_shares: Mapped[float | None] = mapped_column()
    a_shares: Mapped[float | None] = mapped_column()
    b_shares: Mapped[float | None] = mapped_column()
    h_shares: Mapped[float | None] = mapped_column()
    treasury_shares: Mapped[float | None] = mapped_column()
    source_document: Mapped[str | None] = mapped_column(String(2000))
    source_page: Mapped[int | None] = mapped_column(Integer)
    extraction_method: Mapped[str] = mapped_column(String(50), default="CSV_IMPORT")
    confidence: Mapped[float | None] = mapped_column()
    source: Mapped[str] = mapped_column(String(100), index=True)
    raw_text: Mapped[str | None] = mapped_column(Text)
    validation_status: Mapped[str | None] = mapped_column(String(50), default="UNVALIDATED")
    retrieved_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    __table_args__ = (
        UniqueConstraint("company_id", "observation_date", "source", name="uq_capital_structure_identity"),
    )

class CorporateAction(Base):
    """A corporate-action observation (v0.8).

    Conventions:
    - ``ratio``: for BONUS_SHARES / CAPITALISATION_ISSUE / RIGHTS_ISSUE, new
      shares per existing share (每10股送3股 -> 0.3); for STOCK_SPLIT /
      SHARE_CONSOLIDATION, post-event shares per pre-event share (1拆2 -> 2.0).
    - ``cash_amount``: cash per share, pre-tax (每10股派5元 -> 0.5);
      ``total_cash_amount`` is the aggregate where disclosed.
    - ``share_delta``: signed change in issued (total) shares attributable to
      the action, where disclosed or derivable; buybacks leave issued share
      capital unchanged until cancellation, so their count is stored in
      ``shares_affected`` and ``share_delta`` stays 0.
    """
    __tablename__ = "corporate_actions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), index=True)
    disclosure_id: Mapped[int | None] = mapped_column(ForeignKey("disclosures.id"), index=True)
    action_id: Mapped[str] = mapped_column(String(64), index=True)
    action_group: Mapped[str | None] = mapped_column(String(64), index=True)
    action_type: Mapped[str] = mapped_column(String(50), index=True)
    status: Mapped[str | None] = mapped_column(String(40), index=True)
    announcement_id: Mapped[str | None] = mapped_column(String(100), index=True)
    announcement_date: Mapped[str | None] = mapped_column(String(20), index=True)
    record_date: Mapped[str | None] = mapped_column(String(20))
    ex_date: Mapped[str | None] = mapped_column(String(20), index=True)
    payment_date: Mapped[str | None] = mapped_column(String(20))
    listing_date: Mapped[str | None] = mapped_column(String(20))
    effective_date: Mapped[str | None] = mapped_column(String(20), index=True)
    fiscal_period: Mapped[str | None] = mapped_column(String(20))
    base_share_count: Mapped[float | None] = mapped_column()
    old_share_count: Mapped[float | None] = mapped_column()
    new_share_count: Mapped[float | None] = mapped_column()
    share_delta: Mapped[float | None] = mapped_column()
    shares_affected: Mapped[float | None] = mapped_column()
    ratio: Mapped[float | None] = mapped_column()
    cash_amount: Mapped[float | None] = mapped_column()
    total_cash_amount: Mapped[float | None] = mapped_column()
    subscription_price: Mapped[float | None] = mapped_column()
    issue_price: Mapped[float | None] = mapped_column()
    currency: Mapped[str | None] = mapped_column(String(8), default="CNY")
    tax_basis: Mapped[str | None] = mapped_column(String(20))
    source_document: Mapped[str | None] = mapped_column(String(2000))
    source_page: Mapped[int | None] = mapped_column(Integer)
    raw_value: Mapped[str | None] = mapped_column(Text)
    normalised_value: Mapped[str | None] = mapped_column(Text)
    extraction_method: Mapped[str] = mapped_column(String(50))
    confidence: Mapped[float | None] = mapped_column()
    validation_status: Mapped[str | None] = mapped_column(String(50), default="UNVALIDATED")
    source: Mapped[str] = mapped_column(String(100), index=True)
    retrieved_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)
    __table_args__ = (
        UniqueConstraint("company_id", "action_id", name="uq_corporate_action_identity"),
        Index("ix_corporate_action_company_type_date", "company_id", "action_type", "effective_date"),
    )


class CapitalReconciliation(Base):
    """Derived result: capital(t0) + actions(t0, t1] vs capital(t1)."""
    __tablename__ = "capital_reconciliations"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), index=True)
    capital_source: Mapped[str] = mapped_column(String(100))
    t0_date: Mapped[str] = mapped_column(String(20))
    t1_date: Mapped[str] = mapped_column(String(20))
    t0_total_shares: Mapped[float | None] = mapped_column()
    t1_total_shares: Mapped[float | None] = mapped_column()
    expected_t1_total_shares: Mapped[float | None] = mapped_column()
    residual: Mapped[float | None] = mapped_column()
    tolerance: Mapped[float | None] = mapped_column()
    status: Mapped[str] = mapped_column(String(40), index=True)
    t0_tradable_shares: Mapped[float | None] = mapped_column()
    t1_tradable_shares: Mapped[float | None] = mapped_column()
    expected_t1_tradable_shares: Mapped[float | None] = mapped_column()
    tradable_residual: Mapped[float | None] = mapped_column()
    tradable_status: Mapped[str | None] = mapped_column(String(40))
    action_ids: Mapped[str | None] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text)
    run_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    __table_args__ = (
        UniqueConstraint("company_id", "capital_source", "t0_date", "t1_date", name="uq_capital_reconciliation_window"),
    )


class RegulatoryEvent(Base):
    """A regulatory, legal or listing-status event (v0.9).

    ``legal_classification`` records the legal character of the measure:
    an administrative penalty (行政处罚) under the Securities Law is
    distinct from an administrative supervisory measure (行政监管措施),
    from exchange self-regulatory discipline (纪律处分) and measures, and
    from civil, arbitral and criminal proceedings. The classification is
    taken from the instrument named in the document, not inferred from
    severity.
    """
    __tablename__ = "regulatory_events"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int | None] = mapped_column(ForeignKey("companies.id"), index=True)
    disclosure_id: Mapped[int | None] = mapped_column(ForeignKey("disclosures.id"), index=True)
    event_id: Mapped[str] = mapped_column(String(64), index=True)
    case_key: Mapped[str | None] = mapped_column(String(64), index=True)
    link_basis: Mapped[str | None] = mapped_column(String(200))
    event_type: Mapped[str] = mapped_column(String(50), index=True)
    event_subtype: Mapped[str | None] = mapped_column(String(80))
    legal_classification: Mapped[str] = mapped_column(String(60), index=True)
    status: Mapped[str | None] = mapped_column(String(40), index=True)
    authority: Mapped[str | None] = mapped_column(String(40), index=True)
    authority_name: Mapped[str | None] = mapped_column(String(200))
    affected_security: Mapped[str | None] = mapped_column(String(12), index=True)
    announcement_id: Mapped[str | None] = mapped_column(String(100), index=True)
    announcement_date: Mapped[str | None] = mapped_column(String(20), index=True)
    event_date: Mapped[str | None] = mapped_column(String(20), index=True)
    document_number: Mapped[str | None] = mapped_column(String(200))
    case_number: Mapped[str | None] = mapped_column(String(200))
    company_role: Mapped[str | None] = mapped_column(String(30))
    amount_in_dispute: Mapped[float | None] = mapped_column()
    fine_amount_total: Mapped[float | None] = mapped_column()
    fine_amount_company: Mapped[float | None] = mapped_column()
    confiscation_amount: Mapped[float | None] = mapped_column()
    violation_categories: Mapped[str | None] = mapped_column(Text)
    cited_provisions: Mapped[str | None] = mapped_column(Text)
    sanctions: Mapped[str | None] = mapped_column(Text)
    title_cn: Mapped[str | None] = mapped_column(String(1000))
    source_document: Mapped[str | None] = mapped_column(String(2000))
    primary_source_url: Mapped[str | None] = mapped_column(String(2000))
    document_hash: Mapped[str | None] = mapped_column(String(64), index=True)
    source_page: Mapped[int | None] = mapped_column(Integer)
    raw_value: Mapped[str | None] = mapped_column(Text)
    normalised_value: Mapped[str | None] = mapped_column(Text)
    extraction_method: Mapped[str] = mapped_column(String(50))
    confidence: Mapped[float | None] = mapped_column()
    validation_status: Mapped[str | None] = mapped_column(String(50), default="UNVALIDATED")
    source: Mapped[str] = mapped_column(String(100), index=True)
    retrieved_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)
    __table_args__ = (
        UniqueConstraint("event_id", name="uq_regulatory_event_identity"),
        Index("ix_regulatory_event_company_date", "company_id", "event_date"),
    )


class ExtractionState(Base):
    """v2.0.8 (findings 76, 77 and 79): which version of each document extractor last read a document, so that a
    stopped extraction continues with the next document and a new parser version reads every document again."""
    __tablename__ = "extraction_state"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    disclosure_id: Mapped[int] = mapped_column(ForeignKey("disclosures.id"), index=True)
    extractor: Mapped[str] = mapped_column(String(40), index=True)
    version: Mapped[str] = mapped_column(String(40))
    outcome: Mapped[str | None] = mapped_column(String(20))      # READ, EMPTY, ERROR
    extracted_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    __table_args__ = (UniqueConstraint("disclosure_id", "extractor", name="uq_extraction_state"),)


class ValidationFlag(Base):
    """A validation finding (v1.0). Flags never alter the observations they
    concern; they are regenerated by each validation run."""
    __tablename__ = "validation_flags"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    rule: Mapped[str] = mapped_column(String(80), index=True)
    severity: Mapped[str] = mapped_column(String(10), index=True)
    layer: Mapped[str] = mapped_column(String(40), index=True)
    company_id: Mapped[int | None] = mapped_column(ForeignKey("companies.id"), index=True)
    table_name: Mapped[str] = mapped_column(String(60))
    row_ids: Mapped[str] = mapped_column(String(500))
    details: Mapped[str | None] = mapped_column(Text)
    run_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    __table_args__ = (UniqueConstraint("rule", "table_name", "row_ids", name="uq_validation_flag"),)


class DocumentPage(Base):
    """Extracted text of downloaded documents, one row per page (v1.0)."""
    __tablename__ = "document_pages"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    disclosure_id: Mapped[int] = mapped_column(ForeignKey("disclosures.id"), index=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), index=True)
    page: Mapped[int] = mapped_column(Integer)
    text: Mapped[str | None] = mapped_column(Text)
    document_sha256: Mapped[str | None] = mapped_column(String(64))
    indexed_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    __table_args__ = (UniqueConstraint("disclosure_id", "page", name="uq_document_page"),)


class ResearchQuery(Base):
    """Log of research queries and dataset releases, for reproducibility."""
    __tablename__ = "research_queries"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    kind: Mapped[str] = mapped_column(String(30))
    name: Mapped[str | None] = mapped_column(String(200))
    query_text: Mapped[str] = mapped_column(Text)
    query_sha256: Mapped[str] = mapped_column(String(64), index=True)
    parameters: Mapped[str | None] = mapped_column(Text)
    database_sha256: Mapped[str | None] = mapped_column(String(64))
    row_count: Mapped[int | None] = mapped_column(Integer)
    output_path: Mapped[str | None] = mapped_column(String(2000))
    output_sha256: Mapped[str | None] = mapped_column(String(64))
    software_version: Mapped[str | None] = mapped_column(String(20))
    run_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class IndustryClassification(Base):
    """Industry classification of a company under one scheme at one date (v1.1).

    Classifications change (CSRC reclassifies quarterly; SW was revised in
    2021), so they are observations over time, not company attributes.
    """
    __tablename__ = "industry_classifications"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), index=True)
    scheme: Mapped[str] = mapped_column(String(40), index=True)
    effective_date: Mapped[str] = mapped_column(String(20), index=True)
    level1_code: Mapped[str | None] = mapped_column(String(20), index=True)
    level1_name: Mapped[str | None] = mapped_column(String(100))
    level2_code: Mapped[str | None] = mapped_column(String(20), index=True)
    level2_name: Mapped[str | None] = mapped_column(String(100))
    level3_code: Mapped[str | None] = mapped_column(String(20))
    level3_name: Mapped[str | None] = mapped_column(String(100))
    level4_code: Mapped[str | None] = mapped_column(String(20))
    level4_name: Mapped[str | None] = mapped_column(String(100))
    source: Mapped[str] = mapped_column(String(100), index=True)
    source_document: Mapped[str | None] = mapped_column(String(2000))
    extraction_method: Mapped[str] = mapped_column(String(50), default="CSV_IMPORT")
    confidence: Mapped[float | None] = mapped_column()
    validation_status: Mapped[str | None] = mapped_column(String(50), default="UNVALIDATED")
    raw_text: Mapped[str | None] = mapped_column(Text)
    retrieved_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    __table_args__ = (
        UniqueConstraint("company_id", "scheme", "effective_date", "source", name="uq_industry_classification"),
    )


class ManagementEvent(Base):
    """Appointment, resignation, election or dismissal of a director,
    supervisor or senior executive (v1.1)."""
    __tablename__ = "management_events"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), index=True)
    disclosure_id: Mapped[int | None] = mapped_column(ForeignKey("disclosures.id"), index=True)
    event_id: Mapped[str] = mapped_column(String(64), unique=True)
    event_type: Mapped[str] = mapped_column(String(40), index=True)
    person_name: Mapped[str | None] = mapped_column(String(100), index=True)
    role: Mapped[str | None] = mapped_column(String(40), index=True)
    role_cn: Mapped[str | None] = mapped_column(String(200))
    event_date: Mapped[str | None] = mapped_column(String(20), index=True)
    effective_date: Mapped[str | None] = mapped_column(String(20))
    announcement_date: Mapped[str | None] = mapped_column(String(20))
    reason: Mapped[str | None] = mapped_column(String(60))
    reason_text: Mapped[str | None] = mapped_column(String(500))
    remains_with_company: Mapped[bool | None] = mapped_column()
    title_cn: Mapped[str | None] = mapped_column(String(1000))
    source_document: Mapped[str | None] = mapped_column(String(2000))
    source_page: Mapped[int | None] = mapped_column(Integer)
    raw_value: Mapped[str | None] = mapped_column(Text)
    extraction_method: Mapped[str] = mapped_column(String(50))
    confidence: Mapped[float | None] = mapped_column()
    validation_status: Mapped[str | None] = mapped_column(String(50), default="UNVALIDATED")
    source: Mapped[str] = mapped_column(String(100), index=True)
    retrieved_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class ManagementObservation(Base):
    """One person in one role as reported at one date, usually the
    董事、监事、高级管理人员情况 table of an annual report (v1.1)."""
    __tablename__ = "management_observations"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), index=True)
    disclosure_id: Mapped[int | None] = mapped_column(ForeignKey("disclosures.id"), index=True)
    observation_date: Mapped[str] = mapped_column(String(20), index=True)
    person_name: Mapped[str] = mapped_column(String(100), index=True)
    role: Mapped[str] = mapped_column(String(40), index=True)
    role_cn: Mapped[str | None] = mapped_column(String(200))
    gender: Mapped[str | None] = mapped_column(String(4))
    age: Mapped[int | None] = mapped_column(Integer)
    tenure_start: Mapped[str | None] = mapped_column(String(20))
    tenure_end: Mapped[str | None] = mapped_column(String(20))
    status: Mapped[str | None] = mapped_column(String(20))
    shares_start: Mapped[float | None] = mapped_column()
    shares_end: Mapped[float | None] = mapped_column()
    remuneration: Mapped[float | None] = mapped_column()
    paid_by_related_party: Mapped[bool | None] = mapped_column()
    source: Mapped[str] = mapped_column(String(100), index=True)
    source_document: Mapped[str | None] = mapped_column(String(2000))
    source_page: Mapped[int | None] = mapped_column(Integer)
    raw_value: Mapped[str | None] = mapped_column(Text)
    extraction_method: Mapped[str] = mapped_column(String(50))
    confidence: Mapped[float | None] = mapped_column()
    validation_status: Mapped[str | None] = mapped_column(String(50), default="UNVALIDATED")
    extraction_note: Mapped[str | None] = mapped_column(Text)  # v1.5 dual-run result (JSON)
    retrieved_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    __table_args__ = (
        UniqueConstraint("company_id", "observation_date", "person_name", "role", "source",
                         name="uq_management_observation"),
    )


class SegmentObservation(Base):
    """Revenue (and, where reported, cost, margin or assets) of one business,
    product, regional or sales-channel segment for one period (v1.2)."""
    __tablename__ = "segment_observations"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), index=True)
    disclosure_id: Mapped[int | None] = mapped_column(ForeignKey("disclosures.id"), index=True)
    reporting_period: Mapped[str] = mapped_column(String(20), index=True)
    dimension: Mapped[str] = mapped_column(String(30), index=True)
    segment_name: Mapped[str] = mapped_column(String(200), index=True)
    region_class: Mapped[str | None] = mapped_column(String(20))
    revenue: Mapped[float | None] = mapped_column()
    revenue_share: Mapped[float | None] = mapped_column()
    revenue_prior: Mapped[float | None] = mapped_column()
    revenue_yoy: Mapped[float | None] = mapped_column()
    cost: Mapped[float | None] = mapped_column()
    gross_margin: Mapped[float | None] = mapped_column()
    assets: Mapped[float | None] = mapped_column()
    is_total: Mapped[bool | None] = mapped_column()
    table_kind: Mapped[str | None] = mapped_column(String(20))   # v2.0.8: composition or margin (finding 83)
    unit: Mapped[str | None] = mapped_column(String(20))
    source: Mapped[str] = mapped_column(String(100), index=True)
    source_document: Mapped[str | None] = mapped_column(String(2000))
    source_page: Mapped[int | None] = mapped_column(Integer)
    raw_value: Mapped[str | None] = mapped_column(Text)
    extraction_method: Mapped[str] = mapped_column(String(50))
    confidence: Mapped[float | None] = mapped_column()
    validation_status: Mapped[str | None] = mapped_column(String(50), default="UNVALIDATED")
    extraction_note: Mapped[str | None] = mapped_column(Text)  # v1.5 dual-run result (JSON)
    retrieved_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    __table_args__ = (
        UniqueConstraint("company_id", "reporting_period", "dimension", "segment_name", "source", "disclosure_id",
                         name="uq_segment_observation"),
    )


class SubsidiaryObservation(Base):
    """A subsidiary, associate or joint venture as reported at one date (v1.2)."""
    __tablename__ = "subsidiary_observations"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), index=True)
    disclosure_id: Mapped[int | None] = mapped_column(ForeignKey("disclosures.id"), index=True)
    observation_date: Mapped[str] = mapped_column(String(20), index=True)
    entity_name: Mapped[str] = mapped_column(String(300), index=True)
    relationship: Mapped[str | None] = mapped_column(String(30), index=True)
    principal_place: Mapped[str | None] = mapped_column(String(200))
    registered_place: Mapped[str | None] = mapped_column(String(200))
    jurisdiction_class: Mapped[str | None] = mapped_column(String(20), index=True)
    business_nature: Mapped[str | None] = mapped_column(String(500))
    direct_pct: Mapped[float | None] = mapped_column()
    indirect_pct: Mapped[float | None] = mapped_column()
    total_pct: Mapped[float | None] = mapped_column()
    acquisition_method: Mapped[str | None] = mapped_column(String(60))
    consolidated: Mapped[bool | None] = mapped_column()
    registered_capital: Mapped[float | None] = mapped_column()
    total_assets: Mapped[float | None] = mapped_column()
    net_assets: Mapped[float | None] = mapped_column()
    revenue: Mapped[float | None] = mapped_column()
    net_profit: Mapped[float | None] = mapped_column()
    source: Mapped[str] = mapped_column(String(100), index=True)
    source_document: Mapped[str | None] = mapped_column(String(2000))
    source_page: Mapped[int | None] = mapped_column(Integer)
    raw_value: Mapped[str | None] = mapped_column(Text)
    extraction_method: Mapped[str] = mapped_column(String(50))
    confidence: Mapped[float | None] = mapped_column()
    validation_status: Mapped[str | None] = mapped_column(String(50), default="UNVALIDATED")
    entity_id: Mapped[int | None] = mapped_column(Integer, index=True)              # v1.8
    extraction_note: Mapped[str | None] = mapped_column(Text)  # v1.5 dual-run result (JSON)
    retrieved_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    __table_args__ = (
        UniqueConstraint("company_id", "observation_date", "entity_name", "source", name="uq_subsidiary_observation"),
    )


class HumanCapitalObservation(Base):
    """R&D, workforce, education and patent figures for one period (v1.3).

    Stored as (category, item, value) so that the many variants of the
    annual-report tables map onto one schema; ``item`` codes are listed in
    ``ashare.human_capital.ITEMS``.
    """
    __tablename__ = "human_capital_observations"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), index=True)
    disclosure_id: Mapped[int | None] = mapped_column(ForeignKey("disclosures.id"), index=True)
    reporting_period: Mapped[str] = mapped_column(String(20), index=True)
    category: Mapped[str] = mapped_column(String(20), index=True)
    item: Mapped[str] = mapped_column(String(60), index=True)
    value: Mapped[float | None] = mapped_column()
    unit: Mapped[str | None] = mapped_column(String(20))
    label_cn: Mapped[str | None] = mapped_column(String(200))
    source: Mapped[str] = mapped_column(String(100), index=True)
    source_document: Mapped[str | None] = mapped_column(String(2000))
    source_page: Mapped[int | None] = mapped_column(Integer)
    raw_value: Mapped[str | None] = mapped_column(Text)
    extraction_method: Mapped[str] = mapped_column(String(50))
    confidence: Mapped[float | None] = mapped_column()
    validation_status: Mapped[str | None] = mapped_column(String(50), default="UNVALIDATED")
    extraction_note: Mapped[str | None] = mapped_column(Text)  # v1.5 dual-run result (JSON)
    retrieved_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    __table_args__ = (
        UniqueConstraint("company_id", "reporting_period", "item", "source", "disclosure_id", name="uq_human_capital"),
    )


class EsgObservation(Base):
    """An environmental, social or governance data point for one period (v1.3)."""
    __tablename__ = "esg_observations"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), index=True)
    disclosure_id: Mapped[int | None] = mapped_column(ForeignKey("disclosures.id"), index=True)
    reporting_period: Mapped[str] = mapped_column(String(20), index=True)
    pillar: Mapped[str] = mapped_column(String(4), index=True)
    item: Mapped[str] = mapped_column(String(60), index=True)
    value: Mapped[float | None] = mapped_column()
    value_text: Mapped[str | None] = mapped_column(String(500))
    unit: Mapped[str | None] = mapped_column(String(30))
    source: Mapped[str] = mapped_column(String(100), index=True)
    source_document: Mapped[str | None] = mapped_column(String(2000))
    source_page: Mapped[int | None] = mapped_column(Integer)
    raw_value: Mapped[str | None] = mapped_column(Text)
    extraction_method: Mapped[str] = mapped_column(String(50))
    confidence: Mapped[float | None] = mapped_column()
    validation_status: Mapped[str | None] = mapped_column(String(50), default="UNVALIDATED")
    retrieved_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    __table_args__ = (
        UniqueConstraint("company_id", "reporting_period", "item", "source", "disclosure_id", name="uq_esg_observation"),
    )


class EsgRating(Base):
    """A third-party ESG rating (licensed data, imported) (v1.3)."""
    __tablename__ = "esg_ratings"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), index=True)
    provider: Mapped[str] = mapped_column(String(60), index=True)
    rating_date: Mapped[str] = mapped_column(String(20), index=True)
    rating: Mapped[str | None] = mapped_column(String(20))
    score: Mapped[float | None] = mapped_column()
    pillar_e: Mapped[float | None] = mapped_column()
    pillar_s: Mapped[float | None] = mapped_column()
    pillar_g: Mapped[float | None] = mapped_column()
    source: Mapped[str] = mapped_column(String(100))
    source_document: Mapped[str | None] = mapped_column(String(2000))
    retrieved_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    __table_args__ = (
        UniqueConstraint("company_id", "provider", "rating_date", "source", name="uq_esg_rating"),
    )


class ParserCalibration(Base):
    """Measured accuracy of a parser on a verified golden corpus (v1.4).

    One row per parser and field ('*' is the parser as a whole). Extractors
    read the overall row to set calibrated confidence; synthetic corpora are
    recorded for reference but never used for calibration.
    """
    __tablename__ = "parser_calibration"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    parser: Mapped[str] = mapped_column(String(60), index=True)
    field: Mapped[str] = mapped_column(String(60), default="*")
    parser_version: Mapped[str | None] = mapped_column(String(20))
    expected: Mapped[int] = mapped_column(Integer, default=0)
    predicted: Mapped[int] = mapped_column(Integer, default=0)
    correct: Mapped[int] = mapped_column(Integer, default=0)
    wrong: Mapped[int] = mapped_column(Integer, default=0)
    missed: Mapped[int] = mapped_column(Integer, default=0)
    spurious: Mapped[int] = mapped_column(Integer, default=0)
    precision: Mapped[float | None] = mapped_column()
    precision_lower: Mapped[float | None] = mapped_column()
    recall: Mapped[float | None] = mapped_column()
    corpus_name: Mapped[str | None] = mapped_column(String(200))
    corpus_fingerprint: Mapped[str | None] = mapped_column(String(64))
    synthetic: Mapped[int] = mapped_column(Integer, default=0)
    evaluated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    __table_args__ = (UniqueConstraint("parser", "field", "synthetic", name="uq_parser_calibration"),)


class ReviewItem(Base):
    """Something a person should check (v1.5): a flag, a parser disagreement
    or a low-confidence value. Keyed by ``item_key`` so that rebuilding the
    queue keeps decisions already taken."""
    __tablename__ = "review_items"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    item_key: Mapped[str] = mapped_column(String(40), unique=True)
    kind: Mapped[str] = mapped_column(String(20), index=True)
    rule: Mapped[str | None] = mapped_column(String(80))
    severity: Mapped[str | None] = mapped_column(String(10))
    company_id: Mapped[int | None] = mapped_column(ForeignKey("companies.id"), index=True)
    table_name: Mapped[str] = mapped_column(String(60))
    row_id: Mapped[int | None] = mapped_column(Integer)
    natural_key: Mapped[str | None] = mapped_column(Text)
    field: Mapped[str | None] = mapped_column(String(60))
    value: Mapped[str | None] = mapped_column(String(200))
    confidence: Mapped[float | None] = mapped_column()
    materiality: Mapped[float | None] = mapped_column(index=True)
    status: Mapped[str] = mapped_column(String(12), default="OPEN", index=True)
    details: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime)


class ManualCorrection(Base):
    """A reviewer's decision on one field of one observation (v1.5).

    Source MANUAL_REVIEW. The original row is never changed; views apply the
    latest non-superseded correction for the row's natural key."""
    __tablename__ = "manual_corrections"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    table_name: Mapped[str] = mapped_column(String(60), index=True)
    row_id: Mapped[int | None] = mapped_column(Integer)
    natural_key: Mapped[str] = mapped_column(Text)
    field: Mapped[str] = mapped_column(String(60))
    action: Mapped[str] = mapped_column(String(10))          # ACCEPT / CORRECT / REJECT
    original_value: Mapped[str | None] = mapped_column(String(200))
    corrected_value: Mapped[str | None] = mapped_column(String(200))
    reason: Mapped[str | None] = mapped_column(Text)
    reviewer: Mapped[str | None] = mapped_column(String(100))
    source: Mapped[str] = mapped_column(String(30), default="MANUAL_REVIEW")
    review_item_id: Mapped[int | None] = mapped_column(Integer)
    superseded: Mapped[int] = mapped_column(Integer, default=0, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class SecurityHistory(Base):
    """Point-in-time identity of a listed security (v1.6): name, board and
    listing status over [valid_from, valid_to). valid_to NULL = still valid."""
    __tablename__ = "security_history"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), index=True)
    security_code: Mapped[str] = mapped_column(String(12), index=True)
    exchange: Mapped[str | None] = mapped_column(String(8))
    board: Mapped[str | None] = mapped_column(String(40))
    short_name_cn: Mapped[str | None] = mapped_column(String(100))
    legal_name_cn: Mapped[str | None] = mapped_column(String(300))
    listing_status: Mapped[str] = mapped_column(String(20), index=True)   # LISTED / DELISTED
    risk_warning: Mapped[str | None] = mapped_column(String(10))          # ST / *ST
    valid_from: Mapped[str | None] = mapped_column(String(20), index=True)
    valid_to: Mapped[str | None] = mapped_column(String(20), index=True)
    source: Mapped[str] = mapped_column(String(100))                      # DERIVED or an import label
    basis: Mapped[str | None] = mapped_column(String(300))
    recorded_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class ListingEvent(Base):
    """IPO, delisting, board transfer, code or name change, risk warning (v1.6)."""
    __tablename__ = "listing_events"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), index=True)
    event_type: Mapped[str] = mapped_column(String(30), index=True)
    event_date: Mapped[str | None] = mapped_column(String(20), index=True)
    date_basis: Mapped[str | None] = mapped_column(String(30))   # EFFECTIVE / ANNOUNCED / DETECTED
    old_value: Mapped[str | None] = mapped_column(String(300))
    new_value: Mapped[str | None] = mapped_column(String(300))
    source: Mapped[str] = mapped_column(String(100))
    disclosure_id: Mapped[int | None] = mapped_column(ForeignKey("disclosures.id"))
    raw_value: Mapped[str | None] = mapped_column(Text)
    extraction_method: Mapped[str | None] = mapped_column(String(50))
    confidence: Mapped[float | None] = mapped_column()
    retrieved_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    __table_args__ = (UniqueConstraint("company_id", "event_type", "event_date", "new_value", "source",
                                       name="uq_listing_event"),)


class IndexConstituent(Base):
    """Membership of a stock index over [valid_from, valid_to) (v1.6)."""
    __tablename__ = "index_constituents"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    index_code: Mapped[str] = mapped_column(String(20), index=True)
    index_name: Mapped[str | None] = mapped_column(String(100))
    security_code: Mapped[str] = mapped_column(String(12), index=True)
    company_id: Mapped[int | None] = mapped_column(ForeignKey("companies.id"), index=True)
    valid_from: Mapped[str] = mapped_column(String(20), index=True)
    valid_to: Mapped[str | None] = mapped_column(String(20), index=True)
    weight: Mapped[float | None] = mapped_column()
    source: Mapped[str] = mapped_column(String(100))
    retrieved_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    __table_args__ = (UniqueConstraint("index_code", "security_code", "valid_from", "source",
                                       name="uq_index_constituent"),)


class TradingDay(Base):
    """Exchange trading calendar (v1.6), imported or derived from market data."""
    __tablename__ = "trading_calendar"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    exchange: Mapped[str] = mapped_column(String(8), index=True)
    trade_date: Mapped[str] = mapped_column(String(20), index=True)
    is_open: Mapped[int] = mapped_column(Integer, default=1)
    source: Mapped[str] = mapped_column(String(100))
    securities_trading: Mapped[int | None] = mapped_column(Integer)
    __table_args__ = (UniqueConstraint("exchange", "trade_date", name="uq_trading_day"),)


class AdjustmentFactor(Base):
    """Price adjustment factor computed from recorded corporate actions (v1.7)."""
    __tablename__ = "adjustment_factors"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), index=True)
    ex_date: Mapped[str] = mapped_column(String(20), index=True)
    prev_close: Mapped[float | None] = mapped_column()
    cash_per_share: Mapped[float | None] = mapped_column()
    share_ratio: Mapped[float | None] = mapped_column()       # bonus + capitalisation shares per share
    rights_ratio: Mapped[float | None] = mapped_column()
    rights_price: Mapped[float | None] = mapped_column()
    reference_price: Mapped[float | None] = mapped_column()
    factor: Mapped[float | None] = mapped_column()
    cumulative: Mapped[float | None] = mapped_column()
    action_ids: Mapped[str | None] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(40), default="OWN")
    computed_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    __table_args__ = (UniqueConstraint("company_id", "ex_date", "source", name="uq_adjustment_factor"),)


class PledgeEvent(Base):
    """A share pledge or release announced by a listed company (v1.8)."""
    __tablename__ = "pledge_events"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), index=True)
    disclosure_id: Mapped[int | None] = mapped_column(ForeignKey("disclosures.id"), index=True)
    event_type: Mapped[str] = mapped_column(String(20), index=True)        # PLEDGE / RELEASE
    announcement_date: Mapped[str | None] = mapped_column(String(20), index=True)
    pledgor: Mapped[str | None] = mapped_column(String(300), index=True)
    pledgee: Mapped[str | None] = mapped_column(String(300))
    is_controlling_shareholder: Mapped[bool | None] = mapped_column()
    shares: Mapped[float | None] = mapped_column()
    pct_of_holding: Mapped[float | None] = mapped_column()
    pct_of_total: Mapped[float | None] = mapped_column()
    start_date: Mapped[str | None] = mapped_column(String(20))
    end_date: Mapped[str | None] = mapped_column(String(20))
    cumulative_pledged: Mapped[float | None] = mapped_column()
    raw_value: Mapped[str | None] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(100))
    extraction_method: Mapped[str | None] = mapped_column(String(50))
    confidence: Mapped[float | None] = mapped_column()
    retrieved_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    __table_args__ = (UniqueConstraint("company_id", "disclosure_id", "event_type", "pledgor", "shares", "source",
                                       name="uq_pledge_event"),)


class ControlObservation(Base):
    """Controlling shareholder, actual controller and ownership type at a date (v1.8)."""
    __tablename__ = "control_observations"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), index=True)
    disclosure_id: Mapped[int | None] = mapped_column(ForeignKey("disclosures.id"), index=True)
    observation_date: Mapped[str] = mapped_column(String(20), index=True)
    controlling_shareholder: Mapped[str | None] = mapped_column(String(300))
    controlling_nature: Mapped[str | None] = mapped_column(String(100))
    actual_controller: Mapped[str | None] = mapped_column(String(300))
    controller_nature: Mapped[str | None] = mapped_column(String(100))
    no_controlling_shareholder: Mapped[bool | None] = mapped_column()
    no_actual_controller: Mapped[bool | None] = mapped_column()
    ownership_type: Mapped[str | None] = mapped_column(String(20), index=True)
    ownership_basis: Mapped[str | None] = mapped_column(String(300))
    source: Mapped[str] = mapped_column(String(100))
    source_page: Mapped[int | None] = mapped_column(Integer)
    raw_value: Mapped[str | None] = mapped_column(Text)
    extraction_method: Mapped[str | None] = mapped_column(String(50))
    confidence: Mapped[float | None] = mapped_column()
    retrieved_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    __table_args__ = (UniqueConstraint("company_id", "observation_date", "source", name="uq_control_observation"),)


class ControlEdge(Base):
    """One link of a control chain: parent holds pct of child (v1.8)."""
    __tablename__ = "control_edges"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), index=True)   # the listed company
    observation_date: Mapped[str] = mapped_column(String(20), index=True)
    parent_name: Mapped[str] = mapped_column(String(300))
    child_name: Mapped[str] = mapped_column(String(300))
    parent_entity_id: Mapped[int | None] = mapped_column(Integer, index=True)
    child_entity_id: Mapped[int | None] = mapped_column(Integer, index=True)
    pct: Mapped[float | None] = mapped_column()
    basis: Mapped[str | None] = mapped_column(String(200))
    source: Mapped[str] = mapped_column(String(100))
    retrieved_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    __table_args__ = (UniqueConstraint("company_id", "observation_date", "parent_name", "child_name", "source",
                                       name="uq_control_edge"),)


class Entity(Base):
    """An organisation met anywhere in the data (v1.8): shareholder, subsidiary,
    controller or listed company, resolved by credit code or normalised name."""
    __tablename__ = "entities"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(300))
    normalised_name: Mapped[str] = mapped_column(String(300), index=True)
    credit_code: Mapped[str | None] = mapped_column(String(18), index=True)
    entity_type: Mapped[str | None] = mapped_column(String(30))     # COMPANY / GOVERNMENT / FUND / PARTNERSHIP / OTHER
    listed_company_id: Mapped[int | None] = mapped_column(ForeignKey("companies.id"), index=True)
    jurisdiction: Mapped[str | None] = mapped_column(String(20))
    sources: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class EntityAlias(Base):
    __tablename__ = "entity_aliases"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    entity_id: Mapped[int] = mapped_column(ForeignKey("entities.id"), index=True)
    alias: Mapped[str] = mapped_column(String(300), index=True)
    normalised_alias: Mapped[str] = mapped_column(String(300), index=True)
    __table_args__ = (UniqueConstraint("entity_id", "normalised_alias", name="uq_entity_alias"),)


class Person(Base):
    """A natural person resolved across companies (v1.8)."""
    __tablename__ = "persons"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100), index=True)
    gender: Mapped[str | None] = mapped_column(String(4))
    birth_year: Mapped[int | None] = mapped_column(Integer)
    resolution: Mapped[str | None] = mapped_column(String(200))   # basis of the identity
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class PersonRole(Base):
    __tablename__ = "person_roles"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    person_id: Mapped[int] = mapped_column(ForeignKey("persons.id"), index=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), index=True)
    role: Mapped[str | None] = mapped_column(String(40))
    first_date: Mapped[str | None] = mapped_column(String(20))
    last_date: Mapped[str | None] = mapped_column(String(20))
    tenure_start: Mapped[str | None] = mapped_column(String(20))
    tenure_end: Mapped[str | None] = mapped_column(String(20))
    observation_ids: Mapped[str | None] = mapped_column(Text)
    __table_args__ = (UniqueConstraint("person_id", "company_id", "role", name="uq_person_role"),)


"""v1.9 operations: jobs, items and high-water marks."""

class Job(Base):
    __tablename__ = "jobs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    kind: Mapped[str] = mapped_column(String(40), index=True)
    params: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(12), default="QUEUED", index=True)
    total: Mapped[int] = mapped_column(Integer, default=0)
    done: Mapped[int] = mapped_column(Integer, default=0)
    failed: Mapped[int] = mapped_column(Integer, default=0)
    cancel_requested: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    started_at: Mapped[datetime | None] = mapped_column(DateTime)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime)


class JobItem(Base):
    __tablename__ = "job_items"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id"), index=True)
    item_key: Mapped[str] = mapped_column(String(60))
    status: Mapped[str] = mapped_column(String(10), default="PENDING", index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[str | None] = mapped_column(Text)
    result: Mapped[str | None] = mapped_column(Text)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime)
    __table_args__ = (UniqueConstraint("job_id", "item_key", name="uq_job_item"),)


class HighWaterMark(Base):
    __tablename__ = "high_water_marks"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source: Mapped[str] = mapped_column(String(40))
    scope: Mapped[str] = mapped_column(String(20))           # a security code, or '*' for market-wide
    kind: Mapped[str] = mapped_column(String(40))
    value: Mapped[str] = mapped_column(String(20))
    updated_at: Mapped[datetime | None] = mapped_column(DateTime)
    __table_args__ = (UniqueConstraint("source", "scope", "kind", name="uq_high_water_mark"),)


class CatalogueDay(Base):
    """v2.0.3: one row per announcement kind and calendar day of the
    market-wide catalogue, so that a rerun resumes and every shortfall or
    failure is recorded against the exact day.

    status: DONE (everything CNINFO reported was stored), SHORTFALL (fewer
    stored than CNINFO's total, even after splitting the day), FAILED (an
    error; retried on the next run)."""
    __tablename__ = "catalogue_days"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    kind: Mapped[str] = mapped_column(String(40))
    day: Mapped[str] = mapped_column(String(10), index=True)
    status: Mapped[str] = mapped_column(String(12))
    expected: Mapped[int | None] = mapped_column(Integer)      # CNINFO's total for this day (single-day queries)
    stored: Mapped[int | None] = mapped_column(Integer)        # distinct announcements received for this day
    window: Mapped[str | None] = mapped_column(String(25))     # the query window that covered the day
    method: Mapped[str | None] = mapped_column(String(60))     # WINDOW / DAY / CATEGORY_SPLIT / PLATE_SPLIT
    queries: Mapped[int | None] = mapped_column(Integer)
    error: Mapped[str | None] = mapped_column(Text)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime)
    # v2.0.4: rows (announcement x security), gaps by board, split notes, strategy and window total
    rows_multi: Mapped[int | None] = mapped_column(Integer)       # rows beyond the first for one announcement
    gap_in_scope: Mapped[int | None] = mapped_column(Integer)     # rows missing within the enabled boards
    gap_out_scope: Mapped[int | None] = mapped_column(Integer)    # rows missing outside them (e.g. Beijing)
    partition: Mapped[str | None] = mapped_column(String(250))    # notes on splits that did not reach the total
    strategy: Mapped[int | None] = mapped_column(Integer)         # catalogue strategy (2 = v2.0.4)
    window_expected: Mapped[int | None] = mapped_column(Integer)  # CNINFO's total for the window, when fetched
    __table_args__ = (UniqueConstraint("kind", "day", name="uq_catalogue_day"),)


class Source(Base):
    __tablename__ = "sources"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    base_url: Mapped[str | None] = mapped_column(String(1000))
    access_type: Mapped[str] = mapped_column(String(50), default="public")
    notes: Mapped[str | None] = mapped_column(Text)
    licence: Mapped[str | None] = mapped_column(String(30))       # v2.0: overrides the default licence class

class RawRecord(Base):
    __tablename__ = "raw_records"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id"), index=True)
    company_id: Mapped[int | None] = mapped_column(ForeignKey("companies.id"), index=True)
    retrieved_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    url: Mapped[str | None] = mapped_column(String(2000))
    content_type: Mapped[str | None] = mapped_column(String(100))
    sha256: Mapped[str | None] = mapped_column(String(64), index=True)
    payload_path: Mapped[str | None] = mapped_column(String(1000))
    metadata_json: Mapped[str | None] = mapped_column(Text)

_ENGINES: dict[str, object] = {}


def database_url() -> str:
    """SQLite file by default; ASHARE_DB_URL selects another back end (v1.9), e.g.
    postgresql+psycopg://user:pass@host/ashares (needs the psycopg package)."""
    import os
    return os.environ.get("ASHARE_DB_URL") or f"sqlite:///{db_path()}"


def is_sqlite() -> bool:
    return database_url().startswith("sqlite")


def engine():
    """Return a cached engine for the configured database."""
    url = database_url()
    eng = _ENGINES.get(url)
    if eng is None:
        if url.startswith("sqlite"):
            from sqlalchemy import event
            eng = create_engine(url, future=True)

            @event.listens_for(eng, "connect")
            def _pragmas(dbapi_conn, _):     # v1.9: faster bulk writes, safe for one writer
                cur = dbapi_conn.cursor()
                cur.execute("PRAGMA journal_mode=WAL")
                cur.execute("PRAGMA synchronous=NORMAL")
                cur.close()
        else:
            eng = create_engine(url, future=True, pool_pre_ping=True)
        _ENGINES[url] = eng
    return eng


def SessionLocal():
    """Return a new ORM *session* (v0.7 wrongly returned a sessionmaker)."""
    return sessionmaker(bind=engine(), expire_on_commit=False)()


# v2.0: column additions and indexes are now Alembic revisions (ashare/migrations).

_INITIALISED: set[str] = set()


def reset_init_cache() -> None:
    _INITIALISED.clear()


def init_db():
    """Bring the database to the current schema; once per process and database.

    v2.0: the schema is versioned with Alembic (``ashare/migrations``). A new
    database is created at the head revision; an older one, from v0.7 onwards,
    is upgraded in place, after a backup copy of a SQLite file is taken.
    """
    from . import transactions  # noqa: F401  (registers transaction_events)
    url = database_url()
    if url in _INITIALISED and (not url.startswith("sqlite") or db_path().exists()):
        return
    from .migrate import upgrade
    upgrade()
    _INITIALISED.add(url)
