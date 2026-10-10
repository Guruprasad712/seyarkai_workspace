from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel

from app.executions.models import Execution
from app.policies.models import Checkpoint


class CreateExecutionResponse(BaseModel):
    execution_id: str


class CheckpointBrief(BaseModel):
    id: str
    type: str
    assigned_user_id: str
    instruction: str
    stage_id: str | None

    @classmethod
    def from_orm(cls, obj: Checkpoint) -> "CheckpointBrief":
        return cls(
            id=str(obj.id),
            type=obj.type,
            assigned_user_id=str(obj.assigned_user_id),
            instruction=obj.instruction,
            stage_id=str(obj.stage_id) if obj.stage_id else None,
        )


class ExecutionOut(BaseModel):
    id: str
    work_item_id: str
    policy_id: str
    execution_number: int
    status: str
    current_stage_id: str | None
    blocking_checkpoint: CheckpointBrief | None
    started_at: datetime | None
    completed_at: datetime | None
    error: str | None
    created_at: datetime

    @classmethod
    def from_orm(
        cls,
        obj: Execution,
        blocking_checkpoint: Checkpoint | None = None,
    ) -> "ExecutionOut":
        return cls(
            id=str(obj.id),
            work_item_id=str(obj.work_item_id),
            policy_id=str(obj.policy_id),
            execution_number=obj.execution_number,
            status=obj.status,
            current_stage_id=str(obj.current_stage_id) if obj.current_stage_id else None,
            blocking_checkpoint=CheckpointBrief.from_orm(blocking_checkpoint) if blocking_checkpoint else None,
            started_at=obj.started_at,
            completed_at=obj.completed_at,
            error=obj.error,
            created_at=obj.created_at,
        )
