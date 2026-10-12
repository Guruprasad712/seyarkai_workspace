"""Agent module tests — all offline (no Vertex AI calls).

Uses the same _test_db / async_client pattern as test_auth.py.
"""
from __future__ import annotations

import asyncio
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
            {"id": user_id, "email": "agents_test@example.com", "name": "Test", "hp": hash_password("pw")},
        )
        await db.commit()

    token = create_access_token(user_id, "member")
    yield {"Authorization": f"Bearer {token}"}

    async with _test_db(test_db_url) as db:
        await db.execute(text("DELETE FROM users WHERE email = 'agents_test@example.com'"))
        await db.commit()


@pytest_asyncio.fixture()
async def active_tool_ids(test_db_url: str):
    """Return IDs of two active tools, seeding them if missing."""
    async with _test_db(test_db_url) as db:
        result = await db.execute(
            text("SELECT id FROM mcp_tools WHERE status = 'active' LIMIT 2")
        )
        rows = result.fetchall()
        if len(rows) >= 2:
            return [str(r[0]) for r in rows]

        # Seed the two tools so tests work even without running seed_mcp_tools
        for tool_name, name, server_key in [
            ("knowledge_search", "Knowledge Search", "knowledge"),
            ("generate_document", "Generate Document", "docs"),
        ]:
            await db.execute(
                text(
                    "INSERT INTO mcp_tools (id, name, tool_name, server_key, description, status, created_at, updated_at) "
                    "VALUES (gen_random_uuid(), :name, :tool_name, :sk, :desc, 'active', now(), now()) "
                    "ON CONFLICT (tool_name) DO UPDATE SET status='active'"
                ),
                {"name": name, "tool_name": tool_name, "sk": server_key, "desc": name},
            )
        await db.commit()

        result = await db.execute(
            text("SELECT id FROM mcp_tools WHERE status = 'active' LIMIT 2")
        )
        return [str(r[0]) for r in result.fetchall()]


@pytest_asyncio.fixture()
async def created_agent(test_db_url: str, active_tool_ids):
    """Insert one agent + version directly into the DB and return a dict matching the API shape."""
    agent_id = str(uuid.uuid4())
    version_id = str(uuid.uuid4())
    # Use a unique name per fixture invocation to avoid cross-test conflicts
    agent_name = f"Test Agent {agent_id[:8]}"
    async with _test_db(test_db_url) as db:
        seq = (await db.execute(text("SELECT nextval('agent_code_seq')"))).scalar_one()
        agent_code = f"agent-{seq:04d}"
        await db.execute(
            text(
                "INSERT INTO agents (id, agent_code, name, description, role_purpose, status, created_at, updated_at) "
                "VALUES (:id, :code, :name, :desc, :rp, 'draft', now(), now())"
            ),
            {"id": agent_id, "code": agent_code, "name": agent_name, "desc": "desc", "rp": "rp"},
        )
        await db.execute(
            text(
                "INSERT INTO agent_versions (id, agent_id, version, instructions, capabilities, status, published_at, created_at, updated_at) "
                "VALUES (:id, :aid, '1.0', :instr, CAST(:caps AS jsonb), 'draft', NULL, now(), now())"
            ),
            {
                "id": version_id,
                "aid": agent_id,
                "instr": "Do something useful.",
                "caps": '[{"name": "cap1", "description": "can do things"}]',
            },
        )
        if active_tool_ids:
            await db.execute(
                text(
                    "INSERT INTO agent_version_tools (agent_version_id, mcp_tool_id) VALUES (:vid, :tid)"
                ),
                {"vid": version_id, "tid": active_tool_ids[0]},
            )
        await db.commit()

    yield {
        "id": agent_id,
        "agent_code": agent_code,
        "name": agent_name,
        "status": "draft",
        "versions": [{"id": version_id, "status": "draft", "version": "1.0"}],
    }

    async with _test_db(test_db_url) as db:
        # Delete tools for ALL versions (tests may add more versions)
        await db.execute(
            text(
                "DELETE FROM agent_version_tools WHERE agent_version_id IN "
                "(SELECT id FROM agent_versions WHERE agent_id = :aid)"
            ),
            {"aid": agent_id},
        )
        await db.execute(text("DELETE FROM agent_versions WHERE agent_id = :aid"), {"aid": agent_id})
        await db.execute(text("DELETE FROM agents WHERE id = :id"), {"id": agent_id})
        await db.commit()


