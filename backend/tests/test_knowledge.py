"""Knowledge module tests — all offline (no Vertex AI calls)."""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.security import create_access_token, hash_password
from app.knowledge.retrievers import (
    FakeRetriever,
    KnowledgeHit,
    build_injection_block,
    compute_freshness,
)


# ─── Pure-function tests ──────────────────────────────────────────────────────

def test_freshness_fresh_below_boundary():
    assert compute_freshness(89) == "fresh"


def test_freshness_fresh_at_boundary():
    assert compute_freshness(90) == "fresh"  # ≤ ageing_days


def test_freshness_ageing_just_above():
    assert compute_freshness(91) == "ageing"


def test_freshness_ageing_below_stale():
    assert compute_freshness(179) == "ageing"


def test_freshness_ageing_at_stale_boundary():
    assert compute_freshness(180) == "ageing"  # ≤ stale_days


def test_freshness_stale():
    assert compute_freshness(181) == "stale"


def test_freshness_custom_thresholds():
    assert compute_freshness(10, ageing_days=7, stale_days=14) == "ageing"
    assert compute_freshness(15, ageing_days=7, stale_days=14) == "stale"


# ─── build_injection_block ────────────────────────────────────────────────────

def _hit(title: str, freshness: str, age_days: int, snippet: str = "snippet text") -> KnowledgeHit:
    return KnowledgeHit(
        document_id=str(uuid.uuid4()),
        title=title,
        snippet=snippet,
        score=1.0,
        last_verified_at=datetime.now(timezone.utc) - timedelta(days=age_days),
        age_days=age_days,
        freshness=freshness,
    )


def test_build_injection_block_empty():
    assert build_injection_block([]) == ""


def test_build_injection_block_fresh():
    block = build_injection_block([_hit("Doc A", "fresh", 5, "some snippet")])
    assert "Doc A" in block
    assert "FRESH" in block
    assert "some snippet" in block
    assert "verify" not in block.lower()
    assert "outdated" not in block.lower()


def test_build_injection_block_ageing():
    block = build_injection_block([_hit("Doc B", "ageing", 120)])
    assert "AGEING" in block
    assert "verify before relying" in block


def test_build_injection_block_stale():
    block = build_injection_block([_hit("Doc C", "stale", 200)])
    assert "STALE" in block
    assert "may be outdated" in block
    assert "re-verification" in block


def test_build_injection_block_multiple():
    hits = [_hit("A", "fresh", 5), _hit("B", "stale", 200)]
    block = build_injection_block(hits)
    assert "[1]" in block
    assert "[2]" in block
    assert block.index("[1]") < block.index("[2]")


# ─── FakeRetriever ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_fake_retriever_returns_scripted_hits():
    hits = [_hit(f"Doc {i}", "fresh", 5) for i in range(3)]
    retriever = FakeRetriever(hits)
    result = await retriever.search("anything", top_k=2)
    assert len(result) == 2
    assert result[0].title == "Doc 0"


@pytest.mark.asyncio
async def test_fake_retriever_empty():
    result = await FakeRetriever().search("anything", top_k=5)
    assert result == []


# ─── HTTP CRUD (async_client fixture from conftest) ───────────────────────────

@pytest_asyncio.fixture()
async def auth_headers(test_db_url: str) -> dict:
    user_id = str(uuid.uuid4())
    factory = _make_factory(test_db_url)
    async with factory() as db:
        await db.execute(
            text(
                "INSERT INTO users(id,email,name,hashed_password,role,status,created_at,updated_at)"
                " VALUES(:id,:email,'KTest',:pw,'super_admin','active',now(),now())"
            ),
            {"id": user_id, "email": f"ktest_{user_id[:8]}@test.com", "pw": hash_password("pw")},
        )
        await db.commit()

    token = create_access_token(user_id, "super_admin")
    yield {"Authorization": f"Bearer {token}", "_user_id": user_id}

    async with factory() as db:
        await db.execute(
            text("DELETE FROM knowledge_documents WHERE verified_by = :u"), {"u": user_id}
        )
        await db.execute(text("DELETE FROM users WHERE id = :u"), {"u": user_id})
        await db.commit()


@pytest.mark.asyncio
async def test_list_knowledge_empty(async_client: AsyncClient, auth_headers: dict):
    resp = await async_client.get("/knowledge", headers=auth_headers)
    assert resp.status_code == 200
    # May already have docs from other tests; just check shape
    data = resp.json()
    assert isinstance(data, list)


