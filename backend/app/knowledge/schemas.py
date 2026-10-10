from __future__ import annotations

from datetime import datetime, timezone

from pydantic import BaseModel

from app.knowledge.models import KnowledgeDocument
from app.knowledge.retrievers import compute_freshness


class KnowledgeDocumentIn(BaseModel):
    title: str
    content: str
    source: str
    last_verified_at: datetime | None = None


class KnowledgeDocumentOut(BaseModel):
    id: str
    title: str
    content: str
    source: str
    last_verified_at: datetime
    verified_by: str | None
    external_id: str | None
    age_days: int
    freshness: str
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_orm(
        cls,
        doc: KnowledgeDocument,
        ageing_days: int,
        stale_days: int,
    ) -> "KnowledgeDocumentOut":
        lv = doc.last_verified_at
        if lv.tzinfo is None:
            lv = lv.replace(tzinfo=timezone.utc)
        age_days = (datetime.now(timezone.utc) - lv).days
        return cls(
            id=str(doc.id),
            title=doc.title,
            content=doc.content,
            source=doc.source,
            last_verified_at=lv,
            verified_by=str(doc.verified_by) if doc.verified_by else None,
            external_id=doc.external_id,
            age_days=age_days,
            freshness=compute_freshness(age_days, ageing_days, stale_days),
            created_at=doc.created_at,
            updated_at=doc.updated_at,
        )
