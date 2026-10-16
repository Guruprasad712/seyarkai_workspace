"""JWT and password helpers. No database access."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

from app.core.config import settings

_MAX_PW_BYTES = 72
_ALGORITHM = "HS256"


def hash_password(plain: str) -> str:
    encoded = plain.encode()
    if len(encoded) > _MAX_PW_BYTES:
        raise ValueError("password exceeds 72 bytes")
    return bcrypt.hashpw(encoded, bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode(), hashed.encode())


def dummy_verify() -> None:
    """Run a full bcrypt round to equalise timing when the email is unknown."""
    dummy = bcrypt.hashpw(b"_dummy_", bcrypt.gensalt())
    bcrypt.checkpw(b"_dummy_", dummy)


def create_access_token(sub: str, role: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(hours=settings.JWT_EXPIRE_HOURS)
    return jwt.encode(
        {"sub": sub, "role": role, "exp": expire},
        settings.JWT_SECRET,
        algorithm=_ALGORITHM,
    )


def decode_token(token: str) -> dict:
    """Decode and verify a JWT. Raises jwt.InvalidTokenError on any failure."""
    return jwt.decode(token, settings.JWT_SECRET, algorithms=[_ALGORITHM])
