from __future__ import annotations

import sys
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.auth.models import User
from app.core.config import settings
from app.core.db import AsyncSessionLocal, get_db
from app.knowledge.models import KnowledgeDocument
from app.knowledge.retrievers import VertexSearchRetriever
from app.knowledge.schemas import KnowledgeDocumentIn, KnowledgeDocumentOut, KnowledgeHitOut

router = APIRouter()


def _to_out(doc: KnowledgeDocument) -> KnowledgeDocumentOut:
    return KnowledgeDocumentOut.from_orm(
        doc, settings.KNOWLEDGE_AGEING_DAYS, settings.KNOWLEDGE_STALE_DAYS
    )


@router.get("/knowledge", response_model=list[KnowledgeDocumentOut])
async def list_knowledge(
    _: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(KnowledgeDocument).order_by(KnowledgeDocument.created_at.desc())
    )
    docs = list(result.scalars().all())
    return [_to_out(d) for d in docs]


@router.post("/knowledge", response_model=KnowledgeDocumentOut, status_code=status.HTTP_201_CREATED)
async def create_knowledge(
    body: KnowledgeDocumentIn,
    _: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    now = datetime.now(timezone.utc)
    doc = KnowledgeDocument(
        id=uuid.uuid4(),
        title=body.title,
        content=body.content,
        source=body.source,
        last_verified_at=body.last_verified_at or now,
        created_at=now,
        updated_at=now,
    )
    db.add(doc)
    await db.commit()
    await db.refresh(doc)

    # Best-effort index in Vertex AI Search (non-blocking)
    try:
        await _index_document(doc)
    except Exception as exc:
        print(f"[knowledge] Vertex index failed for {doc.id}: {exc}", file=sys.stderr)

    return _to_out(doc)


@router.post("/knowledge/{doc_id}/verify", response_model=KnowledgeDocumentOut)
async def verify_knowledge(
    doc_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(KnowledgeDocument).where(KnowledgeDocument.id == doc_id)
    )
    doc = result.scalar_one_or_none()
    if doc is None:
        raise HTTPException(status_code=404, detail="document not found")

    now = datetime.now(timezone.utc)
    doc.last_verified_at = now
    doc.verified_by = current_user.id
    doc.updated_at = now
    await db.commit()
    await db.refresh(doc)
    return _to_out(doc)


@router.get("/knowledge/search", response_model=list[KnowledgeHitOut])
async def search_knowledge(
    q: str = Query(..., min_length=1),
    top_k: int = Query(default=5, ge=1, le=20),
    _: User = Depends(get_current_user),
):
    if not settings.VERTEX_SEARCH_DATA_STORE_ID:
        return []
    retriever = VertexSearchRetriever(
        db_session_factory=AsyncSessionLocal,
        project=settings.GOOGLE_CLOUD_PROJECT,
        location=settings.VERTEX_SEARCH_LOCATION,
        data_store_id=settings.VERTEX_SEARCH_DATA_STORE_ID,
        ageing_days=settings.KNOWLEDGE_AGEING_DAYS,
        stale_days=settings.KNOWLEDGE_STALE_DAYS,
    )
    hits = await retriever.search(q, top_k)
    return [KnowledgeHitOut.from_hit(h) for h in hits]


async def _index_document(doc: KnowledgeDocument) -> None:
    """Best-effort import of a single document into Vertex AI Search."""
    if not settings.VERTEX_SEARCH_DATA_STORE_ID or not settings.GOOGLE_CLOUD_PROJECT:
        return

    import asyncio
    import json

    def _sync_import() -> None:
        import google.cloud.discoveryengine_v1 as de

        client = de.DocumentServiceClient()
        parent = (
            f"projects/{settings.GOOGLE_CLOUD_PROJECT}"
            f"/locations/{settings.VERTEX_SEARCH_LOCATION}"
            f"/collections/default_collection"
            f"/dataStores/{settings.VERTEX_SEARCH_DATA_STORE_ID}"
            f"/branches/default_branch"
        )
        document = de.Document(
            id=str(doc.id),
            json_data=json.dumps({
                "title": doc.title,
                "content": doc.content,
                "source": doc.source,
                "last_verified_at": doc.last_verified_at.isoformat(),
            }),
        )
        inline_source = de.ImportDocumentsRequest.InlineSource(documents=[document])
        request = de.ImportDocumentsRequest(
            parent=parent,
            inline_source=inline_source,
            reconciliation_mode=de.ImportDocumentsRequest.ReconciliationMode.INCREMENTAL,
        )
        operation = client.import_documents(request=request)
        operation.result(timeout=60)

    await asyncio.to_thread(_sync_import)
