"""v2.3: new tables (work ledger, outputs register, path rewrites, entity identifiers, external relationships,
insider dealings, watchlists and alerts). Additive only: no existing table changes.

Revision ID: 0008_v23_tables
Revises: 0007_v21_expectations
Create Date: 2026-11-08
"""
from alembic import op

revision = "0008_v23_tables"
down_revision = "0007_v21_expectations"
branch_labels = None
depends_on = None


def upgrade() -> None:
    from ashare.migrate import reconcile_tables
    from ashare.models_v23 import V23_TABLES
    reconcile_tables(op.get_bind(), V23_TABLES)


def downgrade() -> None:
    from ashare.models_v23 import V23_TABLES
    for t in reversed(V23_TABLES):
        op.drop_table(t)
