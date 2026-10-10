from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from sse_starlette.sse import EventSourceResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.auth.models import User
from app.core.db import get_db
from app.executions.engine import ExecutionEngine
from app.executions.models import Execution, ExecutionEvent, CheckpointResponse, Message
from app.executions.schemas import (
    CheckpointResponseIn,
    CheckpointResponseOut,
    CreateExecutionResponse,
    ExecutionOut,
)
from app.policies.models import Checkpoint, Policy, PolicyStage
from app.work_items.models import WorkItem

router = APIRouter()

_ACTIVE_STATUSES = ("queued", "running", "waiting_for_approval")
_TERMINAL_STATUSES = ("completed", "failed")


@router.post(
    "/work-items/{work_item_id}/executions",
    response_model=CreateExecutionResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def create_execution(
    work_item_id: str,
    background_tasks: BackgroundTasks,
    _: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # 1. Load work item
    result = await db.execute(select(WorkItem).where(WorkItem.id == work_item_id))
    work_item = result.scalar_one_or_none()
    if work_item is None:
        raise HTTPException(status_code=404, detail="work item not found")

    # 2. Latest published policy
    result = await db.execute(
        select(Policy)
        .where(Policy.work_item_id == work_item_id, Policy.status == "published")
        .order_by(Policy.version.desc())
        .limit(1)
    )
    policy = result.scalar_one_or_none()
    if policy is None:
        raise HTTPException(
            status_code=422,
            detail={
                "error": "no_published_policy",
                "message": "work item has no published policy; publish one before starting an execution",
            },
        )

    # 3. Block if active execution exists
    result = await db.execute(
        select(Execution).where(
            Execution.work_item_id == work_item_id,
            Execution.status.in_(_ACTIVE_STATUSES),
        )
    )
    if result.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=409,
            detail="an active execution already exists for this work item",
        )

    # 4. execution_number = max existing + 1
    result = await db.execute(
        select(func.max(Execution.execution_number)).where(
            Execution.work_item_id == work_item_id
        )
    )
    last = result.scalar_one()
    execution_number = (last or 0) + 1

    # 5. Create execution
    now = datetime.now(timezone.utc)
    execution = Execution(
        work_item_id=work_item_id,
        policy_id=str(policy.id),
        execution_number=execution_number,
        status="queued",
        created_at=now,
        updated_at=now,
    )
    db.add(execution)

    # 6. Transition work item new → in_progress
    if work_item.status == "new":
        work_item.status = "in_progress"
        work_item.updated_at = now

    await db.flush()
    await db.commit()

    background_tasks.add_task(ExecutionEngine().run_execution, str(execution.id))
    return CreateExecutionResponse(execution_id=str(execution.id))


@router.get("/executions/{execution_id}", response_model=ExecutionOut)
async def get_execution(
    execution_id: str,
    _: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Execution).where(Execution.id == execution_id))
    execution = result.scalar_one_or_none()
    if execution is None:
        raise HTTPException(status_code=404, detail="execution not found")

    blocking_checkpoint = None
    if execution.blocking_checkpoint_id is not None:
        result = await db.execute(
            select(Checkpoint).where(Checkpoint.id == execution.blocking_checkpoint_id)
        )
        blocking_checkpoint = result.scalar_one_or_none()

    return ExecutionOut.from_orm(execution, blocking_checkpoint)


@router.get("/work-items/{work_item_id}/executions", response_model=list[ExecutionOut])
async def list_executions(
    work_item_id: str,
    _: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(WorkItem).where(WorkItem.id == work_item_id))
    if result.scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail="work item not found")

    result = await db.execute(
        select(Execution)
        .where(Execution.work_item_id == work_item_id)
        .order_by(Execution.execution_number)
    )
    executions = list(result.scalars().all())
    return [ExecutionOut.from_orm(e) for e in executions]


@router.get("/executions/{execution_id}/stream")
async def stream_execution_events(
    execution_id: str,
    after: str | None = Query(default=None),
    _: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Execution).where(Execution.id == execution_id))
    execution = result.scalar_one_or_none()
    if execution is None:
        raise HTTPException(status_code=404, detail="execution not found")

    query = select(ExecutionEvent).where(ExecutionEvent.execution_id == execution_id)

    if after is not None:
        result = await db.execute(
            select(ExecutionEvent).where(ExecutionEvent.id == after)
        )
        anchor = result.scalar_one_or_none()
        if anchor is not None:
            query = query.where(ExecutionEvent.created_at > anchor.created_at)

    query = query.order_by(ExecutionEvent.created_at)
    result = await db.execute(query)
    events = list(result.scalars().all())

    is_terminal = execution.status in _TERMINAL_STATUSES

    async def _generate():
        for ev in events:
            yield {
                "id": str(ev.id),
                "event": ev.event_type,
                "data": json.dumps(ev.payload),
            }
        if is_terminal and not events:
            # No new events and already terminal — signal to client
            yield {"event": "stream.end", "data": json.dumps({"status": execution.status})}

    return EventSourceResponse(_generate())


# Valid decisions per checkpoint type
_ALLOWED_DECISIONS: dict[str, set[str]] = {
    "approval": {"approve", "reject"},
    "review": {"approve", "reject"},
    "final_review": {"approve", "reject"},
    "input": {"input_provided"},
}


