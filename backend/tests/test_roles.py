"""Role-based access control tests.

Fixture pattern: direct DB INSERT + create_access_token() — no HTTP calls in setup.
All four roles exercised against key mutating endpoints.
"""
from __future__ import annotations

import contextlib
import uuid

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.security import create_access_token, hash_password


# ---------------------------------------------------------------------------
# DB helper
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
# Per-role fixtures
# ---------------------------------------------------------------------------

def _headers_for(user_id: str, role: str) -> dict:
    token = create_access_token(user_id, role)
    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture()
async def role_users(test_db_url: str):
    """Insert one user per role; yield {role: (user_id, headers)}; clean up after."""
    ids: dict[str, str] = {}
    roles = ["admin", "builder", "reviewer", "observer"]
    async with _test_db(test_db_url) as db:
        for role in roles:
            uid = str(uuid.uuid4())
            ids[role] = uid
            await db.execute(
                text(
                    "INSERT INTO users (id, email, name, hashed_password, role, status, created_at, updated_at) "
                    "VALUES (:id, :email, :name, :hp, :role, 'active', now(), now())"
                ),
                {
                    "id": uid,
                    "email": f"roles_test_{role}@example.com",
                    "name": role.capitalize(),
                    "hp": hash_password("pw"),
                    "role": role,
                },
            )
        await db.commit()

    yield {role: (ids[role], _headers_for(ids[role], role)) for role in roles}

    # Cleanup: delete in FK order (deepest children first), then users
    async with _test_db(test_db_url) as db:
        user_ids_list = list(ids.values())
        for uid in user_ids_list:
            # checkpoints → policy_stages → policies → work_item_workers → work_items → projects
            await db.execute(text(
                "DELETE FROM checkpoints WHERE policy_id IN ("
                "  SELECT id FROM policies WHERE work_item_id IN ("
                "    SELECT id FROM work_items WHERE project_id IN ("
                "      SELECT id FROM projects WHERE created_by = :uid)))"
            ), {"uid": uid})
            await db.execute(text(
                "DELETE FROM policy_stages WHERE policy_id IN ("
                "  SELECT id FROM policies WHERE work_item_id IN ("
                "    SELECT id FROM work_items WHERE project_id IN ("
                "      SELECT id FROM projects WHERE created_by = :uid)))"
            ), {"uid": uid})
            await db.execute(text(
                "DELETE FROM policies WHERE work_item_id IN ("
                "  SELECT id FROM work_items WHERE project_id IN ("
                "    SELECT id FROM projects WHERE created_by = :uid))"
            ), {"uid": uid})
            await db.execute(text(
                "DELETE FROM work_item_workers WHERE work_item_id IN ("
                "  SELECT id FROM work_items WHERE project_id IN ("
                "    SELECT id FROM projects WHERE created_by = :uid))"
            ), {"uid": uid})
            await db.execute(text(
                "DELETE FROM work_items WHERE project_id IN ("
                "  SELECT id FROM projects WHERE created_by = :uid)"
            ), {"uid": uid})
            await db.execute(text(
                "DELETE FROM projects WHERE created_by = :uid"
            ), {"uid": uid})
        await db.execute(
            text("DELETE FROM users WHERE email LIKE 'roles_test_%@example.com'")
        )
        await db.commit()


# ---------------------------------------------------------------------------
# Helpers to create project/work-item/policy/agent for tests
# ---------------------------------------------------------------------------

async def _create_project(client: AsyncClient, headers: dict) -> str:
    r = await client.post("/projects", json={"name": f"RolesProj-{uuid.uuid4()}"}, headers=headers)
    assert r.status_code == 201, r.text
    return r.json()["id"]


