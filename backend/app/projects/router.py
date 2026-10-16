from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.models import AgentVersion
from app.auth.dependencies import get_current_user
from app.auth.models import User
from app.core.db import get_db
from app.projects.models import Project
from app.projects.schemas import CreateProjectRequest, PatchProjectRequest, ProjectOut
from app.work_items.models import WorkItem, WorkItemWorker
from app.work_items.schemas import (
    CreateWorkItemRequest,
    WorkerOut,
    WorkItemOut,
)

router = APIRouter()

_NOT_FOUND = HTTPException(status_code=404, detail="project not found")
_NAME_CONFLICT = HTTPException(status_code=409, detail="project name already exists")
_WI_NOT_FOUND = HTTPException(status_code=404, detail="work item not found")
_WI_NAME_CONFLICT = HTTPException(status_code=409, detail="work item name already exists in this project")


async def _work_item_count(db: AsyncSession, project_id: uuid.UUID) -> int:
    result = await db.execute(
        select(func.count()).select_from(WorkItem).where(WorkItem.project_id == project_id)
    )
    return result.scalar_one()


async def _resolve_workers(db: AsyncSession, work_item_id: uuid.UUID) -> list[WorkerOut]:
    result = await db.execute(
        select(WorkItemWorker).where(WorkItemWorker.work_item_id == work_item_id)
    )
    workers = result.scalars().all()

    outs: list[WorkerOut] = []
    for w in workers:
        if w.worker_type == "ai_agent":
            ver_result = await db.execute(
                select(AgentVersion).where(AgentVersion.id == w.agent_version_id)
            )
            ver = ver_result.scalar_one_or_none()
            # also fetch agent name via the agent FK
            agent_name: str | None = None
            agent_version: str | None = None
            if ver is not None:
                from app.agents.models import Agent
                ag_result = await db.execute(select(Agent).where(Agent.id == ver.agent_id))
                ag = ag_result.scalar_one_or_none()
                agent_name = ag.name if ag else None
                agent_version = ver.version
            outs.append(WorkerOut.from_orm(w, agent_name=agent_name, agent_version=agent_version))
        else:
            user_result = await db.execute(select(User).where(User.id == w.user_id))
            user = user_result.scalar_one_or_none()
            outs.append(WorkerOut.from_orm(
                w,
                user_name=user.name if user else None,
                user_email=user.email if user else None,
            ))
    return outs


async def _validate_and_build_workers(
    db: AsyncSession,
    work_item_id: uuid.UUID,
    workers_in: list,
) -> list[WorkItemWorker]:
    now = datetime.now(timezone.utc)
    worker_rows: list[WorkItemWorker] = []
    for w in workers_in:
        if w.type == "ai_agent":
            result = await db.execute(
                select(AgentVersion).where(AgentVersion.id == w.id)
            )
            ver = result.scalar_one_or_none()
            if ver is None or ver.status != "published":
                raise HTTPException(
                    status_code=422,
                    detail=f"agent version {w.id} is not published",
                )
            worker_rows.append(WorkItemWorker(
                id=uuid.uuid4(),
                work_item_id=work_item_id,
                worker_type="ai_agent",
                agent_version_id=uuid.UUID(w.id),
                user_id=None,
                created_at=now,
                updated_at=now,
            ))
        else:
            result = await db.execute(select(User).where(User.id == w.id))
            user = result.scalar_one_or_none()
            if user is None or user.status != "active":
                raise HTTPException(
                    status_code=422,
                    detail=f"user {w.id} is not active",
                )
            worker_rows.append(WorkItemWorker(
                id=uuid.uuid4(),
                work_item_id=work_item_id,
                worker_type="human",
                agent_version_id=None,
                user_id=uuid.UUID(w.id),
                created_at=now,
                updated_at=now,
            ))
    return worker_rows


# ---------------------------------------------------------------------------
# Project routes
# ---------------------------------------------------------------------------

@router.post("/projects", response_model=ProjectOut, status_code=status.HTTP_201_CREATED)
async def create_project(
    body: CreateProjectRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    now = datetime.now(timezone.utc)
    project = Project(
        id=uuid.uuid4(),
        name=body.name,
        description=body.description,
        status="active",
        created_by=current_user.id,
        created_at=now,
        updated_at=now,
    )
    db.add(project)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise _NAME_CONFLICT
    await db.refresh(project)
    return ProjectOut.from_orm(project, work_item_count=0)


@router.get("/projects", response_model=list[ProjectOut])
async def list_projects(
    _: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Project).order_by(Project.created_at))
    projects = result.scalars().all()
    out = []
    for p in projects:
        count = await _work_item_count(db, p.id)
        out.append(ProjectOut.from_orm(p, work_item_count=count))
    return out


@router.get("/projects/{project_id}", response_model=ProjectOut)
async def get_project(
    project_id: str,
    _: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()
    if project is None:
        raise _NOT_FOUND
    count = await _work_item_count(db, project.id)
    return ProjectOut.from_orm(project, work_item_count=count)


@router.patch("/projects/{project_id}", response_model=ProjectOut)
async def patch_project(
    project_id: str,
    body: PatchProjectRequest,
    _: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()
    if project is None:
        raise _NOT_FOUND

    if body.name is not None:
        project.name = body.name
    if body.description is not None:
        project.description = body.description
    if body.status is not None:
        project.status = body.status
    project.updated_at = datetime.now(timezone.utc)

    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise _NAME_CONFLICT

    await db.refresh(project)
    count = await _work_item_count(db, project.id)
    return ProjectOut.from_orm(project, work_item_count=count)


# ---------------------------------------------------------------------------
# Work item routes nested under project
# ---------------------------------------------------------------------------

@router.post(
    "/projects/{project_id}/work-items",
    response_model=WorkItemOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_work_item(
    project_id: str,
    body: CreateWorkItemRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Project).where(Project.id == project_id))
    if result.scalar_one_or_none() is None:
        raise _NOT_FOUND

    now = datetime.now(timezone.utc)
    work_item_id = uuid.uuid4()

    worker_rows = await _validate_and_build_workers(db, work_item_id, body.workers)

    work_item = WorkItem(
        id=work_item_id,
        project_id=uuid.UUID(project_id),
        name=body.name,
        objective=body.objective,
        description=body.description,
        expected_outcome=body.expected_outcome,
        status="new",
        previous_output=body.previous_output,
        created_by=current_user.id,
        created_at=now,
        updated_at=now,
    )
    db.add(work_item)
    for w in worker_rows:
        db.add(w)

    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise _WI_NAME_CONFLICT

    await db.refresh(work_item)
    workers_out = await _resolve_workers(db, work_item.id)
    return WorkItemOut.from_orm(work_item, workers=workers_out)


@router.get("/projects/{project_id}/work-items", response_model=list[WorkItemOut])
async def list_work_items(
    project_id: str,
    _: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Project).where(Project.id == project_id))
    if result.scalar_one_or_none() is None:
        raise _NOT_FOUND

    wi_result = await db.execute(
        select(WorkItem)
        .where(WorkItem.project_id == project_id)
        .order_by(WorkItem.created_at)
    )
    work_items = wi_result.scalars().all()
    out = []
    for wi in work_items:
        workers_out = await _resolve_workers(db, wi.id)
        out.append(WorkItemOut.from_orm(wi, workers=workers_out))
    return out