@router.post(
    "/executions/{execution_id}/checkpoints/{checkpoint_id}/respond",
    response_model=CheckpointResponseOut,
)
async def respond_to_checkpoint(
    execution_id: str,
    checkpoint_id: str,
    body: CheckpointResponseIn,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # 1. Load execution
    result = await db.execute(select(Execution).where(Execution.id == execution_id))
    execution = result.scalar_one_or_none()
    if execution is None:
        raise HTTPException(status_code=404, detail="execution not found")

    # 2. Must be waiting for approval
    if execution.status != "waiting_for_approval":
        raise HTTPException(
            status_code=422,
            detail={"error": "not_waiting", "message": "execution is not waiting for a checkpoint response"},
        )

    # 3. Must be the currently blocking checkpoint
    if execution.blocking_checkpoint_id is None or str(execution.blocking_checkpoint_id) != checkpoint_id:
        raise HTTPException(
            status_code=422,
            detail={"error": "wrong_checkpoint", "message": "this is not the currently blocking checkpoint"},
        )

    # 4. Load checkpoint
    result = await db.execute(select(Checkpoint).where(Checkpoint.id == checkpoint_id))
    checkpoint = result.scalar_one_or_none()
    if checkpoint is None:
        raise HTTPException(status_code=404, detail="checkpoint not found")

    # 5. Permission: assignee or super_admin
    if str(checkpoint.assigned_user_id) != str(current_user.id) and current_user.role != "super_admin":
        raise HTTPException(status_code=403, detail="only the assigned reviewer or a super_admin may respond")

    # 6. Validate decision vs checkpoint type (all-failures)
    failures = []
    allowed = _ALLOWED_DECISIONS.get(checkpoint.type, set())
    if body.decision not in allowed:
        failures.append({
            "code": "invalid_decision",
            "message": f"decision '{body.decision}' is not valid for checkpoint type '{checkpoint.type}'; allowed: {sorted(allowed)}",
        })
    if body.decision == "input_provided" and not (body.input_text or "").strip():
        failures.append({
            "code": "input_text_required",
            "message": "input_text is required when decision is 'input_provided'",
        })
    if failures:
        raise HTTPException(status_code=422, detail={"error": "validation_failed", "failures": failures})

    # ------------------------------------------------------------------
    # All checks passed — apply the response in one transaction
    # ------------------------------------------------------------------
    now = datetime.now(timezone.utc)

    # Insert checkpoint_response record
    cp_response = CheckpointResponse(
        id=uuid.uuid4(),
        checkpoint_id=checkpoint_id,
        execution_id=execution_id,
        responded_by=current_user.id,
        decision=body.decision,
        comment=body.comment or None,
        input={"text": body.input_text} if body.input_text else None,
        created_at=now,
        updated_at=now,
    )
    db.add(cp_response)

    # Emit checkpoint.resolved event
    resolved_payload: dict = {"checkpoint_id": checkpoint_id, "decision": body.decision}
    if body.comment:
        resolved_payload["comment"] = body.comment
    checkpoint_event = ExecutionEvent(
        id=uuid.uuid4(),
        execution_id=execution_id,
        stage_id=str(checkpoint.stage_id) if checkpoint.stage_id else None,
        event_type="checkpoint.resolved",
        actor_type="human",
        actor_id=current_user.id,
        payload=resolved_payload,
        created_at=now,
    )
    db.add(checkpoint_event)

    next_action: str
    next_stage_sequence: int | None = None

    if body.decision == "reject":
        error_msg = body.comment or "rejected by reviewer"
        execution.status = "failed"
        execution.error = error_msg
        execution.completed_at = now
        execution.blocking_checkpoint_id = None
        execution.updated_at = now
        db.add(ExecutionEvent(
            id=uuid.uuid4(),
            execution_id=execution_id,
            stage_id=None,
            event_type="execution.failed",
            actor_type="system",
            payload={"error": error_msg},
            created_at=now,
        ))
        next_action = "failed"

    elif body.decision == "approve" and checkpoint.stage_id is None:
        # Final review approval — complete everything
        result = await db.execute(select(WorkItem).where(WorkItem.id == execution.work_item_id))
        work_item = result.scalar_one()
        execution.status = "completed"
        execution.completed_at = now
        execution.blocking_checkpoint_id = None
        execution.updated_at = now
        work_item.status = "completed"
        work_item.updated_at = now
        db.add(ExecutionEvent(
            id=uuid.uuid4(),
            execution_id=execution_id,
            stage_id=None,
            event_type="execution.completed",
            actor_type="system",
            payload={},
            created_at=now,
        ))
        next_action = "completed"

    else:
        # approve (stage checkpoint) or input_provided — resume engine
        if checkpoint.stage_id is not None:
            result = await db.execute(
                select(PolicyStage).where(PolicyStage.id == checkpoint.stage_id)
            )
            owning_stage = result.scalar_one()
            next_stage_sequence = owning_stage.sequence + 1
        else:
            next_stage_sequence = 1

        if body.decision == "input_provided" and body.input_text:
            # Store input as unconsumed guidance for the next stage
            db.add(Message(
                id=uuid.uuid4(),
                execution_id=execution_id,
                stage_id=checkpoint.stage_id,
                sender_type="human",
                sender_id=current_user.id,
                message_type="guidance",
                content=body.input_text,
                consumed_at=None,
                created_at=now,
                updated_at=now,
            ))

        execution.status = "running"
        execution.blocking_checkpoint_id = None
        execution.updated_at = now
        db.add(ExecutionEvent(
            id=uuid.uuid4(),
            execution_id=execution_id,
            stage_id=None,
            event_type="execution.resumed",
            actor_type="system",
            payload={},
            created_at=now,
        ))
        next_action = "resume"

    await db.commit()

    if next_action == "resume" and next_stage_sequence is not None:
        background_tasks.add_task(
            ExecutionEngine().run_execution, execution_id, next_stage_sequence
        )

    return CheckpointResponseOut(
        execution_id=execution_id,
        status=execution.status,
        next_action=next_action,
    )
