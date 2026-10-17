"""v2.0.3: per-day catalogue bookkeeping (resume, shortfalls, failures)

Revision ID: 0003_v203_catalogue_days
Revises: 0002_v20_licences
Create Date: 2026-10-17
"""
from alembic import op

revision = "0003_v203_catalogue_days"
down_revision = "0002_v20_licences"
branch_labels = None
depends_on = None


def upgrade() -> None:
    from ashare.models import Base
    conn = op.get_bind()
    Base.metadata.tables["catalogue_days"].create(conn, checkfirst=True)


def downgrade() -> None:
    op.drop_table("catalogue_days")
