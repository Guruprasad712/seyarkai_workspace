from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, field_validator

from app.work_items.models import WorkItem, WorkItemWorker


class WorkerIn(BaseModel):
    type: Literal["ai_agent", "human"]
    id: str  # agent_version_id or user_id


class CreateWorkItemRequest(BaseModel):
    name: str
    objective: str
    description: str
    expected_outcome: str
    workers: list[WorkerIn]
    previous_output: str | None = None

    @field_validator("workers")
    @classmethod
    def at_least_one_worker(cls, v: list[WorkerIn]) -> list[WorkerIn]:
        if not v:
            raise ValueError("at least one worker is required")
        return v


class PatchWorkItemRequest(BaseModel):
    name: str | None = None
    objective: str | None = None
    description: str | None = None
    expected_outcome: str | None = None
    previous_output: str | None = None


class WorkerOut(BaseModel):
    type: str
    id: str
    agent_name: str | None = None
    agent_version: str | None = None
    user_name: str | None = None
    user_email: str | None = None

    @classmethod
    def from_orm(
        cls,
        worker: WorkItemWorker,
        agent_name: str | None = None,
        agent_version: str | None = None,
        user_name: str | None = None,
        user_email: str | None = None,
    ) -> "WorkerOut":
        resolved_id = (
            str(worker.agent_version_id)
            if worker.worker_type == "ai_agent"
            else str(worker.user_id)
        )
        return cls(
            type=worker.worker_type,
            id=resolved_id,
            agent_name=agent_name,
            agent_version=agent_version,
            user_name=user_name,
            user_email=user_email,
        )


class WorkItemOut(BaseModel):
    id: str
    project_id: str
    name: str
    objective: str
    description: str
    expected_outcome: str
    status: str
    previous_output: str | None
    created_by: str
    created_at: datetime
    workers: list[WorkerOut] = []

    @classmethod
    def from_orm(cls, obj: WorkItem, workers: list[WorkerOut] = []) -> "WorkItemOut":
        return cls(
            id=str(obj.id),
            project_id=str(obj.project_id),
            name=obj.name,
            objective=obj.objective,
            description=obj.description,
            expected_outcome=obj.expected_outcome,
            status=obj.status,
            previous_output=obj.previous_output,
            created_by=str(obj.created_by),
            created_at=obj.created_at,
            workers=workers,
        )
