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


_VALID_ROLES = {"admin", "builder", "reviewer", "observer"}


class UserAdminOut(BaseModel):
    id: str
    email: str
    name: str
    role: str
    status: str

    model_config = {"from_attributes": True}

    @classmethod
    def from_orm_user(cls, user: object) -> "UserAdminOut":
        return cls(
            id=str(user.id),  # type: ignore[attr-defined]
            email=user.email,  # type: ignore[attr-defined]
            name=user.name,  # type: ignore[attr-defined]
            role=user.role,  # type: ignore[attr-defined]
            status=user.status,  # type: ignore[attr-defined]
        )


class UserDirectoryOut(BaseModel):
    id: str
    name: str
    role: str

    @classmethod
    def from_orm_user(cls, user: object) -> "UserDirectoryOut":
        return cls(
            id=str(user.id),  # type: ignore[attr-defined]
            name=user.name,  # type: ignore[attr-defined]
            role=user.role,  # type: ignore[attr-defined]
        )


class UserCreateIn(BaseModel):
    email: str
    name: str
    temp_password: str
    role: str

    @field_validator("role")
    @classmethod
    def role_valid(cls, v: str) -> str:
        if v not in _VALID_ROLES:
            raise ValueError(f"role must be one of {sorted(_VALID_ROLES)}")
        return v

    @field_validator("temp_password")
    @classmethod
    def password_length(cls, v: str) -> str:
        if len(v.encode()) > 72:
            raise ValueError("password exceeds 72 bytes")
        return v


class UserPatchIn(BaseModel):
    name: str | None = None
    role: str | None = None

    @field_validator("role")
    @classmethod
    def role_valid(cls, v: str | None) -> str | None:
        if v is not None and v not in _VALID_ROLES:
            raise ValueError(f"role must be one of {sorted(_VALID_ROLES)}")
        return v
