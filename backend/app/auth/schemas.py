from __future__ import annotations

from pydantic import BaseModel, field_validator


class LoginRequest(BaseModel):
    email: str
    password: str

    @field_validator("password")
    @classmethod
    def password_length(cls, v: str) -> str:
        if len(v.encode()) > 72:
            raise ValueError("password exceeds 72 bytes")
        return v


class UserOut(BaseModel):
    id: str
    email: str
    name: str
    role: str

    model_config = {"from_attributes": True}

    @classmethod
    def from_orm_user(cls, user: object) -> "UserOut":
        return cls(
            id=str(user.id),  # type: ignore[attr-defined]
            email=user.email,  # type: ignore[attr-defined]
            name=user.name,  # type: ignore[attr-defined]
            role=user.role,  # type: ignore[attr-defined]
        )


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut
