"""Tests for the knowledge MCP server.

Covers:
- In-process client via fastmcp.Client(mcp): confirms dict return shape
  (structured_content = the dict itself, no 'result' wrapper)
- Subprocess smoke test (integration marker): launches the real server and
  lists its tools via McpToolset.get_tools()
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastmcp import Client

import app.mcp_servers.knowledge.server as srv
from app.knowledge.retrievers import FakeRetriever, KnowledgeHit


_HIT = KnowledgeHit(
    document_id="doc-1",
    title="Test Doc",
    snippet="snippet text",
    score=0.9,
    last_verified_at=datetime(2025, 1, 1, tzinfo=timezone.utc),
    age_days=10,
    freshness="fresh",
)


@pytest.fixture(autouse=True)
def fake_hits(monkeypatch):
    monkeypatch.setattr(srv, "_retriever", FakeRetriever(hits=[_HIT]))


async def test_dict_return_structured_content():
    """dict return → structured_content is the dict itself (no 'result' wrapper).

    This confirms FastMCP 4.0.10 behaviour: when a tool returns a dict,
    structured_content = that dict directly. The 'result' wrapper only appears
    for non-dict returns with x-fastmcp-wrap-result in the output_schema.
    """
    async with Client(srv.mcp) as client:
        result = await client.call_tool("knowledge_search", {"query": "test", "top_k": 1})

    # structured_content is the dict directly — not wrapped in {"result": ...}
    assert result.structured_content is not None
    assert "result" not in result.structured_content, (
        "Dict returns must NOT be wrapped in {'result': ...}"
    )
    assert result.structured_content["results"][0]["title"] == "Test Doc"

    # data mirrors structured_content (no output_schema, so data = structured_content)
    assert result.data["results"][0]["title"] == "Test Doc"

    # content[0].text is the string form
    assert "Test Doc" in result.content[0].text


async def test_no_hits(monkeypatch):
    monkeypatch.setattr(srv, "_retriever", FakeRetriever(hits=[]))
    async with Client(srv.mcp) as client:
        result = await client.call_tool("knowledge_search", {"query": "nothing", "top_k": 5})
    assert result.structured_content["results"] == []


async def test_top_k_limits_results(monkeypatch):
    many_hits = [
        KnowledgeHit(
            document_id=f"doc-{i}",
            title=f"Doc {i}",
            snippet="x",
            score=0.5,
            last_verified_at=datetime(2025, 1, 1, tzinfo=timezone.utc),
            age_days=1,
            freshness="fresh",
        )
        for i in range(10)
    ]
    monkeypatch.setattr(srv, "_retriever", FakeRetriever(hits=many_hits))
    async with Client(srv.mcp) as client:
        result = await client.call_tool("knowledge_search", {"query": "x", "top_k": 3})
    assert len(result.structured_content["results"]) == 3


@pytest.mark.integration
async def test_subprocess_server_lists_tools():
    """Launch the knowledge server as a subprocess and confirm it lists knowledge_search."""
    from google.adk.tools import McpToolset
    from google.adk.tools.mcp_tool.mcp_session_manager import StdioConnectionParams
    from mcp import StdioServerParameters

    backend_dir = Path(__file__).resolve().parents[1]
    toolset = McpToolset(
        connection_params=StdioConnectionParams(
            server_params=StdioServerParameters(
                command=sys.executable,
                args=["-m", "app.mcp_servers.knowledge"],
                cwd=str(backend_dir),
                env={**os.environ},
            ),
            timeout=30.0,
        ),
    )
    try:
        tools = await toolset.get_tools()
        names = [t.name for t in tools]
        assert "knowledge_search" in names, f"Expected knowledge_search in {names}"
    finally:
        await toolset.close()
