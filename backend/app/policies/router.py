from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.models import AgentVersion
from app.auth.dependencies import get_current_user
from app.auth.models import User
from app.core.config import settings
from app.core.db import get_db
from app.policies.models import Checkpoint, Policy, PolicyStage
from app.policies.schemas import (
    CheckpointOut,
    CreateCheckpointRequest,
    CreatePolicyRequest,
    CreateStageRequest,
    GenerationResult,
    PatchCheckpointRequest,
    PatchStageRequest,
    PolicyOut,
    ReorderStagesRequest,
    StageOut,
)
from app.runtime import StageError, run_stage
from app.work_items.models import WorkItem, WorkItemWorker

router = APIRouter()

_NOT_FOUND_POLICY = HTTPException(status_code=404, detail="policy not found")
_NOT_FOUND_STAGE = HTTPException(status_code=404, detail="stage not found")
_NOT_FOUND_CHECKPOINT = HTTPException(status_code=404, detail="checkpoint not found")
_NOT_FOUND_WORK_ITEM = HTTPException(status_code=404, detail="work item not found")
_POLICY_NOT_DRAFT = HTTPException(status_code=409, detail="policy is not a draft")
_DRAFT_EXISTS = HTTPException(status_code=409, detail="a draft policy already exists for this work item")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _load_policy(db: AsyncSession, policy_id: str) -> Policy:
    result = await db.execute(select(Policy).where(Policy.id == policy_id))
    policy = result.scalar_one_or_none()
    if policy is None:
        raise _NOT_FOUND_POLICY
    return policy


async def _require_draft(policy: Policy) -> None:
    if policy.status != "draft":
        raise _POLICY_NOT_DRAFT


async def _load_stages(db: AsyncSession, policy_id: str) -> list[PolicyStage]:
    result = await db.execute(
        select(PolicyStage)
        .where(PolicyStage.policy_id == policy_id)
        .order_by(PolicyStage.sequence)
    )
    return list(result.scalars().all())


async def _load_checkpoints(db: AsyncSession, policy_id: str) -> list[Checkpoint]:
    result = await db.execute(
        select(Checkpoint)
        .where(Checkpoint.policy_id == policy_id)
        .order_by(Checkpoint.created_at)
    )
    return list(result.scalars().all())


async def _policy_out(db: AsyncSession, policy: Policy) -> PolicyOut:
    stages = await _load_stages(db, str(policy.id))
    checkpoints = await _load_checkpoints(db, str(policy.id))
    return PolicyOut.from_orm(
        policy,
        stages=[StageOut.from_orm(s) for s in stages],
        checkpoints=[CheckpointOut.from_orm(c) for c in checkpoints],
    )


async def _renumber_stages(db: AsyncSession, policy_id: str) -> None:
    """Rewrite sequences 1..n for remaining stages in creation order."""
    stages = await _load_stages(db, policy_id)
    now = datetime.now(timezone.utc)
    for i, stage in enumerate(stages, start=1):
        if stage.sequence != i:
            stage.sequence = i
            stage.updated_at = now
    await db.commit()


async def _assert_human_worker(db: AsyncSession, work_item_id: str, user_id: str) -> None:
    """Raise 422 if user_id is not an active human worker on the work item."""
    result = await db.execute(
        select(WorkItemWorker).where(
            WorkItemWorker.work_item_id == work_item_id,
            WorkItemWorker.worker_type == "human",
            WorkItemWorker.user_id == user_id,
        )
    )
    worker = result.scalar_one_or_none()
    if worker is None:
        raise HTTPException(
            status_code=422,
            detail=f"user {user_id} is not a human worker on this work item",
        )
    # Also verify user is still active
    user_result = await db.execute(select(User).where(User.id == user_id))
    user = user_result.scalar_one_or_none()
    if user is None or user.status != "active":
        raise HTTPException(
            status_code=422,
            detail=f"user {user_id} is not active",
        )


