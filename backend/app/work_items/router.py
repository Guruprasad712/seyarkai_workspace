from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.auth.models import User
from app.core.db import get_db
from app.work_items.models import WorkItem
from app.work_items.schemas import PatchWorkItemRequest, WorkItemOut

router = APIRouter()

_NOT_FOUND = HTTPException(status_code=404, detail="work item not found")
_NAME_CONFLICT = HTTPException(status_code=409, detail="work item name already exists in this project")


@router.get("/work-items/{work_item_id}", response_model=WorkItemOut)
async def get_work_item(
    work_item_id: str,
    _: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(WorkItem).where(WorkItem.id == work_item_id))
    work_item = result.scalar_one_or_none()
    if work_item is None:
        raise _NOT_FOUND

    from app.projects.router import _resolve_workers
    workers_out = await _resolve_workers(db, work_item.id)
    return WorkItemOut.from_orm(work_item, workers=workers_out)


@router.patch("/work-items/{work_item_id}", response_model=WorkItemOut)
async def patch_work_item(
    work_item_id: str,
    body: PatchWorkItemRequest,
    _: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(WorkItem).where(WorkItem.id == work_item_id))
    work_item = result.scalar_one_or_none()
    if work_item is None:
        raise _NOT_FOUND

    if body.name is not None:
        work_item.name = body.name
    if body.objective is not None:
        work_item.objective = body.objective
    if body.description is not None:
        work_item.description = body.description
    if body.expected_outcome is not None:
        work_item.expected_outcome = body.expected_outcome
    if body.previous_output is not None:
        work_item.previous_output = body.previous_output
    work_item.updated_at = datetime.now(timezone.utc)

    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise _NAME_CONFLICT

    await db.refresh(work_item)
    from app.projects.router import _resolve_workers
    workers_out = await _resolve_workers(db, work_item.id)
    return WorkItemOut.from_orm(work_item, workers=workers_out)
