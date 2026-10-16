from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, field_validator


class CapabilityIn(BaseModel):
    name: str
    description: str


class CreateAgentRequest(BaseModel):
    name: str
    description: str
    role_purpose: str
    instructions: str
    capabilities: list[CapabilityIn]
    tool_ids: list[str] = []

    @field_validator("capabilities")
    @classmethod
    def at_least_one_capability(cls, v: list) -> list:
        if not v:
            raise ValueError("at least one capability is required")
        return v


class PatchAgentRequest(BaseModel):
    name: str | None = None
    description: str | None = None
    role_purpose: str | None = None
    status: str | None = None


class CreateVersionRequest(BaseModel):
    instructions: str
    capabilities: list[CapabilityIn]
    tool_ids: list[str] = []


class PatchVersionRequest(BaseModel):
    instructions: str | None = None
    capabilities: list[CapabilityIn] | None = None
    tool_ids: list[str] | None = None


# ---------------------------------------------------------------------------
# Output schemas
# ---------------------------------------------------------------------------

class McpToolOut(BaseModel):
    id: str
    name: str
    tool_name: str
    server_key: str
    description: str
    status: str

    model_config = {"from_attributes": True}

    @classmethod
    def from_orm(cls, obj: Any) -> "McpToolOut":
        return cls(
            id=str(obj.id),
            name=obj.name,
            tool_name=obj.tool_name,
            server_key=obj.server_key,
            description=obj.description,
            status=obj.status,
        )


class AgentVersionOut(BaseModel):
    id: str
    agent_id: str
    version: str
    instructions: str
    capabilities: list[Any]
    status: str
    published_at: datetime | None
    tool_ids: list[str]

    model_config = {"from_attributes": True}

    @classmethod
    def from_orm(cls, obj: Any, tool_ids: list[str]) -> "AgentVersionOut":
        return cls(
            id=str(obj.id),
            agent_id=str(obj.agent_id),
            version=obj.version,
            instructions=obj.instructions,
            capabilities=obj.capabilities or [],
            status=obj.status,
            published_at=obj.published_at,
            tool_ids=tool_ids,
        )


class AgentSummaryOut(BaseModel):
    id: str
    agent_code: str
    name: str
    description: str
    role_purpose: str
    status: str

    model_config = {"from_attributes": True}

    @classmethod
    def from_orm(cls, obj: Any) -> "AgentSummaryOut":
        return cls(
            id=str(obj.id),
            agent_code=obj.agent_code,
            name=obj.name,
            description=obj.description,
            role_purpose=obj.role_purpose,
            status=obj.status,
        )


class AgentOut(AgentSummaryOut):
    versions: list[AgentVersionOut] = []
