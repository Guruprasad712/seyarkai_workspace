"""Artifact serve endpoint tests — authenticated GET /artifacts/{id}."""
from __future__ import annotations

import contextlib
import uuid

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.security import create_access_token, hash_password
from app.mcp_servers.docs.server import _html_fallback


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

@contextlib.asynccontextmanager
async def _test_db(test_db_url: str):
    engine = create_async_engine(test_db_url, echo=False)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as db:
            yield db
    finally:
        await engine.dispose()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture()
async def artifact_fixture(test_db_url: str):
    """Seed minimal rows: user, project, work_item, agent, agent_version,
    policy, policy_stage, execution, artifact. Yield (user_id, artifact_id, html_content).
    Cleanup in reverse dependency order."""
    user_id = str(uuid.uuid4())
    project_id = str(uuid.uuid4())
    wi_id = str(uuid.uuid4())
    agent_id = str(uuid.uuid4())
    version_id = str(uuid.uuid4())
    policy_id = str(uuid.uuid4())
    stage_id = str(uuid.uuid4())
    execution_id = str(uuid.uuid4())
    artifact_id = str(uuid.uuid4())
    html_content = "<html><body><h1>Test Document</h1></body></html>"

    async with _test_db(test_db_url) as db:
        await db.execute(
            text(
                "INSERT INTO users (id, email, name, hashed_password, role, status, created_at, updated_at) "
                "VALUES (:id, :email, :name, :hp, 'reviewer', 'active', now(), now())"
            ),
            {"id": user_id, "email": f"art_{user_id[:8]}@example.com", "name": "Art User", "hp": hash_password("pw")},
        )
        await db.execute(
            text(
                "INSERT INTO projects (id, name, description, status, created_by, created_at, updated_at) "
                "VALUES (:id, :name, 'desc', 'active', :uid, now(), now())"
            ),
            {"id": project_id, "name": f"proj_{project_id[:8]}", "uid": user_id},
        )
        await db.execute(
            text(
                "INSERT INTO work_items (id, project_id, name, objective, description, expected_outcome, status, created_by, created_at, updated_at) "
                "VALUES (:id, :pid, 'WI', 'obj', 'desc', 'outcome', 'in_progress', :uid, now(), now())"
            ),
            {"id": wi_id, "pid": project_id, "uid": user_id},
        )
        seq = (await db.execute(text("SELECT nextval('agent_code_seq')"))).scalar_one()
        await db.execute(
            text(
                "INSERT INTO agents (id, agent_code, name, description, role_purpose, status, created_at, updated_at) "
                "VALUES (:id, :code, :name, 'desc', 'purpose', 'active', now(), now())"
            ),
            {"id": agent_id, "code": f"agent-{seq:04d}", "name": f"Art Agent {agent_id[:8]}"},
        )
        await db.execute(
            text(
                "INSERT INTO agent_versions (id, agent_id, version, instructions, capabilities, status, created_at, updated_at) "
                "VALUES (:id, :aid, '1.0', 'do stuff', CAST(:caps AS jsonb), 'published', now(), now())"
            ),
            {"id": version_id, "aid": agent_id, "caps": "[]"},
        )
        await db.execute(
            text(
                "INSERT INTO policies (id, work_item_id, version, status, generated_by, created_at, updated_at) "
                "VALUES (:id, :wid, 1, 'published', :uid, now(), now())"
            ),
            {"id": policy_id, "wid": wi_id, "uid": user_id},
        )
        await db.execute(
            text(
                "INSERT INTO policy_stages (id, policy_id, sequence, name, description, expected_output, agent_version_id, created_at, updated_at) "
                "VALUES (:id, :pid, 1, 'Stage 1', 'desc', 'output', :vid, now(), now())"
            ),
            {"id": stage_id, "pid": policy_id, "vid": version_id},
        )
        await db.execute(
            text(
                "INSERT INTO executions (id, work_item_id, policy_id, execution_number, status, created_at, updated_at) "
                "VALUES (:id, :wid, :pid, 1, 'completed', now(), now())"
            ),
            {"id": execution_id, "wid": wi_id, "pid": policy_id},
        )
        await db.execute(
            text(
                "INSERT INTO artifacts (id, execution_id, stage_id, name, type, url, html_content, created_at) "
                "VALUES (:id, :eid, :sid, 'Test Doc', 'html', :url, :html, now())"
            ),
            {
                "id": artifact_id,
                "eid": execution_id,
                "sid": stage_id,
                "url": f"/artifacts/{artifact_id}",
                "html": html_content,
            },
        )
        await db.commit()

    token = create_access_token(user_id, "reviewer")
    yield user_id, artifact_id, html_content, token, execution_id, stage_id

    async with _test_db(test_db_url) as db:
        await db.execute(text("DELETE FROM artifacts WHERE execution_id = :eid"), {"eid": execution_id})
        await db.execute(text("DELETE FROM executions WHERE id = :id"), {"id": execution_id})
        await db.execute(text("DELETE FROM policy_stages WHERE policy_id = :pid"), {"pid": policy_id})
        await db.execute(text("DELETE FROM policies WHERE id = :pid"), {"pid": policy_id})
        await db.execute(text("DELETE FROM agent_versions WHERE id = :vid"), {"vid": version_id})
        await db.execute(text("DELETE FROM agents WHERE id = :aid"), {"aid": agent_id})
        await db.execute(text("DELETE FROM work_items WHERE id = :wid"), {"wid": wi_id})
        await db.execute(text("DELETE FROM projects WHERE id = :pid"), {"pid": project_id})
        await db.execute(text("DELETE FROM users WHERE id = :uid"), {"uid": user_id})
        await db.commit()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_artifact_html_stored_in_db(async_client: AsyncClient, artifact_fixture):
    _, artifact_id, html_content, token, *_ = artifact_fixture
    r = await async_client.get(
        f"/artifacts/{artifact_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200
    assert html_content in r.text


@pytest.mark.asyncio
async def test_artifact_requires_auth(async_client: AsyncClient, artifact_fixture):
    _, artifact_id, *_ = artifact_fixture
    r = await async_client.get(f"/artifacts/{artifact_id}")
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_artifact_sandbox_header(async_client: AsyncClient, artifact_fixture):
    _, artifact_id, _, token, *_ = artifact_fixture
    r = await async_client.get(
        f"/artifacts/{artifact_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200
    assert r.headers.get("content-security-policy") == "sandbox"


@pytest.mark.asyncio
async def test_artifact_nosniff_header(async_client: AsyncClient, artifact_fixture):
    _, artifact_id, _, token, *_ = artifact_fixture
    r = await async_client.get(
        f"/artifacts/{artifact_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200
    assert r.headers.get("x-content-type-options") == "nosniff"


@pytest.mark.asyncio
async def test_artifact_missing(async_client: AsyncClient, artifact_fixture):
    _, _, _, token, *_ = artifact_fixture
    r = await async_client.get(
        f"/artifacts/{uuid.uuid4()}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_artifact_google_doc_not_served(
    async_client: AsyncClient, artifact_fixture, test_db_url: str
):
    """Artifact with type=google_doc → 404 from new endpoint."""
    user_id, _, _, token, execution_id, stage_id = artifact_fixture
    gdoc_id = str(uuid.uuid4())
    async with _test_db(test_db_url) as db:
        await db.execute(
            text(
                "INSERT INTO artifacts (id, execution_id, stage_id, name, type, url, created_at) "
                "VALUES (:id, :eid, :sid, 'GDoc', 'google_doc', 'https://docs.google.com/d/xyz/edit', now())"
            ),
            {"id": gdoc_id, "eid": execution_id, "sid": stage_id},
        )
        await db.commit()

    try:
        r = await async_client.get(
            f"/artifacts/{gdoc_id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 404
    finally:
        async with _test_db(test_db_url) as db:
            await db.execute(text("DELETE FROM artifacts WHERE id = :id"), {"id": gdoc_id})
            await db.commit()


def test_artifact_size_cap():
    """_html_fallback raises ValueError when markdown exceeds 800 KB."""
    big_md = "x" * (900 * 1024)
    with pytest.raises(ValueError, match="too large"):
        _html_fallback("Title", big_md)


@pytest.mark.asyncio
async def test_old_filename_path_returns_404(async_client: AsyncClient, artifact_fixture):
    """Old /artifacts/somefile.html path returns 404 (route removed)."""
    _, _, _, token, *_ = artifact_fixture
    r = await async_client.get(
        "/artifacts/somefile.html",
        headers={"Authorization": f"Bearer {token}"},
    )
    # The new route parses "somefile.html" as a UUID and fails to parse it → 422
    # OR it returns 404 because no such UUID exists. Either confirms the old FS handler is gone.
    assert r.status_code in (404, 422)


@pytest.mark.asyncio
async def test_html_content_absent_from_tool_result_event():
    """normalise() strips html_content from structured_result, puts it in _html_content."""
    from unittest.mock import MagicMock
    from app.runtime.normalise import normalise

    html = "<html><body>doc</body></html>"
    structured_content = {"document_id": "html-abc", "html_content": html}

    fn_resp = MagicMock()
    fn_resp.name = "generate_document"
    fn_resp.response = {
        "structuredContent": structured_content,
        "meta": {},
    }

    part = MagicMock()
    part.thought = None
    part.function_call = None
    part.function_response = fn_resp
    part.text = None

    content = MagicMock()
    content.parts = [part]

    event = MagicMock()
    event.partial = False
    event.content = content
    event.is_final_response.return_value = False

    results = normalise(event)
    assert len(results) == 1
    payload = results[0]["payload"]

    # html_content must not appear anywhere in the event payload summary
    assert "html_content" not in str(payload.get("summary", ""))
    # _html_content must be present so the engine can consume it
    assert payload.get("_html_content") == html
    # structured_result must not contain html_content
    sr = payload.get("structured_result", {})
    assert "html_content" not in sr
