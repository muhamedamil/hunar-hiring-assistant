"""Disposable PostgreSQL qualification for Module 5 constraints and concurrency."""

from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.orm import sessionmaker

from app.call_results.models import VoiceCallResult
from app.candidates.schemas import CandidateCreateRequest
from app.candidates.service import CandidateService
from app.jobs.schemas import JobCreateRequest, JobDefinitionEdit, ScreeningQuestionCreate
from app.jobs.service import JobService
from app.matching.schemas import ShortlistStatus
from app.matching.service import MatchingService
from app.outreach.service import OutreachService
from app.voice_calls.models import VoiceCallExecution

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
def session_factory():
    engine = create_engine(_url(), pool_pre_ping=True, hide_parameters=True)
    factory = sessionmaker(engine, expire_on_commit=False, autoflush=False)
    with engine.begin() as connection:
        connection.execute(
            text(
                "truncate table public.outreach_requests, public.job_candidate_matches, "
                "public.job_candidates, public.sourcing_enrichments, public.sourcing_results, "
                "public.sourcing_runs, public.candidate_external_identities, public.candidates, "
                "public.jobs, public.work_items restart identity cascade"
            )
        )
    yield factory
    engine.dispose()


def _create_shortlisted_context(factory):
    with factory() as session:
        job_service = JobService(session)
        draft = job_service.create_draft(
            JobCreateRequest(
                title="Backend Engineer",
                description="Build reliable backend systems for the hiring assistant.",
                requirements={"required_skills": ["Python"]},
                screening_questions=[
                    ScreeningQuestionCreate(
                        key="interest",
                        prompt="Why are you interested in this role?",
                        answer_type="short_text",
                    )
                ],
            )
        )
        ready = job_service.mark_ready(
            draft.id,
            expected_revision=draft.revision,
            definition=JobDefinitionEdit(
                title=draft.title,
                company_name=draft.company_name,
                description=draft.description,
                requirements=draft.requirements,
                screening_questions=[
                    question.model_dump(mode="python") for question in draft.screening_questions
                ],
            ),
        )
        candidate = CandidateService(session).create_manual_candidate(
            CandidateCreateRequest(
                full_name="Aisha Khan",
                current_title="Backend Engineer",
                phone="+919876543210",
            )
        )
        matching = MatchingService(session)
        relation = matching.add_manual_candidate(ready.id, candidate.id)
        relation_id = relation.id
        relation_revision = relation.revision

    # Attaching and shortlisting are separate HTTP mutations in production. Use a fresh
    # request-scoped session so the read transaction opened by add_manual_candidate's
    # response projection cannot leak into the shortlist mutation.
    with factory() as session:
        matching = MatchingService(session)
        shortlisted = matching.update_shortlist(
            relation_id,
            expected_revision=relation_revision,
            status=ShortlistStatus.SHORTLISTED,
        )
        return shortlisted.id


def _confirm(factory, relation_id):
    with factory() as session:
        service = OutreachService(session)
        preparation = service.get_preparation(relation_id)
        return service.prepare_outreach(
            relation_id,
            preparation_token=preparation.preparation_token,
            screening_questions=preparation.default_screening_questions,
        )


def test_outreach_rls_privileges_constraints_and_immutability(session_factory) -> None:
    relation_id = _create_shortlisted_context(session_factory)
    request = _confirm(session_factory, relation_id)
    with session_factory() as session:
        security = session.execute(
            text(
                "select c.relrowsecurity, "
                "has_table_privilege('anon','public.outreach_requests','SELECT') as anon_read, "
                "has_table_privilege('authenticated','public.outreach_requests','SELECT') "
                "as auth_read from pg_class c join pg_namespace n on n.oid=c.relnamespace "
                "where n.nspname='public' and c.relname='outreach_requests'"
            )
        ).one()
        assert security.relrowsecurity is True
        assert security.anon_read is False
        assert security.auth_read is False

    with pytest.raises(DBAPIError), session_factory.begin() as session:
        session.execute(
            text("update public.outreach_requests set screening_context_hash=:hash where id=:id"),
            {"hash": "b" * 64, "id": request.id},
        )
    with pytest.raises(DBAPIError), session_factory.begin() as session:
        session.execute(
            text("delete from public.outreach_requests where id=:id"), {"id": request.id}
        )

    with session_factory() as session:
        row = session.execute(
            text(
                "select job_candidate_id,decision_match_id from public.outreach_requests "
                "where id=:id"
            ),
            {"id": request.id},
        ).one()
    with pytest.raises(IntegrityError), session_factory.begin() as session:
        session.execute(
            text(
                "insert into public.outreach_requests(job_candidate_id,decision_match_id,"
                "phone_e164_snapshot,screening_questions_snapshot,screening_context_hash) "
                "values (:relation,:match,'invalid','[]',:hash)"
            ),
            {"relation": row.job_candidate_id, "match": row.decision_match_id, "hash": "a" * 63},
        )


def test_concurrent_identical_confirm_creates_one_authoritative_row(session_factory) -> None:
    relation_id = _create_shortlisted_context(session_factory)
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(
            executor.map(lambda _index: _confirm(session_factory, relation_id), range(2))
        )
    assert results[0].id == results[1].id
    with session_factory() as session:
        assert (
            session.execute(text("select count(*) from public.outreach_requests")).scalar_one() == 1
        )


def test_outreach_read_projection_uses_historical_job_and_result_first_state(
    session_factory,
) -> None:
    """Outreach UX reads historical Job context and Module 8 state without rewriting readiness."""

    relation_id = _create_shortlisted_context(session_factory)
    request = _confirm(session_factory, relation_id)
    execution_id = None
    with session_factory.begin() as session:
        row = session.execute(
            text(
                "select j.id as job_id from public.outreach_requests o "
                "join public.job_candidates jc on jc.id=o.job_candidate_id "
                "join public.jobs j on j.id=jc.job_id where o.id=:id"
            ),
            {"id": request.id},
        ).one()
        session.execute(
            text("update public.jobs set title='CURRENT MUTATED TITLE' where id=:job_id"),
            {"job_id": row.job_id},
        )
        execution = VoiceCallExecution(
            id=uuid4(),
            outreach_request_id=request.id,
            agent_id=uuid4(),
            provider_call_id=None,
            provider_request_id="hha-outreach-read-projection",
            status="unknown",
            language="ENGLISH",
            timezone="Asia/Kolkata",
            agent_contract_version="hunar_voice_screening_en_v1",
            provider_initial_status=None,
            provider_payload_snapshot={},
            submitted_at=None,
        )
        session.add(execution)
        session.flush()
        execution_id = execution.id
        now = datetime.now(UTC)
        session.add(
            VoiceCallResult(
                id=uuid4(),
                voice_call_execution_id=execution.id,
                provider_call_id=uuid4(),
                provider_status="COMPLETED",
                lifecycle_status="COMPLETED",
                answered_by="HUMAN",
                screening_result_state="available",
                result_failure_code=None,
                conversation_outcome="completed",
                candidate_interest="interested",
                notes="Projection qualification",
                duration_seconds=30.0,
                started_at=now,
                ended_at=now,
                recording_url="https://provider.invalid/private",
                observed_at=now,
                updated_at=now,
            )
        )

    with session_factory() as session:
        projected = OutreachService(session).get_outreach_request(request.id)

    assert execution_id is not None
    assert projected.readiness == "READY_FOR_EXECUTION"
    assert projected.job_title == "Backend Engineer"
    assert projected.job_definition_version == 1
    assert projected.execution_id == execution_id
    assert projected.screening_state == "result_available"
    assert projected.submission_status == "unknown"
