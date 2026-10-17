"""Idempotent seed: TechSoft contract renewal scenario.

Creates (or reuses if already present):
  - Procurement Agent  (agent + published version with knowledge_search + generate_document)
  - Project "Contract Renewals"
  - WorkItem "Renew contract with TechSoft Solutions"
  - AI worker + human worker (reviewer@seyarkai.example)
  - Policy with Stage 1 (compliance review) → mid-stage review checkpoint
    → Stage 2 (draft with generate_document) → final_review checkpoint
  - Published policy

Usage (from backend/):
    python -m scripts.seed_techsoft
"""
from __future__ import annotations

import asyncio
import re
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[2] / ".env")

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import settings

# ── Constants ─────────────────────────────────────────────────────────────────

_AGENT_NAME        = "Procurement Agent"
_PROJECT_NAME      = "Contract Renewals"
_WORK_ITEM_NAME    = "Renew contract with TechSoft Solutions"
_REVIEWER_EMAIL    = "reviewer@seyarkai.example"
_AGENT_CODE        = "procurement_agent"  # unique slug

_AGENT_INSTRUCTIONS = """\
You are a procurement compliance agent helping with the TechSoft Solutions contract renewal.

Use knowledge_search to gather relevant procurement policies. You must make at least 3 separate \
knowledge_search calls using different queries — for example: "payment terms supplier", \
"security compliance requirements", "approval thresholds contract renewal".

For Stage 1 (Compliance Review): Search thoroughly, then produce a numbered list of findings. \
Clearly flag any document whose freshness is stale or ageing.

For Stage 2 (Draft Recommendation): Use generate_document to create a structured renewal \
recommendation. Title it "TechSoft Solutions Contract Renewal Recommendation". Include: \
executive summary, compliance findings, stale document warnings, and a clear recommendation \
(proceed or escalate).\
"""

_STAGE1_DESC = (
    'Review TechSoft Solutions against company procurement policies. '
    'Search for: "payment terms supplier contract", "compliance security requirements", '
    '"approval thresholds renewal". Make at least 3 knowledge_search calls with distinct queries. '
    'List findings as a numbered list and flag stale documents.'
)
_STAGE1_EXPECTED = (
    'A numbered list of compliance findings with freshness flags on any stale or ageing documents.'
)
_STAGE1_CHECKPOINT_INSTRUCTION = (
    'Review the compliance findings from Stage 1 and approve to proceed to drafting the renewal recommendation. '
    'Check that at least 3 knowledge searches were made and stale documents are clearly flagged.'
)

