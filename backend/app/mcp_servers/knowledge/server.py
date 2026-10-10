from fastmcp import FastMCP

from app.core.config import settings
from app.core.db import AsyncSessionLocal
from app.knowledge.retrievers import FakeRetriever, VertexSearchRetriever

mcp = FastMCP("knowledge")

if settings.VERTEX_SEARCH_DATA_STORE_ID:
    _retriever = VertexSearchRetriever(
        db_session_factory=AsyncSessionLocal,
        project=settings.GOOGLE_CLOUD_PROJECT,
        location=settings.VERTEX_SEARCH_LOCATION,
        data_store_id=settings.VERTEX_SEARCH_DATA_STORE_ID,
        ageing_days=settings.KNOWLEDGE_AGEING_DAYS,
        stale_days=settings.KNOWLEDGE_STALE_DAYS,
    )
else:
    _retriever = FakeRetriever()


@mcp.tool()
async def knowledge_search(query: str, top_k: int = 5) -> dict:
    """Search Company Brain for documents relevant to the query.
    query is free-text describing the information needed, not a file name."""
    hits = await _retriever.search(query, top_k)
    return {
        "results": [
            {**vars(h), "last_verified_at": h.last_verified_at.isoformat()}
            for h in hits
        ]
    }
