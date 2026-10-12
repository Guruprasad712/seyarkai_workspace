from __future__ import annotations

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.models import User
from app.core.db import get_db
from app.core.security import decode_token

# auto_error=False so the global middleware controls the 401 body format
_oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login", auto_error=False)

_INVALID = HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="not authenticated")
_FORBIDDEN = HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="forbidden")


async def get_current_user(
    token: str | None = Depends(_oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    if not token:
        raise _INVALID
    try:
        payload = decode_token(token)
    except jwt.InvalidTokenError:
        raise _INVALID

    user_id: str | None = payload.get("sub")
    if not user_id:
        raise _INVALID

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None or user.status != "active":
        raise _INVALID

    return user


def require_role(role: str):
    async def _check(user: User = Depends(get_current_user)) -> User:
        if user.role != role:
            raise _FORBIDDEN
        return user
    return _check
