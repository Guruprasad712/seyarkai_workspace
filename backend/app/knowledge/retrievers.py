from __future__ import annotations

import asyncio
import sys
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any


@dataclass
class KnowledgeHit:
    document_id: str
    title: str
    snippet: str
    score: float
    last_verified_at: datetime
    age_days: int
    freshness: str  # "fresh" | "ageing" | "stale"


class KnowledgeRetriever(ABC):
    @abstractmethod
    async def search(self, query: str, top_k: int) -> list[KnowledgeHit]: ...


class FakeRetriever(KnowledgeRetriever):
    def __init__(self, hits: list[KnowledgeHit] | None = None):
        self.hits: list[KnowledgeHit] = hits or []

    async def search(self, query: str, top_k: int) -> list[KnowledgeHit]:
        return self.hits[:top_k]


def compute_freshness(
    age_days: int,
    ageing_days: int = 90,
    stale_days: int = 180,
) -> str:
    if age_days <= ageing_days:
        return "fresh"
    if age_days <= stale_days:
        return "ageing"
    return "stale"


def build_injection_block(hits: list[KnowledgeHit]) -> str:
    if not hits:
        return ""
    lines = ["Company knowledge relevant to this stage:"]
    for i, h in enumerate(hits, start=1):
        label = h.freshness.upper()
        header = f"[{i}] {h.title} — last verified {h.age_days} days ago — {label}:"
        lines.append(header)
        if h.freshness == "stale":
            lines.append(
                "    may be outdated; state any reliance on it explicitly and "
                "recommend re-verification."
            )
        elif h.freshness == "ageing":
            lines.append("    verify before relying on this.")
        lines.append(f"    {h.snippet}")
    return "\n".join(lines)


class VertexSearchRetriever(KnowledgeRetriever):
    """Queries Vertex AI Search and resolves freshness from the database."""

    def __init__(
        self,
        db_session_factory: Any,
        project: str,
        location: str,
        data_store_id: str,
        ageing_days: int = 90,
        stale_days: int = 180,
    ) -> None:
        self._db_session_factory = db_session_factory
        self._project = project
        self._location = location
        self._data_store_id = data_store_id
        self._ageing_days = ageing_days
        self._stale_days = stale_days

    async def search(self, query: str, top_k: int = 5) -> list[KnowledgeHit]:
        if not self._data_store_id:
            return []

        try:
            results = await asyncio.to_thread(self._sync_search, query, top_k)
        except Exception as exc:
            print(f"[vertex_retriever] search failed: {exc}", file=sys.stderr)
            return []

        if not results:
            return []

        # Resolve freshness from DB (search index is not the source of truth)
        from sqlalchemy import select
        from app.knowledge.models import KnowledgeDocument

        import uuid as _uuid

        def _normalize_uuid(v: str) -> str | None:
            try:
                return str(_uuid.UUID(v))
            except ValueError:
                return None

        # Normalize IDs: Vertex strips hyphens; DB stores canonical hyphenated UUIDs
        id_map: dict[str, str] = {}  # vertex_id -> canonical_uuid
        for r in results:
            canonical = _normalize_uuid(r["id"])
            if canonical:
                id_map[r["id"]] = canonical

        if not id_map:
            return []
        async with self._db_session_factory() as db:
            rows = await db.execute(
                select(KnowledgeDocument).where(KnowledgeDocument.id.in_(list(id_map.values())))
            )
            docs = {str(doc.id): doc for doc in rows.scalars().all()}

        now = datetime.now(timezone.utc)
        hits: list[KnowledgeHit] = []
        for r in results:
            canonical = id_map.get(r["id"])
            doc = docs.get(canonical) if canonical else None
            if doc is None:
                continue
            lv = doc.last_verified_at
            if lv.tzinfo is None:
                lv = lv.replace(tzinfo=timezone.utc)
            age_days = (now - lv).days
            # Prefer Vertex snippet; fall back to DB content (first 800 chars)
            snippet = r["snippet"] or (doc.content[:800] if doc.content else "")
            hits.append(
                KnowledgeHit(
                    document_id=r["id"],
                    title=doc.title,
                    snippet=snippet,
                    score=r["score"],
                    last_verified_at=lv,
                    age_days=age_days,
                    freshness=compute_freshness(age_days, self._ageing_days, self._stale_days),
                )
            )
        return hits

    def _sync_search(self, query: str, top_k: int) -> list[dict]:
        import google.cloud.discoveryengine_v1 as de

        client = de.SearchServiceClient()
        serving_config = (
            f"projects/{self._project}/locations/{self._location}"
            f"/collections/default_collection/dataStores/{self._data_store_id}"
            f"/servingConfigs/default_config"
        )
        request = de.SearchRequest(
            serving_config=serving_config,
            query=query,
            page_size=top_k,
            content_search_spec=de.SearchRequest.ContentSearchSpec(
                snippet_spec=de.SearchRequest.ContentSearchSpec.SnippetSpec(
                    return_snippet=True,
                    max_snippet_count=3,
                ),
                extractive_content_spec=de.SearchRequest.ContentSearchSpec.ExtractiveContentSpec(
                    max_extractive_answers_count=1,
                    max_extractive_segments_count=2,
                ),
            ),
        )
        response = client.search(request)
        results = []
        for r in response.results:
            doc = r.document
            doc_id = doc.id if doc else r.id
            if not doc_id:
                continue
            snippet = ""
            if doc and doc.derived_struct_data:
                # Try snippets first
                snippets = doc.derived_struct_data.get("snippets", [])
                if snippets:
                    snippet = " … ".join(
                        s.get("snippet", "") for s in snippets if s.get("snippet")
                    )
                # Fall back to extractive answers
                if not snippet:
                    answers = doc.derived_struct_data.get("extractive_answers", [])
                    if answers:
                        snippet = answers[0].get("content", "")
                # Fall back to extractive segments
                if not snippet:
                    segments = doc.derived_struct_data.get("extractive_segments", [])
                    if segments:
                        snippet = segments[0].get("content", "")
            results.append({"id": doc_id, "snippet": snippet, "score": 0.0})
        return results