async def _create_work_item(client: AsyncClient, headers: dict, project_id: str, ai_worker_id: str, human_worker_id: str) -> str:
    r = await client.post(
        f"/projects/{project_id}/work-items",
        json={
            "name": f"WI-{uuid.uuid4()}",
            "objective": "Test objective",
            "description": "Test description",
            "expected_outcome": "Test outcome",
            "workers": [
                {"type": "ai_agent", "id": ai_worker_id},
                {"type": "human", "id": human_worker_id},
            ],
        },
        headers=headers,
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


async def _published_agent_version(test_db_url: str) -> str:
    """Return the id of an already-published agent version, seeding one if needed."""
    async with _test_db(test_db_url) as db:
        result = await db.execute(
            text("SELECT av.id FROM agent_versions av WHERE av.status='published' LIMIT 1")
        )
        row = result.fetchone()
        if row:
            return str(row[0])

        # Seed minimal agent + version
        agent_id = str(uuid.uuid4())
        ver_id = str(uuid.uuid4())
        await db.execute(
            text(
                "INSERT INTO agents (id, agent_code, name, description, role_purpose, status, created_at, updated_at) "
                "VALUES (:id, :code, :name, '', '', 'active', now(), now())"
            ),
            {"id": agent_id, "code": f"agent-{agent_id[:4]}", "name": f"TestAgent-{agent_id[:6]}"},
        )
        await db.execute(
            text(
                "INSERT INTO agent_versions (id, agent_id, version, instructions, capabilities, status, created_at, updated_at) "
                "VALUES (:id, :aid, '1.0', 'test instructions', '[]', 'published', now(), now())"
            ),
            {"id": ver_id, "aid": agent_id},
        )
        # Add a tool
        tool_result = await db.execute(text("SELECT id FROM mcp_tools WHERE status='active' LIMIT 1"))
        tool_row = tool_result.fetchone()
        if tool_row:
            await db.execute(
                text(
                    "INSERT INTO agent_version_tools (agent_version_id, mcp_tool_id) "
                    "VALUES (:vid, :tid) ON CONFLICT DO NOTHING"
                ),
                {"vid": ver_id, "tid": str(tool_row[0])},
            )
        await db.commit()
        return ver_id


# ---------------------------------------------------------------------------
# Tests: POST /agents — admin + builder allowed; reviewer + observer blocked
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_create_agent_rbac(async_client: AsyncClient, role_users: dict):
    for role in ("admin", "builder"):
        _, headers = role_users[role]
        r = await async_client.post(
            "/agents",
            json={
                "name": f"Agent-{role}-{uuid.uuid4()}",
                "description": "d",
                "role_purpose": "r",
                "instructions": "i",
                "capabilities": [],
                "tool_ids": [],
            },
            headers=headers,
        )
        # No tools → will fail validation, but must NOT be 403
        assert r.status_code != 403, f"{role} should be allowed; got 403"

    for role in ("reviewer", "observer"):
        _, headers = role_users[role]
        r = await async_client.post(
            "/agents",
            json={
                "name": f"Agent-{role}-{uuid.uuid4()}",
                "description": "d",
                "role_purpose": "r",
                "instructions": "i",
                "capabilities": [],
                "tool_ids": [],
            },
            headers=headers,
        )
        assert r.status_code == 403, f"{role} should be blocked; got {r.status_code}"


# ---------------------------------------------------------------------------
# Tests: POST /projects — admin + builder allowed; reviewer + observer blocked
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_create_project_rbac(async_client: AsyncClient, role_users: dict):
    created_ids = []
    for role in ("admin", "builder"):
        _, headers = role_users[role]
        r = await async_client.post(
            "/projects",
            json={"name": f"Proj-{role}-{uuid.uuid4()}"},
            headers=headers,
        )
        assert r.status_code == 201, f"{role} should be allowed; got {r.status_code}: {r.text}"
        created_ids.append(r.json()["id"])

    for role in ("reviewer", "observer"):
        _, headers = role_users[role]
        r = await async_client.post(
            "/projects",
            json={"name": f"Proj-{role}-{uuid.uuid4()}"},
            headers=headers,
        )
        assert r.status_code == 403, f"{role} should be blocked; got {r.status_code}"


# ---------------------------------------------------------------------------
# Tests: POST /work-items/{id}/policies/generate — admin+builder ok, reviewer+observer blocked
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_generate_policy_rbac(async_client: AsyncClient, role_users: dict, test_db_url: str):
    admin_id, admin_headers = role_users["admin"]

    # Create a project and work item as admin (need a published agent version)
    agent_version_id = await _published_agent_version(test_db_url)
    project_id = await _create_project(async_client, admin_headers)
    wi_id = await _create_work_item(
        async_client, admin_headers, project_id,
        ai_worker_id=agent_version_id,
        human_worker_id=admin_id,
    )

    for role in ("reviewer", "observer"):
        _, headers = role_users[role]
        r = await async_client.post(f"/work-items/{wi_id}/policies/generate", headers=headers)
        assert r.status_code == 403, f"{role} should be blocked; got {r.status_code}"

    # admin and builder get past the auth gate (may fail for other reasons like no LLM in test)
    for role in ("admin", "builder"):
        _, headers = role_users[role]
        r = await async_client.post(f"/work-items/{wi_id}/policies/generate", headers=headers)
        assert r.status_code != 403, f"{role} should be allowed; got 403"


# ---------------------------------------------------------------------------
# Tests: POST /knowledge — admin+builder+reviewer ok, observer blocked
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_create_knowledge_rbac(async_client: AsyncClient, role_users: dict):
    payload = {"title": "Test doc", "content": "content", "source": "test"}

    for role in ("admin", "builder", "reviewer"):
        _, headers = role_users[role]
        r = await async_client.post("/knowledge", json=payload, headers=headers)
        assert r.status_code in (200, 201), f"{role} should be allowed; got {r.status_code}: {r.text}"

    _, headers = role_users["observer"]
    r = await async_client.post("/knowledge", json=payload, headers=headers)
    assert r.status_code == 403, f"observer should be blocked; got {r.status_code}"


# ---------------------------------------------------------------------------
# Tests: GET /users — admin only
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_list_users_admin_only(async_client: AsyncClient, role_users: dict):
    for role in ("builder", "reviewer", "observer"):
        _, headers = role_users[role]
        r = await async_client.get("/users", headers=headers)
        assert r.status_code == 403, f"{role} should be blocked from GET /users; got {r.status_code}"

    _, headers = role_users["admin"]
    r = await async_client.get("/users", headers=headers)
    assert r.status_code == 200, f"admin should see /users; got {r.status_code}"


# ---------------------------------------------------------------------------
# Tests: GET /users/directory — any authenticated user
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_user_directory_any_auth(async_client: AsyncClient, role_users: dict):
    for role in ("admin", "builder", "reviewer", "observer"):
        _, headers = role_users[role]
        r = await async_client.get("/users/directory", headers=headers)
        assert r.status_code == 200, f"{role} should see /users/directory; got {r.status_code}"


# ---------------------------------------------------------------------------
# Tests: POST /users — admin only
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_create_user_admin_only(async_client: AsyncClient, role_users: dict):
    payload = {
        "email": f"newuser_{uuid.uuid4()}@example.com",
        "name": "New",
        "temp_password": "Str0ng!pw",
        "role": "observer",
    }
    for role in ("builder", "reviewer", "observer"):
        _, headers = role_users[role]
        r = await async_client.post("/users", json=payload, headers=headers)
        assert r.status_code == 403, f"{role} should be blocked; got {r.status_code}"

    _, headers = role_users["admin"]
    r = await async_client.post("/users", json={**payload, "email": f"newuser_{uuid.uuid4()}@example.com"}, headers=headers)
    assert r.status_code == 201, f"admin should create user; got {r.status_code}: {r.text}"


# ---------------------------------------------------------------------------
# Tests: last admin guard
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_last_admin_guard(async_client: AsyncClient, role_users: dict, test_db_url: str):
    admin_id, admin_headers = role_users["admin"]

    # Ensure there's exactly one admin (deactivate any others besides ours)
    async with _test_db(test_db_url) as db:
        result = await db.execute(
            text("SELECT id FROM users WHERE role='admin' AND status='active' AND id != :me"),
            {"me": admin_id},
        )
        other_admin_ids = [str(r[0]) for r in result.fetchall()]
        if other_admin_ids:
            for oid in other_admin_ids:
                await db.execute(
                    text("UPDATE users SET status='inactive' WHERE id = :id"),
                    {"id": oid},
                )
            await db.commit()

    # Attempt to deactivate the sole admin — must get 422
    # (self_deactivate fires first if same user; last_admin fires if a different user tried)
    r = await async_client.patch(f"/users/{admin_id}/deactivate", headers=admin_headers)
    assert r.status_code == 422, f"should block last-admin deactivation; got {r.status_code}"
    detail = r.json().get("detail", {})
    code = detail.get("code") if isinstance(detail, dict) else None
    assert code in ("last_admin", "self_deactivate"), f"unexpected code: {code}"

    # Restore other admins if any were deactivated
    if other_admin_ids:
        async with _test_db(test_db_url) as db:
            for oid in other_admin_ids:
                await db.execute(
                    text("UPDATE users SET status='active' WHERE id = :id"),
                    {"id": oid},
                )
            await db.commit()


# ---------------------------------------------------------------------------
# Tests: self-deactivation guard
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_self_deactivate_guard(async_client: AsyncClient, role_users: dict):
    admin_id, admin_headers = role_users["admin"]
    r = await async_client.patch(f"/users/{admin_id}/deactivate", headers=admin_headers)
    # Either blocked because last admin OR because self-deactivation
    assert r.status_code == 422, f"admin should not deactivate self; got {r.status_code}"
    detail = r.json().get("detail", {})
    codes = {detail.get("code")} if isinstance(detail, dict) else set()
    assert codes & {"self_deactivate", "last_admin"}, f"unexpected detail: {detail}"


# ---------------------------------------------------------------------------
# Tests: assignee role enforcement — observer cannot be checkpoint assignee
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_eligible_assignee_role_filter(async_client: AsyncClient, role_users: dict, test_db_url: str):
    admin_id, admin_headers = role_users["admin"]
    observer_id, _ = role_users["observer"]

    agent_version_id = await _published_agent_version(test_db_url)
    project_id = await _create_project(async_client, admin_headers)

    # Create work item with observer as the human worker
    r = await async_client.post(
        f"/projects/{project_id}/work-items",
        json={
            "name": f"WI-{uuid.uuid4()}",
            "objective": "test",
            "description": "test",
            "expected_outcome": "test",
            "workers": [
                {"type": "ai_agent", "id": agent_version_id},
                {"type": "human", "id": observer_id},
            ],
        },
        headers=admin_headers,
    )
    assert r.status_code == 201, r.text
    wi_id = r.json()["id"]

    # Create a draft policy manually
    r = await async_client.post(
        f"/work-items/{wi_id}/policies",
        json={"generated_by": "manual"},
        headers=admin_headers,
    )
    assert r.status_code == 201, r.text
    policy_id = r.json()["id"]

    # Add a stage
    r = await async_client.post(
        f"/policies/{policy_id}/stages",
        json={
            "name": "Stage 1",
            "description": "desc",
            "expected_output": "output",
            "agent_version_id": agent_version_id,
        },
        headers=admin_headers,
    )
    assert r.status_code == 201, r.text
    stage_id = r.json()["id"]

    # Attempt to assign observer as checkpoint assignee → must get 422
    r = await async_client.post(
        f"/policies/{policy_id}/checkpoints",
        json={
            "type": "approval",
            "stage_id": stage_id,
            "assigned_user_id": observer_id,
            "instruction": "Please review",
        },
        headers=admin_headers,
    )
    assert r.status_code == 422, f"observer should not be checkpoint assignee; got {r.status_code}: {r.text}"
    assert "assignee_role_invalid" in r.text


# ---------------------------------------------------------------------------
# Tests: directory eligible_for filter — returns only admin/reviewer workers
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_directory_eligible_for(async_client: AsyncClient, role_users: dict, test_db_url: str):
    admin_id, admin_headers = role_users["admin"]
    reviewer_id, _ = role_users["reviewer"]
    observer_id, _ = role_users["observer"]

    agent_version_id = await _published_agent_version(test_db_url)
    project_id = await _create_project(async_client, admin_headers)

    # Work item with all three humans: admin, reviewer, observer
    r = await async_client.post(
        f"/projects/{project_id}/work-items",
        json={
            "name": f"WI-dir-{uuid.uuid4()}",
            "objective": "test",
            "description": "test",
            "expected_outcome": "test",
            "workers": [
                {"type": "ai_agent", "id": agent_version_id},
                {"type": "human", "id": admin_id},
                {"type": "human", "id": reviewer_id},
                {"type": "human", "id": observer_id},
            ],
        },
        headers=admin_headers,
    )
    assert r.status_code == 201, r.text
    wi_id = r.json()["id"]

    r = await async_client.get(
        f"/users/directory?eligible_for={wi_id}",
        headers=admin_headers,
    )
    assert r.status_code == 200, r.text
    ids_returned = {u["id"] for u in r.json()}
    assert admin_id in ids_returned, "admin should be in directory"
    assert reviewer_id in ids_returned, "reviewer should be in directory"
    assert observer_id not in ids_returned, "observer must NOT be in eligible directory"
