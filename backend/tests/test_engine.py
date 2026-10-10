"""ExecutionEngine tests — all offline (no Vertex AI calls).

run_stage is patched so no ADK / Gemini involvement.
"""
from __future__ import annotations

import contextlib
import uuid
from unittest.mock import patch

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.security import create_access_token, hash_password
from app.executions.engine import ExecutionEngine


def _make_factory(test_db_url: str):
    engine = create_async_engine(test_db_url, echo=False)
    return async_sessionmaker(engine, expire_on_commit=False)


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


async def _happy_mock(*args, **kwargs):
    yield {"event_type": "tool.called", "payload": {"tool_name": "x", "arguments": {}}}
    yield {"event_type": "tool.result", "payload": {"tool_name": "x", "summary": "ok"}}
    yield {"event_type": "stage.stream_end", "payload": {"final_text": "result text", "total_tokens": {}}}


async def _no_output_mock(*args, **kwargs):
    yield {"event_type": "stage.stream_end", "payload": {"final_text": "result text", "total_tokens": {}}}


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture()
async def engine_setup(test_db_url: str):
    """
    Creates: user, project, work_item, agent+version, policy+stage+final_review
    checkpoint, and a queued Execution row. Yields a dict of all IDs.
    Cleans up in reverse dependency order.
    """
    user_id = str(uuid.uuid4())
    project_id = str(uuid.uuid4())
    wi_id = str(uuid.uuid4())
    agent_id = str(uuid.uuid4())
    version_id = str(uuid.uuid4())
    tool_id = str(uuid.uuid4())
    policy_id = str(uuid.uuid4())
    stage_id = str(uuid.uuid4())
    checkpoint_id = str(uuid.uuid4())
    execution_id = str(uuid.uuid4())

    async with _test_db(test_db_url) as db:
        # User
        await db.execute(
            text(
                "INSERT INTO users (id, email, name, hashed_password, role, status, created_at, updated_at) "
                "VALUES (:id, :email, 'Engine Test', :hp, 'member', 'active', now(), now())"
            ),
            {"id": user_id, "email": f"eng_{user_id[:8]}@example.com", "hp": hash_password("pw")},
        )
        # Project
        await db.execute(
            text(
                "INSERT INTO projects (id, name, description, status, created_by, created_at, updated_at) "
                "VALUES (:id, :name, 'desc', 'active', :uid, now(), now())"
            ),
            {"id": project_id, "name": f"Eng Project {project_id[:8]}", "uid": user_id},
        )
        # Work item
        await db.execute(
            text(
                "INSERT INTO work_items (id, project_id, name, objective, description, expected_outcome, status, created_by, created_at, updated_at) "
                "VALUES (:id, :pid, :name, 'test objective', 'test description', 'test outcome', 'in_progress', :uid, now(), now())"
            ),
            {"id": wi_id, "pid": project_id, "name": f"WI {wi_id[:8]}", "uid": user_id},
        )
        # Agent + version + tool
        seq = (await db.execute(text("SELECT nextval('agent_code_seq')"))).scalar_one()
        await db.execute(
            text(
                "INSERT INTO agents (id, agent_code, name, description, role_purpose, status, created_at, updated_at) "
                "VALUES (:id, :code, :name, 'desc', 'purpose', 'active', now(), now())"
            ),
            {"id": agent_id, "code": f"agent-{seq:04d}", "name": f"Eng Agent {agent_id[:8]}"},
        )
        await db.execute(
            text(
                "INSERT INTO mcp_tools (id, name, tool_name, server_key, description, status, created_at, updated_at) "
                "VALUES (:id, :name, :tool_name, 'knowledge', 'desc', 'active', now(), now()) "
                "ON CONFLICT (tool_name) DO UPDATE SET status='active'"
            ),
            {"id": tool_id, "name": f"EngTool {tool_id[:8]}", "tool_name": f"engtool_{tool_id[:8]}"},
        )
        result = await db.execute(
            text("SELECT id FROM mcp_tools WHERE tool_name = :tn"),
            {"tn": f"engtool_{tool_id[:8]}"},
        )
        tool_id = str(result.scalar_one())
        await db.execute(
            text(
                "INSERT INTO agent_versions (id, agent_id, version, instructions, capabilities, status, created_at, updated_at) "
                "VALUES (:id, :aid, '1.0', 'Do the task carefully', CAST(:caps AS jsonb), 'published', now(), now())"
            ),
            {"id": version_id, "aid": agent_id, "caps": '[{"name":"cap","description":"d"}]'},
        )
        await db.execute(
            text("INSERT INTO agent_version_tools (agent_version_id, mcp_tool_id) VALUES (:vid, :tid)"),
            {"vid": version_id, "tid": tool_id},
        )
        # Policy + stage + final_review checkpoint
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
                "VALUES (:id, :pid, 1, 'Stage 1', 'Do stage 1', 'Some output', :vid, now(), now())"
            ),
            {"id": stage_id, "pid": policy_id, "vid": version_id},
        )
        await db.execute(
            text(
                "INSERT INTO checkpoints (id, policy_id, stage_id, type, assigned_user_id, instruction, created_at, updated_at) "
                "VALUES (:id, :pid, NULL, 'final_review', :uid, 'Approve the result', now(), now())"
            ),
            {"id": checkpoint_id, "pid": policy_id, "uid": user_id},
        )
        # Queued execution
        await db.execute(
            text(
                "INSERT INTO executions (id, work_item_id, policy_id, execution_number, status, created_at, updated_at) "
                "VALUES (:id, :wid, :pid, 1, 'queued', now(), now())"
            ),
            {"id": execution_id, "wid": wi_id, "pid": policy_id},
        )
        await db.commit()

    yield {
        "user_id": user_id,
        "project_id": project_id,
        "work_item_id": wi_id,
        "agent_id": agent_id,
        "version_id": version_id,
        "tool_id": tool_id,
        "policy_id": policy_id,
        "stage_id": stage_id,
        "checkpoint_id": checkpoint_id,
        "execution_id": execution_id,
    }

    async with _test_db(test_db_url) as db:
        await db.execute(text("DELETE FROM execution_events WHERE execution_id = :eid"), {"eid": execution_id})
        await db.execute(text("DELETE FROM messages WHERE execution_id = :eid"), {"eid": execution_id})
        await db.execute(text("DELETE FROM executions WHERE id = :eid"), {"eid": execution_id})
        await db.execute(text("DELETE FROM checkpoints WHERE policy_id = :pid"), {"pid": policy_id})
        await db.execute(text("DELETE FROM policy_stages WHERE policy_id = :pid"), {"pid": policy_id})
        await db.execute(text("DELETE FROM policies WHERE id = :pid"), {"pid": policy_id})
        await db.execute(text("DELETE FROM work_items WHERE id = :wid"), {"wid": wi_id})
        await db.execute(text("DELETE FROM projects WHERE id = :pid"), {"pid": project_id})
        await db.execute(text("DELETE FROM agent_version_tools WHERE agent_version_id = :vid"), {"vid": version_id})
        await db.execute(text("DELETE FROM agent_versions WHERE id = :vid"), {"vid": version_id})
        await db.execute(text("DELETE FROM agents WHERE id = :aid"), {"aid": agent_id})
        await db.execute(text("DELETE FROM users WHERE id = :uid"), {"uid": user_id})
        await db.commit()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_engine_runs_queued_to_paused_at_checkpoint(engine_setup, test_db_url: str):
    exc_id = engine_setup["execution_id"]
    checkpoint_id = engine_setup["checkpoint_id"]

    with patch("app.executions.engine.run_stage", side_effect=_happy_mock):
        await ExecutionEngine(_make_factory(test_db_url)).run_execution(exc_id)

    async with _test_db(test_db_url) as db:
        result = await db.execute(
            text("SELECT status, blocking_checkpoint_id FROM executions WHERE id = :eid"),
            {"eid": exc_id},
        )
        row = result.one()
        assert row.status == "waiting_for_approval"
        assert str(row.blocking_checkpoint_id) == checkpoint_id

        result = await db.execute(
            text("SELECT event_type FROM execution_events WHERE execution_id = :eid ORDER BY created_at"),
            {"eid": exc_id},
        )
        event_types = [r.event_type for r in result.all()]

    assert "execution.started" in event_types
    assert "stage.started" in event_types
    assert "tool.called" in event_types
    assert "tool.result" in event_types
    assert "stage.completed" in event_types
    assert "checkpoint.triggered" in event_types
    assert "execution.paused" in event_types


