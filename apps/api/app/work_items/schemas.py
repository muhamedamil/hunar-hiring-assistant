from __future__ import annotations

from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class WorkItemStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    RETRY_SCHEDULED = "retry_scheduled"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    UNKNOWN = "unknown"


ACTIVE_DEDUPE_STATUSES = {
    WorkItemStatus.PENDING,
    WorkItemStatus.RUNNING,
    WorkItemStatus.RETRY_SCHEDULED,
    WorkItemStatus.UNKNOWN,
}


class WorkItemCreate(BaseModel):
    work_type: str = Field(min_length=1, max_length=100)
    entity_type: str | None = Field(default=None, max_length=100)
    entity_id: UUID | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    dedupe_key: str | None = Field(default=None, max_length=300)
    max_attempts: int = Field(default=3, ge=1, le=20)
