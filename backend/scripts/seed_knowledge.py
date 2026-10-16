"""Seed the knowledge base with demo procurement policy documents.

Reads demo_corpus.json from the same directory, POSTs each document to
POST /knowledge (skipping any whose title already exists), then verifies
the documents appear in Vertex AI Search.

Usage (from backend/):
    python -m scripts.seed_knowledge --env local
    python -m scripts.seed_knowledge --env local --api-url http://localhost:8000
    python -m scripts.seed_knowledge --env local --token <bearer_token>

The script looks up a super_admin user in the database to mint a valid
bearer token. Ensure at least one super_admin exists (run seed_users first).
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.auth.models import User
from app.core.config import settings
from app.core.security import create_access_token

_CORPUS_PATH = Path(__file__).parent / "demo_corpus.json"


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Seed knowledge base with demo corpus")
    p.add_argument(
        "--env",
        default="local",
        choices=["local"],
        help="Environment profile (default: local → http://localhost:8000)",
    )
    p.add_argument("--api-url", default="", help="Override API base URL")
    p.add_argument("--token", default="", help="Bearer token (skips DB lookup)")
    return p.parse_args()


async def _get_admin_token(db_url: str) -> str:
    engine = create_async_engine(db_url, echo=False)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session:
            result = await session.execute(
                select(User).where(User.role == "super_admin").limit(1)
            )
            admin = result.scalar_one_or_none()
            if admin is None:
                print(
                    "ERROR: No super_admin user found in the database.\n"
                    "Run `python -m scripts.seed_users` first (with SEED_ADMIN_PASSWORD set).",
                    file=sys.stderr,
                )
                sys.exit(1)
            return create_access_token(str(admin.id), "super_admin")
    finally:
        await engine.dispose()


def _load_corpus() -> list[dict]:
    with open(_CORPUS_PATH, encoding="utf-8") as f:
        return json.load(f)


def _to_last_verified_at(age_days: int) -> str:
    dt = datetime.now(timezone.utc) - timedelta(days=age_days)
    return dt.isoformat()


def _seed_via_http(api_url: str, token: str, corpus: list[dict]) -> list[str]:
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    created_ids: list[str] = []

    with httpx.Client(base_url=api_url, timeout=30) as client:
        # Fetch existing titles for idempotency
        r = client.get("/knowledge", headers=headers)
        if r.status_code != 200:
            print(f"ERROR: GET /knowledge returned {r.status_code}: {r.text}", file=sys.stderr)
            sys.exit(1)
        existing_titles = {doc["title"] for doc in r.json()}

        for entry in corpus:
            title = entry["title"]
            if title in existing_titles:
                print(f"  [SKIP] {title} (already exists)")
                continue

            body = {
                "title": title,
                "content": entry["content"],
                "source": entry["source"],
                "last_verified_at": _to_last_verified_at(entry["age_days"]),
            }
            r = client.post("/knowledge", headers=headers, json=body)
            if r.status_code == 201:
                doc = r.json()
                created_ids.append(doc["id"])
                print(f"  [OK] {title} (id={doc['id'][:8]}…, freshness={doc['freshness']})")
            else:
                print(f"  [ERR] {title}: {r.status_code} {r.text}", file=sys.stderr)

    return created_ids


async def _verify_vertex(api_url: str, token: str) -> None:
    if not settings.VERTEX_SEARCH_DATA_STORE_ID:
        print("\nVertex AI Search not configured (VERTEX_SEARCH_DATA_STORE_ID is empty) — skipping search verification.")
        return

    print("\nVertex AI Search verification (may take a few seconds for indexing to propagate)…")
    with httpx.Client(base_url=api_url, timeout=30) as client:
        headers = {"Authorization": f"Bearer {token}"}
        r = client.get("/knowledge/search", headers=headers, params={"q": "supplier procurement policy", "top_k": 5})
        if r.status_code == 200:
            hits = r.json()
            if hits:
                print(f"  Search returned {len(hits)} hit(s) for 'supplier procurement policy':")
                for h in hits:
                    print(f"    - {h['title']} (freshness={h['freshness']}, age={h['age_days']}d)")
            else:
                print("  Search returned 0 hits — index may still be propagating. Try again in a minute.")
        else:
            print(f"  Search request failed: {r.status_code} {r.text}", file=sys.stderr)


async def main() -> None:
    args = _parse_args()

    api_url = args.api_url or ("http://localhost:8000" if args.env == "local" else "")
    if not api_url:
        print("ERROR: Could not determine API URL. Pass --api-url.", file=sys.stderr)
        sys.exit(1)

    token = args.token or await _get_admin_token(settings.DATABASE_URL)

    corpus = _load_corpus()
    print(f"Seeding {len(corpus)} document(s) to {api_url} …\n")

    created = _seed_via_http(api_url, token, corpus)
    print(f"\nDone — {len(created)} document(s) created.")

    await _verify_vertex(api_url, token)


if __name__ == "__main__":
    asyncio.run(main())
