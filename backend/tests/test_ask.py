"""Tests for POST /executions/{id}/ask — offline (LLM call is mocked)."""
from __future__ import annotations

import contextlib
import uuid
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.security import create_access_token, hash_password


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


def _fake_run_stage(answer: str):
    """Return an async generator that immediately yields stage.stream_end."""
    async def _gen(*args, **kwargs):
        yield {
            "event_type": "stage.stream_end",
            "payload": {"final_text": answer, "total_tokens": {}},
        }
    return _gen


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture()
async def auth_headers_ask(test_db_url: str):
    user_id = str(uuid.uuid4())
    async with _test_db(test_db_url) as db:
        await db.execute(
            text(
                "INSERT INTO users (id, email, name, hashed_password, role, status, created_at, updated_at) "
                "VALUES (:id, :email, :name, :hp, 'member', 'active', now(), now())"
            ),
            {
                "id": user_id,
                "email": f"ask_test_{user_id[:8]}@example.com",
                "name": "Ask Test",
                "hp": hash_password("pw"),
            },
        )
        await db.commit()

    token = create_access_token(user_id, "member")
    yield {"Authorization": f"Bearer {token}", "_user_id": user_id}

    async with _test_db(test_db_url) as db:
        await db.execute(text("DELETE FROM users WHERE id = :uid"), {"uid": user_id})
        await db.commit()


@pytest_asyncio.fixture()
async def execution_with_stage(test_db_url: str, auth_headers_ask):
    """Running execution with one stage, current_stage_id set."""
    user_id = auth_headers_ask["_user_id"]
    agent_id = str(uuid.uuid4())
    version_id = str(uuid.uuid4())
    project_id = str(uuid.uuid4())
    wi_id = str(uuid.uuid4())
    policy_id = str(uuid.uuid4())
    stage_id = str(uuid.uuid4())
    execution_id = str(uuid.uuid4())

    async with _test_db(test_db_url) as db:
        seq = (await db.execute(text("SELECT nextval('agent_code_seq')"))).scalar_one()
        await db.execute(
            text(
                "INSERT INTO agents (id, agent_code, name, description, role_purpose, status, created_at, updated_at) "
                "VALUES (:id, :code, :name, 'desc', 'purpose', 'active', now(), now())"
            ),
            {"id": agent_id, "code": f"agent-{seq:04d}", "name": f"Ask Agent {agent_id[:8]}"},
        )
        await db.execute(
            text(
                "INSERT INTO agent_versions (id, agent_id, version, instructions, capabilities, status, created_at, updated_at) "
                "VALUES (:id, :aid, '1.0', 'You are a procurement expert.', CAST(:caps AS jsonb), 'published', now(), now())"
            ),
            {"id": version_id, "aid": agent_id, "caps": '[{"name":"cap","description":"d"}]'},
        )
        await db.execute(
            text(
                "INSERT INTO projects (id, name, description, status, created_by, created_at, updated_at) "
                "VALUES (:id, :name, 'desc', 'active', :uid, now(), now())"
            ),
            {"id": project_id, "name": f"Ask Project {project_id[:8]}", "uid": user_id},
        )
        await db.execute(
            text(
                "INSERT INTO work_items (id, project_id, name, objective, description, expected_outcome, status, created_by, created_at, updated_at) "
                "VALUES (:id, :pid, :name, 'obj', 'desc', 'outcome', 'in_progress', :uid, now(), now())"
            ),
            {"id": wi_id, "pid": project_id, "name": f"WI {wi_id[:8]}", "uid": user_id},
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
                "VALUES (:id, :pid, 1, 'Stage 1', 'Write a report', 'Report', :vid, now(), now())"
            ),
            {"id": stage_id, "pid": policy_id, "vid": version_id},
        )
        await db.execute(
            text(
                "INSERT INTO executions (id, work_item_id, policy_id, execution_number, status, current_stage_id, created_at, updated_at) "
                "VALUES (:id, :wid, :pid, 1, 'running', :sid, now(), now())"
            ),
            {"id": execution_id, "wid": wi_id, "pid": policy_id, "sid": stage_id},
        )
        await db.commit()

    yield {
        "execution_id": execution_id,
        "stage_id": stage_id,
        "version_id": version_id,
        "user_id": user_id,
        "wi_id": wi_id,
        "policy_id": policy_id,
        "project_id": project_id,
        "agent_id": agent_id,
    }

    async with _test_db(test_db_url) as db:
        await db.execute(text("DELETE FROM execution_events WHERE execution_id = :eid"), {"eid": execution_id})
        await db.execute(text("DELETE FROM messages WHERE execution_id = :eid"), {"eid": execution_id})
        await db.execute(text("DELETE FROM executions WHERE id = :eid"), {"eid": execution_id})
        await db.execute(text("DELETE FROM policy_stages WHERE policy_id = :pid"), {"pid": policy_id})
        await db.execute(text("DELETE FROM policies WHERE id = :pid"), {"pid": policy_id})
        await db.execute(text("DELETE FROM work_item_workers WHERE work_item_id = :wid"), {"wid": wi_id})
        await db.execute(text("DELETE FROM work_items WHERE id = :wid"), {"wid": wi_id})
        await db.execute(text("DELETE FROM projects WHERE id = :pid"), {"pid": project_id})
        await db.execute(text("DELETE FROM agent_versions WHERE id = :vid"), {"vid": version_id})
        await db.execute(text("DELETE FROM agents WHERE id = :aid"), {"aid": agent_id})
        await db.execute(text("DELETE FROM users WHERE id = :uid"), {"uid": user_id})
        await db.commit()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_ask_returns_answer(
    async_client: AsyncClient, auth_headers_ask, execution_with_stage
):
    """Happy path: answer is returned with Q and A message IDs."""
    eid = execution_with_stage["execution_id"]
    with patch("app.executions.router.run_stage", side_effect=_fake_run_stage("The answer is 42.")):
        r = await async_client.post(
            f"/executions/{eid}/ask",
            json={"question": "What is the answer?"},
            headers=auth_headers_ask,
        )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["answer"] == "The answer is 42."
    assert "question_message_id" in body
    assert "answer_message_id" in body
    assert len(body["question_message_id"]) == 36
    assert len(body["answer_message_id"]) == 36


