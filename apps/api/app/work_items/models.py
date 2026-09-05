from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, Index, Integer, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.work_items.schemas import WorkItemStatus


class WorkItem(Base):
    __tablename__ = "work_items"
    __table_args__ = (
        CheckConstraint(
            "status in ('pending','running','retry_scheduled','succeeded','failed','unknown')",
            name="ck_work_items_status",
        ),
        CheckConstraint("attempt_count >= 0", name="ck_work_items_attempt_count"),
        CheckConstraint("max_attempts >= 1", name="ck_work_items_max_attempts"),
        CheckConstraint(
            "(status = 'running' and locked_at is not null and locked_by is not null) "
            "or (status <> 'running' and locked_at is null and locked_by is null)",
            name="ck_work_items_lock_state",
        ),
        CheckConstraint(
            "(status in ('succeeded','failed') and completed_at is not null) "
            "or (status not in ('succeeded','failed') and completed_at is null)",
            name="ck_work_items_completion_state",
        ),
        Index(
            "ix_work_items_claim",
            "next_attempt_at",
            "created_at",
            postgresql_where=text("status in ('pending', 'retry_scheduled')"),
        ),
        Index(
            "ix_work_items_running",
            "locked_at",
            postgresql_where=text("status = 'running'"),
        ),
        Index(
            "uq_work_items_active_dedupe",
            "dedupe_key",
            unique=True,
            postgresql_where=text(
                "dedupe_key is not null and "
                "status in ('pending','running','retry_scheduled','unknown')"
            ),
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    work_type: Mapped[str] = mapped_column(String(100), nullable=False)
    entity_type: Mapped[str | None] = mapped_column(String(100))
    entity_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    payload: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    status: Mapped[str] = mapped_column(
        String(30), nullable=False, default=WorkItemStatus.PENDING.value
    )
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    next_attempt_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    locked_by: Mapped[str | None] = mapped_column(String(200))
    last_error_code: Mapped[str | None] = mapped_column(String(100))
    last_error_message: Mapped[str | None] = mapped_column(Text)
    dedupe_key: Mapped[str | None] = mapped_column(String(300))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
