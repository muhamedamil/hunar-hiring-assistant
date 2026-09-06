"""Real PostgreSQL qualification for Module 4 constraints, immutability, and RLS."""

from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor
from threading import Event, Lock
from uuid import UUID

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from app.candidates.schemas import CandidateCreateRequest
from app.candidates.service import CandidateService
from app.jobs.schemas import (
    JobCreateRequest,
    JobDefinitionEdit,
    ScreeningAnswerType,
    ScreeningQuestionCreate,
)
from app.jobs.service import JobService
from app.matching.schemas import SemanticCriterionVerdict, SemanticMatchOutput
from app.matching.service import MatchingService

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
    """Yield sessions against a disposable migrated database with Module 4 state cleared."""

    engine = create_engine(_url(), pool_pre_ping=True, hide_parameters=True)
    factory = sessionmaker(engine, expire_on_commit=False, autoflush=False)
    with engine.begin() as connection:
        connection.execute(
            text(
                "truncate table public.job_candidate_matches, public.job_candidates, "
                "public.sourcing_enrichments, public.sourcing_results, public.sourcing_runs, "
                "public.candidate_external_identities, public.candidates, public.jobs, "
                "public.work_items restart identity cascade"
            )
        )
    yield factory
    engine.dispose()


def _create_ready_job(factory) -> UUID:
    with factory() as session:
        service = JobService(session)
        created = service.create_draft(
            JobCreateRequest(
                title="Senior Backend Engineer",
                company_name="Hunar.ai",
                description="Build reliable backend services for the AI hiring assistant.",
                requirements={
                    "alternate_titles": ["Backend Engineer"],
                    "required_skills": ["Python"],
                    "locations": ["Bangalore"],
                },
                screening_questions=[
                    ScreeningQuestionCreate(
                        key="python_experience",
                        prompt="Do you have professional Python experience?",
                        answer_type=ScreeningAnswerType.YES_NO,
                    )
                ],
            )
        )
        ready = service.mark_ready(
            created.id,
            expected_revision=created.revision,
            definition=JobDefinitionEdit(
                title=created.title,
                company_name=created.company_name,
                description=created.description,
                requirements=created.requirements,
                screening_questions=[
                    question.model_dump(mode="python")
                    for question in created.screening_questions
                ],
            ),
        )
        assert ready.approved_version == 1
        return created.id


def _create_candidate(factory, name: str) -> UUID:
    with factory() as session:
        return CandidateService(session).create_manual_candidate(
            CandidateCreateRequest(
                full_name=name,
                current_title="Backend Engineer",
                location="Bangalore",
            )
        ).id


def _insert_relation(session, *, job_id: UUID, candidate_id: UUID) -> UUID:
    return session.execute(
        text(
            "insert into public.job_candidates(job_id,candidate_id,created_source) "
            "values (:job_id,:candidate_id,'manual') returning id"
        ),
        {"job_id": job_id, "candidate_id": candidate_id},
    ).scalar_one()


def _insert_completed_match(
    session,
    *,
    relation_id: UUID,
    job_id: UUID,
    candidate_id: UUID,
    key: str,
) -> UUID:
    return session.execute(
        text(
            "insert into public.job_candidate_matches("
            "job_candidate_id,job_id,candidate_id,definition_version,candidate_revision,"
            "input_snapshot,input_hash,matcher_version,analysis_key_hash,analysis_mode,status,"
            "match_score,evidence_coverage,match_reasons,completed_at) "
            "values (:relation_id,:job_id,:candidate_id,1,0,'{}',:input_hash,"
            "'candidate_job_match_v1',:analysis_key,'deterministic','completed',50,75,'[]',now()) "
            "returning id"
        ),
        {
            "relation_id": relation_id,
            "job_id": job_id,
            "candidate_id": candidate_id,
            "input_hash": key * 64,
            "analysis_key": key * 64,
        },
    ).scalar_one()


def test_module_4_tables_enable_rls_and_relation_is_unique(session_factory) -> None:
    job_id = _create_ready_job(session_factory)
    candidate_id = _create_candidate(session_factory, "Candidate One")

    with session_factory() as session:
        rows = session.execute(
            text(
                "select c.relname, c.relrowsecurity from pg_class c "
                "join pg_namespace n on n.oid=c.relnamespace "
                "where n.nspname='public' and c.relname in "
                "('job_candidates','job_candidate_matches')"
            )
        ).all()
        assert {row.relname: row.relrowsecurity for row in rows} == {
            "job_candidate_matches": True,
            "job_candidates": True,
        }
        privileges = session.execute(
            text(
                "select "
                "has_table_privilege('anon','public.job_candidates','SELECT') as anon_relation, "
                "has_table_privilege('authenticated','public.job_candidates','SELECT') "
                "as auth_relation, "
                "has_table_privilege('anon','public.job_candidate_matches','SELECT') "
                "as anon_match, "
                "has_table_privilege('authenticated','public.job_candidate_matches','SELECT') "
                "as auth_match"
            )
        ).one()
        assert privileges.anon_relation is False
        assert privileges.auth_relation is False
        assert privileges.anon_match is False
        assert privileges.auth_match is False

    with session_factory.begin() as session:
        _insert_relation(session, job_id=job_id, candidate_id=candidate_id)

    with pytest.raises(IntegrityError), session_factory.begin() as session:
        _insert_relation(session, job_id=job_id, candidate_id=candidate_id)


