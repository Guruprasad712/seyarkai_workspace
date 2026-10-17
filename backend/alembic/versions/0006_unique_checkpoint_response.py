"""unique constraint on checkpoint_responses (checkpoint_id, execution_id)

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-18
"""
from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_checkpoint_responses_checkpoint_execution",
        "checkpoint_responses",
        ["checkpoint_id", "execution_id"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_checkpoint_responses_checkpoint_execution",
        "checkpoint_responses",
        type_="unique",
    )
