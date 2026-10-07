from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.auth.models import User
from app.auth.schemas import UserOut
from app.core.db import get_db

router = APIRouter()


@router.get("/users", response_model=list[UserOut])
async def list_users(
    _: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(User).where(User.status == "active").order_by(User.name))
    return [UserOut.from_orm_user(u) for u in result.scalars().all()]