def test_completed_matches_are_immutable_and_score_cannot_exceed_coverage(
    session_factory,
) -> None:
    job_id = _create_ready_job(session_factory)
    candidate_id = _create_candidate(session_factory, "Candidate Two")
    with session_factory.begin() as session:
        relation_id = _insert_relation(session, job_id=job_id, candidate_id=candidate_id)
        match_id = _insert_completed_match(
            session,
            relation_id=relation_id,
            job_id=job_id,
            candidate_id=candidate_id,
            key="a",
        )
        session.execute(
            text("update public.job_candidates set current_match_id=:match_id where id=:id"),
            {"match_id": match_id, "id": relation_id},
        )

    with pytest.raises(IntegrityError), session_factory.begin() as session:
        session.execute(
            text("update public.job_candidate_matches set match_score=60 where id=:id"),
            {"id": match_id},
        )

    with pytest.raises(IntegrityError), session_factory.begin() as session:
        session.execute(
            text(
                "insert into public.job_candidate_matches("
                "job_candidate_id,job_id,candidate_id,definition_version,candidate_revision,"
                "input_snapshot,input_hash,matcher_version,analysis_key_hash,analysis_mode,status,"
                "match_score,evidence_coverage,match_reasons,completed_at) "
                "values (:relation_id,:job_id,:candidate_id,1,0,'{}',:input_hash,"
                "'candidate_job_match_v1',:analysis_key,'deterministic','completed',"
                "80,40,'[]',now())"
            ),
            {
                "relation_id": relation_id,
                "job_id": job_id,
                "candidate_id": candidate_id,
                "input_hash": "b" * 64,
                "analysis_key": "b" * 64,
            },
        )


def test_active_semantic_analysis_is_unique_and_match_pointer_cannot_cross_relation(
    session_factory,
) -> None:
    job_id = _create_ready_job(session_factory)
    candidate_one = _create_candidate(session_factory, "Candidate Three")
    candidate_two = _create_candidate(session_factory, "Candidate Four")
    analysis_key = "c" * 64

    with session_factory.begin() as session:
        relation_one = _insert_relation(session, job_id=job_id, candidate_id=candidate_one)
        relation_two = _insert_relation(session, job_id=job_id, candidate_id=candidate_two)
        match_two = _insert_completed_match(
            session,
            relation_id=relation_two,
            job_id=job_id,
            candidate_id=candidate_two,
            key="d",
        )
        session.execute(
            text(
                "insert into public.job_candidate_matches("
                "job_candidate_id,job_id,candidate_id,definition_version,candidate_revision,"
                "input_snapshot,input_hash,matcher_version,analysis_key_hash,analysis_mode,status) "
                "values (:relation_id,:job_id,:candidate_id,1,0,'{}',:input_hash,"
                "'candidate_job_match_v1',:analysis_key,'hybrid_gemini','analyzing')"
            ),
            {
                "relation_id": relation_one,
                "job_id": job_id,
                "candidate_id": candidate_one,
                "input_hash": "e" * 64,
                "analysis_key": analysis_key,
            },
        )

    with pytest.raises(IntegrityError), session_factory.begin() as session:
        session.execute(
            text(
                "insert into public.job_candidate_matches("
                "job_candidate_id,job_id,candidate_id,definition_version,candidate_revision,"
                "input_snapshot,input_hash,matcher_version,analysis_key_hash,analysis_mode,status) "
                "values (:relation_id,:job_id,:candidate_id,1,0,'{}',:input_hash,"
                "'candidate_job_match_v1',:analysis_key,'hybrid_gemini','analyzing')"
            ),
            {
                "relation_id": relation_one,
                "job_id": job_id,
                "candidate_id": candidate_one,
                "input_hash": "f" * 64,
                "analysis_key": analysis_key,
            },
        )

    with pytest.raises(IntegrityError), session_factory.begin() as session:
        session.execute(
            text("update public.job_candidates set current_match_id=:match where id=:relation"),
            {"match": match_two, "relation": relation_one},
        )


class _BlockingMatchProvider:
    """Hold one provider call open while an identical attachment races it."""

    model_name = "gemini-concurrency-test"

    def __init__(self) -> None:
        self.started = Event()
        self.release = Event()
        self._lock = Lock()
        self.calls = 0

    def analyze(self, *, snapshot, evidence):
        del snapshot
        with self._lock:
            self.calls += 1
        self.started.set()
        assert self.release.wait(timeout=10)
        return SemanticMatchOutput(
            role_alignment=SemanticCriterionVerdict(
                status="supported",
                evidence_ids=[evidence[0].id],
                reason="Explicit title evidence supports role alignment.",
            ),
            seniority_alignment=SemanticCriterionVerdict(
                status="unknown",
                evidence_ids=[],
                reason="Seniority is not established by the supplied titles.",
            ),
        )


def test_concurrent_manual_attachments_create_one_relation_and_one_semantic_analysis(
    session_factory,
) -> None:
    job_id = _create_ready_job(session_factory)
    candidate_id = _create_candidate(session_factory, "Concurrent Candidate")
    provider = _BlockingMatchProvider()

    def attach():
        with session_factory() as session:
            return MatchingService(session, semantic_provider=provider).add_manual_candidate(
                job_id,
                candidate_id,
            )

    with ThreadPoolExecutor(max_workers=2) as executor:
        first_future = executor.submit(attach)
        assert provider.started.wait(timeout=10)
        second_future = executor.submit(attach)
        second = second_future.result(timeout=10)
        provider.release.set()
        first = first_future.result(timeout=10)

    assert first.id == second.id
    assert first.current_match is not None
    assert provider.calls == 1
    with session_factory() as session:
        counts = session.execute(
            text(
                "select "
                "(select count(*) from public.job_candidates) as relations, "
                "(select count(*) from public.job_candidate_matches) as matches, "
                "(select count(*) from public.job_candidate_matches "
                "where status='analyzing') as active"
            )
        ).one()
        assert counts.relations == 1
        assert counts.matches == 1
        assert counts.active == 0
