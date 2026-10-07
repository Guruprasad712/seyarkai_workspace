"""Projects + work items tests — all offline (no Vertex AI calls)."""
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
async def auth_headers(test_db_url: str, async_client: AsyncClient):
    user_id = str(uuid.uuid4())
    async with _test_db(test_db_url) as db:
        await db.execute(
            text(
                "INSERT INTO users (id, email, name, hashed_password, role, status, created_at, updated_at) "
                "VALUES (:id, :email, :name, :hp, 'member', 'active', now(), now())"
            ),
            {"id": user_id, "email": "projects_test@example.com", "name": "Test", "hp": hash_password("pw")},
        )
        await db.commit()

    token = create_access_token(user_id, "member")
    yield {"Authorization": f"Bearer {token}", "_user_id": user_id}

    async with _test_db(test_db_url) as db:
        # Remove projects (and their work items + workers) owned by the test user
        await db.execute(
            text(
                "DELETE FROM work_item_workers WHERE work_item_id IN "
                "(SELECT wi.id FROM work_items wi "
                " JOIN projects p ON wi.project_id = p.id "
                " WHERE p.created_by = :uid)"
            ),
            {"uid": user_id},
        )
        await db.execute(
            text(
                "DELETE FROM work_items WHERE project_id IN "
                "(SELECT id FROM projects WHERE created_by = :uid)"
            ),
            {"uid": user_id},
        )
        await db.execute(text("DELETE FROM projects WHERE created_by = :uid"), {"uid": user_id})
        await db.execute(text("DELETE FROM users WHERE email = 'projects_test@example.com'"))
        await db.commit()


@pytest_asyncio.fixture()
async def created_project(test_db_url: str, auth_headers):
    """Insert a project directly and return its id + owner user_id."""
    project_id = str(uuid.uuid4())
    user_id = auth_headers["_user_id"]
    project_name = f"Test Project {project_id[:8]}"
    async with _test_db(test_db_url) as db:
        await db.execute(
            text(
                "INSERT INTO projects (id, name, description, status, created_by, created_at, updated_at) "
                "VALUES (:id, :name, :desc, 'active', :uid, now(), now())"
            ),
            {"id": project_id, "name": project_name, "desc": "A test project", "uid": user_id},
        )
        await db.commit()

    yield {"id": project_id, "name": project_name, "user_id": user_id}

    async with _test_db(test_db_url) as db:
        # cascade: workers → work_items → project
        await db.execute(
            text(
                "DELETE FROM work_item_workers WHERE work_item_id IN "
                "(SELECT id FROM work_items WHERE project_id = :pid)"
            ),
            {"pid": project_id},
        )
        await db.execute(text("DELETE FROM work_items WHERE project_id = :pid"), {"pid": project_id})
        await db.execute(text("DELETE FROM projects WHERE id = :pid"), {"pid": project_id})
        await db.commit()


@pytest_asyncio.fixture()
async def published_agent_version(test_db_url: str):
    """Insert an agent + published version + one active tool. Return version id."""
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
            {"id": agent_id, "code": f"agent-{seq:04d}", "name": f"WI Agent {agent_id[:8]}"},
        )
        await db.execute(
            text(
                "INSERT INTO mcp_tools (id, name, tool_name, server_key, description, status, created_at, updated_at) "
                "VALUES (:id, :name, :tool_name, 'knowledge', 'desc', 'active', now(), now()) "
                "ON CONFLICT (tool_name) DO UPDATE SET status='active' RETURNING id"
            ),
            {"id": tool_id, "name": f"Tool {tool_id[:8]}", "tool_name": f"tool_{tool_id[:8]}"},
        )
        # use the actual id (may differ if ON CONFLICT updated)
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
        # Remove work item workers referencing this version before deleting it
        await db.execute(
            text("DELETE FROM work_item_workers WHERE agent_version_id = :vid"),
            {"vid": version_id},
        )
        await db.execute(text("DELETE FROM agent_version_tools WHERE agent_version_id = :vid"), {"vid": version_id})
        await db.execute(text("DELETE FROM agent_versions WHERE id = :vid"), {"vid": version_id})
        await db.execute(text("DELETE FROM agents WHERE id = :aid"), {"aid": agent_id})
        await db.commit()


@pytest_asyncio.fixture()
async def inactive_user(test_db_url: str):
    """Insert an inactive user. Return its id."""
    user_id = str(uuid.uuid4())
    async with _test_db(test_db_url) as db:
        await db.execute(
            text(
                "INSERT INTO users (id, email, name, hashed_password, role, status, created_at, updated_at) "
                "VALUES (:id, :email, 'Inactive', :hp, 'member', 'inactive', now(), now())"
            ),
            {"id": user_id, "email": f"inactive_{user_id[:8]}@example.com", "hp": hash_password("pw")},
        )
        await db.commit()
    yield user_id
    async with _test_db(test_db_url) as db:
        await db.execute(text("DELETE FROM users WHERE id = :id"), {"id": user_id})
        await db.commit()


