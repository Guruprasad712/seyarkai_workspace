from fastmcp import FastMCP

from app.knowledge.retrievers import FakeRetriever

mcp = FastMCP("knowledge")
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