@pytest.mark.asyncio
async def test_engine_emits_execution_started(engine_setup, test_db_url: str):
    exc_id = engine_setup["execution_id"]

    with patch("app.executions.engine.run_stage", side_effect=_no_output_mock):
        await ExecutionEngine(_make_factory(test_db_url)).run_execution(exc_id)

    async with _test_db(test_db_url) as db:
        result = await db.execute(
            text(
                "SELECT event_type, payload FROM execution_events "
                "WHERE execution_id = :eid ORDER BY created_at LIMIT 1"
            ),
            {"eid": exc_id},
        )
        row = result.one()

    assert row.event_type == "execution.started"
    assert row.payload.get("execution_number") == 1


@pytest.mark.asyncio
async def test_engine_emits_stage_started_and_completed(engine_setup, test_db_url: str):
    exc_id = engine_setup["execution_id"]

    with patch("app.executions.engine.run_stage", side_effect=_no_output_mock):
        await ExecutionEngine(_make_factory(test_db_url)).run_execution(exc_id)

    async with _test_db(test_db_url) as db:
        result = await db.execute(
            text(
                "SELECT event_type, payload FROM execution_events "
                "WHERE execution_id = :eid AND event_type IN ('stage.started', 'stage.completed') "
                "ORDER BY created_at"
            ),
            {"eid": exc_id},
        )
        rows = result.all()

    types = [r.event_type for r in rows]
    assert "stage.started" in types
    assert "stage.completed" in types
    started = next(r for r in rows if r.event_type == "stage.started")
    assert started.payload["sequence"] == 1
    assert started.payload["name"] == "Stage 1"


