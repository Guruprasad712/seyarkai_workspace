from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel

from app.executions.models import Execution, ExecutionEvent, Message  # noqa: F401
from app.policies.models import Checkpoint, PolicyStage


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
    pending_summary: str | None
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
            pending_summary=obj.pending_summary,
            created_at=obj.created_at,
        )


class EventOut(BaseModel):
    id: str
    execution_id: str
    stage_id: str | None
    event_type: str
    actor_type: str
    actor_id: str | None
    payload: dict
    created_at: datetime

    @classmethod
    def from_orm(cls, obj: ExecutionEvent) -> "EventOut":
        return cls(
            id=str(obj.id),
            execution_id=str(obj.execution_id),
            stage_id=str(obj.stage_id) if obj.stage_id else None,
            event_type=obj.event_type,
            actor_type=obj.actor_type,
            actor_id=str(obj.actor_id) if obj.actor_id else None,
            payload=obj.payload,
            created_at=obj.created_at,
        )


class StageSummary(BaseModel):
    sequence: int
    name: str
    description: str
    expected_output: str
    agent_output: str | None
    checkpoint_decision: str | None
    checkpoint_comment: str | None
    checkpoint_type: str | None

    @classmethod
    def build(
        cls,
        stage: PolicyStage,
        output_msg: Message | None,
        cp_response: "CheckpointResponseRow | None",
        cp_type: str | None,
    ) -> "StageSummary":
        return cls(
            sequence=stage.sequence,
            name=stage.name,
            description=stage.description,
            expected_output=stage.expected_output,
            agent_output=output_msg.content if output_msg else None,
            checkpoint_decision=cp_response.decision if cp_response else None,
            checkpoint_comment=cp_response.comment if cp_response else None,
            checkpoint_type=cp_type,
        )


class CheckpointResponseRow(BaseModel):
    decision: str
    comment: str | None


class ExecutionSummaryOut(BaseModel):
    execution_id: str
    execution_number: int
    status: str
    started_at: datetime | None
    completed_at: datetime | None
    error: str | None
    work_item_objective: str
    work_item_description: str
    work_item_expected_outcome: str
    stages: list[StageSummary]
    final_review_decision: str | None
    final_review_comment: str | None


class CheckpointResponseIn(BaseModel):
    decision: str
    comment: str | None = None
    input_text: str | None = None


class CheckpointResponseOut(BaseModel):
    execution_id: str
    status: str
    next_action: str


class GuidanceMessageIn(BaseModel):
    content: str


class GuidanceMessageOut(BaseModel):
    id: str
    execution_id: str
    content: str
    created_at: datetime

    @classmethod
    def from_orm(cls, obj: Message) -> "GuidanceMessageOut":
        return cls(
            id=str(obj.id),
            execution_id=str(obj.execution_id),
            content=obj.content,
            created_at=obj.created_at,
        )
