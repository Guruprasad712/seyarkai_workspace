"""Idempotency test for scripts.seed_mcp_tools.

The migrated_test_db fixture runs alembic upgrade/downgrade in a thread
(alembic's online mode calls asyncio.run internally, so it cannot be awaited
directly inside the running event loop).
"""
import asyncio
from pathlib import Path

import pytest

from scripts.seed_mcp_tools import TOOLS, seed

_BACKEND_DIR = Path(__file__).resolve().parents[1]


def _run_alembic(test_db_url: str, direction: str) -> None:
    from alembic import command
    from alembic.config import Config

    cfg = Config(str(_BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(_BACKEND_DIR / "alembic"))
    cfg.set_main_option("sqlalchemy.url", test_db_url)
    if direction == "upgrade":
        command.upgrade(cfg, "head")
    else:
        command.downgrade(cfg, "base")


@pytest.fixture()
def seed_db(test_db_url: str):
    """Synchronous fixture: upgrade before yield, downgrade after.

    Alembic's online mode calls asyncio.run() internally, so this must be
    a sync fixture — running it inside an already-running event loop would
    raise 'This event loop is already running'.
    """
    _run_alembic(test_db_url, "upgrade")
    yield test_db_url
    _run_alembic(test_db_url, "downgrade")


@pytest.mark.anyio
async def test_seed_is_idempotent(seed_db: str):
    count_first = await seed(db_url=seed_db)
    count_second = await seed(db_url=seed_db)
    assert count_first == count_second == len(TOOLS)