@pytest.mark.asyncio
async def test_engine_persists_stage_output_as_message(engine_setup, test_db_url: str):
    exc_id = engine_setup["execution_id"]
    stage_id = engine_setup["stage_id"]

    with patch("app.executions.engine.run_stage", side_effect=_no_output_mock):
        await ExecutionEngine(_make_factory(test_db_url)).run_execution(exc_id)

    async with _test_db(test_db_url) as db:
        result = await db.execute(
            text(
                "SELECT content, sender_type, message_type FROM messages "
                "WHERE execution_id = :eid AND sender_type = 'agent'"
            ),
            {"eid": exc_id},
        )
        row = result.one()

    assert row.content == "result text"
    assert row.sender_type == "agent"
    assert row.message_type == "stage_output"


@pytest.mark.asyncio
async def test_engine_stage_timeout_sets_failed(engine_setup, test_db_url: str):
    from app.runtime import StageError

    exc_id = engine_setup["execution_id"]

    async def _timeout_mock(*args, **kwargs):
        raise StageError("Stage timed out after 300.0s")
        yield  # make it an async generator

    with patch("app.executions.engine.run_stage", side_effect=_timeout_mock):
        await ExecutionEngine(_make_factory(test_db_url)).run_execution(exc_id)

    async with _test_db(test_db_url) as db:
        result = await db.execute(
            text("SELECT status, error FROM executions WHERE id = :eid"),
            {"eid": exc_id},
        )
        row = result.one()
        result2 = await db.execute(
            text("SELECT event_type FROM execution_events WHERE execution_id = :eid AND event_type = 'execution.failed'"),
            {"eid": exc_id},
        )
        failed_events = result2.all()

    assert row.status == "failed"
    assert "timed out" in row.error
    assert len(failed_events) == 1


