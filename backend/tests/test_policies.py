"""Policy engine tests — all offline (no Vertex AI calls)."""
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
            {"id": user_id, "email": f"policy_test_{user_id[:8]}@example.com", "name": "Policy Test", "hp": hash_password("pw")},
        )
        await db.commit()

    token = create_access_token(user_id, "member")
    yield {"Authorization": f"Bearer {token}", "_user_id": user_id}

    async with _test_db(test_db_url) as db:
        await db.execute(
            text("DELETE FROM checkpoints WHERE policy_id IN (SELECT po.id FROM policies po JOIN work_items wi ON po.work_item_id = wi.id JOIN projects p ON wi.project_id = p.id WHERE p.created_by = :uid)"),
            {"uid": user_id},
        )
        await db.execute(
            text("DELETE FROM policy_stages WHERE policy_id IN (SELECT po.id FROM policies po JOIN work_items wi ON po.work_item_id = wi.id JOIN projects p ON wi.project_id = p.id WHERE p.created_by = :uid)"),
            {"uid": user_id},
        )
        await db.execute(
            text("DELETE FROM policies WHERE work_item_id IN (SELECT wi.id FROM work_items wi JOIN projects p ON wi.project_id = p.id WHERE p.created_by = :uid)"),
            {"uid": user_id},
        )
        await db.execute(
            text("DELETE FROM work_item_workers WHERE work_item_id IN (SELECT wi.id FROM work_items wi JOIN projects p ON wi.project_id = p.id WHERE p.created_by = :uid)"),
            {"uid": user_id},
        )
        await db.execute(
            text("DELETE FROM work_items WHERE project_id IN (SELECT id FROM projects WHERE created_by = :uid)"),
            {"uid": user_id},
        )
        await db.execute(text("DELETE FROM projects WHERE created_by = :uid"), {"uid": user_id})
        await db.execute(text("DELETE FROM users WHERE id = :uid"), {"uid": user_id})
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
            {"id": agent_id, "code": f"agent-{seq:04d}", "name": f"Policy Agent {agent_id[:8]}"},
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
async def created_work_item(test_db_url: str, auth_headers, published_agent_version):
    """Insert project + work item + AI worker + human worker (auth user). Return work_item_id."""
    project_id = str(uuid.uuid4())
    wi_id = str(uuid.uuid4())
    user_id = auth_headers["_user_id"]

    async with _test_db(test_db_url) as db:
        project_name = f"Policy Project {project_id[:8]}"
        await db.execute(
            text(
                "INSERT INTO projects (id, name, description, status, created_by, created_at, updated_at) "
                "VALUES (:id, :name, 'desc', 'active', :uid, now(), now())"
            ),
            {"id": project_id, "name": project_name, "uid": user_id},
        )
        await db.execute(
            text(
                "INSERT INTO work_items (id, project_id, name, objective, description, expected_outcome, status, created_by, created_at, updated_at) "
                "VALUES (:id, :pid, :name, 'obj', 'desc', 'outcome', 'new', :uid, now(), now())"
            ),
            {"id": wi_id, "pid": project_id, "name": f"WI {wi_id[:8]}", "uid": user_id},
        )
        # AI worker
        await db.execute(
            text(
                "INSERT INTO work_item_workers (id, work_item_id, worker_type, agent_version_id, user_id, created_at, updated_at) "
                "VALUES (:id, :wid, 'ai_agent', :vid, NULL, now(), now())"
            ),
            {"id": str(uuid.uuid4()), "wid": wi_id, "vid": published_agent_version},
        )
        # Human worker (the test user)
        await db.execute(
            text(
                "INSERT INTO work_item_workers (id, work_item_id, worker_type, agent_version_id, user_id, created_at, updated_at) "
                "VALUES (:id, :wid, 'human', NULL, :uid, now(), now())"
            ),
            {"id": str(uuid.uuid4()), "wid": wi_id, "uid": user_id},
        )
        await db.commit()

    yield {"id": wi_id, "project_id": project_id, "user_id": user_id}

    async with _test_db(test_db_url) as db:
        await db.execute(text("DELETE FROM checkpoints WHERE policy_id IN (SELECT id FROM policies WHERE work_item_id = :wid)"), {"wid": wi_id})
        await db.execute(text("DELETE FROM policy_stages WHERE policy_id IN (SELECT id FROM policies WHERE work_item_id = :wid)"), {"wid": wi_id})
        await db.execute(text("DELETE FROM policies WHERE work_item_id = :wid"), {"wid": wi_id})
        await db.execute(text("DELETE FROM work_item_workers WHERE work_item_id = :wid"), {"wid": wi_id})
        await db.execute(text("DELETE FROM work_items WHERE id = :wid"), {"wid": wi_id})
        await db.execute(text("DELETE FROM projects WHERE id = :pid"), {"pid": project_id})
        await db.commit()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _create_policy(client: AsyncClient, wi_id: str, headers: dict) -> dict:
    r = await client.post(f"/work-items/{wi_id}/policies", json={}, headers=headers)
    assert r.status_code == 201, r.text
    return r.json()