_STAGE2_DESC = (
    'Draft the renewal recommendation for TechSoft Solutions. '
    'Call generate_document with title "TechSoft Solutions Contract Renewal Recommendation" '
    'and structured Markdown content including: executive summary, compliance findings from Stage 1, '
    'stale document warnings, and a recommendation (proceed or escalate with conditions).'
)
_STAGE2_EXPECTED = (
    'A generated document artifact: "TechSoft Solutions Contract Renewal Recommendation" '
    'covering all findings, stale flags, and a clear recommendation.'
)
_FINAL_CHECKPOINT_INSTRUCTION = (
    'Review the completed renewal recommendation document before closing this work item. '
    'Confirm the document covers all compliance findings and makes a clear recommendation.'
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _mask_db_url(url: str) -> str:
    try:
        parsed = urlparse(url)
        if parsed.password:
            url = url.replace(parsed.password, "***")
    except Exception:
        pass
    return url


async def seed() -> None:
    db_url = settings.DATABASE_URL
    masked = _mask_db_url(db_url)
    print(f"  DATABASE_URL: {masked}")

    parsed = urlparse(db_url)
    host = parsed.hostname or ""
    if host not in ("localhost", "127.0.0.1", "::1"):
        print(f"\n  STOP: DATABASE_URL host is '{host}' — not localhost. Refusing to seed.")
        sys.exit(1)
    print(f"  Host confirmed: {host}\n")

    engine = create_async_engine(db_url.replace("postgresql+asyncpg://", "postgresql+asyncpg://", 1), echo=False)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    try:
        async with factory() as session:
            await _do_seed(session)
            await session.commit()
    finally:
        await engine.dispose()


async def _do_seed(session) -> None:
    from app.agents.models import Agent, AgentVersion, AgentVersionTool, McpTool
    from app.policies.models import Checkpoint, Policy, PolicyStage
    from app.projects.models import Project
    from app.work_items.models import WorkItem, WorkItemWorker

    # ── 1. Look up reviewer ───────────────────────────────────────────────────
    result = await session.execute(
        text("SELECT id, name, role FROM users WHERE email = :email AND status = 'active'"),
        {"email": _REVIEWER_EMAIL},
    )
    reviewer_row = result.fetchone()
    if reviewer_row is None:
        print(f"  STOP: {_REVIEWER_EMAIL} not found or inactive.")
        print("  Run python -m scripts.seed_users first (with SEED_REVIEWER_PASSWORD set).")
        sys.exit(1)
    reviewer_id = reviewer_row[0]
    reviewer_role = reviewer_row[2]
    if reviewer_role not in ("admin", "reviewer"):
        print(f"  STOP: {_REVIEWER_EMAIL} has role '{reviewer_role}' — must be admin or reviewer.")
        sys.exit(1)
    print(f"  Reviewer: {_REVIEWER_EMAIL}  (id={reviewer_id}, role={reviewer_role})")

    # ── 2. Look up admin user to use as created_by ────────────────────────────
    result = await session.execute(
        text("SELECT id FROM users WHERE role = 'admin' AND status = 'active' LIMIT 1"),
    )
    admin_row = result.fetchone()
    if admin_row is None:
        print("  STOP: no active admin user found. Run seed_users.py first.")
        sys.exit(1)
    admin_id = admin_row[0]
    print(f"  Admin: id={admin_id}")

    # ── 3. Look up MCP tools ──────────────────────────────────────────────────
    result = await session.execute(
        select(McpTool).where(McpTool.tool_name.in_(["knowledge_search", "generate_document"]))
    )
    tools = {t.tool_name: t for t in result.scalars().all()}
    missing = [n for n in ["knowledge_search", "generate_document"] if n not in tools]
    if missing:
        print(f"  STOP: MCP tools not found: {missing}")
        print("  Run python -m scripts.seed_mcp_tools first.")
        sys.exit(1)
    print(f"  MCP tools: knowledge_search ({tools['knowledge_search'].id}), "
          f"generate_document ({tools['generate_document'].id})")

    # ── 4. Upsert Agent ───────────────────────────────────────────────────────
    result = await session.execute(
        select(Agent).where(Agent.name == _AGENT_NAME)
    )
    agent = result.scalar_one_or_none()
    if agent is None:
        agent = Agent(
            id=uuid.uuid4(),
            name=_AGENT_NAME,
            agent_code=_AGENT_CODE,
            description="Procurement compliance agent for contract renewals.",
            role_purpose="procurement",
            status="active",
            created_at=_now(),
            updated_at=_now(),
        )
        session.add(agent)
        await session.flush()
        print(f"  Created agent: {_AGENT_NAME}  (id={agent.id})")
    else:
        print(f"  Reusing agent: {_AGENT_NAME}  (id={agent.id})")

    # ── 5. Upsert AgentVersion (published) ───────────────────────────────────
    result = await session.execute(
        select(AgentVersion)
        .where(AgentVersion.agent_id == agent.id, AgentVersion.status == "published")
        .order_by(AgentVersion.published_at.desc())
    )
    agent_version = result.scalars().first()
    if agent_version is None:
        agent_version = AgentVersion(
            id=uuid.uuid4(),
            agent_id=agent.id,
            version="1",
            instructions=_AGENT_INSTRUCTIONS,
            capabilities=["knowledge", "document_generation"],
            status="published",
            published_at=_now(),
            created_at=_now(),
            updated_at=_now(),
        )
        session.add(agent_version)
        await session.flush()

        # Wire tools
        for tool in tools.values():
            session.add(AgentVersionTool(
                agent_version_id=agent_version.id,
                mcp_tool_id=tool.id,
            ))
        await session.flush()
        print(f"  Created & published agent version v{agent_version.version}  (id={agent_version.id})")
    else:
        print(f"  Reusing published agent version v{agent_version.version}  (id={agent_version.id})")

    # ── 6. Upsert Project ─────────────────────────────────────────────────────
    result = await session.execute(
        select(Project).where(Project.name == _PROJECT_NAME)
    )
    project = result.scalar_one_or_none()
    if project is None:
        project = Project(
            id=uuid.uuid4(),
            name=_PROJECT_NAME,
            description="Contract renewal work items for vendor procurement.",
            status="active",
            created_by=admin_id,
            created_at=_now(),
            updated_at=_now(),
        )
        session.add(project)
        await session.flush()
        print(f"  Created project: {_PROJECT_NAME}  (id={project.id})")
    else:
        print(f"  Reusing project: {_PROJECT_NAME}  (id={project.id})")

    # ── 7. Upsert WorkItem ────────────────────────────────────────────────────
    result = await session.execute(
        select(WorkItem).where(
            WorkItem.project_id == project.id,
            WorkItem.name == _WORK_ITEM_NAME,
        )
    )
    work_item = result.scalar_one_or_none()
    if work_item is None:
        work_item = WorkItem(
            id=uuid.uuid4(),
            project_id=project.id,
            name=_WORK_ITEM_NAME,
            objective="Renew the annual contract with TechSoft Solutions.",
            description=(
                "TechSoft Solutions is a key software vendor. Their contract expires next quarter. "
                "Perform a compliance review against current procurement policies, identify any "
                "stale policy documents, and draft a renewal recommendation for management approval."
            ),
            expected_outcome=(
                "A signed-off renewal recommendation document covering compliance findings, "
                "stale policy flags, and a clear proceed/escalate decision."
            ),
            status="new",
            created_by=admin_id,
            created_at=_now(),
            updated_at=_now(),
        )
        session.add(work_item)
        await session.flush()
        print(f"  Created work item: {_WORK_ITEM_NAME}  (id={work_item.id})")
    else:
        print(f"  Reusing work item: {_WORK_ITEM_NAME}  (id={work_item.id})")

    # ── 8. Upsert Workers ─────────────────────────────────────────────────────
    result = await session.execute(
        select(WorkItemWorker).where(
            WorkItemWorker.work_item_id == work_item.id,
            WorkItemWorker.worker_type == "ai_agent",
        )
    )
    if result.scalar_one_or_none() is None:
        session.add(WorkItemWorker(
            id=uuid.uuid4(),
            work_item_id=work_item.id,
            worker_type="ai_agent",
            agent_version_id=agent_version.id,
            user_id=None,
            created_at=_now(),
            updated_at=_now(),
        ))
        print("  Created AI worker")
    else:
        print("  AI worker already exists")

    result = await session.execute(
        select(WorkItemWorker).where(
            WorkItemWorker.work_item_id == work_item.id,
            WorkItemWorker.worker_type == "human",
            WorkItemWorker.user_id == reviewer_id,
        )
    )
    if result.scalar_one_or_none() is None:
        session.add(WorkItemWorker(
            id=uuid.uuid4(),
            work_item_id=work_item.id,
            worker_type="human",
            agent_version_id=None,
            user_id=reviewer_id,
            created_at=_now(),
            updated_at=_now(),
        ))
        print(f"  Created human worker: {_REVIEWER_EMAIL}")
    else:
        print(f"  Human worker already exists: {_REVIEWER_EMAIL}")

    await session.flush()

    # ── 9. Check if a published policy already exists ─────────────────────────
    result = await session.execute(
        select(Policy).where(
            Policy.work_item_id == work_item.id,
            Policy.status == "published",
        )
    )
    existing_published = result.scalar_one_or_none()
    if existing_published is not None:
        print(f"\n  Policy already published (id={existing_published.id}) — skipping policy creation.")
        print("  Done.")
        return

    # ── 10. Create Policy ─────────────────────────────────────────────────────
    result = await session.execute(
        select(Policy).where(Policy.work_item_id == work_item.id)
        .order_by(Policy.version.desc())
    )
    existing_policy = result.scalars().first()
    next_version = (existing_policy.version + 1) if existing_policy else 1

    policy = Policy(
        id=uuid.uuid4(),
        work_item_id=work_item.id,
        version=next_version,
        status="draft",
        generated_by="seed_techsoft",
        published_by=admin_id,
        published_at=None,
        created_at=_now(),
        updated_at=_now(),
    )
    session.add(policy)
    await session.flush()
    print(f"  Created policy v{next_version}  (id={policy.id})")

    # ── 11. Create Stages ─────────────────────────────────────────────────────
    stage1 = PolicyStage(
        id=uuid.uuid4(),
        policy_id=policy.id,
        sequence=1,
        name="Compliance Review",
        description=_STAGE1_DESC,
        expected_output=_STAGE1_EXPECTED,
        agent_version_id=agent_version.id,
        created_at=_now(),
        updated_at=_now(),
    )
    stage2 = PolicyStage(
        id=uuid.uuid4(),
        policy_id=policy.id,
        sequence=2,
        name="Draft Renewal Recommendation",
        description=_STAGE2_DESC,
        expected_output=_STAGE2_EXPECTED,
        agent_version_id=agent_version.id,
        created_at=_now(),
        updated_at=_now(),
    )
    session.add(stage1)
    session.add(stage2)
    await session.flush()
    print(f"  Created Stage 1: Compliance Review  (id={stage1.id})")
    print(f"  Created Stage 2: Draft Renewal Recommendation  (id={stage2.id})")

    # ── 12. Create Checkpoints ────────────────────────────────────────────────
    # Mid-stage review (after Stage 1, before Stage 2)
    cp1 = Checkpoint(
        id=uuid.uuid4(),
        policy_id=policy.id,
        stage_id=stage1.id,
        type="review",
        assigned_user_id=reviewer_id,
        instruction=_STAGE1_CHECKPOINT_INSTRUCTION,
        created_at=_now(),
        updated_at=_now(),
    )
    # Final review (after all stages)
    cp2 = Checkpoint(
        id=uuid.uuid4(),
        policy_id=policy.id,
        stage_id=None,  # final_review has no stage_id
        type="final_review",
        assigned_user_id=reviewer_id,
        instruction=_FINAL_CHECKPOINT_INSTRUCTION,
        created_at=_now(),
        updated_at=_now(),
    )
    session.add(cp1)
    session.add(cp2)
    await session.flush()
    print(f"  Created mid-stage review checkpoint  (id={cp1.id})")
    print(f"  Created final_review checkpoint  (id={cp2.id})")

    # ── 13. Publish Policy ────────────────────────────────────────────────────
    policy.status = "published"
    policy.published_at = _now()
    policy.updated_at = _now()
    print(f"  Policy published  (id={policy.id})")

    print("\n  TechSoft scenario seeded successfully.")


if __name__ == "__main__":
    asyncio.run(seed())