# ---------------------------------------------------------------------------
# Project CRUD tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_create_project(async_client: AsyncClient, auth_headers):
    r = await async_client.post(
        "/projects",
        json={"name": f"My Project {uuid.uuid4().hex[:6]}", "description": "desc"},
        headers=auth_headers,
    )
    assert r.status_code == 201
    data = r.json()
    assert data["name"].startswith("My Project")
    assert data["status"] == "active"
    assert data["work_item_count"] == 0


@pytest.mark.asyncio
async def test_create_project_duplicate_name(async_client: AsyncClient, auth_headers, created_project):
    r = await async_client.post(
        "/projects",
        json={"name": created_project["name"]},
        headers=auth_headers,
    )
    assert r.status_code == 409


@pytest.mark.asyncio
async def test_list_projects(async_client: AsyncClient, auth_headers, created_project):
    r = await async_client.get("/projects", headers=auth_headers)
    assert r.status_code == 200
    ids = [p["id"] for p in r.json()]
    assert created_project["id"] in ids


@pytest.mark.asyncio
async def test_get_project(async_client: AsyncClient, auth_headers, created_project):
    r = await async_client.get(f"/projects/{created_project['id']}", headers=auth_headers)
    assert r.status_code == 200
    assert r.json()["id"] == created_project["id"]


@pytest.mark.asyncio
async def test_get_project_not_found(async_client: AsyncClient, auth_headers):
    r = await async_client.get(f"/projects/{uuid.uuid4()}", headers=auth_headers)
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_patch_project_name(async_client: AsyncClient, auth_headers, created_project):
    new_name = f"Renamed {uuid.uuid4().hex[:6]}"
    r = await async_client.patch(
        f"/projects/{created_project['id']}",
        json={"name": new_name},
        headers=auth_headers,
    )
    assert r.status_code == 200
    assert r.json()["name"] == new_name


@pytest.mark.asyncio
async def test_patch_project_status(async_client: AsyncClient, auth_headers, created_project):
    r = await async_client.patch(
        f"/projects/{created_project['id']}",
        json={"status": "inactive"},
        headers=auth_headers,
    )
    assert r.status_code == 200
    assert r.json()["status"] == "inactive"


@pytest.mark.asyncio
async def test_patch_project_duplicate_name(async_client: AsyncClient, auth_headers, created_project):
    # Create a second project
    other_name = f"Other {uuid.uuid4().hex[:6]}"
    r = await async_client.post("/projects", json={"name": other_name}, headers=auth_headers)
    assert r.status_code == 201

    # Rename created_project to other_name → conflict
    r = await async_client.patch(
        f"/projects/{created_project['id']}",
        json={"name": other_name},
        headers=auth_headers,
    )
    assert r.status_code == 409


# ---------------------------------------------------------------------------
# Work item tests
# ---------------------------------------------------------------------------

def _wi_body(agent_version_id: str, **overrides) -> dict:
    base = {
        "name": f"WI {uuid.uuid4().hex[:6]}",
        "objective": "do the thing",
        "description": "context",
        "expected_outcome": "result",
        "workers": [{"type": "ai_agent", "id": agent_version_id}],
    }
    base.update(overrides)
    return base


@pytest.mark.asyncio
async def test_create_work_item(
    async_client: AsyncClient, auth_headers, created_project, published_agent_version
):
    r = await async_client.post(
        f"/projects/{created_project['id']}/work-items",
        json=_wi_body(published_agent_version),
        headers=auth_headers,
    )
    assert r.status_code == 201
    data = r.json()
    assert data["status"] == "new"
    assert len(data["workers"]) == 1
    assert data["workers"][0]["type"] == "ai_agent"
    assert data["workers"][0]["agent_version"] == "1.0"


@pytest.mark.asyncio
async def test_create_work_item_no_workers(
    async_client: AsyncClient, auth_headers, created_project
):
    r = await async_client.post(
        f"/projects/{created_project['id']}/work-items",
        json={
            "name": "WI", "objective": "obj", "description": "desc",
            "expected_outcome": "out", "workers": [],
        },
        headers=auth_headers,
    )
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_create_work_item_unpublished_agent(
    async_client: AsyncClient, auth_headers, created_project, test_db_url
):
    # Insert a draft agent version
    draft_version_id = str(uuid.uuid4())
    agent_id = str(uuid.uuid4())
    async with _test_db(test_db_url) as db:
        seq = (await db.execute(text("SELECT nextval('agent_code_seq')"))).scalar_one()
        await db.execute(
            text(
                "INSERT INTO agents (id, agent_code, name, description, role_purpose, status, created_at, updated_at) "
                "VALUES (:id, :code, :name, 'desc', 'p', 'draft', now(), now())"
            ),
            {"id": agent_id, "code": f"agent-{seq:04d}", "name": f"Draft Agent {agent_id[:8]}"},
        )
        await db.execute(
            text(
                "INSERT INTO agent_versions (id, agent_id, version, instructions, capabilities, status, created_at, updated_at) "
                "VALUES (:id, :aid, '1.0', 'x', CAST(:caps AS jsonb), 'draft', now(), now())"
            ),
            {"id": draft_version_id, "aid": agent_id, "caps": "[]"},
        )
        await db.commit()

    r = await async_client.post(
        f"/projects/{created_project['id']}/work-items",
        json=_wi_body(draft_version_id),
        headers=auth_headers,
    )
    assert r.status_code == 422

    async with _test_db(test_db_url) as db:
        await db.execute(text("DELETE FROM agent_versions WHERE id = :id"), {"id": draft_version_id})
        await db.execute(text("DELETE FROM agents WHERE id = :id"), {"id": agent_id})
        await db.commit()