async def _add_stage(client: AsyncClient, policy_id: str, agent_version_id: str, headers: dict, name: str = "Stage") -> dict:
    r = await client.post(
        f"/policies/{policy_id}/stages",
        json={"name": name, "description": "desc", "expected_output": "output", "agent_version_id": agent_version_id},
        headers=headers,
    )
    assert r.status_code == 201, r.text
    return r.json()


async def _add_final_review(client: AsyncClient, policy_id: str, user_id: str, headers: dict) -> dict:
    r = await client.post(
        f"/policies/{policy_id}/checkpoints",
        json={"type": "final_review", "stage_id": None, "assigned_user_id": user_id, "instruction": "approve"},
        headers=headers,
    )
    assert r.status_code == 201, r.text
    return r.json()


# ---------------------------------------------------------------------------
# Policy CRUD
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_create_policy(async_client: AsyncClient, auth_headers, created_work_item):
    r = await async_client.post(
        f"/work-items/{created_work_item['id']}/policies",
        json={},
        headers=auth_headers,
    )
    assert r.status_code == 201
    data = r.json()
    assert data["status"] == "draft"
    assert data["version"] == 1
    assert data["stages"] == []
    assert data["checkpoints"] == []


@pytest.mark.asyncio
async def test_create_policy_version_increments(async_client: AsyncClient, auth_headers, created_work_item, test_db_url):
    # Insert a published policy manually so version should be 2 for new draft
    wi_id = created_work_item["id"]
    policy_id = str(uuid.uuid4())
    async with _test_db(test_db_url) as db:
        await db.execute(
            text(
                "INSERT INTO policies (id, work_item_id, version, status, generated_by, created_at, updated_at) "
                "VALUES (:id, :wid, 1, 'published', 'manual', now(), now())"
            ),
            {"id": policy_id, "wid": wi_id},
        )
        await db.commit()

    r = await async_client.post(f"/work-items/{wi_id}/policies", json={}, headers=auth_headers)
    assert r.status_code == 201
    assert r.json()["version"] == 2

    async with _test_db(test_db_url) as db:
        await db.execute(text("DELETE FROM policies WHERE id = :id"), {"id": policy_id})
        await db.commit()


@pytest.mark.asyncio
async def test_create_policy_duplicate_draft(async_client: AsyncClient, auth_headers, created_work_item):
    wi_id = created_work_item["id"]
    r1 = await async_client.post(f"/work-items/{wi_id}/policies", json={}, headers=auth_headers)
    assert r1.status_code == 201
    r2 = await async_client.post(f"/work-items/{wi_id}/policies", json={}, headers=auth_headers)
    assert r2.status_code == 409


@pytest.mark.asyncio
async def test_list_policies(async_client: AsyncClient, auth_headers, created_work_item):
    wi_id = created_work_item["id"]
    await _create_policy(async_client, wi_id, auth_headers)
    r = await async_client.get(f"/work-items/{wi_id}/policies", headers=auth_headers)
    assert r.status_code == 200
    assert len(r.json()) >= 1


