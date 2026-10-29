"""v2.0.8: resume state for every document extractor, and the kind of segment table a row came from

Revision ID: 0006_v208_extraction_state
Revises: 0005_v206_extraction_state
Create Date: 2026-10-29
"""
from alembic import op

from ashare.migrate import add_column_if_missing

revision = "0006_v208_extraction_state"
down_revision = "0005_v206_extraction_state"
branch_labels = None
depends_on = None


def upgrade() -> None:
    from ashare.models import Base
    conn = op.get_bind()
    Base.metadata.tables["extraction_state"].create(conn, checkfirst=True)
    add_column_if_missing(conn, "segment_observations", "table_kind", "VARCHAR(20)")


def downgrade() -> None:
    op.drop_table("extraction_state")
    with op.batch_alter_table("segment_observations") as b:
        b.drop_column("table_kind")
