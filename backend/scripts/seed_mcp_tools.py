"""Idempotent seed script for the mcp_tools table.

Run from backend/:
    python -m scripts.seed_mcp_tools

Running it more than once must not change row counts or data (upsert on tool_name).
"""
from __future__ import annotations

import asyncio
import uuid

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings

_INSERT_SQL = """
INSERT INTO mcp_tools (id, name, tool_name, server_key, description, status, created_at, updated_at)
VALUES (:id, :name, :tool_name, :server_key, :description, :status, now(), now())
ON CONFLICT (tool_name)
DO UPDATE SET
    name        = EXCLUDED.name,
    server_key  = EXCLUDED.server_key,
    description = EXCLUDED.description,
    status      = EXCLUDED.status,
    updated_at  = now()
"""

TOOLS: list[dict] = [
    {
        "tool_name": "knowledge_search",
        "name": "Knowledge Search",
        "server_key": "knowledge",
        "description": (
            "Search Company Brain for documents relevant to the query. "
            "query is free-text describing the information needed, not a file name."
        ),
        "status": "active",
    },
    {
        "tool_name": "generate_document",
        "name": "Generate Document",
        "server_key": "docs",
        "description": (
            "Generate a Google Doc from Markdown content. "
            "title is the document title; content_markdown is the body in Markdown."
        ),
        "status": "active",
    },
]


async def seed(db_url: str | None = None) -> int:
    """Upsert all MVP tools. Returns the count of seeded tools found in mcp_tools after seeding."""
    url = db_url or settings.DATABASE_URL
    engine = create_async_engine(url, echo=False)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    tool_names = [t["tool_name"] for t in TOOLS]
    try:
        async with session_factory() as session:
            for tool in TOOLS:
                await session.execute(
                    text(_INSERT_SQL),
                    {"id": str(uuid.uuid4()), **tool},
                )
            await session.commit()
            result = await session.execute(
                text("SELECT COUNT(*) FROM mcp_tools WHERE tool_name = ANY(:names)"),
                {"names": tool_names},
            )
            return result.scalar_one()
    finally:
        await engine.dispose()


if __name__ == "__main__":
    count = asyncio.run(seed())
    print(f"mcp_tools rows: {count}")
