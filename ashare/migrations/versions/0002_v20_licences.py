"""v2.0: licence class per source

Revision ID: 0002_v20_licences
Revises: 0001_baseline_v19
Create Date: 2026-10-08
"""
from alembic import op

from ashare.migrate import add_column_if_missing

revision = "0002_v20_licences"
down_revision = "0001_baseline_v19"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    add_column_if_missing(conn, "sources", "licence", "VARCHAR(30)")


def downgrade() -> None:
    with op.batch_alter_table("sources") as b:
        b.drop_column("licence")