@pytest.mark.asyncio
async def test_ask_persists_messages(
    async_client: AsyncClient, auth_headers_ask, execution_with_stage, test_db_url: str
):
    """Q and A are stored in messages with the correct types."""
    eid = execution_with_stage["execution_id"]
    with patch("app.executions.router.run_stage", side_effect=_fake_run_stage("Answer text")):
        r = await async_client.post(
            f"/executions/{eid}/ask",
            json={"question": "My question"},
            headers=auth_headers_ask,
        )
    assert r.status_code == 200, r.text
    body = r.json()

    async with _test_db(test_db_url) as db:
        result = await db.execute(
            text("SELECT message_type, content, sender_type FROM messages WHERE execution_id = :eid ORDER BY created_at"),
            {"eid": eid},
        )
        rows = result.fetchall()

    types = [(r[0], r[2]) for r in rows]
    assert ("question", "human") in types
    assert ("answer", "agent") in types

    contents = [r[1] for r in rows]
    assert "My question" in contents
    assert "Answer text" in contents


@pytest.mark.asyncio
async def test_ask_emits_executor_response_event(
    async_client: AsyncClient, auth_headers_ask, execution_with_stage, test_db_url: str
):
    """executor.response event is emitted."""
    eid = execution_with_stage["execution_id"]
    with patch("app.executions.router.run_stage", side_effect=_fake_run_stage("Some answer")):
        r = await async_client.post(
            f"/executions/{eid}/ask",
            json={"question": "Event test?"},
            headers=auth_headers_ask,
        )
    assert r.status_code == 200, r.text

    async with _test_db(test_db_url) as db:
        result = await db.execute(
            text("SELECT event_type FROM execution_events WHERE execution_id = :eid"),
            {"eid": eid},
        )
        event_types = [r[0] for r in result.fetchall()]
    assert "executor.response" in event_types


@pytest.mark.asyncio
async def test_ask_does_not_change_execution_status(
    async_client: AsyncClient, auth_headers_ask, execution_with_stage, test_db_url: str
):
    """Execution stays in 'running' after ask."""
    eid = execution_with_stage["execution_id"]
    with patch("app.executions.router.run_stage", side_effect=_fake_run_stage("ok")):
        r = await async_client.post(
            f"/executions/{eid}/ask",
            json={"question": "Status check?"},
            headers=auth_headers_ask,
        )
    assert r.status_code == 200, r.text

    async with _test_db(test_db_url) as db:
        result = await db.execute(
            text("SELECT status FROM executions WHERE id = :eid"), {"eid": eid}
        )
        status = result.scalar_one()
    assert status == "running"


@pytest.mark.asyncio
async def test_ask_404_unknown_execution(
    async_client: AsyncClient, auth_headers_ask
):
    r = await async_client.post(
        f"/executions/{uuid.uuid4()}/ask",
        json={"question": "hello"},
        headers=auth_headers_ask,
    )
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_ask_422_blank_question(
    async_client: AsyncClient, auth_headers_ask, execution_with_stage
):
    eid = execution_with_stage["execution_id"]
    r = await async_client.post(
        f"/executions/{eid}/ask",
        json={"question": "   "},
        headers=auth_headers_ask,
    )
    assert r.status_code == 422
    assert r.json()["detail"]["error"] == "question_empty"


@pytest.mark.asyncio
async def test_ask_422_no_stage_context(
    async_client: AsyncClient, auth_headers_ask, execution_with_stage, test_db_url: str
):
    """422 when current_stage_id is cleared and no stage outputs exist."""
    eid = execution_with_stage["execution_id"]
    # Clear current_stage_id so no stage context is available
    async with _test_db(test_db_url) as db:
        await db.execute(
            text("UPDATE executions SET current_stage_id = NULL WHERE id = :eid"),
            {"eid": eid},
        )
        await db.commit()

    r = await async_client.post(
        f"/executions/{eid}/ask",
        json={"question": "No context?"},
        headers=auth_headers_ask,
    )
    assert r.status_code == 422
    assert r.json()["detail"]["error"] == "no_stage_context"


@pytest.mark.asyncio
async def test_ask_502_when_model_fails(
    async_client: AsyncClient, auth_headers_ask, execution_with_stage
):
    """502 when the LLM call throws StageError."""
    from app.runtime import StageError

    async def _failing_gen(*args, **kwargs):
        raise StageError("model error")
        yield  # makes it an async generator

    eid = execution_with_stage["execution_id"]
    with patch("app.executions.router.run_stage", side_effect=_failing_gen):
        r = await async_client.post(
            f"/executions/{eid}/ask",
            json={"question": "Will this fail?"},
            headers=auth_headers_ask,
        )
    assert r.status_code == 502
    assert r.json()["detail"]["error"] == "model_error"
