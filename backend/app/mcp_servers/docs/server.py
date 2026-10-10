"""Docs MCP server — generate_document tool.

Creates a Google Doc from Markdown content using keyless impersonation of
DOCS_SERVICE_ACCOUNT_EMAIL, then shares it with DOCS_SHARE_WITH as reader.

Fallback: when Docs credentials are unavailable or the API call fails, renders
the content as a minimal HTML file stored under backend/artifacts/ and returns
a local URL.
"""
from __future__ import annotations

import asyncio
import re
import uuid
from html import escape
from pathlib import Path

from fastmcp import FastMCP

from app.core.config import settings

mcp = FastMCP("docs")

# Artifacts directory: backend/artifacts/  (created at import time)
_ARTIFACTS_DIR = Path(__file__).resolve().parents[3] / "artifacts"
_ARTIFACTS_DIR.mkdir(exist_ok=True)


# ── HTML conversion (fallback path) ─────────────────────────────────────────

def _md_to_html(title: str, content_markdown: str) -> str:
    """Convert Markdown to a minimal HTML5 document."""
    body_html = _render_md_body(content_markdown)
    return (
        "<!doctype html>\n"
        "<html lang=\"en\">\n"
        "<head>\n"
        "  <meta charset=\"utf-8\">\n"
        "  <meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">\n"
        f"  <title>{escape(title)}</title>\n"
        "  <style>body{font-family:system-ui,sans-serif;max-width:48rem;margin:2rem auto;padding:0 1rem}"
        "  pre{background:#f4f4f4;padding:1rem;border-radius:4px;overflow-x:auto}</style>\n"
        "</head>\n"
        "<body>\n"
        f"<h1>{escape(title)}</h1>\n"
        f"{body_html}\n"
        "</body>\n"
        "</html>\n"
    )


def _render_md_body(md: str) -> str:
    """Convert Markdown body to HTML without external dependencies."""
    lines = md.splitlines()
    out: list[str] = []
    i = 0
    in_code_block = False
    code_lines: list[str] = []
    in_ul = False
    in_ol = False

    def _close_lists():
        nonlocal in_ul, in_ol
        if in_ul:
            out.append("</ul>")
            in_ul = False
        if in_ol:
            out.append("</ol>")
            in_ol = False

    while i < len(lines):
        line = lines[i]

        # Fenced code block
        if line.strip().startswith("```"):
            if in_code_block:
                out.append("<pre><code>" + escape("\n".join(code_lines)) + "</code></pre>")
                code_lines = []
                in_code_block = False
            else:
                _close_lists()
                in_code_block = True
            i += 1
            continue

        if in_code_block:
            code_lines.append(line)
            i += 1
            continue

        # Headings
        m = re.match(r"^(#{1,6})\s+(.*)", line)
        if m:
            _close_lists()
            level = len(m.group(1))
            text = _inline_md(m.group(2))
            out.append(f"<h{level}>{text}</h{level}>")
            i += 1
            continue

        # Unordered list
        m = re.match(r"^[-*]\s+(.*)", line)
        if m:
            if in_ol:
                out.append("</ol>")
                in_ol = False
            if not in_ul:
                out.append("<ul>")
                in_ul = True
            out.append(f"<li>{_inline_md(m.group(1))}</li>")
            i += 1
            continue

        # Ordered list
        m = re.match(r"^\d+\.\s+(.*)", line)
        if m:
            if in_ul:
                out.append("</ul>")
                in_ul = False
            if not in_ol:
                out.append("<ol>")
                in_ol = True
            out.append(f"<li>{_inline_md(m.group(1))}</li>")
            i += 1
            continue

        # Blank line — close any open list, paragraph break
        if line.strip() == "":
            _close_lists()
            out.append("")
            i += 1
            continue

        # Regular paragraph
        _close_lists()
        out.append(f"<p>{_inline_md(line)}</p>")
        i += 1

    _close_lists()
    if in_code_block and code_lines:
        out.append("<pre><code>" + escape("\n".join(code_lines)) + "</code></pre>")

    return "\n".join(out)