# ---------------------------------------------------------------------------
# mcp-tools
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_list_mcp_tools(async_client: AsyncClient, auth_headers, active_tool_ids):
    r = await async_client.get("/mcp-tools", headers=auth_headers)
    assert r.status_code == 200
    tools = r.json()
    assert isinstance(tools, list)
    assert len(tools) >= 1
    assert all("tool_name" in t for t in tools)


# ---------------------------------------------------------------------------
# POST /agents
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_create_agent_success(async_client: AsyncClient, auth_headers, active_tool_ids):
    name = f"Create Success Agent {uuid.uuid4().hex[:6]}"
    r = await async_client.post(
        "/agents",
        headers=auth_headers,
        json={
            "name": name,
            "description": "d",
            "role_purpose": "rp",
            "instructions": "i",
            "capabilities": [{"name": "c", "description": "cd"}],
            "tool_ids": active_tool_ids[:1],
        },
    )
    assert r.status_code == 201, r.text
    body = r.json()
    import re
    assert re.match(r"agent-\d{4}", body["agent_code"])
    assert body["status"] == "draft"
    assert len(body["versions"]) == 1
    assert body["versions"][0]["version"] == "1.0"
    assert body["versions"][0]["status"] == "draft"


@pytest.mark.anyio
async def test_create_agent_duplicate_name(async_client: AsyncClient, auth_headers):
    name = f"Duplicate Name Agent {uuid.uuid4().hex[:6]}"
    payload = {
        "name": name,
        "description": "d",
        "role_purpose": "rp",
        "instructions": "i",
        "capabilities": [{"name": "c", "description": "cd"}],
        "tool_ids": [],
    }
    r1 = await async_client.post("/agents", headers=auth_headers, json=payload)
    assert r1.status_code == 201
    r2 = await async_client.post("/agents", headers=auth_headers, json=payload)
    assert r2.status_code == 409


@pytest.mark.anyio
async def test_create_agent_unknown_tool(async_client: AsyncClient, auth_headers):
    r = await async_client.post(
        "/agents",
        headers=auth_headers,
        json={
            "name": "Unknown Tool Agent",
            "description": "d",
            "role_purpose": "rp",
            "instructions": "i",
            "capabilities": [{"name": "c", "description": "cd"}],
            "tool_ids": [str(uuid.uuid4())],
        },
    )
    assert r.status_code == 422


@pytest.mark.anyio
async def test_create_agent_inactive_tool(test_db_url: str, async_client: AsyncClient, auth_headers):
    # Insert an inactive tool
    inactive_id = str(uuid.uuid4())
    async with _test_db(test_db_url) as db:
        await db.execute(
            text(
                "INSERT INTO mcp_tools (id, name, tool_name, server_key, description, status, created_at, updated_at) "
                "VALUES (:id, 'Inactive', 'inactive_test_tool', 'x', 'x', 'inactive', now(), now()) "
                "ON CONFLICT (tool_name) DO UPDATE SET status='inactive'"
            ),
            {"id": inactive_id},
        )
        await db.commit()
        result = await db.execute(
            text("SELECT id FROM mcp_tools WHERE tool_name = 'inactive_test_tool'")
        )
        inactive_id = str(result.scalar_one())

    r = await async_client.post(
        "/agents",
        headers=auth_headers,
        json={
            "name": "Inactive Tool Agent",
            "description": "d",
            "role_purpose": "rp",
            "instructions": "i",
            "capabilities": [{"name": "c", "description": "cd"}],
            "tool_ids": [inactive_id],
        },
    )
    assert r.status_code == 422