@pytest.mark.asyncio
async def test_list_policies_work_item_not_found(async_client: AsyncClient, auth_headers):
    r = await async_client.get(f"/work-items/{uuid.uuid4()}/policies", headers=auth_headers)
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_get_policy(async_client: AsyncClient, auth_headers, created_work_item):
    policy = await _create_policy(async_client, created_work_item["id"], auth_headers)
    r = await async_client.get(f"/policies/{policy['id']}", headers=auth_headers)
    assert r.status_code == 200
    data = r.json()
    assert data["id"] == policy["id"]
    assert "stages" in data
    assert "checkpoints" in data


@pytest.mark.asyncio
async def test_get_policy_not_found(async_client: AsyncClient, auth_headers):
    r = await async_client.get(f"/policies/{uuid.uuid4()}", headers=auth_headers)
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# Stages
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_add_stage(async_client: AsyncClient, auth_headers, created_work_item, published_agent_version):
    policy = await _create_policy(async_client, created_work_item["id"], auth_headers)
    stage = await _add_stage(async_client, policy["id"], published_agent_version, auth_headers)
    assert stage["sequence"] == 1
    assert stage["name"] == "Stage"


@pytest.mark.asyncio
async def test_add_two_stages_sequences(async_client: AsyncClient, auth_headers, created_work_item, published_agent_version):
    policy = await _create_policy(async_client, created_work_item["id"], auth_headers)
    pid = policy["id"]
    s1 = await _add_stage(async_client, pid, published_agent_version, auth_headers, name="Stage One")
    s2 = await _add_stage(async_client, pid, published_agent_version, auth_headers, name="Stage Two")
    assert s1["sequence"] == 1
    assert s2["sequence"] == 2


@pytest.mark.asyncio
async def test_patch_stage(async_client: AsyncClient, auth_headers, created_work_item, published_agent_version):
    policy = await _create_policy(async_client, created_work_item["id"], auth_headers)
    stage = await _add_stage(async_client, policy["id"], published_agent_version, auth_headers)
    r = await async_client.patch(
        f"/policies/{policy['id']}/stages/{stage['id']}",
        json={"name": "Renamed", "description": "new desc"},
        headers=auth_headers,
    )
    assert r.status_code == 200
    assert r.json()["name"] == "Renamed"
    assert r.json()["description"] == "new desc"


@pytest.mark.asyncio
async def test_delete_stage_renumbers(async_client: AsyncClient, auth_headers, created_work_item, published_agent_version):
    policy = await _create_policy(async_client, created_work_item["id"], auth_headers)
    pid = policy["id"]
    s1 = await _add_stage(async_client, pid, published_agent_version, auth_headers, name="A")
    s2 = await _add_stage(async_client, pid, published_agent_version, auth_headers, name="B")
    s3 = await _add_stage(async_client, pid, published_agent_version, auth_headers, name="C")

    # Delete middle stage
    r = await async_client.delete(f"/policies/{pid}/stages/{s2['id']}", headers=auth_headers)
    assert r.status_code == 204

    r = await async_client.get(f"/policies/{pid}", headers=auth_headers)
    stages = r.json()["stages"]
    assert len(stages) == 2
    seqs = [s["sequence"] for s in stages]
    assert seqs == [1, 2]
    names = [s["name"] for s in stages]
    assert "A" in names and "C" in names


@pytest.mark.asyncio
async def test_delete_stage_not_found(async_client: AsyncClient, auth_headers, created_work_item, published_agent_version):
    policy = await _create_policy(async_client, created_work_item["id"], auth_headers)
    r = await async_client.delete(f"/policies/{policy['id']}/stages/{uuid.uuid4()}", headers=auth_headers)
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_delete_stage_with_checkpoint_fails(
    async_client: AsyncClient, auth_headers, created_work_item, published_agent_version
):
    policy = await _create_policy(async_client, created_work_item["id"], auth_headers)
    pid = policy["id"]
    stage = await _add_stage(async_client, pid, published_agent_version, auth_headers)

    # Add checkpoint on this stage
    r = await async_client.post(
        f"/policies/{pid}/checkpoints",
        json={"type": "approval", "stage_id": stage["id"], "assigned_user_id": created_work_item["user_id"], "instruction": "ok"},
        headers=auth_headers,
    )
    assert r.status_code == 201

    r = await async_client.delete(f"/policies/{pid}/stages/{stage['id']}", headers=auth_headers)
    assert r.status_code == 422
    assert "stage_has_checkpoints" in r.text


