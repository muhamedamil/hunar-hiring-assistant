"""Unit tests for durable work-item state transitions and stale recovery semantics."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

from app.core.config import Settings
from app.core.retry import AmbiguousWorkError, BackoffPolicy, PermanentWorkError, RetryableWorkError
from app.work_items.schemas import WorkItemStatus
from app.worker.registry import WorkHandlerRegistry
from app.worker.runner import WorkerRunner


class FakeRepository:
    def __init__(self, item=None):  # type: ignore[no-untyped-def]
        self.item = item
        self.outcome = None

    def claim_next(self, session, *, worker_id):  # type: ignore[no-untyped-def]
        item, self.item = self.item, None
        return item

    def recover_stale_running(self, session, *, lease_seconds):  # type: ignore[no-untyped-def]
        return 0

    def mark_succeeded(self, session, **kwargs):  # type: ignore[no-untyped-def]
        self.outcome = (WorkItemStatus.SUCCEEDED, kwargs)
        return True

    def schedule_retry(self, session, **kwargs):  # type: ignore[no-untyped-def]
        self.outcome = (WorkItemStatus.RETRY_SCHEDULED, kwargs)
        return True

    def mark_failed(self, session, **kwargs):  # type: ignore[no-untyped-def]
        self.outcome = (WorkItemStatus.FAILED, kwargs)
        return True

    def mark_unknown(self, session, **kwargs):  # type: ignore[no-untyped-def]
        self.outcome = (WorkItemStatus.UNKNOWN, kwargs)
        return True


def _item(*, attempts: int = 1, max_attempts: int = 3):  # type: ignore[no-untyped-def]
    return SimpleNamespace(
        id=uuid4(),
        work_type="test",
        payload={},
        attempt_count=attempts,
        max_attempts=max_attempts,
    )


def _runner(repo, handler):  # type: ignore[no-untyped-def]
    registry = WorkHandlerRegistry()
    registry.register("test", handler)
    settings = Settings(
        database_url="postgresql://user:pass@localhost/db",
        app_env="test",
        worker_poll_interval_seconds=0.01,
        worker_lease_seconds=30,
    )
    runner = WorkerRunner(
        registry=registry,
        repository=repo,
        settings=settings,
        backoff_policy=BackoffPolicy(base_seconds=2, max_seconds=10, jitter_ratio=0),
        worker_id="test-worker",
    )
    return runner


def _fake_session_scope(monkeypatch):  # type: ignore[no-untyped-def]
    class Scope:
        def __enter__(self):
            return object()

        def __exit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr("app.worker.runner.session_scope", lambda: Scope())


def test_success(monkeypatch) -> None:
    _fake_session_scope(monkeypatch)
    repo = FakeRepository(_item())
    runner = _runner(repo, lambda item: None)
    assert runner.process_one() is True
    assert repo.outcome[0] == WorkItemStatus.SUCCEEDED


def test_retryable_error_schedules_retry(monkeypatch) -> None:
    _fake_session_scope(monkeypatch)
    repo = FakeRepository(_item(attempts=1, max_attempts=3))

    def handler(item):  # type: ignore[no-untyped-def]
        raise RetryableWorkError(code="TEMP", message="temporary")

    runner = _runner(repo, handler)
    before = datetime.now(UTC)
    runner.process_one()
    assert repo.outcome[0] == WorkItemStatus.RETRY_SCHEDULED
    assert repo.outcome[1]["next_attempt_at"] > before


def test_retry_budget_exhaustion_fails(monkeypatch) -> None:
    _fake_session_scope(monkeypatch)
    repo = FakeRepository(_item(attempts=3, max_attempts=3))

    def handler(item):  # type: ignore[no-untyped-def]
        raise RetryableWorkError(code="TEMP", message="temporary")

    _runner(repo, handler).process_one()
    assert repo.outcome[0] == WorkItemStatus.FAILED


def test_permanent_error_fails(monkeypatch) -> None:
    _fake_session_scope(monkeypatch)
    repo = FakeRepository(_item())

    def handler(item):  # type: ignore[no-untyped-def]
        raise PermanentWorkError(code="BAD", message="bad input")

    _runner(repo, handler).process_one()
    assert repo.outcome[0] == WorkItemStatus.FAILED


def test_ambiguous_error_becomes_unknown(monkeypatch) -> None:
    _fake_session_scope(monkeypatch)
    repo = FakeRepository(_item())

    def handler(item):  # type: ignore[no-untyped-def]
        raise AmbiguousWorkError(code="UNKNOWN", message="uncertain")

    _runner(repo, handler).process_one()
    assert repo.outcome[0] == WorkItemStatus.UNKNOWN


def test_unclassified_error_becomes_unknown(monkeypatch) -> None:
    _fake_session_scope(monkeypatch)
    repo = FakeRepository(_item())

    def handler(item):  # type: ignore[no-untyped-def]
        raise RuntimeError("boom")

    _runner(repo, handler).process_one()
    assert repo.outcome[0] == WorkItemStatus.UNKNOWN


def test_stale_recovery_invokes_domain_reconciliation_hook(monkeypatch) -> None:
    _fake_session_scope(monkeypatch)
    repo = FakeRepository()
    calls: list[str] = []
    registry = WorkHandlerRegistry()
    settings = Settings(
        database_url="postgresql://user:pass@localhost/db",
        app_env="test",
        worker_poll_interval_seconds=0.01,
        worker_lease_seconds=30,
    )
    runner = WorkerRunner(
        registry=registry,
        repository=repo,
        settings=settings,
        worker_id="test-worker",
        after_stale_recovery=lambda: calls.append("reconciled"),
    )

    assert runner.recover_stale_work() == 0
    assert calls == ["reconciled"]