@pytest.mark.asyncio
async def test_create_knowledge(async_client: AsyncClient, auth_headers: dict):
    resp = await async_client.post(
        "/knowledge",
        json={"title": "Test Doc", "content": "some content", "source": "Test Team"},
        headers=auth_headers,
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["title"] == "Test Doc"
    assert data["freshness"] == "fresh"
    assert data["age_days"] == 0
    assert "id" in data


@pytest.mark.asyncio
async def test_create_knowledge_defaults_last_verified_to_now(
    async_client: AsyncClient, auth_headers: dict
):
    resp = await async_client.post(
        "/knowledge",
        json={"title": "Default Date Doc", "content": "x", "source": "Src"},
        headers=auth_headers,
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["age_days"] == 0
    assert data["freshness"] == "fresh"


@pytest.mark.asyncio
async def test_create_knowledge_custom_last_verified(
    async_client: AsyncClient, auth_headers: dict
):
    # A doc verified 200 days ago should come back as stale
    old_date = (datetime.now(timezone.utc) - timedelta(days=200)).isoformat()
    resp = await async_client.post(
        "/knowledge",
        json={"title": "Old Doc", "content": "x", "source": "Src", "last_verified_at": old_date},
        headers=auth_headers,
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["freshness"] == "stale"
    assert data["age_days"] >= 200


@pytest.mark.asyncio
async def test_verify_knowledge_updates_freshness(
    async_client: AsyncClient, auth_headers: dict
):
    # Create a stale doc
    old_date = (datetime.now(timezone.utc) - timedelta(days=200)).isoformat()
    create_resp = await async_client.post(
        "/knowledge",
        json={"title": "To Verify", "content": "x", "source": "Src", "last_verified_at": old_date},
        headers=auth_headers,
    )
    assert create_resp.status_code == 201
    doc_id = create_resp.json()["id"]

    verify_resp = await async_client.post(
        f"/knowledge/{doc_id}/verify", headers=auth_headers
    )
    assert verify_resp.status_code == 200
    data = verify_resp.json()
    assert data["freshness"] == "fresh"
    assert data["age_days"] == 0


@pytest.mark.asyncio
async def test_verify_sets_verified_by(
    async_client: AsyncClient, auth_headers: dict
):
    user_id = auth_headers["_user_id"]
    create_resp = await async_client.post(
        "/knowledge",
        json={"title": "Verify By Doc", "content": "x", "source": "Src"},
        headers=auth_headers,
    )
    assert create_resp.status_code == 201
    doc_id = create_resp.json()["id"]

    verify_resp = await async_client.post(f"/knowledge/{doc_id}/verify", headers=auth_headers)
    assert verify_resp.status_code == 200
    data = verify_resp.json()
    assert data["verified_by"] == user_id


@pytest.mark.asyncio
async def test_verify_requires_auth(async_client: AsyncClient):
    resp = await async_client.post(f"/knowledge/{uuid.uuid4()}/verify")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_verify_not_found(async_client: AsyncClient, auth_headers: dict):
    resp = await async_client.post(
        f"/knowledge/{uuid.uuid4()}/verify", headers=auth_headers
    )
    assert resp.status_code == 404


# ─── Engine knowledge injection ───────────────────────────────────────────────
# These tests reuse the engine_setup fixture from test_engine.py context.
# They live here to keep knowledge tests co-located.

import contextlib

from app.executions.engine import ExecutionEngine
from app.executions.models import Execution, ExecutionEvent


def _make_factory(test_db_url: str):
    engine = create_async_engine(test_db_url, echo=False)
    return async_sessionmaker(engine, expire_on_commit=False)


@contextlib.asynccontextmanager
async def _test_db(factory):
    async with factory() as db:
        yield db


async def _happy_mock(*args, **kwargs):
    yield {"event_type": "tool.called", "payload": {"tool_name": "x", "arguments": {}}}
    yield {"event_type": "stage.stream_end", "payload": {"final_text": "result", "total_tokens": {}}}


@pytest_asyncio.fixture()
async def ki_setup(test_db_url: str):
    """Minimal engine_setup: user, project, work_item, agent+version, policy+stage+final_review."""
    factory = _make_factory(test_db_url)
    user_id = uuid.uuid4()
    project_id = uuid.uuid4()
    wi_id = uuid.uuid4()
    agent_id = uuid.uuid4()
    av_id = uuid.uuid4()
    tool_id = uuid.uuid4()
    policy_id = uuid.uuid4()
    stage_id = uuid.uuid4()
    cp_id = uuid.uuid4()
    exec_id = uuid.uuid4()

    async with factory() as db:
        await db.execute(text(
            "INSERT INTO users(id,email,name,hashed_password,role,status,created_at,updated_at) "
            "VALUES(:id,:email,'U',:pw,'super_admin','active',now(),now())"
        ), {"id": user_id, "email": f"ki_{user_id}@test.com", "pw": hash_password("x")})
        await db.execute(text(
            "INSERT INTO projects(id,name,description,status,created_by,created_at,updated_at) "
            "VALUES(:id,'KI P','d','active',:u,now(),now())"
        ), {"id": project_id, "u": user_id})
        await db.execute(text(
            "INSERT INTO work_items(id,project_id,name,objective,description,expected_outcome,"
            "status,created_by,created_at,updated_at) "
            "VALUES(:id,:p,'WI','Obj','Desc','Out','new',:u,now(),now())"
        ), {"id": wi_id, "p": project_id, "u": user_id})
        await db.execute(text(
            "INSERT INTO agents(id,agent_code,name,description,role_purpose,status,created_at,updated_at)"
            " VALUES(:id,'ki-ac-001','KI Agent','d','r','active',now(),now())"
        ), {"id": agent_id})
        await db.execute(text(
            "INSERT INTO agent_versions(id,agent_id,version,instructions,capabilities,status,created_at,updated_at)"
            " VALUES(:id,:a,'1.0','instr','[]'::jsonb,'published',now(),now())"
        ), {"id": av_id, "a": agent_id})
        await db.execute(text(
            "INSERT INTO mcp_tools(id,name,tool_name,server_key,description,status,created_at,updated_at)"
            " VALUES(:id,'KS','knowledge_search','knowledge','d','active',now(),now())"
        ), {"id": tool_id})
        await db.execute(text(
            "INSERT INTO agent_version_tools(agent_version_id,mcp_tool_id) VALUES(:a,:t)"
        ), {"a": av_id, "t": tool_id})
        await db.execute(text(
            "INSERT INTO work_item_workers(id,work_item_id,worker_type,agent_version_id,user_id,"
            "created_at,updated_at) VALUES(:id,:w,'ai_agent',:a,null,now(),now())"
        ), {"id": uuid.uuid4(), "w": wi_id, "a": av_id})
        await db.execute(text(
            "INSERT INTO policies(id,work_item_id,version,status,generated_by,created_at,updated_at)"
            " VALUES(:id,:w,1,'published','manual',now(),now())"
        ), {"id": policy_id, "w": wi_id})
        await db.execute(text(
            "INSERT INTO policy_stages(id,policy_id,sequence,name,description,expected_output,"
            "agent_version_id,created_at,updated_at) "
            "VALUES(:id,:p,1,'S1','Do the thing','Output',:a,now(),now())"
        ), {"id": stage_id, "p": policy_id, "a": av_id})
        # Final review checkpoint (required by engine)
        await db.execute(text(
            "INSERT INTO checkpoints(id,policy_id,stage_id,type,assigned_user_id,instruction,"
            "created_at,updated_at) VALUES(:id,:p,null,'final_review',:u,'Review',now(),now())"
        ), {"id": cp_id, "p": policy_id, "u": user_id})
        await db.execute(text(
            "INSERT INTO executions(id,work_item_id,policy_id,execution_number,status,"
            "created_at,updated_at) VALUES(:id,:w,:p,1,'queued',now(),now())"
        ), {"id": exec_id, "w": wi_id, "p": policy_id})
        await db.commit()

    yield {
        "exec_id": exec_id, "stage_id": stage_id, "policy_id": policy_id,
        "wi_id": wi_id, "user_id": user_id, "cp_id": cp_id,
        "factory": factory,
    }

    async with factory() as db:
        # Delete all executions (and their events/messages) for this policy
        rows = await db.execute(
            text("SELECT id FROM executions WHERE policy_id = :p"), {"p": policy_id}
        )
        all_exec_ids = [r[0] for r in rows.fetchall()]
        for eid in all_exec_ids:
            await db.execute(
                text("DELETE FROM execution_events WHERE execution_id = :e"), {"e": eid}
            )
            await db.execute(
                text("DELETE FROM messages WHERE execution_id = :e"), {"e": eid}
            )
            await db.execute(
                text("UPDATE executions SET blocking_checkpoint_id = NULL WHERE id = :e"),
                {"e": eid},
            )
        await db.commit()

    async with factory() as db:
        await db.execute(
            text("DELETE FROM executions WHERE policy_id = :p"), {"p": policy_id}
        )
        await db.execute(text("DELETE FROM checkpoints WHERE policy_id = :p"), {"p": policy_id})
        await db.execute(text("DELETE FROM policy_stages WHERE policy_id = :p"), {"p": policy_id})
        await db.execute(text("DELETE FROM policies WHERE id = :p"), {"p": policy_id})
        await db.execute(text("DELETE FROM work_item_workers WHERE work_item_id = :w"), {"w": wi_id})
        await db.execute(text("DELETE FROM work_items WHERE id = :w"), {"w": wi_id})
        await db.execute(text("DELETE FROM agent_version_tools WHERE agent_version_id = :a"), {"a": av_id})
        await db.execute(text("DELETE FROM agent_versions WHERE id = :a"), {"a": av_id})
        await db.execute(text("DELETE FROM agents WHERE id = :a"), {"a": agent_id})
        await db.execute(text("DELETE FROM mcp_tools WHERE id = :t"), {"t": tool_id})
        await db.execute(text("DELETE FROM projects WHERE id = :p"), {"p": project_id})
        await db.execute(text("DELETE FROM users WHERE id = :u"), {"u": user_id})
        await db.commit()


async def _fresh_execution(ki_setup, factory) -> uuid.UUID:
    """Insert a fresh queued execution for the ki_setup policy/work_item."""
    exec_id = uuid.uuid4()
    async with factory() as db:
        await db.execute(
            text(
                "INSERT INTO executions(id,work_item_id,policy_id,execution_number,"
                "status,created_at,updated_at) VALUES(:id,:w,:p,99,'queued',now(),now())"
            ),
            {"id": exec_id, "w": ki_setup["wi_id"], "p": ki_setup["policy_id"]},
        )
        await db.commit()
    return exec_id


@pytest.mark.asyncio
async def test_engine_injects_knowledge_block(ki_setup, test_db_url: str):
    hit = _hit("Company Policy", "fresh", 5, "Important policy text")
    fake_retriever = FakeRetriever([hit])
    factory = _make_factory(test_db_url)
    exec_id = await _fresh_execution(ki_setup, factory)

    with patch("app.executions.engine.run_stage", side_effect=_happy_mock):
        engine = ExecutionEngine(session_factory=factory, retriever=fake_retriever)
        await engine.run_execution(str(exec_id))

    async with factory() as db:
        result = await db.execute(
            text("SELECT event_type, payload FROM execution_events WHERE execution_id = :e"),
            {"e": exec_id},
        )
        events = {row.event_type: row.payload for row in result.fetchall()}

    assert "knowledge.retrieved" in events
    payload = events["knowledge.retrieved"]
    assert payload["documents"][0]["title"] == "Company Policy"
    assert payload["stale_count"] == 0


@pytest.mark.asyncio
async def test_engine_knowledge_failure_does_not_fail_execution(ki_setup, test_db_url: str):
    class ErrorRetriever(FakeRetriever):
        async def search(self, query, top_k):
            raise RuntimeError("Vertex down")

    factory = _make_factory(test_db_url)
    exec_id = await _fresh_execution(ki_setup, factory)

    with patch("app.executions.engine.run_stage", side_effect=_happy_mock):
        engine = ExecutionEngine(session_factory=factory, retriever=ErrorRetriever())
        await engine.run_execution(str(exec_id))

    async with factory() as db:
        result = await db.execute(
            text("SELECT status, error FROM executions WHERE id = :e"), {"e": exec_id}
        )
        row = result.fetchone()

    assert row.status in ("waiting_for_approval", "completed")


@pytest.mark.asyncio
async def test_engine_empty_hits_skips_event(ki_setup, test_db_url: str):
    factory = _make_factory(test_db_url)
    exec_id = await _fresh_execution(ki_setup, factory)

    with patch("app.executions.engine.run_stage", side_effect=_happy_mock):
        engine = ExecutionEngine(session_factory=factory, retriever=FakeRetriever([]))
        await engine.run_execution(str(exec_id))

    async with factory() as db:
        result = await db.execute(
            text("SELECT event_type FROM execution_events WHERE execution_id = :e"),
            {"e": exec_id},
        )
        event_types = [row.event_type for row in result.fetchall()]

    assert "knowledge.retrieved" not in event_types