@pytest.mark.asyncio
async def test_create_work_item_inactive_user(
    async_client: AsyncClient, auth_headers, created_project, inactive_user
):
    r = await async_client.post(
        f"/projects/{created_project['id']}/work-items",
        json={
            "name": f"WI {uuid.uuid4().hex[:6]}",
            "objective": "obj", "description": "desc", "expected_outcome": "out",
            "workers": [{"type": "human", "id": inactive_user}],
        },
        headers=auth_headers,
    )
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_create_work_item_ai_and_human_workers(
    async_client: AsyncClient, auth_headers, created_project, published_agent_version
):
    human_id = auth_headers["_user_id"]
    r = await async_client.post(
        f"/projects/{created_project['id']}/work-items",
        json={
            "name": f"WI {uuid.uuid4().hex[:6]}",
            "objective": "obj", "description": "desc", "expected_outcome": "out",
            "workers": [
                {"type": "ai_agent", "id": published_agent_version},
                {"type": "human", "id": human_id},
            ],
        },
        headers=auth_headers,
    )
    assert r.status_code == 201
    types = {w["type"] for w in r.json()["workers"]}
    assert types == {"ai_agent", "human"}


@pytest.mark.asyncio
async def test_create_work_item_duplicate_name_same_project(
    async_client: AsyncClient, auth_headers, created_project, published_agent_version
):
    name = f"Dup WI {uuid.uuid4().hex[:6]}"
    body = _wi_body(published_agent_version, name=name)
    r1 = await async_client.post(
        f"/projects/{created_project['id']}/work-items", json=body, headers=auth_headers
    )
    assert r1.status_code == 201
    r2 = await async_client.post(
        f"/projects/{created_project['id']}/work-items", json=body, headers=auth_headers
    )
    assert r2.status_code == 409


@pytest.mark.asyncio
async def test_create_work_item_same_name_different_projects(
    async_client: AsyncClient, auth_headers, created_project, published_agent_version
):
    # Create a second project
    r = await async_client.post(
        "/projects", json={"name": f"Proj2 {uuid.uuid4().hex[:6]}"}, headers=auth_headers
    )
    assert r.status_code == 201
    proj2_id = r.json()["id"]

    name = f"Shared WI {uuid.uuid4().hex[:6]}"
    body = _wi_body(published_agent_version, name=name)
    r1 = await async_client.post(
        f"/projects/{created_project['id']}/work-items", json=body, headers=auth_headers
    )
    r2 = await async_client.post(
        f"/projects/{proj2_id}/work-items", json=body, headers=auth_headers
    )
    assert r1.status_code == 201
    assert r2.status_code == 201  # different project → no conflict


@pytest.mark.asyncio
async def test_list_work_items(
    async_client: AsyncClient, auth_headers, created_project, published_agent_version
):
    # Create one work item first
    await async_client.post(
        f"/projects/{created_project['id']}/work-items",
        json=_wi_body(published_agent_version),
        headers=auth_headers,
    )
    r = await async_client.get(
        f"/projects/{created_project['id']}/work-items", headers=auth_headers
    )
    assert r.status_code == 200
    assert len(r.json()) >= 1


@pytest.mark.asyncio
async def test_get_work_item(
    async_client: AsyncClient, auth_headers, created_project, published_agent_version
):
    r = await async_client.post(
        f"/projects/{created_project['id']}/work-items",
        json=_wi_body(published_agent_version),
        headers=auth_headers,
    )
    wi_id = r.json()["id"]

    r = await async_client.get(f"/work-items/{wi_id}", headers=auth_headers)
    assert r.status_code == 200
    data = r.json()
    assert data["id"] == wi_id
    assert len(data["workers"]) == 1
    assert data["workers"][0]["agent_name"] is not None


@pytest.mark.asyncio
async def test_patch_work_item(
    async_client: AsyncClient, auth_headers, created_project, published_agent_version
):
    r = await async_client.post(
        f"/projects/{created_project['id']}/work-items",
        json=_wi_body(published_agent_version),
        headers=auth_headers,
    )
    wi_id = r.json()["id"]

    r = await async_client.patch(
        f"/work-items/{wi_id}",
        json={"objective": "updated objective", "previous_output": "prior context"},
        headers=auth_headers,
    )
    assert r.status_code == 200
    data = r.json()
    assert data["objective"] == "updated objective"
    assert data["previous_output"] == "prior context"
    assert data["status"] == "new"  # status unchanged by patch