async def _assert_stage_in_policy(db: AsyncSession, policy_id: str, stage_id: str) -> None:
    """Raise 422 if stage_id is not in this policy."""
    result = await db.execute(
        select(PolicyStage).where(
            PolicyStage.id == stage_id,
            PolicyStage.policy_id == policy_id,
        )
    )
    if result.scalar_one_or_none() is None:
        raise HTTPException(
            status_code=422,
            detail=f"stage {stage_id} does not belong to this policy",
        )


# ---------------------------------------------------------------------------
# Policy routes (nested under work-items)
# ---------------------------------------------------------------------------

@router.post(
    "/work-items/{work_item_id}/policies",
    response_model=PolicyOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_policy(
    work_item_id: str,
    body: CreatePolicyRequest,
    _: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    wi_result = await db.execute(select(WorkItem).where(WorkItem.id == work_item_id))
    if wi_result.scalar_one_or_none() is None:
        raise _NOT_FOUND_WORK_ITEM

    # At most one draft per work item
    draft_result = await db.execute(
        select(Policy).where(
            Policy.work_item_id == work_item_id,
            Policy.status == "draft",
        )
    )
    if draft_result.scalar_one_or_none() is not None:
        raise _DRAFT_EXISTS

    # Next version number
    ver_result = await db.execute(
        select(func.max(Policy.version)).where(Policy.work_item_id == work_item_id)
    )
    max_ver = ver_result.scalar_one()
    next_version = (max_ver or 0) + 1

    now = datetime.now(timezone.utc)
    policy = Policy(
        id=uuid.uuid4(),
        work_item_id=uuid.UUID(work_item_id),
        version=next_version,
        status="draft",
        generated_by=body.generated_by,
        published_by=None,
        published_at=None,
        created_at=now,
        updated_at=now,
    )
    db.add(policy)
    await db.commit()
    await db.refresh(policy)
    return await _policy_out(db, policy)


@router.get("/work-items/{work_item_id}/policies", response_model=list[PolicyOut])
async def list_policies(
    work_item_id: str,
    _: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    wi_result = await db.execute(select(WorkItem).where(WorkItem.id == work_item_id))
    if wi_result.scalar_one_or_none() is None:
        raise _NOT_FOUND_WORK_ITEM

    result = await db.execute(
        select(Policy)
        .where(Policy.work_item_id == work_item_id)
        .order_by(Policy.version)
    )
    policies = result.scalars().all()
    return [await _policy_out(db, p) for p in policies]


# ---------------------------------------------------------------------------
# Generation helpers
# ---------------------------------------------------------------------------

def _build_generate_prompt(
    work_item: WorkItem,
    wi_workers: list[WorkItemWorker],
    worker_details: list[dict],
) -> str:
    """Build the task_text for run_stage from work item + resolved worker details."""
    lines = [
        "You are a workflow planner for an enterprise execution engine.",
        "",
        "## Work Item",
        f"Objective: {work_item.objective}",
        f"Description: {work_item.description}",
        f"Expected Outcome: {work_item.expected_outcome}",
        "",
        "## Available Workers",
        "Use these worker_id values exactly in your output.",
    ]
    for detail in worker_details:
        if detail["type"] == "ai_agent":
            caps = ", ".join(detail.get("capabilities", [])) or "none"
            tools = ", ".join(detail.get("tools", [])) or "none"
            lines += [
                f"- worker_id: {detail['worker_id']}",
                f"  type: ai_agent",
                f"  name: {detail['name']} (version {detail['version']})",
                f"  capabilities: {caps}",
                f"  tools: {tools}",
            ]
        else:
            lines += [
                f"- worker_id: {detail['worker_id']}",
                f"  type: human",
                f"  name: {detail['name']}",
            ]
    lines += [
        "",
        "## Output Rules",
        "1. Prefer AI agents for work tasks.",
        "2. Add checkpoints where human judgement is needed.",
        "3. End with EXACTLY one final_review checkpoint with stage_index null.",
        "4. worker_ref and assignee_ref MUST be worker_id values from the list above.",
        "5. Non-final checkpoints MUST have a zero-based stage_index (integer).",
        "",
        "## Required Output Schema",
        "Return ONLY valid JSON — no markdown fences, no commentary, nothing else.",
        json.dumps({
            "stages": [
                {"name": "string", "description": "string",
                 "expected_output": "string", "worker_ref": "worker_id string"}
            ],
            "checkpoints": [
                {"type": "approval|review|input|final_review",
                 "stage_index": "integer or null", "assignee_ref": "worker_id string",
                 "instruction": "string"}
            ],
        }, indent=2),
    ]
    return "\n".join(lines)


def _validate_generation(result: GenerationResult, ai_worker_ids: set[str], human_worker_ids: set[str]) -> list[dict]:
    """Collect all pre-flight validation failures for a generated policy proposal."""
    failures: list[dict] = []

    if not result.stages:
        failures.append({"code": "no_stages", "message": "generation produced no stages"})
        return failures  # remaining checks need stages to exist

    for i, stage in enumerate(result.stages):
        if stage.worker_ref not in ai_worker_ids:
            failures.append({
                "code": "worker_ref_invalid",
                "message": f"stage {i}: worker_ref '{stage.worker_ref}' is not an AI worker on this work item",
            })

    final_reviews = [cp for cp in result.checkpoints if cp.type == "final_review"]
    if len(final_reviews) == 0:
        failures.append({"code": "missing_final_review", "message": "no final_review checkpoint"})
    elif len(final_reviews) > 1:
        failures.append({"code": "multiple_final_reviews", "message": f"{len(final_reviews)} final_review checkpoints (must be exactly 1)"})

    for j, cp in enumerate(result.checkpoints):
        if cp.assignee_ref not in human_worker_ids:
            failures.append({
                "code": "assignee_ref_invalid",
                "message": f"checkpoint {j}: assignee_ref '{cp.assignee_ref}' is not a human worker on this work item",
            })
        if cp.type == "final_review":
            if cp.stage_index is not None:
                failures.append({
                    "code": "final_review_has_stage_index",
                    "message": f"checkpoint {j}: final_review must have stage_index null",
                })
        else:
            if cp.stage_index is None:
                failures.append({
                    "code": "non_final_review_missing_stage_index",
                    "message": f"checkpoint {j}: non-final checkpoint requires a stage_index",
                })
            elif cp.stage_index >= len(result.stages):
                failures.append({
                    "code": "stage_index_out_of_range",
                    "message": f"checkpoint {j}: stage_index {cp.stage_index} out of range (0–{len(result.stages) - 1})",
                })

    return failures


@router.post(
    "/work-items/{work_item_id}/policies/generate",
    response_model=PolicyOut,
    status_code=status.HTTP_201_CREATED,
)
async def generate_policy(
    work_item_id: str,
    _: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    wi_result = await db.execute(select(WorkItem).where(WorkItem.id == work_item_id))
    work_item = wi_result.scalar_one_or_none()
    if work_item is None:
        raise _NOT_FOUND_WORK_ITEM

    draft_result = await db.execute(
        select(Policy).where(
            Policy.work_item_id == work_item_id,
            Policy.status == "draft",
        )
    )
    if draft_result.scalar_one_or_none() is not None:
        raise _DRAFT_EXISTS

    # Load all workers on this work item
    workers_result = await db.execute(
        select(WorkItemWorker).where(WorkItemWorker.work_item_id == work_item_id)
    )
    wi_workers = list(workers_result.scalars().all())

    # Resolve worker details for the prompt
    worker_details: list[dict] = []
    ai_worker_ids: set[str] = set()
    human_worker_ids: set[str] = set()

    for w in wi_workers:
        wid = str(w.id)
        if w.worker_type == "ai_agent" and w.agent_version_id:
            ver_result = await db.execute(
                select(AgentVersion).where(AgentVersion.id == w.agent_version_id)
            )
            ver = ver_result.scalar_one_or_none()
            if ver is None:
                continue
            from app.agents.models import Agent
            agent_result = await db.execute(select(Agent).where(Agent.id == ver.agent_id))
            agent = agent_result.scalar_one_or_none()
            caps = [c.get("name", "") for c in (ver.capabilities or [])]
            # Load tool names
            tools_result = await db.execute(
                text(
                    "SELECT t.tool_name FROM mcp_tools t "
                    "JOIN agent_version_tools avt ON avt.mcp_tool_id = t.id "
                    "WHERE avt.agent_version_id = :vid"
                ),
                {"vid": str(ver.id)},
            )
            tools = [row[0] for row in tools_result.fetchall()]
            worker_details.append({
                "type": "ai_agent",
                "worker_id": wid,
                "name": agent.name if agent else "unknown",
                "version": ver.version,
                "capabilities": caps,
                "tools": tools,
            })
            ai_worker_ids.add(wid)
        elif w.worker_type == "human" and w.user_id:
            user_result = await db.execute(select(User).where(User.id == w.user_id))
            user = user_result.scalar_one_or_none()
            worker_details.append({
                "type": "human",
                "worker_id": wid,
                "name": user.name if user else "unknown",
            })
            human_worker_ids.add(wid)

    prompt = _build_generate_prompt(work_item, wi_workers, worker_details)
    model = settings.GEMINI_MODEL_FAST or "gemini-2.5-flash"
    agent_def = {
        "name": "policy_generator",
        "instructions": "You generate structured workflow policies as JSON.",
        "_model": model,
    }

    final_text: str | None = None
    try:
        async for event in run_stage(agent_def, prompt, tool_names=[], max_llm_calls=1, timeout_seconds=60.0):
            if event.get("event_type") == "stage.stream_end":
                final_text = event["payload"]["final_text"]
    except StageError as e:
        raise HTTPException(502, {"error": "Policy generation failed", "detail": str(e)})

    if not final_text:
        raise HTTPException(502, {"error": "Policy generation failed", "detail": "no output"})

    try:
        # Strip markdown fences if Gemini wraps anyway
        text_clean = final_text.strip()
        if text_clean.startswith("```"):
            text_clean = "\n".join(text_clean.splitlines()[1:])
            if text_clean.endswith("```"):
                text_clean = text_clean[: text_clean.rfind("```")]
        raw = json.loads(text_clean)
        result = GenerationResult.model_validate(raw)
    except Exception as e:
        raise HTTPException(502, {"error": "Policy generation failed", "detail": f"parse error: {e}"})

    failures = _validate_generation(result, ai_worker_ids, human_worker_ids)
    if failures:
        raise HTTPException(422, {"error": "generation_validation_failed", "failures": failures})

    # Persist — all in one transaction
    now = datetime.now(timezone.utc)
    ver_result = await db.execute(
        select(func.max(Policy.version)).where(Policy.work_item_id == work_item_id)
    )
    next_version = (ver_result.scalar_one() or 0) + 1

    policy = Policy(
        id=uuid.uuid4(),
        work_item_id=uuid.UUID(work_item_id),
        version=next_version,
        status="draft",
        generated_by="llm",
        published_by=None,
        published_at=None,
        created_at=now,
        updated_at=now,
    )
    db.add(policy)
    await db.flush()

    wi_worker_map = {str(w.id): w for w in wi_workers}

    for i, s in enumerate(result.stages, start=1):
        worker = wi_worker_map[s.worker_ref]
        db.add(PolicyStage(
            id=uuid.uuid4(),
            policy_id=policy.id,
            sequence=i,
            name=s.name,
            description=s.description,
            expected_output=s.expected_output,
            agent_version_id=worker.agent_version_id,
            created_at=now,
            updated_at=now,
        ))

    await db.flush()
    stages_in_order = await _load_stages(db, str(policy.id))
    stage_id_by_index = {idx: s.id for idx, s in enumerate(stages_in_order)}

    for cp in result.checkpoints:
        sid = stage_id_by_index[cp.stage_index] if cp.stage_index is not None else None
        db.add(Checkpoint(
            id=uuid.uuid4(),
            policy_id=policy.id,
            stage_id=sid,
            type=cp.type,
            assigned_user_id=uuid.UUID(str(wi_worker_map[cp.assignee_ref].user_id)),
            instruction=cp.instruction,
            created_at=now,
            updated_at=now,
        ))

    await db.commit()
    await db.refresh(policy)
    return await _policy_out(db, policy)


# ---------------------------------------------------------------------------
# Policy detail
# ---------------------------------------------------------------------------

@router.get("/policies/{policy_id}", response_model=PolicyOut)
async def get_policy(
    policy_id: str,
    _: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    policy = await _load_policy(db, policy_id)
    return await _policy_out(db, policy)


# ---------------------------------------------------------------------------
# Stage routes
# ---------------------------------------------------------------------------

@router.post(
    "/policies/{policy_id}/stages",
    response_model=StageOut,
    status_code=status.HTTP_201_CREATED,
)
async def add_stage(
    policy_id: str,
    body: CreateStageRequest,
    _: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    policy = await _load_policy(db, policy_id)
    await _require_draft(policy)

    seq_result = await db.execute(
        select(func.max(PolicyStage.sequence)).where(PolicyStage.policy_id == policy_id)
    )
    max_seq = seq_result.scalar_one()
    next_seq = (max_seq or 0) + 1

    now = datetime.now(timezone.utc)
    stage = PolicyStage(
        id=uuid.uuid4(),
        policy_id=uuid.UUID(policy_id),
        sequence=next_seq,
        name=body.name,
        description=body.description,
        expected_output=body.expected_output,
        agent_version_id=uuid.UUID(body.agent_version_id),
        created_at=now,
        updated_at=now,
    )
    db.add(stage)
    await db.commit()
    await db.refresh(stage)
    return StageOut.from_orm(stage)


@router.patch("/policies/{policy_id}/stages/{stage_id}", response_model=StageOut)
async def patch_stage(
    policy_id: str,
    stage_id: str,
    body: PatchStageRequest,
    _: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    policy = await _load_policy(db, policy_id)
    await _require_draft(policy)

    result = await db.execute(
        select(PolicyStage).where(
            PolicyStage.id == stage_id,
            PolicyStage.policy_id == policy_id,
        )
    )
    stage = result.scalar_one_or_none()
    if stage is None:
        raise _NOT_FOUND_STAGE

    if body.name is not None:
        stage.name = body.name
    if body.description is not None:
        stage.description = body.description
    if body.expected_output is not None:
        stage.expected_output = body.expected_output
    if body.agent_version_id is not None:
        stage.agent_version_id = uuid.UUID(body.agent_version_id)
    stage.updated_at = datetime.now(timezone.utc)

    await db.commit()
    await db.refresh(stage)
    return StageOut.from_orm(stage)


@router.delete(
    "/policies/{policy_id}/stages/{stage_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_stage(
    policy_id: str,
    stage_id: str,
    _: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    policy = await _load_policy(db, policy_id)
    await _require_draft(policy)

    result = await db.execute(
        select(PolicyStage).where(
            PolicyStage.id == stage_id,
            PolicyStage.policy_id == policy_id,
        )
    )
    stage = result.scalar_one_or_none()
    if stage is None:
        raise _NOT_FOUND_STAGE

    # Cannot delete a stage that has checkpoints
    cp_result = await db.execute(
        select(func.count()).select_from(Checkpoint).where(Checkpoint.stage_id == stage_id)
    )
    if cp_result.scalar_one() > 0:
        raise HTTPException(
            status_code=422,
            detail={"error": "stage_has_checkpoints", "message": "stage has checkpoints; delete them first"},
        )

    await db.delete(stage)
    await db.commit()
    await _renumber_stages(db, policy_id)


@router.put("/policies/{policy_id}/stages/order", response_model=PolicyOut)
async def reorder_stages(
    policy_id: str,
    body: ReorderStagesRequest,
    _: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    policy = await _load_policy(db, policy_id)
    await _require_draft(policy)

    existing = await _load_stages(db, policy_id)
    existing_ids = {str(s.id) for s in existing}
    incoming_ids = set(body.stage_ids)

    if existing_ids != incoming_ids:
        raise HTTPException(
            status_code=422,
            detail="stage_ids must be exactly the set of current stage IDs",
        )

    id_to_stage = {str(s.id): s for s in existing}
    now = datetime.now(timezone.utc)
    for i, sid in enumerate(body.stage_ids, start=1):
        stage = id_to_stage[sid]
        stage.sequence = i
        stage.updated_at = now

    await db.commit()
    return await _policy_out(db, policy)


# ---------------------------------------------------------------------------
# Checkpoint routes
# ---------------------------------------------------------------------------

@router.post(
    "/policies/{policy_id}/checkpoints",
    response_model=CheckpointOut,
    status_code=status.HTTP_201_CREATED,
)
async def add_checkpoint(
    policy_id: str,
    body: CreateCheckpointRequest,
    _: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    policy = await _load_policy(db, policy_id)
    await _require_draft(policy)

    # Validate stage_id vs type
    if body.type == "final_review":
        if body.stage_id is not None:
            raise HTTPException(status_code=422, detail="final_review checkpoint must not have a stage_id")
    else:
        if body.stage_id is None:
            raise HTTPException(status_code=422, detail="non-final_review checkpoint requires a stage_id")
        await _assert_stage_in_policy(db, policy_id, body.stage_id)

    await _assert_human_worker(db, str(policy.work_item_id), body.assigned_user_id)

    now = datetime.now(timezone.utc)
    checkpoint = Checkpoint(
        id=uuid.uuid4(),
        policy_id=uuid.UUID(policy_id),
        stage_id=uuid.UUID(body.stage_id) if body.stage_id else None,
        type=body.type,
        assigned_user_id=uuid.UUID(body.assigned_user_id),
        instruction=body.instruction,
        created_at=now,
        updated_at=now,
    )
    db.add(checkpoint)
    await db.commit()
    await db.refresh(checkpoint)
    return CheckpointOut.from_orm(checkpoint)


@router.patch("/policies/{policy_id}/checkpoints/{checkpoint_id}", response_model=CheckpointOut)
async def patch_checkpoint(
    policy_id: str,
    checkpoint_id: str,
    body: PatchCheckpointRequest,
    _: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    policy = await _load_policy(db, policy_id)
    await _require_draft(policy)

    result = await db.execute(
        select(Checkpoint).where(
            Checkpoint.id == checkpoint_id,
            Checkpoint.policy_id == policy_id,
        )
    )
    checkpoint = result.scalar_one_or_none()
    if checkpoint is None:
        raise _NOT_FOUND_CHECKPOINT

    if body.stage_id is not None:
        effective_type = checkpoint.type
        if effective_type == "final_review":
            raise HTTPException(status_code=422, detail="final_review checkpoint must not have a stage_id")
        await _assert_stage_in_policy(db, policy_id, body.stage_id)
        checkpoint.stage_id = uuid.UUID(body.stage_id)

    if body.assigned_user_id is not None:
        await _assert_human_worker(db, str(policy.work_item_id), body.assigned_user_id)
        checkpoint.assigned_user_id = uuid.UUID(body.assigned_user_id)

    if body.instruction is not None:
        checkpoint.instruction = body.instruction

    checkpoint.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(checkpoint)
    return CheckpointOut.from_orm(checkpoint)


@router.delete(
    "/policies/{policy_id}/checkpoints/{checkpoint_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_checkpoint(
    policy_id: str,
    checkpoint_id: str,
    _: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    policy = await _load_policy(db, policy_id)
    await _require_draft(policy)

    result = await db.execute(
        select(Checkpoint).where(
            Checkpoint.id == checkpoint_id,
            Checkpoint.policy_id == policy_id,
        )
    )
    checkpoint = result.scalar_one_or_none()
    if checkpoint is None:
        raise _NOT_FOUND_CHECKPOINT

    await db.delete(checkpoint)
    await db.commit()


# ---------------------------------------------------------------------------
# Publish
# ---------------------------------------------------------------------------

@router.post("/policies/{policy_id}/publish", response_model=PolicyOut)
async def publish_policy(
    policy_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    policy = await _load_policy(db, policy_id)
    stages = await _load_stages(db, policy_id)
    checkpoints = await _load_checkpoints(db, policy_id)

    # Collect ALL failures before raising — same pattern as agents publish
    failures: list[dict] = []

    if policy.status != "draft":
        failures.append({"code": "not_draft", "message": "policy is not a draft"})

    if not stages:
        failures.append({"code": "no_stages", "message": "policy has no stages"})
    else:
        # Verify sequences are exactly 1..n
        expected = list(range(1, len(stages) + 1))
        actual = [s.sequence for s in stages]
        if actual != expected:
            failures.append({
                "code": "sequence_not_contiguous",
                "message": f"stage sequences must be 1..{len(stages)}, got {actual}",
            })

        # Fetch work item workers for validation
        wi_workers_result = await db.execute(
            select(WorkItemWorker).where(WorkItemWorker.work_item_id == policy.work_item_id)
        )
        wi_workers = wi_workers_result.scalars().all()
        ai_worker_version_ids = {str(w.agent_version_id) for w in wi_workers if w.worker_type == "ai_agent"}

        for stage in stages:
            stage_avid = str(stage.agent_version_id)
            if stage_avid not in ai_worker_version_ids:
                failures.append({
                    "code": "stage_worker_not_assigned",
                    "message": f"stage '{stage.name}' agent version is not an AI worker on the work item",
                })
            else:
                ver_result = await db.execute(
                    select(AgentVersion).where(AgentVersion.id == stage.agent_version_id)
                )
                ver = ver_result.scalar_one_or_none()
                if ver is None or ver.status != "published":
                    failures.append({
                        "code": "stage_agent_not_published",
                        "message": f"stage '{stage.name}' agent version is not published",
                    })

    # Final review check
    final_reviews = [c for c in checkpoints if c.type == "final_review"]
    if len(final_reviews) == 0:
        failures.append({"code": "missing_final_review", "message": "policy must have exactly one final review checkpoint"})
    elif len(final_reviews) > 1:
        failures.append({"code": "multiple_final_reviews", "message": "policy has more than one final review checkpoint"})

    # At most one checkpoint per stage
    stage_checkpoint_counts: dict[str, int] = {}
    for cp in checkpoints:
        if cp.stage_id is not None:
            sid = str(cp.stage_id)
            stage_checkpoint_counts[sid] = stage_checkpoint_counts.get(sid, 0) + 1
    for sid, count in stage_checkpoint_counts.items():
        if count > 1:
            failures.append({
                "code": "multiple_checkpoints_on_stage",
                "message": f"stage {sid} has {count} checkpoints (max 1)",
            })

    # Validate checkpoint assignees are active human workers
    wi_human_user_ids_result = await db.execute(
        select(WorkItemWorker.user_id).where(
            WorkItemWorker.work_item_id == policy.work_item_id,
            WorkItemWorker.worker_type == "human",
        )
    )
    wi_human_ids = {str(r) for r in wi_human_user_ids_result.scalars().all()}
    for cp in checkpoints:
        if str(cp.assigned_user_id) not in wi_human_ids:
            failures.append({
                "code": "checkpoint_assignee_invalid",
                "message": f"checkpoint assignee {cp.assigned_user_id} is not a human worker on this work item",
            })

    if failures:
        raise HTTPException(
            status_code=422,
            detail={"error": "publish_validation_failed", "failures": failures},
        )

    now = datetime.now(timezone.utc)
    policy.status = "published"
    policy.published_by = current_user.id
    policy.published_at = now
    policy.updated_at = now

    await db.commit()
    await db.refresh(policy)
    return await _policy_out(db, policy)
