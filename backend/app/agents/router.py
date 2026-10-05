from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.models import Agent, AgentVersion, AgentVersionTool, McpTool
from app.agents.schemas import (
    AgentOut,
    AgentSummaryOut,
    AgentVersionOut,
    CreateAgentRequest,
    CreateVersionRequest,
    McpToolOut,
    PatchAgentRequest,
    PatchVersionRequest,
)
from app.auth.dependencies import get_current_user
from app.auth.models import User
from app.core.db import get_db

router = APIRouter()

_NOT_FOUND_AGENT = HTTPException(status_code=404, detail="agent not found")
_NOT_FOUND_VERSION = HTTPException(status_code=404, detail="version not found")
_NAME_CONFLICT = HTTPException(status_code=409, detail="name already exists")
_VERSION_NOT_DRAFT = HTTPException(status_code=409, detail="version is not a draft")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _load_tools(db: AsyncSession, tool_ids: list[str]) -> list[McpTool]:
    """Load McpTool rows for the given IDs; 422 on unknown or inactive tools."""
    if not tool_ids:
        return []
    result = await db.execute(select(McpTool).where(McpTool.id.in_(tool_ids)))
    found = {str(t.id): t for t in result.scalars().all()}
    for tid in tool_ids:
        if tid not in found:
            raise HTTPException(422, detail=f"tool {tid} not found")
        if found[tid].status != "active":
            raise HTTPException(422, detail=f"tool {found[tid].tool_name} is inactive")
    return [found[tid] for tid in tool_ids]


async def _version_tool_ids(db: AsyncSession, version_id: uuid.UUID) -> list[str]:
    result = await db.execute(
        select(AgentVersionTool.mcp_tool_id).where(
            AgentVersionTool.agent_version_id == version_id
        )
    )
    return [str(r) for r in result.scalars().all()]


async def _agent_out(db: AsyncSession, agent: Agent) -> AgentOut:
    result = await db.execute(
        select(AgentVersion)
        .where(AgentVersion.agent_id == agent.id)
        .order_by(AgentVersion.created_at)
    )
    versions = result.scalars().all()
    version_outs = []
    for v in versions:
        tids = await _version_tool_ids(db, v.id)
        version_outs.append(AgentVersionOut.from_orm(v, tids))
    out = AgentOut.from_orm(agent)
    out.versions = version_outs
    return out


def _next_version(existing: list[str]) -> str:
    """Return the next version string given existing version strings like '1.0', '2.0'."""
    if not existing:
        return "1.0"
    max_num = max(float(v) for v in existing)
    return f"{max_num + 1.0:.1f}"


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get("/mcp-tools", response_model=list[McpToolOut])
async def list_mcp_tools(
    _: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(McpTool).order_by(McpTool.name))
    return [McpToolOut.from_orm(t) for t in result.scalars().all()]


@router.post("/agents", response_model=AgentOut, status_code=status.HTTP_201_CREATED)
async def create_agent(
    body: CreateAgentRequest,
    _: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    tools = await _load_tools(db, body.tool_ids)

    # Allocate agent_code from the Postgres sequence
    seq_result = await db.execute(text("SELECT nextval('agent_code_seq')"))
    seq_val = seq_result.scalar_one()
    agent_code = f"agent-{seq_val:04d}"

    agent_id = uuid.uuid4()
    version_id = uuid.uuid4()
    now = datetime.now(timezone.utc)

    agent = Agent(
        id=agent_id,
        agent_code=agent_code,
        name=body.name,
        description=body.description,
        role_purpose=body.role_purpose,
        status="draft",
        created_at=now,
        updated_at=now,
    )
    version = AgentVersion(
        id=version_id,
        agent_id=agent_id,
        version="1.0",
        instructions=body.instructions,
        capabilities=[c.model_dump() for c in body.capabilities],
        status="draft",
        published_at=None,
        created_at=now,
        updated_at=now,
    )
    db.add(agent)
    db.add(version)
    for tool in tools:
        db.add(AgentVersionTool(agent_version_id=version_id, mcp_tool_id=tool.id))

    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise _NAME_CONFLICT

    await db.refresh(agent)
    await db.refresh(version)
    return await _agent_out(db, agent)


@router.get("/agents", response_model=list[AgentSummaryOut])
async def list_agents(
    _: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Agent).order_by(Agent.created_at))
    return [AgentSummaryOut.from_orm(a) for a in result.scalars().all()]


@router.get("/agents/{agent_id}", response_model=AgentOut)
async def get_agent(
    agent_id: str,
    _: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Agent).where(Agent.id == agent_id))
    agent = result.scalar_one_or_none()
    if agent is None:
        raise _NOT_FOUND_AGENT
    return await _agent_out(db, agent)


@router.patch("/agents/{agent_id}", response_model=AgentOut)
async def patch_agent(
    agent_id: str,
    body: PatchAgentRequest,
    _: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Agent).where(Agent.id == agent_id))
    agent = result.scalar_one_or_none()
    if agent is None:
        raise _NOT_FOUND_AGENT

    if body.name is not None:
        agent.name = body.name
    if body.description is not None:
        agent.description = body.description
    if body.role_purpose is not None:
        agent.role_purpose = body.role_purpose
    if body.status is not None:
        agent.status = body.status
    agent.updated_at = datetime.now(timezone.utc)

    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise _NAME_CONFLICT

    await db.refresh(agent)
    return await _agent_out(db, agent)


