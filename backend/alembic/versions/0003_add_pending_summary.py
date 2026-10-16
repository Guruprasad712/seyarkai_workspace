"""add pending_summary to executions

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-10
"""
from alembic import op
import sqlalchemy as sa

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("executions", sa.Column("pending_summary", sa.TEXT(), nullable=True))


def downgrade() -> None:
    op.drop_column("executions", "pending_summary")
