"""add previous_output to work_items; unique name per project

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-08
"""
from alembic import op
import sqlalchemy as sa

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("work_items", sa.Column("previous_output", sa.TEXT(), nullable=True))
    op.create_unique_constraint("uq_work_items_project_name", "work_items", ["project_id", "name"])
    op.create_unique_constraint("uq_projects_name", "projects", ["name"])


def downgrade() -> None:
    op.drop_constraint("uq_projects_name", "projects", type_="unique")
    op.drop_constraint("uq_work_items_project_name", "work_items", type_="unique")
    op.drop_column("work_items", "previous_output")
