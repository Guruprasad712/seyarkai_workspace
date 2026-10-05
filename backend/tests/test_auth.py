"""Auth tests — all offline (no Vertex AI calls).

Fixtures seed_user and auth_headers are local to this module.
The session-scoped apply_migrations and async_client come from conftest.py.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import jwt
import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import text

from app.core.config import settings
from app.core.security import create_access_token, hash_password

_PASSWORD = "correct-horse-battery"
_INACTIVE_PASSWORD = "inactive-pass-123"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

import contextlib
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker


@contextlib.asynccontextmanager
async def _test_db(test_db_url: str):
    """Isolated engine/session for fixture setup and teardown."""
    engine = create_async_engine(test_db_url, echo=False)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as db:
            yield db
    finally:
        await engine.dispose()


@pytest_asyncio.fixture()
async def seed_user(test_db_url: str, async_client: AsyncClient):
    """Insert one active user; delete on teardown."""
    user_id = str(uuid.uuid4())
    async with _test_db(test_db_url) as db:
        await db.execute(
            text(
                "INSERT INTO users (id, email, name, hashed_password, role, status, created_at, updated_at) "
                "VALUES (:id, :email, :name, :hp, 'member', 'active', now(), now())"
            ),
            {"id": user_id, "email": "test@example.com", "name": "Test User", "hp": hash_password(_PASSWORD)},
        )
        await db.commit()

    yield {"id": user_id, "email": "test@example.com", "role": "member"}

    async with _test_db(test_db_url) as db:
        await db.execute(text("DELETE FROM users WHERE id = :id"), {"id": user_id})
        await db.commit()


@pytest_asyncio.fixture()
async def inactive_user(test_db_url: str, async_client: AsyncClient):
    """Insert one inactive user; delete on teardown."""
    user_id = str(uuid.uuid4())
    async with _test_db(test_db_url) as db:
        await db.execute(
            text(
                "INSERT INTO users (id, email, name, hashed_password, role, status, created_at, updated_at) "
                "VALUES (:id, :email, :name, :hp, 'member', 'inactive', now(), now())"
            ),
            {
                "id": user_id,
                "email": "inactive@example.com",
                "name": "Inactive User",
                "hp": hash_password(_INACTIVE_PASSWORD),
            },
        )
        await db.commit()

    yield {"id": user_id, "email": "inactive@example.com"}

    async with _test_db(test_db_url) as db:
        await db.execute(text("DELETE FROM users WHERE id = :id"), {"id": user_id})
        await db.commit()


@pytest.fixture()
def auth_headers(seed_user):
    token = create_access_token(seed_user["id"], seed_user["role"])
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# Login tests
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_login_success(async_client: AsyncClient, seed_user):
    r = await async_client.post(
        "/auth/login", json={"email": seed_user["email"], "password": _PASSWORD}
    )
    assert r.status_code == 200
    body = r.json()
    assert "access_token" in body
    assert body["token_type"] == "bearer"
    assert "user" in body
    assert body["user"]["email"] == seed_user["email"]
    # hashed_password must never appear anywhere in the response
    assert "hashed_password" not in str(body)


@pytest.mark.anyio
async def test_login_wrong_password(async_client: AsyncClient, seed_user):
    r = await async_client.post(
        "/auth/login", json={"email": seed_user["email"], "password": "wrong-password"}
    )
    assert r.status_code == 401
    assert r.json() == {"detail": "invalid credentials"}


@pytest.mark.anyio
async def test_login_unknown_email(async_client: AsyncClient):
    r = await async_client.post(
        "/auth/login", json={"email": "nobody@example.com", "password": "anything"}
    )
    assert r.status_code == 401
    assert r.json() == {"detail": "invalid credentials"}


@pytest.mark.anyio
async def test_login_inactive_user(async_client: AsyncClient, inactive_user):
    r = await async_client.post(
        "/auth/login",
        json={"email": inactive_user["email"], "password": _INACTIVE_PASSWORD},
    )
    assert r.status_code == 401
    assert r.json() == {"detail": "invalid credentials"}


@pytest.mark.anyio
async def test_all_three_401_bodies_identical(async_client: AsyncClient, seed_user, inactive_user):
    r_wrong_pw = await async_client.post(
        "/auth/login", json={"email": seed_user["email"], "password": "wrong"}
    )
    r_unknown = await async_client.post(
        "/auth/login", json={"email": "nobody@example.com", "password": "x"}
    )
    r_inactive = await async_client.post(
        "/auth/login", json={"email": inactive_user["email"], "password": _INACTIVE_PASSWORD}
    )
    assert r_wrong_pw.json() == r_unknown.json() == r_inactive.json()


@pytest.mark.anyio
async def test_password_over_72_bytes(async_client: AsyncClient, seed_user):
    long_pw = "a" * 73
    r = await async_client.post(
        "/auth/login", json={"email": seed_user["email"], "password": long_pw}
    )
    assert r.status_code == 422


# ---------------------------------------------------------------------------
# Token validation tests
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_expired_token(async_client: AsyncClient, seed_user):
    expired = jwt.encode(
        {"sub": seed_user["id"], "role": "member", "exp": datetime.now(timezone.utc) - timedelta(hours=1)},
        settings.JWT_SECRET,
        algorithm="HS256",
    )
    r = await async_client.get("/auth/me", headers={"Authorization": f"Bearer {expired}"})
    assert r.status_code == 401


@pytest.mark.anyio
async def test_tampered_token(async_client: AsyncClient, auth_headers):
    token = auth_headers["Authorization"][7:]
    # flip the last character
    tampered = token[:-1] + ("A" if token[-1] != "A" else "B")
    r = await async_client.get("/auth/me", headers={"Authorization": f"Bearer {tampered}"})
    assert r.status_code == 401


@pytest.mark.anyio
async def test_deactivated_user_token(
    test_db_url: str, async_client: AsyncClient, seed_user, auth_headers
):
    # Deactivate the user after the token was issued
    async with _test_db(test_db_url) as db:
        await db.execute(
            text("UPDATE users SET status = 'inactive' WHERE id = :id"),
            {"id": seed_user["id"]},
        )
        await db.commit()

    r = await async_client.get("/auth/me", headers=auth_headers)
    assert r.status_code == 401

    # Re-activate so the fixture teardown DELETE succeeds cleanly
    async with _test_db(test_db_url) as db:
        await db.execute(
            text("UPDATE users SET status = 'active' WHERE id = :id"),
            {"id": seed_user["id"]},
        )
        await db.commit()


# ---------------------------------------------------------------------------
# Response shape test
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_password_hash_never_in_response(async_client: AsyncClient, seed_user, auth_headers):
    r_login = await async_client.post(
        "/auth/login", json={"email": seed_user["email"], "password": _PASSWORD}
    )
    r_me = await async_client.get("/auth/me", headers=auth_headers)

    assert "hashed_password" not in r_login.text
    assert "hashed_password" not in r_me.text


# ---------------------------------------------------------------------------
# Global auth coverage test
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_every_registered_route_requires_auth(async_client: AsyncClient):
    """Walk every registered route; assert 401 without a token (allowlist excepted)."""
    from app.main import app

    _ALLOWLIST = {("/health", "GET"), ("/auth/login", "POST")}

    missing_auth: list[str] = []
    for route in app.routes:
        path = getattr(route, "path", None)
        methods = getattr(route, "methods", None)
        if path is None or methods is None:
            continue
        for method in methods:
            if method == "OPTIONS":
                continue
            if (path, method) in _ALLOWLIST:
                continue
            r = await async_client.request(method, path)
            if r.status_code != 401:
                missing_auth.append(f"{method} {path} → {r.status_code}")

    assert not missing_auth, f"Routes missing auth: {missing_auth}"