@pytest.mark.asyncio
async def test_reorder_stages(async_client: AsyncClient, auth_headers, created_work_item, published_agent_version):
    policy = await _create_policy(async_client, created_work_item["id"], auth_headers)
    pid = policy["id"]
    s1 = await _add_stage(async_client, pid, published_agent_version, auth_headers, name="First")
    s2 = await _add_stage(async_client, pid, published_agent_version, auth_headers, name="Second")

    # Swap order
    r = await async_client.put(
        f"/policies/{pid}/stages/order",
        json={"stage_ids": [s2["id"], s1["id"]]},
        headers=auth_headers,
    )
    assert r.status_code == 200
    stages = r.json()["stages"]
    assert stages[0]["id"] == s2["id"]
    assert stages[0]["sequence"] == 1
    assert stages[1]["id"] == s1["id"]
    assert stages[1]["sequence"] == 2


@pytest.mark.asyncio
async def test_reorder_stages_wrong_ids(async_client: AsyncClient, auth_headers, created_work_item, published_agent_version):
    policy = await _create_policy(async_client, created_work_item["id"], auth_headers)
    pid = policy["id"]
    await _add_stage(async_client, pid, published_agent_version, auth_headers)

    r = await async_client.put(
        f"/policies/{pid}/stages/order",
        json={"stage_ids": [str(uuid.uuid4())]},  # wrong id
        headers=auth_headers,
    )
    assert r.status_code == 422


# ---------------------------------------------------------------------------
# Checkpoints
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_add_checkpoint_approval(async_client: AsyncClient, auth_headers, created_work_item, published_agent_version):
    policy = await _create_policy(async_client, created_work_item["id"], auth_headers)
    stage = await _add_stage(async_client, policy["id"], published_agent_version, auth_headers)
    r = await async_client.post(
        f"/policies/{policy['id']}/checkpoints",
        json={"type": "approval", "stage_id": stage["id"], "assigned_user_id": created_work_item["user_id"], "instruction": "approve it"},
        headers=auth_headers,
    )
    assert r.status_code == 201
    data = r.json()
    assert data["type"] == "approval"
    assert data["stage_id"] == stage["id"]


@pytest.mark.asyncio
async def test_add_final_review_checkpoint(async_client: AsyncClient, auth_headers, created_work_item):
    policy = await _create_policy(async_client, created_work_item["id"], auth_headers)
    r = await async_client.post(
        f"/policies/{policy['id']}/checkpoints",
        json={"type": "final_review", "stage_id": None, "assigned_user_id": created_work_item["user_id"], "instruction": "approve"},
        headers=auth_headers,
    )
    assert r.status_code == 201
    assert r.json()["stage_id"] is None
    assert r.json()["type"] == "final_review"


@pytest.mark.asyncio
async def test_add_final_review_with_stage_fails(
    async_client: AsyncClient, auth_headers, created_work_item, published_agent_version
):
    policy = await _create_policy(async_client, created_work_item["id"], auth_headers)
    stage = await _add_stage(async_client, policy["id"], published_agent_version, auth_headers)
    r = await async_client.post(
        f"/policies/{policy['id']}/checkpoints",
        json={"type": "final_review", "stage_id": stage["id"], "assigned_user_id": created_work_item["user_id"], "instruction": "x"},
        headers=auth_headers,
    )
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_add_non_final_checkpoint_without_stage_fails(async_client: AsyncClient, auth_headers, created_work_item):
    policy = await _create_policy(async_client, created_work_item["id"], auth_headers)
    r = await async_client.post(
        f"/policies/{policy['id']}/checkpoints",
        json={"type": "approval", "stage_id": None, "assigned_user_id": created_work_item["user_id"], "instruction": "x"},
        headers=auth_headers,
    )
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_add_checkpoint_non_human_worker_fails(
    async_client: AsyncClient, auth_headers, created_work_item, published_agent_version, test_db_url
):
    """Assigning a user who is NOT a human worker on the work item must fail with 422."""
    policy = await _create_policy(async_client, created_work_item["id"], auth_headers)
    stage = await _add_stage(async_client, policy["id"], published_agent_version, auth_headers)

    # Insert a separate active user NOT on the work item
    other_id = str(uuid.uuid4())
    async with _test_db(test_db_url) as db:
        await db.execute(
            text(
                "INSERT INTO users (id, email, name, hashed_password, role, status, created_at, updated_at) "
                "VALUES (:id, :email, 'Other', :hp, 'member', 'active', now(), now())"
            ),
            {"id": other_id, "email": f"other_{other_id[:8]}@example.com", "hp": hash_password("pw")},
        )
        await db.commit()

    r = await async_client.post(
        f"/policies/{policy['id']}/checkpoints",
        json={"type": "approval", "stage_id": stage["id"], "assigned_user_id": other_id, "instruction": "x"},
        headers=auth_headers,
    )
    assert r.status_code == 422

    async with _test_db(test_db_url) as db:
        await db.execute(text("DELETE FROM users WHERE id = :id"), {"id": other_id})
        await db.commit()


