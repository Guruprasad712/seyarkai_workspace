from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime


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
