"""Real PostgreSQL qualification for Module 3 schema, locking, and sourcing constraints."""

from __future__ import annotations

import os
import threading
from datetime import UTC, datetime
from uuid import UUID

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from app.core.config import Settings
from app.jobs.errors import JobNotReadyError
from app.jobs.schemas import (
    JobCreateRequest,
    JobDefinitionEdit,
    ScreeningAnswerType,
    ScreeningQuestionCreate,
    ScreeningQuestionEdit,
)
from app.jobs.service import JobService
from app.sourcing.models import SourcingRun
from app.sourcing.repository import SourcingRepository
from app.sourcing.schemas import ProviderSearchPage
from app.sourcing.service import SourcingService
from app.sourcing.workers import SourcingWorkHandlers

TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL,
    reason="Set TEST_DATABASE_URL to a migrated disposable Supabase/Postgres database",
)


def _url() -> str:
    assert TEST_DATABASE_URL
    if TEST_DATABASE_URL.startswith("postgresql+psycopg://"):
        return TEST_DATABASE_URL
    return TEST_DATABASE_URL.replace("postgresql://", "postgresql+psycopg://", 1)


@pytest.fixture()
def session_factory():  # type: ignore[no-untyped-def]
    engine = create_engine(_url(), pool_pre_ping=True, hide_parameters=True)
    factory = sessionmaker(engine, expire_on_commit=False, autoflush=False)
    with engine.begin() as connection:
        connection.execute(
            text(
                "truncate table public.sourcing_enrichments, public.sourcing_results, "
                "public.sourcing_runs, public.candidate_external_identities, "
                "public.candidates, public.work_items restart identity cascade"
            )
        )
    yield factory
    engine.dispose()


def _create_ready_job(factory) -> tuple[UUID, int]:  # type: ignore[no-untyped-def]
    with factory() as session:
        service = JobService(session)
        created = service.create_draft(
            JobCreateRequest(
                title="Senior Backend Engineer",
                company_name="Hunar.ai",
                description="Build reliable backend services for a production AI hiring platform.",
                requirements={"required_skills": ["Python"]},
                screening_questions=[
                    ScreeningQuestionCreate(
                        key="interest",
                        prompt="Are you interested in this role?",
                        answer_type=ScreeningAnswerType.YES_NO,
                    )
                ],
            )
        )
        question = created.screening_questions[0]
        ready = service.mark_ready(
            created.id,
            expected_revision=0,
            definition=JobDefinitionEdit(
                title=created.title,
                company_name=created.company_name,
                description=created.description,
                requirements=created.requirements,
                screening_questions=[
                    ScreeningQuestionEdit(
                        id=question.id,
                        key=question.key,
                        prompt=question.prompt,
                        answer_type=question.answer_type,
                        required=question.required,
                        options=question.options,
                    )
                ],
            ),
        )
        return created.id, ready.revision


class EmptyProvider:
    """Return a successful zero-result search without external side effects."""

    def search_people(self, query):  # type: ignore[no-untyped-def]
        assert query.per_page <= 50
        return ProviderSearchPage(hits=[], total_matches=0)


def test_module_3_tables_enable_rls_and_result_count_cannot_exceed_limit(
    session_factory,  # type: ignore[no-untyped-def]
) -> None:
    job_id, _ = _create_ready_job(session_factory)
    with session_factory() as session:
        rows = session.execute(
            text(
                "select c.relname, c.relrowsecurity from pg_class c "
                "join pg_namespace n on n.oid=c.relnamespace "
                "where n.nspname='public' and c.relname in "
                "('sourcing_runs','sourcing_results','sourcing_enrichments')"
            )
        ).all()
        assert {row.relname: row.relrowsecurity for row in rows} == {
            "sourcing_enrichments": True,
            "sourcing_results": True,
            "sourcing_runs": True,
        }

    with pytest.raises(IntegrityError), session_factory.begin() as session:
        session.execute(
            text(
                "insert into public.sourcing_runs"
                "(job_id,definition_version,provider,status,criteria,provider_query,"
                "mapping_version,result_limit,result_count,completed_at) "
                "values (:job_id,1,'apollo','completed','{}','{}','test',10,11,now())"
            ),
            {"job_id": job_id},
        )

    with pytest.raises(IntegrityError), session_factory.begin() as session:
        session.execute(
            text(
                "insert into public.sourcing_runs"
                "(job_id,definition_version,provider,status,criteria,provider_query,"
                "mapping_version,result_limit,result_count,search_generation) "
                "values (:job_id,1,'apollo','searching','{}','{}','test',10,0,0)"
            ),
            {"job_id": job_id},
        )


