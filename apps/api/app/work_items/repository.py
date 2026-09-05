from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import Select, select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.work_items.models import WorkItem
from app.work_items.schemas import ACTIVE_DEDUPE_STATUSES, WorkItemCreate, WorkItemStatus


class WorkItemRepository:
    def enqueue(self, session: Session, command: WorkItemCreate) -> WorkItem:
        item = WorkItem(
            work_type=command.work_type,
            entity_type=command.entity_type,
            entity_id=command.entity_id,
            payload=command.payload,
            dedupe_key=command.dedupe_key,
            max_attempts=command.max_attempts,
            status=WorkItemStatus.PENDING.value,
            next_attempt_at=datetime.now(UTC),
        )

        if command.dedupe_key is None:
            session.add(item)
            session.flush()
            return item

        try:
            with session.begin_nested():
                session.add(item)
                session.flush()
            return item
        except IntegrityError:
            existing = self.get_active_by_dedupe_key(session, command.dedupe_key)
            if existing is None:
                raise
            return existing

    def get_active_by_dedupe_key(self, session: Session, dedupe_key: str) -> WorkItem | None:
        statement = select(WorkItem).where(
            WorkItem.dedupe_key == dedupe_key,
            WorkItem.status.in_([status.value for status in ACTIVE_DEDUPE_STATUSES]),
        )
        return session.execute(statement).scalar_one_or_none()

    def claim_next(self, session: Session, *, worker_id: str) -> WorkItem | None:
        now = datetime.now(UTC)
        statement: Select[tuple[WorkItem]] = (
            select(WorkItem)
            .where(
                WorkItem.status.in_(
                    [WorkItemStatus.PENDING.value, WorkItemStatus.RETRY_SCHEDULED.value]
                ),
                WorkItem.next_attempt_at <= now,
            )
            .order_by(WorkItem.next_attempt_at.asc(), WorkItem.created_at.asc())
            .with_for_update(skip_locked=True)
            .limit(1)
        )
        item = session.execute(statement).scalar_one_or_none()
        if item is None:
            return None

        item.status = WorkItemStatus.RUNNING.value
        item.locked_at = now
        item.locked_by = worker_id
        item.attempt_count += 1
        item.updated_at = now
        session.flush()
        return item

    def mark_succeeded(self, session: Session, *, item_id: UUID, worker_id: str) -> bool:
        now = datetime.now(UTC)
        result: CursorResult[tuple[()]] = session.execute(  # type: ignore[assignment]
            update(WorkItem)
            .where(
                WorkItem.id == item_id,
                WorkItem.status == WorkItemStatus.RUNNING.value,
                WorkItem.locked_by == worker_id,
            )
            .values(
                status=WorkItemStatus.SUCCEEDED.value,
                completed_at=now,
                locked_at=None,
                locked_by=None,
                last_error_code=None,
                last_error_message=None,
                updated_at=now,
            )
        )
        return bool(result.rowcount)

    def schedule_retry(
        self,
        session: Session,
        *,
        item_id: UUID,
        worker_id: str,
        next_attempt_at: datetime,
        error_code: str,
        error_message: str,
    ) -> bool:
        now = datetime.now(UTC)
        result: CursorResult[tuple[()]] = session.execute(  # type: ignore[assignment]
            update(WorkItem)
            .where(
                WorkItem.id == item_id,
                WorkItem.status == WorkItemStatus.RUNNING.value,
                WorkItem.locked_by == worker_id,
            )
            .values(
                status=WorkItemStatus.RETRY_SCHEDULED.value,
                next_attempt_at=next_attempt_at,
                locked_at=None,
                locked_by=None,
                last_error_code=error_code,
                last_error_message=error_message,
                updated_at=now,
            )
        )
        return bool(result.rowcount)

    def mark_failed(
        self,
        session: Session,
        *,
        item_id: UUID,
        worker_id: str,
        error_code: str,
        error_message: str,
    ) -> bool:
        now = datetime.now(UTC)
        result: CursorResult[tuple[()]] = session.execute(  # type: ignore[assignment]
            update(WorkItem)
            .where(
                WorkItem.id == item_id,
                WorkItem.status == WorkItemStatus.RUNNING.value,
                WorkItem.locked_by == worker_id,
            )
            .values(
                status=WorkItemStatus.FAILED.value,
                completed_at=now,
                locked_at=None,
                locked_by=None,
                last_error_code=error_code,
                last_error_message=error_message,
                updated_at=now,
            )
        )
        return bool(result.rowcount)

    def mark_unknown(
        self,
        session: Session,
        *,
        item_id: UUID,
        worker_id: str,
        error_code: str,
        error_message: str,
    ) -> bool:
        now = datetime.now(UTC)
        result: CursorResult[tuple[()]] = session.execute(  # type: ignore[assignment]
            update(WorkItem)
            .where(
                WorkItem.id == item_id,
                WorkItem.status == WorkItemStatus.RUNNING.value,
                WorkItem.locked_by == worker_id,
            )
            .values(
                status=WorkItemStatus.UNKNOWN.value,
                locked_at=None,
                locked_by=None,
                last_error_code=error_code,
                last_error_message=error_message,
                updated_at=now,
            )
        )
        return bool(result.rowcount)

    def recover_stale_running(self, session: Session, *, lease_seconds: int) -> int:
        cutoff = datetime.now(UTC) - timedelta(seconds=lease_seconds)
        now = datetime.now(UTC)
        result: CursorResult[tuple[()]] = session.execute(  # type: ignore[assignment]
            update(WorkItem)
            .where(
                WorkItem.status == WorkItemStatus.RUNNING.value,
                WorkItem.locked_at < cutoff,
            )
            .values(
                status=WorkItemStatus.UNKNOWN.value,
                locked_at=None,
                locked_by=None,
                last_error_code="WORKER_LEASE_EXPIRED",
                last_error_message=(
                    "Worker lease expired while item was running; execution outcome is ambiguous."
                ),
                updated_at=now,
            )
        )
        return int(result.rowcount or 0)