@pytest.mark.asyncio
async def test_engine_stage_error_sets_failed(engine_setup, test_db_url: str):
    from app.runtime import StageError

    exc_id = engine_setup["execution_id"]

    async def _error_mock(*args, **kwargs):
        raise StageError("Stage failed: ValueError")
        yield  # make it an async generator

    with patch("app.executions.engine.run_stage", side_effect=_error_mock):
        await ExecutionEngine(_make_factory(test_db_url)).run_execution(exc_id)

    async with _test_db(test_db_url) as db:
        result = await db.execute(
            text("SELECT status, error FROM executions WHERE id = :eid"),
            {"eid": exc_id},
        )
        row = result.one()

    assert row.status == "failed"
    assert "ValueError" in row.error


@pytest.mark.asyncio
async def test_engine_no_final_review_completes(engine_setup, test_db_url: str):
    """Policy with no checkpoints at all → execution + work_item both completed."""
    policy_id = engine_setup["policy_id"]
    checkpoint_id = engine_setup["checkpoint_id"]
    wi_id = engine_setup["work_item_id"]

    # Create a fresh execution for a policy without any checkpoints
    new_exec_id = str(uuid.uuid4())
    async with _test_db(test_db_url) as db:
        # Remove the final_review checkpoint temporarily by deleting it
        await db.execute(
            text("DELETE FROM checkpoints WHERE id = :cid"),
            {"cid": checkpoint_id},
        )
        await db.execute(
            text(
                "INSERT INTO executions (id, work_item_id, policy_id, execution_number, status, created_at, updated_at) "
                "VALUES (:id, :wid, :pid, 2, 'queued', now(), now())"
            ),
            {"id": new_exec_id, "wid": wi_id, "pid": policy_id},
        )
        await db.commit()

    try:
        with patch("app.executions.engine.run_stage", side_effect=_no_output_mock):
            await ExecutionEngine(_make_factory(test_db_url)).run_execution(new_exec_id)

        async with _test_db(test_db_url) as db:
            result = await db.execute(
                text("SELECT status FROM executions WHERE id = :eid"),
                {"eid": new_exec_id},
            )
            exec_status = result.scalar_one()

            result = await db.execute(
                text("SELECT status FROM work_items WHERE id = :wid"),
                {"wid": wi_id},
            )
            wi_status = result.scalar_one()

            result = await db.execute(
                text("SELECT event_type FROM execution_events WHERE execution_id = :eid AND event_type = 'execution.completed'"),
                {"eid": new_exec_id},
            )
            completed_events = result.all()

        assert exec_status == "completed"
        assert wi_status == "completed"
        assert len(completed_events) == 1

    finally:
        async with _test_db(test_db_url) as db:
            await db.execute(text("DELETE FROM execution_events WHERE execution_id = :eid"), {"eid": new_exec_id})
            await db.execute(text("DELETE FROM messages WHERE execution_id = :eid"), {"eid": new_exec_id})
            await db.execute(text("DELETE FROM executions WHERE id = :eid"), {"eid": new_exec_id})
            # Restore work_item status for fixture cleanup
            await db.execute(
                text("UPDATE work_items SET status = 'in_progress', updated_at = now() WHERE id = :wid"),
                {"wid": wi_id},
            )
            # Restore checkpoint (fixture teardown will try to delete it but it's already gone — OK)
            await db.commit()


@pytest.mark.asyncio
async def test_engine_consumes_pending_guidance(engine_setup, test_db_url: str):
    exc_id = engine_setup["execution_id"]
    msg_id = str(uuid.uuid4())

    async with _test_db(test_db_url) as db:
        await db.execute(
            text(
                "INSERT INTO messages (id, execution_id, sender_type, message_type, content, consumed_at, created_at, updated_at) "
                "VALUES (:id, :eid, 'human', 'guidance', 'Please focus on accuracy', NULL, now(), now())"
            ),
            {"id": msg_id, "eid": exc_id},
        )
        await db.commit()

    with patch("app.executions.engine.run_stage", side_effect=_no_output_mock):
        await ExecutionEngine(_make_factory(test_db_url)).run_execution(exc_id)

    async with _test_db(test_db_url) as db:
        result = await db.execute(
            text("SELECT consumed_at FROM messages WHERE id = :mid"),
            {"mid": msg_id},
        )
        consumed_at = result.scalar_one()

    assert consumed_at is not None
