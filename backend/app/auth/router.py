from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.auth.models import User
from app.auth.schemas import LoginRequest, TokenResponse, UserOut
from app.core.db import get_db
from app.core.security import create_access_token, dummy_verify, verify_password

router = APIRouter()

_INVALID = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="invalid credentials",
)


@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.email == body.email))
    user = result.scalar_one_or_none()

    if user is None:
        dummy_verify()
        raise _INVALID

    if not verify_password(body.password, user.hashed_password):
        raise _INVALID

    if user.status != "active":
        raise _INVALID

    token = create_access_token(str(user.id), user.role)
    return TokenResponse(access_token=token, user=UserOut.from_orm_user(user))


@router.get("/me", response_model=UserOut)
async def me(user: User = Depends(get_current_user)):
    return UserOut.from_orm_user(user)