def _inline_md(text: str) -> str:
    """Convert inline Markdown (bold, italic, code) to HTML."""
    # Inline code: `code`
    text = re.sub(r"`([^`]+)`", lambda m: f"<code>{escape(m.group(1))}</code>", text)
    # Bold: **text** or __text__
    text = re.sub(r"\*\*(.+?)\*\*|__(.+?)__",
                  lambda m: f"<strong>{m.group(1) or m.group(2)}</strong>", text)
    # Italic: *text* or _text_ (single, not preceded by another * or _)
    text = re.sub(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)|(?<!_)_(?!_)(.+?)(?<!_)_(?!_)",
                  lambda m: f"<em>{m.group(1) or m.group(2)}</em>", text)
    # Escape remaining HTML in plain text portions (already escaped above for code)
    # We need to escape only the parts that aren't already tags
    return text


# ── Google Docs conversion ───────────────────────────────────────────────────

def _md_to_docs_requests(content_markdown: str) -> list[dict]:
    """Convert Markdown to a list of Google Docs API batchUpdate requests.

    Inserts all text first, then applies styles. Uses index tracking to build
    correct index ranges for style requests.
    """
    lines = content_markdown.splitlines(keepends=True)
    requests: list[dict] = []

    # Google Docs batchUpdate: insertText requests build the doc from the end
    # to keep indices stable, OR we insert sequentially and track offsets.
    # Simplest correct approach: build one insertText per "block", track cursor.
    # Initial doc has 1 character (newline at index 0); insertions go at index 1.

    cursor = 1  # insertions happen after the initial \n
    plain_lines: list[tuple[int, int, str]] = []  # (start, end, style) per block

    # First pass: insert all text, track positions
    insert_requests: list[dict] = []
    style_requests: list[dict] = []

    in_code_block = False
    code_buffer: list[str] = []
    code_start: int = 0

    for line in lines:
        stripped = line.rstrip("\n")

        if stripped.strip().startswith("```"):
            if in_code_block:
                # Close code block — insert accumulated code + trailing newline
                code_text = "\n".join(code_buffer) + "\n"
                insert_requests.append({
                    "insertText": {"location": {"index": cursor}, "text": code_text}
                })
                block_end = cursor + len(code_text)
                # Apply monospace (Courier New) to code block
                style_requests.append({
                    "updateTextStyle": {
                        "range": {"startIndex": cursor, "endIndex": block_end},
                        "textStyle": {"weightedFontFamily": {"fontFamily": "Courier New"}},
                        "fields": "weightedFontFamily",
                    }
                })
                cursor = block_end
                code_buffer = []
                in_code_block = False
            else:
                in_code_block = True
            continue

        if in_code_block:
            code_buffer.append(stripped)
            continue

        # All text blocks end with a newline in Docs
        text = stripped + "\n"
        start = cursor

        insert_requests.append({
            "insertText": {"location": {"index": cursor}, "text": text}
        })
        cursor += len(text)
        end = cursor

        # Detect heading
        m_h = re.match(r"^(#{1,6})\s+(.*)", stripped)
        if m_h:
            level = len(m_h.group(1))
            named_style = f"HEADING_{level}"
            style_requests.append({
                "updateParagraphStyle": {
                    "range": {"startIndex": start, "endIndex": end},
                    "paragraphStyle": {"namedStyleType": named_style},
                    "fields": "namedStyleType",
                }
            })
            continue

        # Detect bullet list
        m_ul = re.match(r"^[-*]\s+(.*)", stripped)
        if m_ul:
            style_requests.append({
                "createParagraphBullets": {
                    "range": {"startIndex": start, "endIndex": end - 1},
                    "bulletPreset": "BULLET_DISC_CIRCLE_SQUARE",
                }
            })
            continue

        # Detect ordered list
        m_ol = re.match(r"^\d+\.\s+(.*)", stripped)
        if m_ol:
            style_requests.append({
                "createParagraphBullets": {
                    "range": {"startIndex": start, "endIndex": end - 1},
                    "bulletPreset": "NUMBERED_DECIMAL_ALPHA_ROMAN",
                }
            })
            continue

    # Handle unclosed code block
    if in_code_block and code_buffer:
        code_text = "\n".join(code_buffer) + "\n"
        insert_requests.append({
            "insertText": {"location": {"index": cursor}, "text": code_text}
        })
        block_end = cursor + len(code_text)
        style_requests.append({
            "updateTextStyle": {
                "range": {"startIndex": cursor, "endIndex": block_end},
                "textStyle": {"weightedFontFamily": {"fontFamily": "Courier New"}},
                "fields": "weightedFontFamily",
            }
        })

    # Order matters: insertText first, then styles
    return insert_requests + style_requests