@pytest.mark.asyncio
async def test_patch_checkpoint(async_client: AsyncClient, auth_headers, created_work_item, published_agent_version):
    policy = await _create_policy(async_client, created_work_item["id"], auth_headers)
    stage = await _add_stage(async_client, policy["id"], published_agent_version, auth_headers)
    r = await async_client.post(
        f"/policies/{policy['id']}/checkpoints",
        json={"type": "review", "stage_id": stage["id"], "assigned_user_id": created_work_item["user_id"], "instruction": "original"},
        headers=auth_headers,
    )
    cp_id = r.json()["id"]

    r = await async_client.patch(
        f"/policies/{policy['id']}/checkpoints/{cp_id}",
        json={"instruction": "updated instruction"},
        headers=auth_headers,
    )
    assert r.status_code == 200
    assert r.json()["instruction"] == "updated instruction"


@pytest.mark.asyncio
async def test_delete_checkpoint(async_client: AsyncClient, auth_headers, created_work_item):
    policy = await _create_policy(async_client, created_work_item["id"], auth_headers)
    pid = policy["id"]
    r = await async_client.post(
        f"/policies/{pid}/checkpoints",
        json={"type": "final_review", "stage_id": None, "assigned_user_id": created_work_item["user_id"], "instruction": "go"},
        headers=auth_headers,
    )
    cp_id = r.json()["id"]

    r = await async_client.delete(f"/policies/{pid}/checkpoints/{cp_id}", headers=auth_headers)
    assert r.status_code == 204


# ---------------------------------------------------------------------------
# Immutability: published policy cannot be edited
# ---------------------------------------------------------------------------

async def _setup_valid_policy(client: AsyncClient, wi: dict, agent_version_id: str, headers: dict) -> dict:
    """Create + stage + final_review, publish. Return the policy."""
    policy = await _create_policy(client, wi["id"], headers)
    pid = policy["id"]
    await _add_stage(client, pid, agent_version_id, headers)
    await _add_final_review(client, pid, wi["user_id"], headers)
    r = await client.post(f"/policies/{pid}/publish", headers=headers)
    assert r.status_code == 200, r.text
    return r.json()


@pytest.mark.asyncio
async def test_edit_published_policy_stage_fails(
    async_client: AsyncClient, auth_headers, created_work_item, published_agent_version
):
    policy = await _setup_valid_policy(async_client, created_work_item, published_agent_version, auth_headers)
    stage_id = policy["stages"][0]["id"]
    r = await async_client.patch(
        f"/policies/{policy['id']}/stages/{stage_id}",
        json={"name": "Mutation"},
        headers=auth_headers,
    )
    assert r.status_code == 409


@pytest.mark.asyncio
async def test_edit_published_policy_checkpoint_fails(
    async_client: AsyncClient, auth_headers, created_work_item, published_agent_version
):
    policy = await _setup_valid_policy(async_client, created_work_item, published_agent_version, auth_headers)
    cp_id = policy["checkpoints"][0]["id"]
    r = await async_client.patch(
        f"/policies/{policy['id']}/checkpoints/{cp_id}",
        json={"instruction": "Mutated"},
        headers=auth_headers,
    )
    assert r.status_code == 409


