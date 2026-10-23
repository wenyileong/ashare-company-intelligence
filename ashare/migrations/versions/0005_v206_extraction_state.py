"""v2.0.6: which extractor version last read each document, so that a stopped extraction continues

Revision ID: 0005_v206_extraction_state
Revises: 0004_v204_catalogue_detail
Create Date: 2026-10-23
"""
from alembic import op

from ashare.migrate import add_column_if_missing

revision = "0005_v206_extraction_state"
down_revision = "0004_v204_catalogue_detail"
branch_labels = None
depends_on = None

COLUMNS = (("extracted_version", "VARCHAR(40)"), ("extracted_at", "TIMESTAMP"))


def upgrade() -> None:
    conn = op.get_bind()
    for name, ddl in COLUMNS:
        add_column_if_missing(conn, "disclosures", name, ddl)


def downgrade() -> None:
    with op.batch_alter_table("disclosures") as b:
        for name, _ in COLUMNS:
            b.drop_column(name)
