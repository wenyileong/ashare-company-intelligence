"""v2.0.4: catalogue detail per day (rows per security, gaps by board, splits, strategy)

Revision ID: 0004_v204_catalogue_detail
Revises: 0003_v203_catalogue_days
Create Date: 2026-10-18
"""
from alembic import op

from ashare.migrate import add_column_if_missing

revision = "0004_v204_catalogue_detail"
down_revision = "0003_v203_catalogue_days"
branch_labels = None
depends_on = None

COLUMNS = (("rows_multi", "INTEGER"), ("gap_in_scope", "INTEGER"), ("gap_out_scope", "INTEGER"),
           ("partition", "VARCHAR(250)"), ("strategy", "INTEGER"), ("window_expected", "INTEGER"))


def upgrade() -> None:
    conn = op.get_bind()
    for name, ddl in COLUMNS:
        add_column_if_missing(conn, "catalogue_days", name, ddl)


def downgrade() -> None:
    with op.batch_alter_table("catalogue_days") as b:
        for name, _ in COLUMNS:
            b.drop_column(name)
