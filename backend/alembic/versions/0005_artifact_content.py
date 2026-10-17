"""add html_content to artifacts

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-17
"""
from alembic import op
import sqlalchemy as sa

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("artifacts", sa.Column("html_content", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("artifacts", "html_content")