# ---------------------------------------------------------------------------
# Publish
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_publish_policy(async_client: AsyncClient, auth_headers, created_work_item, published_agent_version):
    policy = await _create_policy(async_client, created_work_item["id"], auth_headers)
    pid = policy["id"]
    await _add_stage(async_client, pid, published_agent_version, auth_headers)
    await _add_final_review(async_client, pid, created_work_item["user_id"], auth_headers)

    r = await async_client.post(f"/policies/{pid}/publish", headers=auth_headers)
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "published"
    assert data["published_by"] is not None
    assert data["published_at"] is not None


@pytest.mark.asyncio
async def test_publish_policy_no_stages(async_client: AsyncClient, auth_headers, created_work_item):
    policy = await _create_policy(async_client, created_work_item["id"], auth_headers)
    r = await async_client.post(f"/policies/{policy['id']}/publish", headers=auth_headers)
    assert r.status_code == 422
    detail = r.json()["detail"]
    codes = [f["code"] for f in detail["failures"]]
    assert "no_stages" in codes


@pytest.mark.asyncio
async def test_publish_policy_missing_final_review(
    async_client: AsyncClient, auth_headers, created_work_item, published_agent_version
):
    policy = await _create_policy(async_client, created_work_item["id"], auth_headers)
    await _add_stage(async_client, policy["id"], published_agent_version, auth_headers)
    # No final_review checkpoint

    r = await async_client.post(f"/policies/{policy['id']}/publish", headers=auth_headers)
    assert r.status_code == 422
    codes = [f["code"] for f in r.json()["detail"]["failures"]]
    assert "missing_final_review" in codes


@pytest.mark.asyncio
async def test_publish_policy_stage_agent_not_worker(
    async_client: AsyncClient, auth_headers, created_work_item, test_db_url
):
    """Stage using an agent version NOT assigned to the work item → publish fails."""
    other_agent_id = str(uuid.uuid4())
    other_version_id = str(uuid.uuid4())
    async with _test_db(test_db_url) as db:
        seq = (await db.execute(text("SELECT nextval('agent_code_seq')"))).scalar_one()
        await db.execute(
            text(
                "INSERT INTO agents (id, agent_code, name, description, role_purpose, status, created_at, updated_at) "
                "VALUES (:id, :code, :name, 'x', 'x', 'active', now(), now())"
            ),
            {"id": other_agent_id, "code": f"agent-{seq:04d}", "name": f"Other {other_agent_id[:8]}"},
        )
        await db.execute(
            text(
                "INSERT INTO agent_versions (id, agent_id, version, instructions, capabilities, status, created_at, updated_at) "
                "VALUES (:id, :aid, '1.0', 'x', '[]'::jsonb, 'published', now(), now())"
            ),
            {"id": other_version_id, "aid": other_agent_id},
        )
        await db.commit()

    policy = await _create_policy(async_client, created_work_item["id"], auth_headers)
    pid = policy["id"]
    # Add stage with the OTHER agent (not a worker on this work item)
    r = await async_client.post(
        f"/policies/{pid}/stages",
        json={"name": "S", "description": "d", "expected_output": "o", "agent_version_id": other_version_id},
        headers=auth_headers,
    )
    assert r.status_code == 201
    await _add_final_review(async_client, pid, created_work_item["user_id"], auth_headers)

    r = await async_client.post(f"/policies/{pid}/publish", headers=auth_headers)
    assert r.status_code == 422
    codes = [f["code"] for f in r.json()["detail"]["failures"]]
    assert "stage_worker_not_assigned" in codes

    async with _test_db(test_db_url) as db:
        await db.execute(text("DELETE FROM policy_stages WHERE agent_version_id = :vid"), {"vid": other_version_id})
        await db.execute(text("DELETE FROM agent_versions WHERE id = :id"), {"id": other_version_id})
        await db.execute(text("DELETE FROM agents WHERE id = :id"), {"id": other_agent_id})
        await db.commit()
