"""Tests for the docs MCP server — generate_document tool.

Covers:
- In-process via fastmcp.Client(mcp): return shape {document_id, url}
- HTML fallback when SA email is not set
- HTML fallback when the Docs API raises
- HTML file is actually created on disk
- Share call is made with the right email
- Subprocess smoke test (integration marker): tool list includes generate_document
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastmcp import Client

import app.mcp_servers.docs.server as srv
from app.mcp_servers.docs.server import _html_fallback, _md_to_html


# ── helpers ──────────────────────────────────────────────────────────────────

def _mock_docs_api(doc_id: str = "fake-doc-id") -> MagicMock:
    """Return a mock that satisfies the google-api-python-client call chain."""
    mock_docs_service = MagicMock()
    mock_docs_service.documents().create().execute.return_value = {"documentId": doc_id}
    mock_docs_service.documents().batchUpdate().execute.return_value = {}

    mock_drive_service = MagicMock()
    mock_drive_service.permissions().create().execute.return_value = {}

    def _build_side_effect(service, version, credentials=None):
        if service == "docs":
            return mock_docs_service
        return mock_drive_service

    return _build_side_effect, mock_drive_service


# ── offline tests ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_generate_document_returns_doc_id_and_url(monkeypatch):
    """When Docs API succeeds, structured_content has document_id and url."""
    monkeypatch.setattr(srv.settings, "DOCS_SERVICE_ACCOUNT_EMAIL", "sa@example.iam.gserviceaccount.com")
    monkeypatch.setattr(srv.settings, "GOOGLE_CLOUD_PROJECT", "test-project")

    _build_fn, _ = _mock_docs_api("fake-doc-id")

    with (
        patch("app.mcp_servers.docs.server._create_google_doc",
              return_value={"document_id": "fake-doc-id",
                            "url": "https://docs.google.com/document/d/fake-doc-id/edit"}),
    ):
        async with Client(srv.mcp) as client:
            result = await client.call_tool(
                "generate_document",
                {"title": "Test Doc", "content_markdown": "# Hello\n\nWorld"},
            )

    sc = result.structured_content
    assert sc is not None
    assert sc["document_id"] == "fake-doc-id"
    assert "docs.google.com" in sc["url"]


@pytest.mark.asyncio
async def test_generate_document_fallback_when_no_sa_email(monkeypatch):
    """When DOCS_SERVICE_ACCOUNT_EMAIL is empty, tool falls back to HTML inline."""
    monkeypatch.setattr(srv.settings, "DOCS_SERVICE_ACCOUNT_EMAIL", "")

    async with Client(srv.mcp) as client:
        result = await client.call_tool(
            "generate_document",
            {"title": "Fallback Doc", "content_markdown": "# Fallback\n\nContent"},
        )

    sc = result.structured_content
    assert sc["document_id"].startswith("html-")
    # html_content is returned inline; no url or filesystem write
    assert "html_content" in sc
    assert "Fallback Doc" in sc["html_content"]


@pytest.mark.asyncio
async def test_generate_document_fallback_on_api_error(monkeypatch):
    """When the Docs API raises, the tool falls back to HTML inline."""
    monkeypatch.setattr(srv.settings, "DOCS_SERVICE_ACCOUNT_EMAIL", "sa@example.iam.gserviceaccount.com")
    monkeypatch.setattr(srv.settings, "GOOGLE_CLOUD_PROJECT", "test-project")

    with patch("app.mcp_servers.docs.server._create_google_doc",
               side_effect=Exception("API error")):
        async with Client(srv.mcp) as client:
            result = await client.call_tool(
                "generate_document",
                {"title": "Error Doc", "content_markdown": "body"},
            )

    sc = result.structured_content
    assert sc["document_id"].startswith("html-")
    assert "html_content" in sc


@pytest.mark.asyncio
async def test_generate_document_calls_share(monkeypatch):
    """When DOCS_SHARE_WITH is set, drive.permissions().create() is called."""
    monkeypatch.setattr(srv.settings, "DOCS_SERVICE_ACCOUNT_EMAIL", "sa@example.iam.gserviceaccount.com")
    monkeypatch.setattr(srv.settings, "GOOGLE_CLOUD_PROJECT", "test-project")
    monkeypatch.setattr(srv.settings, "DOCS_SHARE_WITH", "reader@example.com")

    mock_drive = MagicMock()
    mock_docs = MagicMock()
    mock_docs.documents().create().execute.return_value = {"documentId": "doc-123"}
    mock_docs.documents().batchUpdate().execute.return_value = {}

    def _build(service, version, credentials=None):
        return mock_docs if service == "docs" else mock_drive

    with (
        patch("google.auth.default", return_value=(MagicMock(), "project")),
        patch("google.auth.impersonated_credentials.Credentials"),
        patch("app.mcp_servers.docs.server.gapi_build", side_effect=_build),
    ):
        srv._create_google_doc("My Doc", "# Hello")

    mock_drive.permissions().create.assert_called_once()
    call_kwargs = mock_drive.permissions().create.call_args
    body = call_kwargs[1]["body"] if call_kwargs[1] else call_kwargs[0][1]
    assert body["emailAddress"] == "reader@example.com"
    assert body["role"] == "reader"


def test_html_fallback_returns_content():
    """_html_fallback returns html_content inline (no filesystem write)."""
    result = _html_fallback("My Report", "# Section\n\nContent here.")

    assert result["document_id"].startswith("html-")
    assert "html_content" in result
    html = result["html_content"]
    assert "My Report" in html
    assert "Section" in html


def test_md_to_html_headings():
    html = _md_to_html("T", "# H1\n## H2\n### H3")
    assert "<h1>H1</h1>" in html
    assert "<h2>H2</h2>" in html
    assert "<h3>H3</h3>" in html


def test_md_to_html_bold_italic():
    html = _md_to_html("T", "**bold** and *italic*")
    assert "<strong>bold</strong>" in html
    assert "<em>italic</em>" in html


def test_md_to_html_code_block():
    html = _md_to_html("T", "```\nsome code\n```")
    assert "<pre><code>" in html
    assert "some code" in html


# ── integration test ──────────────────────────────────────────────────────────

@pytest.mark.integration
@pytest.mark.asyncio
async def test_subprocess_server_lists_tools():
    """Launch the docs server as a subprocess and confirm it lists generate_document."""
    from google.adk.tools import McpToolset
    from google.adk.tools.mcp_tool.mcp_session_manager import StdioConnectionParams
    from mcp import StdioServerParameters

    backend_dir = Path(__file__).resolve().parents[1]
    toolset = McpToolset(
        connection_params=StdioConnectionParams(
            server_params=StdioServerParameters(
                command=sys.executable,
                args=["-m", "app.mcp_servers.docs"],
                cwd=str(backend_dir),
                env={**os.environ},
            ),
            timeout=30.0,
        ),
    )
    try:
        tools = await toolset.get_tools()
        names = [t.name for t in tools]
        assert "generate_document" in names, f"Expected generate_document in {names}"
    finally:
        await toolset.close()
