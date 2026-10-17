from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user, require_any
from app.auth.models import User
from app.auth.schemas import UserAdminOut, UserCreateIn, UserDirectoryOut, UserPatchIn
from app.core.db import get_db
from app.core.security import hash_password
from app.work_items.models import WorkItemWorker

router = APIRouter()


# ---------------------------------------------------------------------------
# Admin-only: full user list
# ---------------------------------------------------------------------------

@router.get("/users", response_model=list[UserAdminOut])
async def list_users(
    _: User = Depends(require_any("admin")),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(User).order_by(User.name))
    return [UserAdminOut.from_orm_user(u) for u in result.scalars().all()]


# ---------------------------------------------------------------------------
# Open to any authenticated user: directory (for assignee pickers)
# ---------------------------------------------------------------------------

@router.get("/users/directory", response_model=list[UserDirectoryOut])
async def user_directory(
    eligible_for: str | None = Query(default=None, description="work_item_id — filter to admin/reviewer workers on this work item"),
    _: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if eligible_for is not None:
        # Return only admin/reviewer users who are human workers on this work item
        result = await db.execute(
            select(User)
            .join(WorkItemWorker, WorkItemWorker.user_id == User.id)
            .where(
                WorkItemWorker.work_item_id == eligible_for,
                WorkItemWorker.worker_type == "human",
                User.status == "active",
                User.role.in_(("admin", "reviewer")),
            )
            .order_by(User.name)
        )
    else:
        result = await db.execute(
            select(User)
            .where(User.status == "active")
            .order_by(User.name)
        )
    return [UserDirectoryOut.from_orm_user(u) for u in result.scalars().all()]


# ---------------------------------------------------------------------------
# Admin-only: create user
# ---------------------------------------------------------------------------

@router.post("/users", response_model=UserAdminOut, status_code=status.HTTP_201_CREATED)
async def create_user(
    body: UserCreateIn,
    _: User = Depends(require_any("admin")),
    db: AsyncSession = Depends(get_db),
):
    existing = await db.execute(select(User).where(User.email == body.email))
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(status_code=409, detail="email already in use")

    now = datetime.now(timezone.utc)
    user = User(
        id=uuid.uuid4(),
        email=body.email,
        name=body.name,
        hashed_password=hash_password(body.temp_password),
        role=body.role,
        status="active",
        created_at=now,
        updated_at=now,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return UserAdminOut.from_orm_user(user)


# ---------------------------------------------------------------------------
# Admin-only: patch user name/role
# ---------------------------------------------------------------------------

@router.patch("/users/{user_id}", response_model=UserAdminOut)
async def patch_user(
    user_id: str,
    body: UserPatchIn,
    current_admin: User = Depends(require_any("admin")),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=404, detail="user not found")

    if body.role is not None and body.role != user.role:
        # Prevent demoting the last admin
        if user.role == "admin":
            count_result = await db.execute(
                select(func.count()).select_from(User).where(
                    User.role == "admin", User.status == "active"
                )
            )
            if count_result.scalar_one() <= 1:
                raise HTTPException(
                    status_code=422,
                    detail={"code": "last_admin", "message": "cannot change the role of the last active admin"},
                )
        user.role = body.role

    if body.name is not None:
        user.name = body.name

    user.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(user)
    return UserAdminOut.from_orm_user(user)


# ---------------------------------------------------------------------------
# Admin-only: deactivate / activate
# ---------------------------------------------------------------------------

@router.patch("/users/{user_id}/deactivate", response_model=UserAdminOut)
async def deactivate_user(
    user_id: str,
    current_admin: User = Depends(require_any("admin")),
    db: AsyncSession = Depends(get_db),
):
    if str(current_admin.id) == user_id:
        raise HTTPException(
            status_code=422,
            detail={"code": "self_deactivate", "message": "you cannot deactivate your own account"},
        )

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=404, detail="user not found")

    if user.role == "admin":
        count_result = await db.execute(
            select(func.count()).select_from(User).where(
                User.role == "admin", User.status == "active"
            )
        )
        if count_result.scalar_one() <= 1:
            raise HTTPException(
                status_code=422,
                detail={"code": "last_admin", "message": "cannot deactivate the last active admin"},
            )

    user.status = "inactive"
    user.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(user)
    return UserAdminOut.from_orm_user(user)


@router.patch("/users/{user_id}/activate", response_model=UserAdminOut)
async def activate_user(
    user_id: str,
    _: User = Depends(require_any("admin")),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=404, detail="user not found")

    user.status = "active"
    user.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(user)
    return UserAdminOut.from_orm_user(user)
