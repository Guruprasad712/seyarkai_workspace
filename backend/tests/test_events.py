"""GET /executions/{id}/events endpoint tests â€” all offline."""
from __future__ import annotations

import contextlib
import uuid
from datetime import datetime, timezone

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.security import create_access_token, hash_password


@pytest.fixture(autouse=True)
def _no_engine(monkeypatch):
    async def _noop(self, execution_id: str, start_from_stage_sequence: int = 1) -> None:
        return None

    monkeypatch.setattr(
        "app.executions.engine.ExecutionEngine.run_execution", _noop
    )


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
async def ev_setup(test_db_url: str):
    """User, project, work item, published policy+stage, execution ready to insert events."""
    user_id = str(uuid.uuid4())
    agent_id = str(uuid.uuid4())
    version_id = str(uuid.uuid4())
    tool_id = str(uuid.uuid4())
    project_id = str(uuid.uuid4())
    wi_id = str(uuid.uuid4())
    policy_id = str(uuid.uuid4())
    stage_id = str(uuid.uuid4())
    cp_id = str(uuid.uuid4())
    exec_id = str(uuid.uuid4())

    async with _test_db(test_db_url) as db:
        await db.execute(
            text(
                "INSERT INTO users (id, email, name, hashed_password, role, status, created_at, updated_at) "
                "VALUES (:id, :email, 'Events User', :hp, 'admin', 'active', now(), now())"
            ),
            {"id": user_id, "email": f"ev_test_{user_id[:8]}@example.com", "hp": hash_password("pw")},
        )
        seq = (await db.execute(text("SELECT nextval('agent_code_seq')"))).scalar_one()
        await db.execute(
            text(
                "INSERT INTO agents (id, agent_code, name, description, role_purpose, status, created_at, updated_at) "
                "VALUES (:id, :code, :name, 'desc', 'purpose', 'active', now(), now())"
            ),
            {"id": agent_id, "code": f"agent-{seq:04d}", "name": f"EV Agent {agent_id[:8]}"},
        )
        await db.execute(
            text(
                "INSERT INTO mcp_tools (id, name, tool_name, server_key, description, status, created_at, updated_at) "
                "VALUES (:id, :name, :tn, 'knowledge', 'desc', 'active', now(), now()) "
                "ON CONFLICT (tool_name) DO UPDATE SET status='active'"
            ),
            {"id": tool_id, "name": f"EV Tool {tool_id[:8]}", "tn": f"ev_tool_{tool_id[:8]}"},
        )
        actual_tool_id = (await db.execute(
            text("SELECT id FROM mcp_tools WHERE tool_name = :tn"),
            {"tn": f"ev_tool_{tool_id[:8]}"},
        )).scalar_one()
        await db.execute(
            text(
                "INSERT INTO agent_versions (id, agent_id, version, instructions, capabilities, status, created_at, updated_at) "
                "VALUES (:id, :aid, '1.0', 'do stuff', CAST(:caps AS jsonb), 'published', now(), now())"
            ),
            {"id": version_id, "aid": agent_id, "caps": '[{"name":"cap","description":"d"}]'},
        )
        await db.execute(
            text("INSERT INTO agent_version_tools (agent_version_id, mcp_tool_id) VALUES (:vid, :tid)"),
            {"vid": version_id, "tid": str(actual_tool_id)},
        )
        await db.execute(
            text(
                "INSERT INTO projects (id, name, description, status, created_by, created_at, updated_at) "
                "VALUES (:id, :name, 'desc', 'active', :uid, now(), now())"
            ),
            {"id": project_id, "name": f"EV Project {project_id[:8]}", "uid": user_id},
        )
        await db.execute(
            text(
                "INSERT INTO work_items (id, project_id, name, objective, description, expected_outcome, status, created_by, created_at, updated_at) "
                "VALUES (:id, :pid, :name, 'obj', 'desc', 'outcome', 'new', :uid, now(), now())"
            ),
            {"id": wi_id, "pid": project_id, "name": f"EV WI {wi_id[:8]}", "uid": user_id},
        )
        await db.execute(
            text(
                "INSERT INTO work_item_workers (id, work_item_id, worker_type, agent_version_id, user_id, created_at, updated_at) "
                "VALUES (:id, :wiid, 'ai_agent', :vid, NULL, now(), now())"
            ),
            {"id": str(uuid.uuid4()), "wiid": wi_id, "vid": version_id},
        )
        await db.execute(
            text(
                "INSERT INTO work_item_workers (id, work_item_id, worker_type, agent_version_id, user_id, created_at, updated_at) "
                "VALUES (:id, :wiid, 'human', NULL, :uid, now(), now())"
            ),
            {"id": str(uuid.uuid4()), "wiid": wi_id, "uid": user_id},
        )
        await db.execute(
            text(
                "INSERT INTO policies (id, work_item_id, version, status, generated_by, created_at, updated_at) "
                "VALUES (:id, :wiid, 1, 'published', 'manual', now(), now())"
            ),
            {"id": policy_id, "wiid": wi_id},
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
                "VALUES (:id, :pid, NULL, 'final_review', :uid, 'Review', now(), now())"
            ),
            {"id": cp_id, "pid": policy_id, "uid": user_id},
        )
        await db.execute(
            text(
                "INSERT INTO executions (id, work_item_id, policy_id, execution_number, status, created_at, updated_at) "
                "VALUES (:id, :wiid, :pid, 1, 'running', now(), now())"
            ),
            {"id": exec_id, "wiid": wi_id, "pid": policy_id},
        )
        await db.commit()

    token = create_access_token(user_id, "admin")
    yield {
        "exec_id": exec_id,
        "stage_id": stage_id,
        "user_id": user_id,
        "token": token,
        "headers": {"Authorization": f"Bearer {token}"},
    }

    async with _test_db(test_db_url) as db:
        await db.execute(text("DELETE FROM execution_events WHERE execution_id = :eid"), {"eid": exec_id})
        await db.execute(text("DELETE FROM executions WHERE id = :eid"), {"eid": exec_id})
        await db.execute(text("DELETE FROM checkpoints WHERE policy_id = :pid"), {"pid": policy_id})
        await db.execute(text("DELETE FROM policy_stages WHERE policy_id = :pid"), {"pid": policy_id})
        await db.execute(text("DELETE FROM policies WHERE id = :pid"), {"pid": policy_id})
        await db.execute(text("DELETE FROM work_item_workers WHERE work_item_id = :wiid"), {"wiid": wi_id})
        await db.execute(text("DELETE FROM work_items WHERE id = :wiid"), {"wiid": wi_id})
        await db.execute(text("DELETE FROM projects WHERE id = :pid"), {"pid": project_id})
        await db.execute(text("DELETE FROM agent_version_tools WHERE agent_version_id = :vid"), {"vid": version_id})
        await db.execute(text("DELETE FROM agent_versions WHERE id = :vid"), {"vid": version_id})
        await db.execute(text("DELETE FROM agents WHERE id = :aid"), {"aid": agent_id})
        await db.execute(text("DELETE FROM users WHERE id = :uid"), {"uid": user_id})
        await db.commit()


