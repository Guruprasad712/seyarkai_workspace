"""Execution create/read/list endpoint tests — all offline (no engine runs)."""
from __future__ import annotations

import contextlib
import uuid

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.security import create_access_token, hash_password


# Suppress the background engine task for all tests in this file — these tests
# cover the HTTP layer only (create/read/list). The engine itself is tested in
# test_engine.py. Without this, the engine fires in a background task and races
# with fixture teardown (deleting rows the engine is still using).
@pytest.fixture(autouse=True)
def _no_engine(monkeypatch):
    async def _noop(self, execution_id: str) -> None:
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
async def auth_headers(test_db_url: str):
    user_id = str(uuid.uuid4())
    async with _test_db(test_db_url) as db:
        await db.execute(
            text(
                "INSERT INTO users (id, email, name, hashed_password, role, status, created_at, updated_at) "
                "VALUES (:id, :email, :name, :hp, 'member', 'active', now(), now())"
            ),
            {
                "id": user_id,
                "email": f"exec_test_{user_id[:8]}@example.com",
                "name": "Exec Test",
                "hp": hash_password("pw"),
            },
        )
        await db.commit()

    token = create_access_token(user_id, "member")
    yield {"Authorization": f"Bearer {token}", "_user_id": user_id}

    async with _test_db(test_db_url) as db:
        uid = user_id
        await db.execute(
            text(
                "DELETE FROM executions WHERE work_item_id IN "
                "(SELECT wi.id FROM work_items wi JOIN projects p ON wi.project_id = p.id WHERE p.created_by = :uid)"
            ),
            {"uid": uid},
        )
        await db.execute(
            text(
                "DELETE FROM checkpoints WHERE policy_id IN "
                "(SELECT po.id FROM policies po JOIN work_items wi ON po.work_item_id = wi.id "
                "JOIN projects p ON wi.project_id = p.id WHERE p.created_by = :uid)"
            ),
            {"uid": uid},
        )
        await db.execute(
            text(
                "DELETE FROM policy_stages WHERE policy_id IN "
                "(SELECT po.id FROM policies po JOIN work_items wi ON po.work_item_id = wi.id "
                "JOIN projects p ON wi.project_id = p.id WHERE p.created_by = :uid)"
            ),
            {"uid": uid},
        )
        await db.execute(
            text(
                "DELETE FROM policies WHERE work_item_id IN "
                "(SELECT wi.id FROM work_items wi JOIN projects p ON wi.project_id = p.id WHERE p.created_by = :uid)"
            ),
            {"uid": uid},
        )
        await db.execute(
            text(
                "DELETE FROM work_item_workers WHERE work_item_id IN "
                "(SELECT wi.id FROM work_items wi JOIN projects p ON wi.project_id = p.id WHERE p.created_by = :uid)"
            ),
            {"uid": uid},
        )
        await db.execute(
            text(
                "DELETE FROM work_items WHERE project_id IN "
                "(SELECT id FROM projects WHERE created_by = :uid)"
            ),
            {"uid": uid},
        )
        await db.execute(text("DELETE FROM projects WHERE created_by = :uid"), {"uid": uid})
        await db.execute(text("DELETE FROM users WHERE id = :uid"), {"uid": uid})
        await db.commit()


@pytest_asyncio.fixture()
async def published_agent_version(test_db_url: str):
    agent_id = str(uuid.uuid4())
    version_id = str(uuid.uuid4())
    tool_id = str(uuid.uuid4())
    async with _test_db(test_db_url) as db:
        seq = (await db.execute(text("SELECT nextval('agent_code_seq')"))).scalar_one()
        await db.execute(
            text(
                "INSERT INTO agents (id, agent_code, name, description, role_purpose, status, created_at, updated_at) "
                "VALUES (:id, :code, :name, 'desc', 'purpose', 'active', now(), now())"
            ),
            {"id": agent_id, "code": f"agent-{seq:04d}", "name": f"Exec Agent {agent_id[:8]}"},
        )
        await db.execute(
            text(
                "INSERT INTO mcp_tools (id, name, tool_name, server_key, description, status, created_at, updated_at) "
                "VALUES (:id, :name, :tool_name, 'knowledge', 'desc', 'active', now(), now()) "
                "ON CONFLICT (tool_name) DO UPDATE SET status='active'"
            ),
            {"id": tool_id, "name": f"Tool {tool_id[:8]}", "tool_name": f"tool_{tool_id[:8]}"},
        )
        result = await db.execute(
            text("SELECT id FROM mcp_tools WHERE tool_name = :tn"),
            {"tn": f"tool_{tool_id[:8]}"},
        )
        tool_id = str(result.scalar_one())
        await db.execute(
            text(
                "INSERT INTO agent_versions (id, agent_id, version, instructions, capabilities, status, created_at, updated_at) "
                "VALUES (:id, :aid, '1.0', 'do stuff', CAST(:caps AS jsonb), 'published', now(), now())"
            ),
            {"id": version_id, "aid": agent_id, "caps": '[{"name":"cap","description":"d"}]'},
        )
        await db.execute(
            text("INSERT INTO agent_version_tools (agent_version_id, mcp_tool_id) VALUES (:vid, :tid)"),
            {"vid": version_id, "tid": tool_id},
        )
        await db.commit()

    yield version_id

    async with _test_db(test_db_url) as db:
        await db.execute(text("DELETE FROM work_item_workers WHERE agent_version_id = :vid"), {"vid": version_id})
        await db.execute(text("DELETE FROM policy_stages WHERE agent_version_id = :vid"), {"vid": version_id})
        await db.execute(text("DELETE FROM agent_version_tools WHERE agent_version_id = :vid"), {"vid": version_id})
        await db.execute(text("DELETE FROM agent_versions WHERE id = :vid"), {"vid": version_id})
        await db.execute(text("DELETE FROM agents WHERE id = :aid"), {"aid": agent_id})
        await db.commit()


