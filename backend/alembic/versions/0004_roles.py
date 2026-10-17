"""normalise user roles to four-value enum

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-17
"""
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("UPDATE users SET role = 'admin' WHERE role = 'super_admin'")
    op.execute(
        "UPDATE users SET role = 'observer' "
        "WHERE role NOT IN ('admin', 'builder', 'reviewer', 'observer')"
    )
    op.execute(
        "ALTER TABLE users ADD CONSTRAINT ck_users_role "
        "CHECK (role IN ('admin', 'builder', 'reviewer', 'observer'))"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE users DROP CONSTRAINT ck_users_role")
