"""Checkpoint response endpoint tests — all offline (no engine runs)."""
from __future__ import annotations

import contextlib
import uuid

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.security import create_access_token, hash_password


# Suppress background engine task for all tests in this file.
@pytest.fixture(autouse=True)
def _no_engine(monkeypatch):
    async def _noop(self, execution_id: str, start_from_stage_sequence: int = 1) -> None:
        return None

    monkeypatch.setattr(
        "app.executions.engine.ExecutionEngine.run_execution", _noop
    )


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
async def cp_setup(test_db_url: str, async_client: AsyncClient):
    """
    Full chain: assignee_user, other_user, project, work_item, agent+version,
    published policy with 1 stage + final_review checkpoint, execution in
    waiting_for_approval with final_review as blocking checkpoint.

    Yields a dict of all IDs and both sets of auth headers.
    """
    assignee_id = str(uuid.uuid4())
    other_id = str(uuid.uuid4())
    project_id = str(uuid.uuid4())
    wi_id = str(uuid.uuid4())
    agent_id = str(uuid.uuid4())
    version_id = str(uuid.uuid4())
    tool_id_key = str(uuid.uuid4())
    policy_id = str(uuid.uuid4())
    stage_id = str(uuid.uuid4())
    final_cp_id = str(uuid.uuid4())
    stage_cp_id = str(uuid.uuid4())
    execution_id = str(uuid.uuid4())

    async with _test_db(test_db_url) as db:
        for uid, suffix in [(assignee_id, "asgn"), (other_id, "othr")]:
            await db.execute(
                text(
                    "INSERT INTO users (id, email, name, hashed_password, role, status, created_at, updated_at) "
                    "VALUES (:id, :email, :name, :hp, 'member', 'active', now(), now())"
                ),
                {"id": uid, "email": f"cp_{suffix}_{uid[:8]}@example.com", "name": f"CP {suffix}", "hp": hash_password("pw")},
            )
        await db.execute(
            text(
                "INSERT INTO projects (id, name, description, status, created_by, created_at, updated_at) "
                "VALUES (:id, :name, 'desc', 'active', :uid, now(), now())"
            ),
            {"id": project_id, "name": f"CP Project {project_id[:8]}", "uid": assignee_id},
        )
        await db.execute(
            text(
                "INSERT INTO work_items (id, project_id, name, objective, description, expected_outcome, "
                "status, created_by, created_at, updated_at) "
                "VALUES (:id, :pid, :name, 'obj', 'desc', 'outcome', 'in_progress', :uid, now(), now())"
            ),
            {"id": wi_id, "pid": project_id, "name": f"WI {wi_id[:8]}", "uid": assignee_id},
        )
        seq = (await db.execute(text("SELECT nextval('agent_code_seq')"))).scalar_one()
        await db.execute(
            text(
                "INSERT INTO agents (id, agent_code, name, description, role_purpose, status, created_at, updated_at) "
                "VALUES (:id, :code, :name, 'desc', 'purpose', 'active', now(), now())"
            ),
            {"id": agent_id, "code": f"agent-{seq:04d}", "name": f"CP Agent {agent_id[:8]}"},
        )
        await db.execute(
            text(
                "INSERT INTO mcp_tools (id, name, tool_name, server_key, description, status, created_at, updated_at) "
                "VALUES (:id, :name, :tool_name, 'knowledge', 'desc', 'active', now(), now()) "
                "ON CONFLICT (tool_name) DO UPDATE SET status='active'"
            ),
            {"id": tool_id_key, "name": f"CPTool {tool_id_key[:8]}", "tool_name": f"cptool_{tool_id_key[:8]}"},
        )
        result = await db.execute(
            text("SELECT id FROM mcp_tools WHERE tool_name = :tn"),
            {"tn": f"cptool_{tool_id_key[:8]}"},
        )
        actual_tool_id = str(result.scalar_one())
        await db.execute(
            text(
                "INSERT INTO agent_versions (id, agent_id, version, instructions, capabilities, status, created_at, updated_at) "
                "VALUES (:id, :aid, '1.0', 'Do stuff', CAST(:caps AS jsonb), 'published', now(), now())"
            ),
            {"id": version_id, "aid": agent_id, "caps": '[{"name":"cap","description":"d"}]'},
        )
        await db.execute(
            text("INSERT INTO agent_version_tools (agent_version_id, mcp_tool_id) VALUES (:vid, :tid)"),
            {"vid": version_id, "tid": actual_tool_id},
        )
        await db.execute(
            text(
                "INSERT INTO policies (id, work_item_id, version, status, generated_by, created_at, updated_at) "
                "VALUES (:id, :wid, 1, 'published', :uid, now(), now())"
            ),
            {"id": policy_id, "wid": wi_id, "uid": assignee_id},
        )
        await db.execute(
            text(
                "INSERT INTO policy_stages (id, policy_id, sequence, name, description, expected_output, "
                "agent_version_id, created_at, updated_at) "
                "VALUES (:id, :pid, 1, 'Stage 1', 'desc', 'output', :vid, now(), now())"
            ),
            {"id": stage_id, "pid": policy_id, "vid": version_id},
        )
        # Stage checkpoint (approval type) assigned to assignee
        await db.execute(
            text(
                "INSERT INTO checkpoints (id, policy_id, stage_id, type, assigned_user_id, instruction, created_at, updated_at) "
                "VALUES (:id, :pid, :sid, 'approval', :uid, 'Review stage 1', now(), now())"
            ),
            {"id": stage_cp_id, "pid": policy_id, "sid": stage_id, "uid": assignee_id},
        )
        # Final review checkpoint assigned to assignee
        await db.execute(
            text(
                "INSERT INTO checkpoints (id, policy_id, stage_id, type, assigned_user_id, instruction, created_at, updated_at) "
                "VALUES (:id, :pid, NULL, 'final_review', :uid, 'Approve final result', now(), now())"
            ),
            {"id": final_cp_id, "pid": policy_id, "uid": assignee_id},
        )
        # Execution paused at final_review
        await db.execute(
            text(
                "INSERT INTO executions (id, work_item_id, policy_id, execution_number, status, "
                "blocking_checkpoint_id, created_at, updated_at) "
                "VALUES (:id, :wid, :pid, 1, 'waiting_for_approval', :cpid, now(), now())"
            ),
            {"id": execution_id, "wid": wi_id, "pid": policy_id, "cpid": final_cp_id},
        )
        await db.commit()

    assignee_token = create_access_token(assignee_id, "member")
    other_token = create_access_token(other_id, "member")

    yield {
        "execution_id": execution_id,
        "final_cp_id": final_cp_id,
        "stage_cp_id": stage_cp_id,
        "stage_id": stage_id,
        "work_item_id": wi_id,
        "assignee_id": assignee_id,
        "other_id": other_id,
        "policy_id": policy_id,
        "version_id": version_id,
        "agent_id": agent_id,
        "project_id": project_id,
        "headers_assignee": {"Authorization": f"Bearer {assignee_token}"},
        "headers_other": {"Authorization": f"Bearer {other_token}"},
    }

    async with _test_db(test_db_url) as db:
        await db.execute(text("DELETE FROM checkpoint_responses WHERE execution_id = :eid"), {"eid": execution_id})
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
        await db.execute(text("DELETE FROM users WHERE id IN (:a, :b)"), {"a": assignee_id, "b": other_id})
        await db.commit()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_approve_final_review(async_client: AsyncClient, cp_setup, test_db_url: str):
    exc_id = cp_setup["execution_id"]
    cp_id = cp_setup["final_cp_id"]
    wi_id = cp_setup["work_item_id"]

    r = await async_client.post(
        f"/executions/{exc_id}/checkpoints/{cp_id}/respond",
        json={"decision": "approve"},
        headers=cp_setup["headers_assignee"],
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["next_action"] == "completed"
    assert body["status"] == "completed"

    async with _test_db(test_db_url) as db:
        result = await db.execute(
            text("SELECT status FROM executions WHERE id = :eid"), {"eid": exc_id}
        )
        assert result.scalar_one() == "completed"

        result = await db.execute(
            text("SELECT status FROM work_items WHERE id = :wid"), {"wid": wi_id}
        )
        assert result.scalar_one() == "completed"

        result = await db.execute(
            text("SELECT event_type FROM execution_events WHERE execution_id = :eid AND event_type = 'execution.completed'"),
            {"eid": exc_id},
        )
        assert len(result.all()) == 1


@pytest.mark.asyncio
async def test_reject_checkpoint(async_client: AsyncClient, cp_setup, test_db_url: str):
    exc_id = cp_setup["execution_id"]
    cp_id = cp_setup["final_cp_id"]

    r = await async_client.post(
        f"/executions/{exc_id}/checkpoints/{cp_id}/respond",
        json={"decision": "reject", "comment": "not good enough"},
        headers=cp_setup["headers_assignee"],
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["next_action"] == "failed"
    assert body["status"] == "failed"

    async with _test_db(test_db_url) as db:
        result = await db.execute(
            text("SELECT status, error FROM executions WHERE id = :eid"), {"eid": exc_id}
        )
        row = result.one()
        assert row.status == "failed"
        assert row.error == "not good enough"

        result = await db.execute(
            text("SELECT event_type FROM execution_events WHERE execution_id = :eid AND event_type = 'execution.failed'"),
            {"eid": exc_id},
        )
        assert len(result.all()) == 1


@pytest.mark.asyncio
async def test_approve_stage_checkpoint_resumes(
    async_client: AsyncClient, cp_setup, test_db_url: str
):
    """Approve a stage checkpoint (not final_review) → execution becomes running."""
    exc_id = cp_setup["execution_id"]
    stage_cp_id = cp_setup["stage_cp_id"]

    # Swap the blocking checkpoint to the stage checkpoint
    async with _test_db(test_db_url) as db:
        await db.execute(
            text("UPDATE executions SET blocking_checkpoint_id = :cpid WHERE id = :eid"),
            {"cpid": stage_cp_id, "eid": exc_id},
        )
        await db.commit()

    r = await async_client.post(
        f"/executions/{exc_id}/checkpoints/{stage_cp_id}/respond",
        json={"decision": "approve"},
        headers=cp_setup["headers_assignee"],
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["next_action"] == "resume"
    assert body["status"] == "running"

    async with _test_db(test_db_url) as db:
        result = await db.execute(
            text("SELECT event_type FROM execution_events WHERE execution_id = :eid AND event_type = 'execution.resumed'"),
            {"eid": exc_id},
        )
        assert len(result.all()) == 1


@pytest.mark.asyncio
async def test_input_provided_stores_message(
    async_client: AsyncClient, cp_setup, test_db_url: str
):
    """input_provided decision stores a guidance message."""
    exc_id = cp_setup["execution_id"]
    stage_cp_id = cp_setup["stage_cp_id"]

    # Set stage checkpoint as blocking, and change its type to 'input'
    async with _test_db(test_db_url) as db:
        await db.execute(
            text("UPDATE executions SET blocking_checkpoint_id = :cpid WHERE id = :eid"),
            {"cpid": stage_cp_id, "eid": exc_id},
        )
        await db.execute(
            text("UPDATE checkpoints SET type = 'input' WHERE id = :cpid"),
            {"cpid": stage_cp_id},
        )
        await db.commit()

    r = await async_client.post(
        f"/executions/{exc_id}/checkpoints/{stage_cp_id}/respond",
        json={"decision": "input_provided", "input_text": "Focus on conciseness"},
        headers=cp_setup["headers_assignee"],
    )
    assert r.status_code == 200, r.text
    assert r.json()["next_action"] == "resume"

    async with _test_db(test_db_url) as db:
        result = await db.execute(
            text(
                "SELECT sender_type, message_type, content FROM messages "
                "WHERE execution_id = :eid AND sender_type = 'human'"
            ),
            {"eid": exc_id},
        )
        row = result.one()
        assert row.sender_type == "human"
        assert row.message_type == "guidance"
        assert row.content == "Focus on conciseness"


@pytest.mark.asyncio
async def test_input_provided_requires_input_text(
    async_client: AsyncClient, cp_setup, test_db_url: str
):
    exc_id = cp_setup["execution_id"]
    stage_cp_id = cp_setup["stage_cp_id"]

    async with _test_db(test_db_url) as db:
        await db.execute(
            text("UPDATE executions SET blocking_checkpoint_id = :cpid WHERE id = :eid"),
            {"cpid": stage_cp_id, "eid": exc_id},
        )
        await db.execute(
            text("UPDATE checkpoints SET type = 'input' WHERE id = :cpid"),
            {"cpid": stage_cp_id},
        )
        await db.commit()

    r = await async_client.post(
        f"/executions/{exc_id}/checkpoints/{stage_cp_id}/respond",
        json={"decision": "input_provided"},  # no input_text
        headers=cp_setup["headers_assignee"],
    )
    assert r.status_code == 422, r.text
    detail = r.json()["detail"]
    codes = [f["code"] for f in detail["failures"]]
    assert "input_text_required" in codes


@pytest.mark.asyncio
async def test_wrong_decision_for_type(async_client: AsyncClient, cp_setup):
    exc_id = cp_setup["execution_id"]
    cp_id = cp_setup["final_cp_id"]  # type = final_review, allows approve/reject only

    r = await async_client.post(
        f"/executions/{exc_id}/checkpoints/{cp_id}/respond",
        json={"decision": "input_provided", "input_text": "something"},
        headers=cp_setup["headers_assignee"],
    )
    assert r.status_code == 422, r.text
    detail = r.json()["detail"]
    codes = [f["code"] for f in detail["failures"]]
    assert "invalid_decision" in codes


@pytest.mark.asyncio
async def test_not_assignee_forbidden(async_client: AsyncClient, cp_setup):
    exc_id = cp_setup["execution_id"]
    cp_id = cp_setup["final_cp_id"]

    r = await async_client.post(
        f"/executions/{exc_id}/checkpoints/{cp_id}/respond",
        json={"decision": "approve"},
        headers=cp_setup["headers_other"],  # not the assignee
    )
    assert r.status_code == 403, r.text


@pytest.mark.asyncio
async def test_not_waiting_returns_422(
    async_client: AsyncClient, cp_setup, test_db_url: str
):
    exc_id = cp_setup["execution_id"]
    cp_id = cp_setup["final_cp_id"]

    async with _test_db(test_db_url) as db:
        await db.execute(
            text("UPDATE executions SET status = 'queued', blocking_checkpoint_id = NULL WHERE id = :eid"),
            {"eid": exc_id},
        )
        await db.commit()

    r = await async_client.post(
        f"/executions/{exc_id}/checkpoints/{cp_id}/respond",
        json={"decision": "approve"},
        headers=cp_setup["headers_assignee"],
    )
    assert r.status_code == 422, r.text
    assert r.json()["detail"]["error"] == "not_waiting"
