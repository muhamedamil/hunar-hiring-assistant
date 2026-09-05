from __future__ import annotations

import logging
import os
import socket
import time
import uuid
from datetime import UTC, datetime, timedelta

from app.core.config import Settings, get_settings
from app.core.database import session_scope
from app.core.retry import (
    AmbiguousWorkError,
    BackoffPolicy,
    PermanentWorkError,
    RetryableWorkError,
)
from app.work_items.models import WorkItem
from app.work_items.repository import WorkItemRepository
from app.worker.registry import WorkHandlerRegistry

logger = logging.getLogger(__name__)


class WorkerRunner:
    def __init__(
        self,
        *,
        registry: WorkHandlerRegistry,
        repository: WorkItemRepository | None = None,
        settings: Settings | None = None,
        backoff_policy: BackoffPolicy | None = None,
        worker_id: str | None = None,
    ) -> None:
        self.registry = registry
        self.repository = repository or WorkItemRepository()
        self.settings = settings or get_settings()
        self.backoff_policy = backoff_policy or BackoffPolicy()
        self.worker_id = worker_id or self._build_worker_id()

    @staticmethod
    def _build_worker_id() -> str:
        return f"{socket.gethostname()}:{os.getpid()}:{uuid.uuid4().hex[:8]}"

    def recover_stale_work(self) -> int:
        with session_scope() as session:
            recovered = self.repository.recover_stale_running(
                session,
                lease_seconds=self.settings.worker_lease_seconds,
            )
        if recovered:
            logger.warning(
                "Moved stale running work to UNKNOWN",
                extra={"context": {"count": recovered}},
            )
        return recovered

    def claim_one(self) -> WorkItem | None:
        with session_scope() as session:
            return self.repository.claim_next(session, worker_id=self.worker_id)

    def process_one(self) -> bool:
        item = self.claim_one()
        if item is None:
            return False

        handler = self.registry.get(item.work_type)
        if handler is None:
            self._mark_failed(
                item,
                code="UNKNOWN_WORK_TYPE",
                message=f"No worker handler registered for {item.work_type}",
            )
            return True

        try:
            handler(item)
        except RetryableWorkError as exc:
            if item.attempt_count >= item.max_attempts:
                self._mark_failed(item, code=exc.code, message=exc.message)
            else:
                delay = (
                    exc.retry_after_seconds
                    if exc.retry_after_seconds is not None
                    else self.backoff_policy.delay_seconds(item.attempt_count)
                )
                self._schedule_retry(
                    item,
                    next_attempt_at=datetime.now(UTC) + timedelta(seconds=delay),
                    code=exc.code,
                    message=exc.message,
                )
        except PermanentWorkError as exc:
            self._mark_failed(item, code=exc.code, message=exc.message)
        except AmbiguousWorkError as exc:
            self._mark_unknown(item, code=exc.code, message=exc.message)
        except Exception:
            logger.exception(
                "Unclassified worker exception; preserving item as UNKNOWN",
                extra={"context": {"work_item_id": str(item.id), "work_type": item.work_type}},
            )
            self._mark_unknown(
                item,
                code="UNCLASSIFIED_WORKER_ERROR",
                message="Worker raised an unclassified exception; execution outcome is ambiguous.",
            )
        else:
            self._mark_succeeded(item)
        return True

    def run_forever(self) -> None:
        logger.info("Worker started", extra={"context": {"worker_id": self.worker_id}})
        self.recover_stale_work()
        last_recovery_at = time.monotonic()

        while True:
            try:
                did_work = self.process_one()
                if time.monotonic() - last_recovery_at >= self.settings.worker_lease_seconds:
                    self.recover_stale_work()
                    last_recovery_at = time.monotonic()
                if not did_work:
                    time.sleep(self.settings.worker_poll_interval_seconds)
            except KeyboardInterrupt:
                logger.info("Worker stopped", extra={"context": {"worker_id": self.worker_id}})
                return
            except Exception:
                logger.exception("Worker loop infrastructure failure")
                time.sleep(min(10.0, max(1.0, self.settings.worker_poll_interval_seconds * 2)))

    def _mark_succeeded(self, item: WorkItem) -> None:
        with session_scope() as session:
            updated = self.repository.mark_succeeded(
                session, item_id=item.id, worker_id=self.worker_id
            )
        self._ensure_state_update(updated, item)

    def _schedule_retry(
        self,
        item: WorkItem,
        *,
        next_attempt_at: datetime,
        code: str,
        message: str,
    ) -> None:
        with session_scope() as session:
            updated = self.repository.schedule_retry(
                session,
                item_id=item.id,
                worker_id=self.worker_id,
                next_attempt_at=next_attempt_at,
                error_code=code,
                error_message=message,
            )
        self._ensure_state_update(updated, item)

    def _mark_failed(self, item: WorkItem, *, code: str, message: str) -> None:
        with session_scope() as session:
            updated = self.repository.mark_failed(
                session,
                item_id=item.id,
                worker_id=self.worker_id,
                error_code=code,
                error_message=message,
            )
        self._ensure_state_update(updated, item)

    def _mark_unknown(self, item: WorkItem, *, code: str, message: str) -> None:
        with session_scope() as session:
            updated = self.repository.mark_unknown(
                session,
                item_id=item.id,
                worker_id=self.worker_id,
                error_code=code,
                error_message=message,
            )
        self._ensure_state_update(updated, item)

    @staticmethod
    def _ensure_state_update(updated: bool, item: WorkItem) -> None:
        if not updated:
            raise RuntimeError(
                f"Work item {item.id} changed ownership/state before worker could persist outcome"
            )