@pytest_asyncio.fixture()
async def work_item_with_policy(test_db_url: str, auth_headers, published_agent_version):
    """Project + work item + published policy with one stage + final_review checkpoint."""
    project_id = str(uuid.uuid4())
    wi_id = str(uuid.uuid4())
    policy_id = str(uuid.uuid4())
    stage_id = str(uuid.uuid4())
    checkpoint_id = str(uuid.uuid4())
    user_id = auth_headers["_user_id"]
    version_id = published_agent_version

    async with _test_db(test_db_url) as db:
        await db.execute(
            text(
                "INSERT INTO projects (id, name, description, status, created_by, created_at, updated_at) "
                "VALUES (:id, :name, 'desc', 'active', :uid, now(), now())"
            ),
            {"id": project_id, "name": f"Exec Project {project_id[:8]}", "uid": user_id},
        )
        await db.execute(
            text(
                "INSERT INTO work_items (id, project_id, name, objective, description, expected_outcome, status, created_by, created_at, updated_at) "
                "VALUES (:id, :pid, :name, 'obj', 'desc', 'outcome', 'new', :uid, now(), now())"
            ),
            {"id": wi_id, "pid": project_id, "name": f"WI {wi_id[:8]}", "uid": user_id},
        )
        await db.execute(
            text(
                "INSERT INTO work_item_workers (id, work_item_id, worker_type, agent_version_id, user_id, created_at, updated_at) "
                "VALUES (:id, :wid, 'ai_agent', :vid, NULL, now(), now())"
            ),
            {"id": str(uuid.uuid4()), "wid": wi_id, "vid": version_id},
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
                "INSERT INTO checkpoints (id, policy_id, stage_id, type, assigned_user_id, instruction, created_at, updated_at) "
                "VALUES (:id, :pid, NULL, 'final_review', :uid, 'Approve the result', now(), now())"
            ),
            {"id": checkpoint_id, "pid": policy_id, "uid": user_id},
        )
        await db.commit()

    yield {
        "work_item_id": wi_id,
        "project_id": project_id,
        "policy_id": policy_id,
        "stage_id": stage_id,
        "checkpoint_id": checkpoint_id,
        "user_id": user_id,
    }

    async with _test_db(test_db_url) as db:
        await db.execute(text("DELETE FROM executions WHERE work_item_id = :wid"), {"wid": wi_id})
        await db.execute(text("DELETE FROM checkpoints WHERE policy_id = :pid"), {"pid": policy_id})
        await db.execute(text("DELETE FROM policy_stages WHERE policy_id = :pid"), {"pid": policy_id})
        await db.execute(text("DELETE FROM policies WHERE id = :pid"), {"pid": policy_id})
        await db.execute(text("DELETE FROM work_item_workers WHERE work_item_id = :wid"), {"wid": wi_id})
        await db.execute(text("DELETE FROM work_items WHERE id = :wid"), {"wid": wi_id})
        await db.execute(text("DELETE FROM projects WHERE id = :pid"), {"pid": project_id})
        await db.commit()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_create_execution_success(
    async_client: AsyncClient, auth_headers, work_item_with_policy
):
    wi_id = work_item_with_policy["work_item_id"]
    r = await async_client.post(f"/work-items/{wi_id}/executions", headers=auth_headers)
    assert r.status_code == 202, r.text
    body = r.json()
    assert "execution_id" in body
    assert len(body["execution_id"]) == 36  # UUID