async def _insert_event(
    test_db_url: str,
    exec_id: str,
    event_type: str,
    actor_type: str = "system",
    stage_id: str | None = None,
    payload: dict | None = None,
    ts_offset_micros: int = 0,
) -> str:
    ev_id = str(uuid.uuid4())
    payload_json = str(payload or {}).replace("'", '"')
    async with _test_db(test_db_url) as db:
        await db.execute(
            text(
                "INSERT INTO execution_events (id, execution_id, stage_id, event_type, actor_type, payload, created_at) "
                "VALUES (:id, :eid, :sid, :et, :at, CAST(:payload AS jsonb), now() + (:offset * interval '1 microsecond'))"
            ),
            {
                "id": ev_id,
                "eid": exec_id,
                "sid": stage_id,
                "et": event_type,
                "at": actor_type,
                "payload": payload_json,
                "offset": ts_offset_micros,
            },
        )
        await db.commit()
    return ev_id


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_list_events_empty(async_client: AsyncClient, ev_setup):
    r = await async_client.get(
        f"/executions/{ev_setup['exec_id']}/events",
        headers=ev_setup["headers"],
    )
    assert r.status_code == 200
    assert r.json() == []


@pytest.mark.asyncio
async def test_list_events_ordered_by_created_at(
    async_client: AsyncClient, ev_setup, test_db_url: str
):
    exec_id = ev_setup["exec_id"]
    await _insert_event(test_db_url, exec_id, "execution.started", ts_offset_micros=0)
    await _insert_event(test_db_url, exec_id, "stage.started", ts_offset_micros=1000)
    await _insert_event(test_db_url, exec_id, "stage.completed", ts_offset_micros=2000)

    r = await async_client.get(
        f"/executions/{exec_id}/events", headers=ev_setup["headers"]
    )
    assert r.status_code == 200
    types = [ev["event_type"] for ev in r.json()]
    assert types == ["execution.started", "stage.started", "stage.completed"]