def test_zero_result_search_is_completed_history_and_creates_no_candidates(
    session_factory,  # type: ignore[no-untyped-def]
) -> None:
    job_id, _ = _create_ready_job(session_factory)
    with session_factory() as session:
        run = SourcingService(session, search_provider=EmptyProvider()).start_search(
            job_id,
            result_limit=10,
        )
        assert run.status.value == "completed"
        assert run.result_count == 0
        assert run.definition_version == 1

    with session_factory() as session:
        assert session.execute(text("select count(*) from public.candidates")).scalar_one() == 0


def test_signed_bigint_request_id_and_single_enrichment_per_result_are_enforced(
    session_factory,  # type: ignore[no-untyped-def]
) -> None:
    job_id, _ = _create_ready_job(session_factory)
    with session_factory.begin() as session:
        run_id = session.execute(
            text(
                "insert into public.sourcing_runs"
                "(job_id,definition_version,provider,status,criteria,provider_query,"
                "mapping_version,result_limit,result_count,completed_at) "
                "values (:job_id,1,'apollo','completed','{}','{}','test',10,1,now()) "
                "returning id"
            ),
            {"job_id": job_id},
        ).scalar_one()
        result_id = session.execute(
            text(
                "insert into public.sourcing_results"
                "(sourcing_run_id,provider_person_id,result_position) "
                "values (:run_id,'person-1',1) returning id"
            ),
            {"run_id": run_id},
        ).scalar_one()
        session.execute(
            text(
                "insert into public.sourcing_enrichments"
                "(sourcing_result_id,provider,status,provider_request_id) "
                "values (:result_id,'apollo','awaiting_phone',:request_id)"
            ),
            {"result_id": result_id, "request_id": -1039995589705121900},
        )

    with pytest.raises(IntegrityError), session_factory.begin() as session:
        session.execute(
            text(
                "insert into public.sourcing_enrichments"
                "(sourcing_result_id,provider,status) values (:result_id,'apollo','pending')"
            ),
            {"result_id": result_id},
        )


def test_reopen_first_blocks_new_sourcing_after_row_lock_release(
    session_factory,  # type: ignore[no-untyped-def]
) -> None:
    job_id, ready_revision = _create_ready_job(session_factory)
    lock_acquired = threading.Event()
    reopen_committed = threading.Event()

    def reopen_first() -> None:
        with session_factory() as session:
            with session.begin():
                job = session.execute(
                    text("select id from public.jobs where id=:id for update"),
                    {"id": job_id},
                ).one()
                assert job.id == job_id
                lock_acquired.set()
                session.execute(
                    text(
                        "update public.jobs set status='draft', revision=revision+1, "
                        "updated_at=now() where id=:id and revision=:revision"
                    ),
                    {"id": job_id, "revision": ready_revision},
                )
            reopen_committed.set()

    thread = threading.Thread(target=reopen_first)
    thread.start()
    assert lock_acquired.wait(timeout=5)
    assert reopen_committed.wait(timeout=5)

    with session_factory() as session, pytest.raises(JobNotReadyError):
        SourcingService(session, search_provider=EmptyProvider()).start_search(
            job_id,
            result_limit=10,
        )
    thread.join(timeout=5)

    with session_factory() as session:
        assert session.execute(text("select count(*) from public.sourcing_runs")).scalar_one() == 0


