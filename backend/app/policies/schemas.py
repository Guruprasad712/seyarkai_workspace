from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, field_validator

from app.policies.models import Checkpoint, Policy, PolicyStage


class CreatePolicyRequest(BaseModel):
    generated_by: str = "manual"


class CreateStageRequest(BaseModel):
    name: str
    description: str
    expected_output: str
    agent_version_id: str


class PatchStageRequest(BaseModel):
    name: str | None = None
    description: str | None = None
    expected_output: str | None = None
    agent_version_id: str | None = None


class ReorderStagesRequest(BaseModel):
    stage_ids: list[str]

    @field_validator("stage_ids")
    @classmethod
    def at_least_one(cls, v: list[str]) -> list[str]:
        if not v:
            raise ValueError("stage_ids must not be empty")
        return v


class CreateCheckpointRequest(BaseModel):
    type: Literal["approval", "review", "input", "final_review"]
    stage_id: str | None = None
    assigned_user_id: str
    instruction: str


class PatchCheckpointRequest(BaseModel):
    stage_id: str | None = None
    assigned_user_id: str | None = None
    instruction: str | None = None


class StageOut(BaseModel):
    id: str
    policy_id: str
    sequence: int
    name: str
    description: str
    expected_output: str
    agent_version_id: str
    created_at: datetime

    @classmethod
    def from_orm(cls, obj: PolicyStage) -> "StageOut":
        return cls(
            id=str(obj.id),
            policy_id=str(obj.policy_id),
            sequence=obj.sequence,
            name=obj.name,
            description=obj.description,
            expected_output=obj.expected_output,
            agent_version_id=str(obj.agent_version_id),
            created_at=obj.created_at,
        )


class CheckpointOut(BaseModel):
    id: str
    policy_id: str
    stage_id: str | None
    type: str
    assigned_user_id: str
    instruction: str
    created_at: datetime

    @classmethod
    def from_orm(cls, obj: Checkpoint) -> "CheckpointOut":
        return cls(
            id=str(obj.id),
            policy_id=str(obj.policy_id),
            stage_id=str(obj.stage_id) if obj.stage_id else None,
            type=obj.type,
            assigned_user_id=str(obj.assigned_user_id),
            instruction=obj.instruction,
            created_at=obj.created_at,
        )


class PolicyOut(BaseModel):
    id: str
    work_item_id: str
    version: int
    status: str
    generated_by: str
    published_by: str | None
    published_at: datetime | None
    created_at: datetime
    stages: list[StageOut] = []
    checkpoints: list[CheckpointOut] = []

    @classmethod
    def from_orm(
        cls,
        obj: Policy,
        stages: list[StageOut] = [],
        checkpoints: list[CheckpointOut] = [],
    ) -> "PolicyOut":
        return cls(
            id=str(obj.id),
            work_item_id=str(obj.work_item_id),
            version=obj.version,
            status=obj.status,
            generated_by=obj.generated_by,
            published_by=str(obj.published_by) if obj.published_by else None,
            published_at=obj.published_at,
            created_at=obj.created_at,
            stages=stages,
            checkpoints=checkpoints,
        )
