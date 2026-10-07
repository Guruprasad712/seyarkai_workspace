from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.models import AgentVersion
from app.auth.dependencies import get_current_user
from app.auth.models import User
from app.core.db import get_db
from app.policies.models import Checkpoint, Policy, PolicyStage
from app.policies.schemas import (
    CheckpointOut,
    CreateCheckpointRequest,
    CreatePolicyRequest,
    CreateStageRequest,
    PatchCheckpointRequest,
    PatchStageRequest,
    PolicyOut,
    ReorderStagesRequest,
    StageOut,
)
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
