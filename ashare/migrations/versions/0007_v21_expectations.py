"""v2.1: expectations (management guidance and imported analyst forecasts)

Revision ID: 0007_v21_expectations
Revises: 0006_v208_extraction_state
Create Date: 2026-10-30
"""
from alembic import op

revision = "0007_v21_expectations"
down_revision = "0006_v208_extraction_state"
branch_labels = None
depends_on = None


def upgrade() -> None:
    from ashare.models import Base
    Base.metadata.tables["expectation_observations"].create(op.get_bind(), checkfirst=True)


def downgrade() -> None:
    op.drop_table("expectation_observations")
