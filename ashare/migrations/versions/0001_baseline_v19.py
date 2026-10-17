"""Baseline: the v1.9 schema, reached from any database written by v0.7 to v1.9

Revision ID: 0001_baseline_v19
Revises:
Create Date: 2026-10-08
"""
from alembic import op

from ashare.migrate import reconcile_tables, create_index_if_missing

revision = "0001_baseline_v19"
down_revision = None
branch_labels = None
depends_on = None

V19_TABLES = (
    "adjustment_factors", "capital_reconciliations", "capital_structure_observations", "companies",
    "control_edges", "control_observations", "corporate_actions", "disclosures", "document_pages", "entities",
    "entity_aliases", "esg_observations", "esg_ratings", "financial_facts", "high_water_marks",
    "human_capital_observations", "index_constituents", "industry_classifications", "job_items", "jobs",
    "listing_events", "management_events", "management_observations", "manual_corrections", "market_bars",
    "market_snapshots", "ownership_observations", "parser_calibration", "person_roles", "persons",
    "pledge_events", "raw_records", "regulatory_events", "research_queries", "review_items", "securities",
    "security_history", "segment_observations", "sources", "subsidiary_observations", "trading_calendar",
    "transaction_events", "validation_flags",
)

V19_INDEXES = (
    ("ix_market_bars_company_date", "market_bars", "company_id, adjustment, trade_date"),
    ("ix_financial_facts_company_metric", "financial_facts", "company_id, metric, reporting_period"),
    ("ix_disclosures_company_date", "disclosures", "company_id, announcement_date"),
    ("ix_disclosures_kind_date", "disclosures", "kind, announcement_date"),
    ("ix_ownership_company_date", "ownership_observations", "company_id, observation_date"),
    ("ix_mgmt_obs_company_date", "management_observations", "company_id, observation_date"),
    ("ix_validation_flags_company_rule", "validation_flags", "company_id, rule"),
    ("ix_job_items_job_status", "job_items", "job_id, status"),
)


def upgrade() -> None:
    conn = op.get_bind()
    reconcile_tables(conn, V19_TABLES)
    for name, table, cols in V19_INDEXES:
        create_index_if_missing(conn, name, table, cols)


def downgrade() -> None:
    raise NotImplementedError("the baseline cannot be downgraded; restore the backup copy instead")