# ---------------------------------------------------------------------------
# GET /agents and GET /agents/{id}
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_get_agent(async_client: AsyncClient, auth_headers, created_agent):
    agent_id = created_agent["id"]
    r = await async_client.get(f"/agents/{agent_id}", headers=auth_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["id"] == agent_id
    assert len(body["versions"]) >= 1


@pytest.mark.anyio
async def test_get_agent_not_found(async_client: AsyncClient, auth_headers):
    r = await async_client.get(f"/agents/{uuid.uuid4()}", headers=auth_headers)
    assert r.status_code == 404


@pytest.mark.anyio
async def test_list_agents(async_client: AsyncClient, auth_headers, created_agent):
    r = await async_client.get("/agents", headers=auth_headers)
    assert r.status_code == 200
    ids = [a["id"] for a in r.json()]
    assert created_agent["id"] in ids


# ---------------------------------------------------------------------------
# PATCH /agents/{id}
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_patch_agent_name(async_client: AsyncClient, auth_headers, created_agent):
    agent_id = created_agent["id"]
    r = await async_client.patch(
        f"/agents/{agent_id}", headers=auth_headers, json={"name": "Renamed Agent"}
    )
    assert r.status_code == 200
    assert r.json()["name"] == "Renamed Agent"


@pytest.mark.anyio
async def test_patch_agent_rename_to_own_name(async_client: AsyncClient, auth_headers, created_agent):
    agent_id = created_agent["id"]
    own_name = created_agent["name"]
    r = await async_client.patch(
        f"/agents/{agent_id}", headers=auth_headers, json={"name": own_name}
    )
    # Renaming to own name hits the unique constraint with itself — Postgres UPDATE
    # with same value doesn't raise a conflict. Should be 200.
    assert r.status_code == 200


@pytest.mark.anyio
async def test_patch_agent_rename_conflict(async_client: AsyncClient, auth_headers):
    suffix = uuid.uuid4().hex[:6]
    alpha_name = f"Conflict Alpha {suffix}"
    beta_name = f"Conflict Beta {suffix}"
    # Create two agents
    r1 = await async_client.post(
        "/agents", headers=auth_headers,
        json={"name": alpha_name, "description": "d", "role_purpose": "rp",
              "instructions": "i", "capabilities": [{"name": "c", "description": "cd"}], "tool_ids": []},
    )
    r2 = await async_client.post(
        "/agents", headers=auth_headers,
        json={"name": beta_name, "description": "d", "role_purpose": "rp",
              "instructions": "i", "capabilities": [{"name": "c", "description": "cd"}], "tool_ids": []},
    )
    assert r1.status_code == 201 and r2.status_code == 201
    # Try renaming Beta to Alpha's name
    r = await async_client.patch(
        f"/agents/{r2.json()['id']}", headers=auth_headers, json={"name": alpha_name}
    )
    assert r.status_code == 409


# ---------------------------------------------------------------------------
# POST /agents/{id}/versions
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_add_version(async_client: AsyncClient, auth_headers, created_agent, active_tool_ids):
    agent_id = created_agent["id"]
    r = await async_client.post(
        f"/agents/{agent_id}/versions",
        headers=auth_headers,
        json={
            "instructions": "New instructions",
            "capabilities": [{"name": "cap2", "description": "new cap"}],
            "tool_ids": active_tool_ids[:1],
        },
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["version"] == "2.0"
    assert body["status"] == "draft"


# ---------------------------------------------------------------------------
# PATCH /agents/{id}/versions/{vid}
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_patch_version_draft(async_client: AsyncClient, auth_headers, created_agent, active_tool_ids):
    agent_id = created_agent["id"]
    version_id = created_agent["versions"][0]["id"]
    r = await async_client.patch(
        f"/agents/{agent_id}/versions/{version_id}",
        headers=auth_headers,
        json={"instructions": "Updated instructions"},
    )
    assert r.status_code == 200
    assert r.json()["instructions"] == "Updated instructions"


@pytest.mark.anyio
async def test_patch_version_not_draft(async_client: AsyncClient, auth_headers, created_agent, active_tool_ids):
    """Publishing a version and then attempting to patch it should return 409."""
    agent_id = created_agent["id"]
    version_id = created_agent["versions"][0]["id"]

    # Publish the version first
    r_pub = await async_client.post(
        f"/agents/{agent_id}/versions/{version_id}/publish",
        headers=auth_headers,
    )
    assert r_pub.status_code == 200, r_pub.text

    # Now try to patch the published version
    r = await async_client.patch(
        f"/agents/{agent_id}/versions/{version_id}",
        headers=auth_headers,
        json={"instructions": "Should fail"},
    )
    assert r.status_code == 409


# ---------------------------------------------------------------------------
# POST /agents/{id}/versions/{vid}/publish
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_publish_success(async_client: AsyncClient, auth_headers, created_agent):
    agent_id = created_agent["id"]
    version_id = created_agent["versions"][0]["id"]

    r = await async_client.post(
        f"/agents/{agent_id}/versions/{version_id}/publish",
        headers=auth_headers,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "published"
    assert body["published_at"] is not None

    # Agent should now be active
    r_agent = await async_client.get(f"/agents/{agent_id}", headers=auth_headers)
    assert r_agent.json()["status"] == "active"


@pytest.mark.anyio
async def test_publish_retires_previous(async_client: AsyncClient, auth_headers, created_agent, active_tool_ids):
    agent_id = created_agent["id"]
    v1_id = created_agent["versions"][0]["id"]

    # Publish v1
    r1 = await async_client.post(
        f"/agents/{agent_id}/versions/{v1_id}/publish", headers=auth_headers
    )
    assert r1.status_code == 200

    # Add v2
    r_v2 = await async_client.post(
        f"/agents/{agent_id}/versions",
        headers=auth_headers,
        json={
            "instructions": "v2 instructions",
            "capabilities": [{"name": "c", "description": "d"}],
            "tool_ids": active_tool_ids[:1],
        },
    )
    assert r_v2.status_code == 201
    v2_id = r_v2.json()["id"]

    # Publish v2
    r2 = await async_client.post(
        f"/agents/{agent_id}/versions/{v2_id}/publish", headers=auth_headers
    )
    assert r2.status_code == 200

    # Check that v1 is now retired
    r_agent = await async_client.get(f"/agents/{agent_id}", headers=auth_headers)
    versions = {v["id"]: v for v in r_agent.json()["versions"]}
    assert versions[v1_id]["status"] == "retired"
    assert versions[v2_id]["status"] == "published"


@pytest.mark.anyio
async def test_publish_collect_all_failures(
    test_db_url: str, async_client: AsyncClient, auth_headers
):
    """A version with empty instructions, no capabilities, and no tools → 3 failures."""
    # Create agent with minimal valid data
    r = await async_client.post(
        "/agents",
        headers=auth_headers,
        json={
            "name": "Fail All Agent",
            "description": "d",
            "role_purpose": "rp",
            "instructions": "placeholder",
            "capabilities": [{"name": "c", "description": "d"}],
            "tool_ids": [],
        },
    )
    assert r.status_code == 201
    agent_id = r.json()["id"]
    version_id = r.json()["versions"][0]["id"]

    # Blank out instructions, capabilities, and tools directly in DB
    async with _test_db(test_db_url) as db:
        await db.execute(
            text(
                "UPDATE agent_versions SET instructions='', capabilities='[]' "
                "WHERE id = :vid"
            ),
            {"vid": version_id},
        )
        await db.commit()

    r_pub = await async_client.post(
        f"/agents/{agent_id}/versions/{version_id}/publish",
        headers=auth_headers,
    )
    assert r_pub.status_code == 422
    detail = r_pub.json()["detail"]
    assert detail["error"] == "publish_validation_failed"
    codes = {f["code"] for f in detail["failures"]}
    assert "missing_instructions" in codes
    assert "no_capabilities" in codes
    assert "no_tools" in codes


@pytest.mark.anyio
async def test_publish_inactive_tool_failure(
    test_db_url: str, async_client: AsyncClient, auth_headers
):
    # Insert inactive tool
    inactive_id = str(uuid.uuid4())
    async with _test_db(test_db_url) as db:
        await db.execute(
            text(
                "INSERT INTO mcp_tools (id, name, tool_name, server_key, description, status, created_at, updated_at) "
                "VALUES (:id, 'Inactive2', 'inactive_tool2', 'x', 'x', 'active', now(), now()) "
                "ON CONFLICT (tool_name) DO UPDATE SET status='active', id=:id"
            ),
            {"id": inactive_id},
        )
        await db.commit()
        result = await db.execute(
            text("SELECT id FROM mcp_tools WHERE tool_name = 'inactive_tool2'")
        )
        inactive_id = str(result.scalar_one())

    # Create agent with that tool
    r = await async_client.post(
        "/agents",
        headers=auth_headers,
        json={
            "name": "Inactive Tool Publish Agent",
            "description": "d",
            "role_purpose": "rp",
            "instructions": "valid instructions",
            "capabilities": [{"name": "c", "description": "d"}],
            "tool_ids": [inactive_id],
        },
    )
    assert r.status_code == 201
    agent_id = r.json()["id"]
    version_id = r.json()["versions"][0]["id"]

    # Now mark the tool inactive in the DB
    async with _test_db(test_db_url) as db:
        await db.execute(
            text("UPDATE mcp_tools SET status='inactive' WHERE id = :id"),
            {"id": inactive_id},
        )
        await db.commit()

    r_pub = await async_client.post(
        f"/agents/{agent_id}/versions/{version_id}/publish",
        headers=auth_headers,
    )
    assert r_pub.status_code == 422
    codes = {f["code"] for f in r_pub.json()["detail"]["failures"]}
    assert "inactive_tool" in codes


@pytest.mark.anyio
async def test_publish_not_draft(async_client: AsyncClient, auth_headers, created_agent):
    agent_id = created_agent["id"]
    version_id = created_agent["versions"][0]["id"]

    # First publish succeeds
    r1 = await async_client.post(
        f"/agents/{agent_id}/versions/{version_id}/publish", headers=auth_headers
    )
    assert r1.status_code == 200

    # Second publish on same version → not_draft failure
    r2 = await async_client.post(
        f"/agents/{agent_id}/versions/{version_id}/publish", headers=auth_headers
    )
    assert r2.status_code == 422
    codes = {f["code"] for f in r2.json()["detail"]["failures"]}
    assert "not_draft" in codes


@pytest.mark.anyio
async def test_concurrent_double_publish(async_client: AsyncClient, auth_headers, created_agent):
    """Two simultaneous publish requests: exactly one succeeds, one gets 422 not_draft."""
    agent_id = created_agent["id"]
    version_id = created_agent["versions"][0]["id"]

    async def do_publish():
        return await async_client.post(
            f"/agents/{agent_id}/versions/{version_id}/publish",
            headers=auth_headers,
        )

    r1, r2 = await asyncio.gather(do_publish(), do_publish())
    statuses = sorted([r1.status_code, r2.status_code])
    assert statuses == [200, 422], f"Expected [200, 422], got {statuses}"

    # The 422 must be a not_draft failure
    failed = r1 if r1.status_code == 422 else r2
    codes = {f["code"] for f in failed.json()["detail"]["failures"]}
    assert "not_draft" in codes
