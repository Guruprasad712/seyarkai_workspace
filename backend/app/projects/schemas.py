from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel

from app.projects.models import Project


class CreateProjectRequest(BaseModel):
    name: str
    description: str = ""


class PatchProjectRequest(BaseModel):
    name: str | None = None
    description: str | None = None
    status: str | None = None


class ProjectOut(BaseModel):
    id: str
    name: str
    description: str
    status: str
    created_by: str
    created_at: datetime
    work_item_count: int = 0

    @classmethod
    def from_orm(cls, obj: Project, work_item_count: int = 0) -> "ProjectOut":
        return cls(
            id=str(obj.id),
            name=obj.name,
            description=obj.description,
            status=obj.status,
            created_by=str(obj.created_by),
            created_at=obj.created_at,
            work_item_count=work_item_count,
        )