@pytest.mark.asyncio
async def test_list_events_payload_structure(
    async_client: AsyncClient, ev_setup, test_db_url: str
):
    exec_id = ev_setup["exec_id"]
    await _insert_event(
        test_db_url, exec_id, "execution.started",
        actor_type="system",
        payload={"execution_number": 1},
    )
    r = await async_client.get(
        f"/executions/{exec_id}/events", headers=ev_setup["headers"]
    )
    assert r.status_code == 200
    ev = r.json()[0]
    for key in ("id", "execution_id", "stage_id", "event_type", "actor_type", "actor_id", "payload", "created_at"):
        assert key in ev, f"missing key: {key}"
    assert ev["event_type"] == "execution.started"
    assert ev["execution_id"] == exec_id
    assert ev["stage_id"] is None


@pytest.mark.asyncio
async def test_list_events_after_cursor(
    async_client: AsyncClient, ev_setup, test_db_url: str
):
    exec_id = ev_setup["exec_id"]
    ev1 = await _insert_event(test_db_url, exec_id, "execution.started", ts_offset_micros=0)
    await _insert_event(test_db_url, exec_id, "stage.started", ts_offset_micros=1000)
    await _insert_event(test_db_url, exec_id, "stage.completed", ts_offset_micros=2000)

    r = await async_client.get(
        f"/executions/{exec_id}/events?after={ev1}", headers=ev_setup["headers"]
    )
    assert r.status_code == 200
    data = r.json()
    assert len(data) == 2
    assert data[0]["event_type"] == "stage.started"
    assert data[1]["event_type"] == "stage.completed"


@pytest.mark.asyncio
async def test_list_events_limit(
    async_client: AsyncClient, ev_setup, test_db_url: str
):
    exec_id = ev_setup["exec_id"]
    for i in range(5):
        await _insert_event(test_db_url, exec_id, "stage.started", ts_offset_micros=i * 1000)

    r = await async_client.get(
        f"/executions/{exec_id}/events?limit=2", headers=ev_setup["headers"]
    )
    assert r.status_code == 200
    assert len(r.json()) == 2


@pytest.mark.asyncio
async def test_list_events_execution_not_found(
    async_client: AsyncClient, ev_setup
):
    r = await async_client.get(
        f"/executions/{uuid.uuid4()}/events", headers=ev_setup["headers"]
    )
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_list_events_requires_auth(async_client: AsyncClient, ev_setup):
    r = await async_client.get(f"/executions/{ev_setup['exec_id']}/events")
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_list_events_actor_type_and_payload_content(
    async_client: AsyncClient, ev_setup, test_db_url: str
):
    exec_id = ev_setup["exec_id"]
    stage_id = ev_setup["stage_id"]
    await _insert_event(
        test_db_url, exec_id, "tool.called",
        actor_type="agent",
        stage_id=stage_id,
        payload={"tool_name": "knowledge_search", "arguments": {"query": "test"}},
    )
    r = await async_client.get(
        f"/executions/{exec_id}/events", headers=ev_setup["headers"]
    )
    assert r.status_code == 200
    ev = r.json()[0]
    assert ev["event_type"] == "tool.called"
    assert ev["actor_type"] == "agent"
    assert ev["stage_id"] == stage_id
    assert ev["payload"]["tool_name"] == "knowledge_search"