# ── Google Docs API (sync, runs in thread) ───────────────────────────────────

# Module-level alias so tests can patch app.mcp_servers.docs.server.gapi_build
try:
    from googleapiclient.discovery import build as gapi_build
except ImportError:
    gapi_build = None  # type: ignore[assignment]


def _create_google_doc(title: str, content_markdown: str) -> dict:
    """Create a Google Doc via keyless impersonation of DOCS_SERVICE_ACCOUNT_EMAIL."""
    import google.auth
    from google.auth.impersonated_credentials import Credentials as ImpersonatedCredentials

    scopes = [
        "https://www.googleapis.com/auth/documents",
        "https://www.googleapis.com/auth/drive.file",
    ]

    base_creds, _ = google.auth.default(scopes=scopes)
    creds = ImpersonatedCredentials(
        source_credentials=base_creds,
        target_principal=settings.DOCS_SERVICE_ACCOUNT_EMAIL,
        target_scopes=scopes,
        lifetime=3600,
    )

    # gapi_build is the module-level alias; patching srv.gapi_build in tests works
    # because Python function bodies look up globals at call time.
    docs = gapi_build("docs", "v1", credentials=creds)
    doc = docs.documents().create(body={"title": title}).execute()
    doc_id = doc["documentId"]

    batch_requests = _md_to_docs_requests(content_markdown)
    if batch_requests:
        docs.documents().batchUpdate(
            documentId=doc_id,
            body={"requests": batch_requests},
        ).execute()

    if settings.DOCS_SHARE_WITH:
        drive = gapi_build("drive", "v3", credentials=creds)
        drive.permissions().create(
            fileId=doc_id,
            body={
                "type": "user",
                "role": "reader",
                "emailAddress": settings.DOCS_SHARE_WITH,
            },
            sendNotificationEmail=False,
        ).execute()

    return {
        "document_id": doc_id,
        "url": f"https://docs.google.com/document/d/{doc_id}/edit",
    }


# ── HTML fallback ────────────────────────────────────────────────────────────

def _html_fallback(title: str, content_markdown: str) -> dict:
    """Render content as a local HTML file and return its URL."""
    artifact_id = str(uuid.uuid4())
    filename = f"{artifact_id}.html"
    html = _md_to_html(title, content_markdown)
    (_ARTIFACTS_DIR / filename).write_text(html, encoding="utf-8")
    url = f"{settings.API_BASE_URL.rstrip('/')}/artifacts/{filename}"
    return {"document_id": f"html-{artifact_id}", "url": url}


# ── Tool ─────────────────────────────────────────────────────────────────────

@mcp.tool()
async def generate_document(title: str, content_markdown: str) -> dict:
    """Create a Google Doc from Markdown content and share it as a reader link.

    title is the document title.
    content_markdown is the document body in Markdown format.
    Returns {document_id, url} where url is a shareable link to the document.
    """
    if not settings.DOCS_SERVICE_ACCOUNT_EMAIL or not settings.GOOGLE_CLOUD_PROJECT:
        return await asyncio.to_thread(_html_fallback, title, content_markdown)
    try:
        return await asyncio.to_thread(_create_google_doc, title, content_markdown)
    except Exception:
        return await asyncio.to_thread(_html_fallback, title, content_markdown)
