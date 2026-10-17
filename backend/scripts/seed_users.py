"""Idempotent seed: four role-based demo users.

Passwords come from env vars — never hard-coded (repo is public):
  SEED_ADMIN_PASSWORD
  SEED_BUILDER_PASSWORD
  SEED_REVIEWER_PASSWORD
  SEED_OBSERVER_PASSWORD

A missing env var skips that user. Run twice: row counts stay the same.

Usage (from backend/):
    python -m scripts.seed_users
"""
from __future__ import annotations

import asyncio
import os
import uuid
from pathlib import Path

from dotenv import load_dotenv

# Load repo-root .env so SEED_* vars are available without manual export
load_dotenv(Path(__file__).resolve().parents[2] / ".env")

from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import settings
from app.core.security import hash_password

_USERS = [
    {
        "email": "admin@seyarkai.example",
        "name": "Admin User",
        "role": "admin",
        "env_var": "SEED_ADMIN_PASSWORD",
    },
    {
        "email": "builder@seyarkai.example",
        "name": "Builder User",
        "role": "builder",
        "env_var": "SEED_BUILDER_PASSWORD",
    },
    {
        "email": "reviewer@seyarkai.example",
        "name": "Reviewer User",
        "role": "reviewer",
        "env_var": "SEED_REVIEWER_PASSWORD",
    },
    {
        "email": "observer@seyarkai.example",
        "name": "Observer User",
        "role": "observer",
        "env_var": "SEED_OBSERVER_PASSWORD",
    },
]

_UPSERT = """
INSERT INTO users (id, email, name, hashed_password, role, status, created_at, updated_at)
VALUES (:id, :email, :name, :hashed_password, :role, 'active', now(), now())
ON CONFLICT (email)
DO UPDATE SET
    name            = EXCLUDED.name,
    hashed_password = EXCLUDED.hashed_password,
    role            = EXCLUDED.role,
    updated_at      = now()
"""


async def seed(db_url: str | None = None) -> int:
    url = db_url or settings.DATABASE_URL
    engine = create_async_engine(url, echo=False)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    seeded = 0
    try:
        async with factory() as session:
            for spec in _USERS:
                password = os.environ.get(spec["env_var"], "")
                if not password:
                    print(f"  skip {spec['email']} ({spec['env_var']} not set)")
                    continue
                await session.execute(
                    text(_UPSERT),
                    {
                        "id": str(uuid.uuid4()),
                        "email": spec["email"],
                        "name": spec["name"],
                        "hashed_password": hash_password(password),
                        "role": spec["role"],
                    },
                )
                print(f"  upserted {spec['email']} ({spec['role']})")
                seeded += 1
            await session.commit()
    finally:
        await engine.dispose()
    return seeded


if __name__ == "__main__":
    count = asyncio.run(seed())
    print(f"Done — {count} user(s) seeded.")
