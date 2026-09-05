from __future__ import annotations

import os
import threading
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.work_items.repository import WorkItemRepository
from app.work_items.schemas import WorkItemCreate, WorkItemStatus

TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL,
    reason="Set TEST_DATABASE_URL to a migrated local Supabase/Postgres database",
)


def _url() -> str:
    assert TEST_DATABASE_URL
    if TEST_DATABASE_URL.startswith("postgresql+psycopg://"):
        return TEST_DATABASE_URL
    return TEST_DATABASE_URL.replace("postgresql://", "postgresql+psycopg://", 1)


@pytest.fixture()
def session_factory():  # type: ignore[no-untyped-def]
    engine = create_engine(_url(), pool_pre_ping=True)
    factory = sessionmaker(engine, expire_on_commit=False)
    with engine.begin() as connection:
        connection.execute(text("delete from public.work_items"))
    yield factory
    engine.dispose()


def test_enqueue_deduplicates_active_work(session_factory) -> None:  # type: ignore[no-untyped-def]
    repo = WorkItemRepository()
    command = WorkItemCreate(work_type="test", dedupe_key="same")
    with session_factory.begin() as session:
        first = repo.enqueue(session, command)
        second = repo.enqueue(session, command)
        assert first.id == second.id


def test_stale_running_becomes_unknown_not_pending(session_factory) -> None:  # type: ignore[no-untyped-def]
    repo = WorkItemRepository()
    with session_factory.begin() as session:
        item = repo.enqueue(session, WorkItemCreate(work_type="test"))
        item.status = WorkItemStatus.RUNNING.value
        item.locked_at = datetime.now(UTC) - timedelta(minutes=10)
        item.locked_by = "dead-worker"
        session.flush()
        item_id = item.id

    with session_factory.begin() as session:
        assert repo.recover_stale_running(session, lease_seconds=30) == 1

    with session_factory() as session:
        row = session.execute(
            text("select status, last_error_code from public.work_items where id=:id"),
            {"id": item_id},
        ).one()
        assert row.status == WorkItemStatus.UNKNOWN.value
        assert row.last_error_code == "WORKER_LEASE_EXPIRED"


def test_skip_locked_prevents_double_claim(session_factory) -> None:  # type: ignore[no-untyped-def]
    repo = WorkItemRepository()
    with session_factory.begin() as session:
        repo.enqueue(session, WorkItemCreate(work_type="test"))
        repo.enqueue(session, WorkItemCreate(work_type="test"))

    claimed: list[uuid.UUID] = []
    barrier = threading.Barrier(2)

    def claim(worker_id: str) -> None:
        with session_factory.begin() as session:
            barrier.wait()
            item = repo.claim_next(session, worker_id=worker_id)
            assert item is not None
            claimed.append(item.id)

    t1 = threading.Thread(target=claim, args=("w1",))
    t2 = threading.Thread(target=claim, args=("w2",))
    t1.start()
    t2.start()
    t1.join()
    t2.join()

    assert len(claimed) == 2
    assert claimed[0] != claimed[1]