@router.post(
    "/agents/{agent_id}/versions",
    response_model=AgentVersionOut,
    status_code=status.HTTP_201_CREATED,
)
async def add_version(
    agent_id: str,
    body: CreateVersionRequest,
    _: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Agent).where(Agent.id == agent_id))
    agent = result.scalar_one_or_none()
    if agent is None:
        raise _NOT_FOUND_AGENT

    tools = await _load_tools(db, body.tool_ids)

    # Determine next version number
    ver_result = await db.execute(
        select(AgentVersion.version).where(AgentVersion.agent_id == agent_id)
    )
    existing_versions = ver_result.scalars().all()
    new_version = _next_version(list(existing_versions))

    version_id = uuid.uuid4()
    now = datetime.now(timezone.utc)
    version = AgentVersion(
        id=version_id,
        agent_id=uuid.UUID(agent_id),
        version=new_version,
        instructions=body.instructions,
        capabilities=[c.model_dump() for c in body.capabilities],
        status="draft",
        published_at=None,
        created_at=now,
        updated_at=now,
    )
    db.add(version)
    for tool in tools:
        db.add(AgentVersionTool(agent_version_id=version_id, mcp_tool_id=tool.id))

    await db.commit()
    await db.refresh(version)
    tids = await _version_tool_ids(db, version.id)
    return AgentVersionOut.from_orm(version, tids)


@router.patch("/agents/{agent_id}/versions/{version_id}", response_model=AgentVersionOut)
async def patch_version(
    agent_id: str,
    version_id: str,
    body: PatchVersionRequest,
    _: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(AgentVersion).where(
            AgentVersion.id == version_id,
            AgentVersion.agent_id == agent_id,
        )
    )
    version = result.scalar_one_or_none()
    if version is None:
        raise _NOT_FOUND_VERSION
    if version.status != "draft":
        raise _VERSION_NOT_DRAFT

    if body.instructions is not None:
        version.instructions = body.instructions
    if body.capabilities is not None:
        version.capabilities = [c.model_dump() for c in body.capabilities]
    if body.tool_ids is not None:
        # Validate new tools
        await _load_tools(db, body.tool_ids)
        # Replace tool associations
        await db.execute(
            text("DELETE FROM agent_version_tools WHERE agent_version_id = :vid"),
            {"vid": version_id},
        )
        for tid in body.tool_ids:
            db.add(AgentVersionTool(
                agent_version_id=uuid.UUID(version_id),
                mcp_tool_id=uuid.UUID(tid),
            ))

    version.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(version)
    tids = await _version_tool_ids(db, version.id)
    return AgentVersionOut.from_orm(version, tids)


@router.post("/agents/{agent_id}/versions/{version_id}/publish", response_model=AgentVersionOut)
async def publish_version(
    agent_id: str,
    version_id: str,
    _: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # Load agent and version (no lock yet — just read)
    agent_result = await db.execute(select(Agent).where(Agent.id == agent_id))
    agent = agent_result.scalar_one_or_none()
    if agent is None:
        raise _NOT_FOUND_AGENT

    ver_result = await db.execute(
        select(AgentVersion).where(
            AgentVersion.id == version_id,
            AgentVersion.agent_id == agent_id,
        )
    )
    version = ver_result.scalar_one_or_none()
    if version is None:
        raise _NOT_FOUND_VERSION

    # Load tools for this version
    tool_result = await db.execute(
        select(McpTool)
        .join(AgentVersionTool, AgentVersionTool.mcp_tool_id == McpTool.id)
        .where(AgentVersionTool.agent_version_id == version_id)
    )
    tools = tool_result.scalars().all()

    # Collect ALL failures before raising
    failures: list[dict] = []

    if version.status != "draft":
        failures.append({"code": "not_draft", "message": "version is not a draft"})
    if not version.instructions or not version.instructions.strip():
        failures.append({"code": "missing_instructions", "message": "instructions are required"})
    if not version.capabilities:
        failures.append({"code": "no_capabilities", "message": "at least one capability is required"})
    if not tools:
        failures.append({"code": "no_tools", "message": "at least one tool is required"})
    else:
        for t in tools:
            if t.status != "active":
                failures.append({
                    "code": "inactive_tool",
                    "message": f"tool {t.tool_name} is inactive",
                })

    if failures:
        raise HTTPException(
            status_code=422,
            detail={"error": "publish_validation_failed", "failures": failures},
        )

    # Acquire a row-level lock to prevent concurrent double-publishes
    await db.execute(
        text("SELECT id FROM agents WHERE id = :aid FOR UPDATE"),
        {"aid": agent_id},
    )

    # Re-check status after acquiring the lock (another request may have just published)
    await db.refresh(version)
    if version.status != "draft":
        raise HTTPException(
            status_code=422,
            detail={
                "error": "publish_validation_failed",
                "failures": [{"code": "not_draft", "message": "version is not a draft"}],
            },
        )

    now = datetime.now(timezone.utc)

    # Retire any currently published version
    await db.execute(
        text(
            "UPDATE agent_versions SET status='retired', updated_at=:now "
            "WHERE agent_id=:aid AND status='published'"
        ),
        {"now": now, "aid": agent_id},
    )

    # Publish this version
    version.status = "published"
    version.published_at = now
    version.updated_at = now

    # Activate agent if it was draft
    if agent.status == "draft":
        agent.status = "active"
        agent.updated_at = now

    await db.commit()
    await db.refresh(version)
    tids = await _version_tool_ids(db, version.id)
    return AgentVersionOut.from_orm(version, tids)
