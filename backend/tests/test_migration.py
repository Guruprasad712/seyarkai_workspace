"""Verify the migration is idempotent: upgrade → downgrade → upgrade."""
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config

_BACKEND_DIR = Path(__file__).resolve().parents[1]


def _alembic_cfg(url: str) -> Config:
    cfg = Config(str(_BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(_BACKEND_DIR / "alembic"))
    cfg.set_main_option("sqlalchemy.url", url)
    return cfg


def test_migration_upgrade_downgrade_upgrade(test_db_url):
    """
    apply_migrations (session fixture) already ran upgrade head.
    Here we downgrade to base and upgrade again to confirm the migration
    is fully reversible and re-applicable.
    """
    cfg = _alembic_cfg(test_db_url)

    command.downgrade(cfg, "base")
    command.upgrade(cfg, "head")
    # If both complete without exception, the migration is sound.
