"""Idempotent seed: 1 super_admin + 2 members.

Passwords come from env vars — never hard-coded (repo is public):
  SEED_ADMIN_PASSWORD
  SEED_MEMBER1_PASSWORD
  SEED_MEMBER2_PASSWORD

A missing env var skips that user. Run twice: row counts stay the same.

Usage (from backend/):
    python -m scripts.seed_users
"""
from __future__ import annotations

import asyncio
import os
import uuid

from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import settings
from app.core.security import hash_password

_USERS = [
    {
        "email": "admin@seyarkai.example",
        "name": "Admin",
        "role": "super_admin",
        "env_var": "SEED_ADMIN_PASSWORD",
    },
    {
        "email": "member1@seyarkai.example",
        "name": "Member One",
        "role": "member",
        "env_var": "SEED_MEMBER1_PASSWORD",
    },
    {
        "email": "member2@seyarkai.example",
        "name": "Member Two",
        "role": "member",
        "env_var": "SEED_MEMBER2_PASSWORD",
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
