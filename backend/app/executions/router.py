from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.auth.models import User
from app.core.db import get_db
from app.executions.models import Execution
from app.executions.schemas import CreateExecutionResponse, ExecutionOut
from app.policies.models import Checkpoint, Policy
from app.work_items.models import WorkItem

router = APIRouter()

_ACTIVE_STATUSES = ("queued", "running", "waiting_for_approval")


@router.post(
    "/work-items/{work_item_id}/executions",
    response_model=CreateExecutionResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def create_execution(
    work_item_id: str,
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