@pytest.mark.asyncio
async def test_create_execution_no_published_policy(
    async_client: AsyncClient, auth_headers, test_db_url: str, published_agent_version
):
    user_id = auth_headers["_user_id"]
    project_id = str(uuid.uuid4())
    wi_id = str(uuid.uuid4())
    async with _test_db(test_db_url) as db:
        await db.execute(
            text(
                "INSERT INTO projects (id, name, description, status, created_by, created_at, updated_at) "
                "VALUES (:id, :name, 'desc', 'active', :uid, now(), now())"
            ),
            {"id": project_id, "name": f"No Policy Project {project_id[:8]}", "uid": user_id},
        )
        await db.execute(
            text(
                "INSERT INTO work_items (id, project_id, name, objective, description, expected_outcome, status, created_by, created_at, updated_at) "
                "VALUES (:id, :pid, :name, 'obj', 'desc', 'outcome', 'new', :uid, now(), now())"
            ),
            {"id": wi_id, "pid": project_id, "name": f"WI NP {wi_id[:8]}", "uid": user_id},
        )
        await db.commit()

    try:
        r = await async_client.post(f"/work-items/{wi_id}/executions", headers=auth_headers)
        assert r.status_code == 422, r.text
        detail = r.json()["detail"]
        assert detail["error"] == "no_published_policy"
    finally:
        async with _test_db(test_db_url) as db:
            await db.execute(text("DELETE FROM work_items WHERE id = :wid"), {"wid": wi_id})
            await db.execute(text("DELETE FROM projects WHERE id = :pid"), {"pid": project_id})
            await db.commit()


@pytest.mark.asyncio
async def test_create_execution_active_exists(
    async_client: AsyncClient, auth_headers, work_item_with_policy
):
    wi_id = work_item_with_policy["work_item_id"]
    r1 = await async_client.post(f"/work-items/{wi_id}/executions", headers=auth_headers)
    assert r1.status_code == 202, r1.text

    r2 = await async_client.post(f"/work-items/{wi_id}/executions", headers=auth_headers)
    assert r2.status_code == 409, r2.text


@pytest.mark.asyncio
async def test_create_execution_transitions_work_item_to_in_progress(
    async_client: AsyncClient, auth_headers, work_item_with_policy, test_db_url: str
):
    wi_id = work_item_with_policy["work_item_id"]
    r = await async_client.post(f"/work-items/{wi_id}/executions", headers=auth_headers)
    assert r.status_code == 202, r.text

    async with _test_db(test_db_url) as db:
        result = await db.execute(
            text("SELECT status FROM work_items WHERE id = :wid"), {"wid": wi_id}
        )
        wi_status = result.scalar_one()

    assert wi_status == "in_progress"


@pytest.mark.asyncio
async def test_create_execution_failed_can_retry(
    async_client: AsyncClient, auth_headers, work_item_with_policy, test_db_url: str
):
    wi_id = work_item_with_policy["work_item_id"]
    r1 = await async_client.post(f"/work-items/{wi_id}/executions", headers=auth_headers)
    assert r1.status_code == 202, r1.text
    exec_id = r1.json()["execution_id"]

    async with _test_db(test_db_url) as db:
        await db.execute(
            text("UPDATE executions SET status = 'failed' WHERE id = :eid"),
            {"eid": exec_id},
        )
        await db.commit()

    r2 = await async_client.post(f"/work-items/{wi_id}/executions", headers=auth_headers)
    assert r2.status_code == 202, r2.text


@pytest.mark.asyncio
async def test_get_execution(
    async_client: AsyncClient, auth_headers, work_item_with_policy
):
    wi_id = work_item_with_policy["work_item_id"]
    r = await async_client.post(f"/work-items/{wi_id}/executions", headers=auth_headers)
    assert r.status_code == 202, r.text
    exec_id = r.json()["execution_id"]

    r2 = await async_client.get(f"/executions/{exec_id}", headers=auth_headers)
    assert r2.status_code == 200, r2.text
    body = r2.json()
    assert body["id"] == exec_id
    assert body["status"] == "queued"
    assert body["work_item_id"] == wi_id
    assert body["execution_number"] == 1
    assert body["blocking_checkpoint"] is None


@pytest.mark.asyncio
async def test_list_executions(
    async_client: AsyncClient, auth_headers, work_item_with_policy
):
    wi_id = work_item_with_policy["work_item_id"]
    r = await async_client.post(f"/work-items/{wi_id}/executions", headers=auth_headers)
    assert r.status_code == 202, r.text

    r2 = await async_client.get(f"/work-items/{wi_id}/executions", headers=auth_headers)
    assert r2.status_code == 200, r2.text
    items = r2.json()
    assert len(items) == 1
    assert items[0]["execution_number"] == 1
    assert items[0]["status"] == "queued"


@pytest.mark.asyncio
async def test_execution_number_increments(
    async_client: AsyncClient, auth_headers, work_item_with_policy, test_db_url: str
):
    wi_id = work_item_with_policy["work_item_id"]

    r1 = await async_client.post(f"/work-items/{wi_id}/executions", headers=auth_headers)
    assert r1.status_code == 202, r1.text
    exec_id_1 = r1.json()["execution_id"]

    async with _test_db(test_db_url) as db:
        await db.execute(
            text("UPDATE executions SET status = 'failed' WHERE id = :eid"),
            {"eid": exec_id_1},
        )
        await db.commit()

    r2 = await async_client.post(f"/work-items/{wi_id}/executions", headers=auth_headers)
    assert r2.status_code == 202, r2.text
    exec_id_2 = r2.json()["execution_id"]

    r3 = await async_client.get(f"/executions/{exec_id_2}", headers=auth_headers)
    assert r3.status_code == 200, r3.text
    assert r3.json()["execution_number"] == 2
