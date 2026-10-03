import os
from pathlib import Path

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

# Locate alembic.ini at backend/
_BACKEND_DIR = Path(__file__).resolve().parents[1]


def _get_test_url() -> str:
    url = os.environ.get("TEST_DATABASE_URL", "")
    if not url:
        # Fall back to reading from .env at repo root
        env_path = _BACKEND_DIR.parent / ".env"
        if env_path.exists():
            for line in env_path.read_text().splitlines():
                if line.startswith("TEST_DATABASE_URL="):
                    url = line.split("=", 1)[1].strip().strip('"').strip("'")
                    break
    if not url:
        pytest.skip("TEST_DATABASE_URL not set")
    return url


@pytest.fixture(scope="session")
def test_db_url() -> str:
    return _get_test_url()


@pytest.fixture(scope="session", autouse=True)
def apply_migrations(test_db_url):
    """Run upgrade at session start; downgrade at teardown."""
    from alembic import command
    from alembic.config import Config

    cfg = Config(str(_BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(_BACKEND_DIR / "alembic"))
    cfg.set_main_option("sqlalchemy.url", test_db_url)

    command.upgrade(cfg, "head")
    yield
    command.downgrade(cfg, "base")


@pytest_asyncio.fixture()
async def async_client(test_db_url):
    """HTTP client wired to the app, using the test database."""
    # Override DATABASE_URL so the app's engine points at the test DB
    os.environ["DATABASE_URL"] = test_db_url

    # Re-import app after env override so the engine uses the test URL
    import importlib
    import app.core.config as cfg_mod
    import app.core.db as db_mod
    import app.main as main_mod

    # Reload in dependency order
    importlib.reload(cfg_mod)
    importlib.reload(db_mod)
    importlib.reload(main_mod)

    from app.main import create_app
    application = create_app()

    async with AsyncClient(
        transport=ASGITransport(app=application),
        base_url="http://test",
    ) as client:
        yield client
