"""Hosted/local PostgreSQL qualification for Module 1 state and immutability invariants."""

from __future__ import annotations

import os
import threading

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.orm import sessionmaker

from app.jobs.schemas import JobCreateRequest, JobDefinitionEdit, ScreeningAnswerType
from app.jobs.service import JobService

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
    yield factory
    engine.dispose()


def _create_ready_job(factory):  # type: ignore[no-untyped-def]
    with factory() as session:
        service = JobService(session)
        created = service.create_draft(
            JobCreateRequest(
                title="Senior Python Engineer",
                company_name="Hunar.ai",
                description="Build reliable Python APIs for an AI hiring product.",
                requirements={"required_skills": ["Python"]},
                screening_questions=[
                    {
                        "key": "interest",
                        "prompt": "Are you interested in this role?",
                        "answer_type": ScreeningAnswerType.YES_NO,
                    }
                ],
            )
        )
        question = created.screening_questions[0]
        definition = JobDefinitionEdit(
            title=created.title,
            company_name=created.company_name,
            description=created.description,
            requirements=created.requirements,
            screening_questions=[question.model_dump(mode="python")],
        )
        ready = service.mark_ready(
            created.id,
            expected_revision=created.revision,
            definition=definition,
        )
    return ready, definition


def test_approved_version_fk_and_snapshot_immutability(session_factory) -> None:  # type: ignore[no-untyped-def]
    ready, _ = _create_ready_job(session_factory)

    with session_factory.begin() as session:
        row = session.execute(
            text(
                "select approved_version from public.jobs where id = :id"
            ),
            {"id": ready.id},
        ).one()
        assert row.approved_version == 1

    with pytest.raises(DBAPIError), session_factory.begin() as session:
        session.execute(
            text(
                "update public.job_definition_versions set title='Changed' "
                "where job_id=:job_id and version=1"
            ),
            {"job_id": ready.id},
        )

    with pytest.raises(IntegrityError), session_factory.begin() as session:
        session.execute(
            text("update public.jobs set approved_version=99 where id=:job_id"),
            {"job_id": ready.id},
        )


def test_reopen_and_reapprove_preserve_v1(session_factory) -> None:  # type: ignore[no-untyped-def]
    ready, definition = _create_ready_job(session_factory)

    with session_factory() as session:
        service = JobService(session)
        reopened = service.reopen(ready.id, expected_revision=ready.revision)
        updated = definition.model_copy(deep=True)
        updated.requirements.required_skills = ["Python", "PostgreSQL"]
        saved = service.save_draft(
            ready.id,
            expected_revision=reopened.revision,
            definition=updated,
        )
        ready_v2 = service.mark_ready(
            ready.id,
            expected_revision=saved.revision,
            definition=updated,
        )
        assert ready_v2.approved_version == 2

    with session_factory() as session:
        versions = session.execute(
            text(
                "select version, requirements from public.job_definition_versions "
                "where job_id=:job_id order by version"
            ),
            {"job_id": ready.id},
        ).all()
        assert versions[0].requirements["required_skills"] == ["Python"]
        assert versions[1].requirements["required_skills"] == ["Python", "PostgreSQL"]


def test_concurrent_ready_same_revision_creates_one_snapshot(session_factory) -> None:  # type: ignore[no-untyped-def]
    with session_factory() as session:
        service = JobService(session)
        created = service.create_draft(
            JobCreateRequest(
                title="Senior Python Engineer",
                description="Build reliable Python APIs for an AI hiring product.",
                screening_questions=[
                    {
                        "key": "interest",
                        "prompt": "Are you interested in this role?",
                        "answer_type": "yes_no",
                    }
                ],
            )
        )
        definition = JobDefinitionEdit(
            title=created.title,
            description=created.description,
            requirements=created.requirements,
            screening_questions=[created.screening_questions[0].model_dump(mode="python")],
        )

    outcomes: list[str] = []
    barrier = threading.Barrier(2)

    def approve() -> None:
        with session_factory() as session:
            service = JobService(session)
            barrier.wait()
            try:
                service.mark_ready(
                    created.id,
                    expected_revision=0,
                    definition=definition,
                )
                outcomes.append("ready")
            except Exception as exc:  # noqa: BLE001 - assertion captures competing state error
                outcomes.append(type(exc).__name__)

    first = threading.Thread(target=approve)
    second = threading.Thread(target=approve)
    first.start()
    second.start()
    first.join()
    second.join()

    assert outcomes.count("ready") == 1
    with session_factory() as session:
        count = session.execute(
            text("select count(*) from public.job_definition_versions where job_id=:job_id"),
            {"job_id": created.id},
        ).scalar_one()
        assert count == 1