def test_sourcing_binding_commits_before_later_reopen_without_rewriting_history(
    session_factory,  # type: ignore[no-untyped-def]
) -> None:
    job_id, ready_revision = _create_ready_job(session_factory)
    with session_factory() as session, session.begin():
        definition = JobService(session).lock_ready_definition_for_downstream_binding(job_id)
        run = SourcingRun(
            job_id=definition.job_id,
            definition_version=definition.version,
            provider="apollo",
            status="searching",
            criteria={"titles": [definition.title], "result_limit": 10},
            provider_query={"person_titles": [definition.title], "per_page": 10},
            mapping_version="test",
            result_limit=10,
            result_count=0,
            attempt_count=1,
            started_at=datetime.now(UTC),
        )
        SourcingRepository().create_run(session, run)
        run_id = run.id

    with session_factory() as session:
        JobService(session).reopen(job_id, expected_revision=ready_revision)

    with session_factory() as session:
        row = session.execute(
            text(
                "select definition_version from public.sourcing_runs where id=:id"
            ),
            {"id": run_id},
        ).one()
        assert row.definition_version == 1
        assert session.execute(
            text("select status from public.jobs where id=:id"), {"id": job_id}
        ).scalar_one() == "draft"


def test_unknown_work_reconciles_credit_enrichment_and_recovers_read_only_poll(
    session_factory,  # type: ignore[no-untyped-def]
) -> None:
    job_id, _ = _create_ready_job(session_factory)
    with session_factory.begin() as session:
        run_id = session.execute(
            text(
                "insert into public.sourcing_runs"
                "(job_id,definition_version,provider,status,criteria,provider_query,"
                "mapping_version,result_limit,result_count,completed_at) "
                "values (:job_id,1,'apollo','completed','{}','{}','test',10,2,now()) "
                "returning id"
            ),
            {"job_id": job_id},
        ).scalar_one()
        first_result_id = session.execute(
            text(
                "insert into public.sourcing_results"
                "(sourcing_run_id,provider_person_id,result_position) "
                "values (:run_id,'person-credit',1) returning id"
            ),
            {"run_id": run_id},
        ).scalar_one()
        second_result_id = session.execute(
            text(
                "insert into public.sourcing_results"
                "(sourcing_run_id,provider_person_id,result_position) "
                "values (:run_id,'person-poll',2) returning id"
            ),
            {"run_id": run_id},
        ).scalar_one()
        pending_id = session.execute(
            text(
                "insert into public.sourcing_enrichments"
                "(sourcing_result_id,provider,status) "
                "values (:result_id,'apollo','pending') returning id"
            ),
            {"result_id": first_result_id},
        ).scalar_one()
        awaiting_id = session.execute(
            text(
                "insert into public.sourcing_enrichments"
                "(sourcing_result_id,provider,status,provider_request_id) "
                "values (:result_id,'apollo','awaiting_phone',-7) returning id"
            ),
            {"result_id": second_result_id},
        ).scalar_one()
        session.execute(
            text(
                "insert into public.work_items"
                "(work_type,entity_type,entity_id,payload,dedupe_key,status,"
                "attempt_count,max_attempts,next_attempt_at,last_error_code) "
                "values "
                "('apollo_people_enrichment','sourcing_enrichment',:pending,'{}',"
                ":pending_key,'unknown',1,2,now(),'WORKER_LEASE_EXPIRED'),"
                "('apollo_enrichment_poll','sourcing_enrichment',:awaiting,'{}',"
                ":poll_key,'unknown',1,20,now(),'WORKER_LEASE_EXPIRED')"
            ),
            {
                "pending": pending_id,
                "awaiting": awaiting_id,
                "pending_key": f"apollo-people-enrichment:{pending_id}",
                "poll_key": f"apollo-enrichment-poll:{awaiting_id}",
            },
        )

    handlers = SourcingWorkHandlers(
        session_factory=session_factory,
        provider=None,
        settings=Settings(
            database_url=_url(),
            apollo_webhook_base_url="https://example.test",
            apollo_webhook_signing_secret="test-secret",
        ),
    )
    changed, recovered = handlers.reconcile_unknown_work()

    assert changed == 1
    assert recovered >= 1
    with session_factory() as session:
        pending_status = session.execute(
            text("select status from public.sourcing_enrichments where id=:id"),
            {"id": pending_id},
        ).scalar_one()
        assert pending_status == "unknown"
        recovery_rows = session.execute(
            text(
                "select count(*) from public.work_items "
                "where work_type='apollo_enrichment_poll' "
                "and entity_id=:id and status='pending' "
                "and dedupe_key like 'apollo-enrichment-poll-recovery:%'"
            ),
            {"id": awaiting_id},
        ).scalar_one()
        assert recovery_rows == 1
