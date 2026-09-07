"""Disposable PostgreSQL qualification for Module 8 scale, history, parity, and query plans."""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import sessionmaker

from app.call_results.models import VoiceCallResult, VoiceScreeningAnswer
from app.candidates.models import Candidate
from app.dashboard.repository import (
    DashboardRepository,
    dashboard_sort_at_expression,
)
from app.dashboard.schemas import DashboardScreeningState
from app.dashboard.service import DashboardService
from app.jobs.models import Job, JobDefinitionVersion
from app.matching.models import JobCandidate, JobCandidateMatch
from app.outreach.models import OutreachRequest
from app.sourcing.models import SourcingResult  # noqa: F401  # register FK target metadata
from app.voice_calls.models import VoiceCallExecution


def _database_url() -> str:
    value = os.environ["TEST_DATABASE_URL"]
    return value.replace("postgresql://", "postgresql+psycopg://", 1)


@pytest.fixture(name="dashboard_db")
def dashboard_db_fixture():
    """Seed 105 Jobs/Candidates and 106 immutable screening executions for qualification."""

    if not os.getenv("TEST_DATABASE_URL"):
        pytest.skip(
            "Set TEST_DATABASE_URL to a disposable PostgreSQL database migrated through Module 7"
        )
    engine = create_engine(_database_url(), hide_parameters=True)
    with engine.begin() as connection:
        connection.execute(
            text(
                "truncate table public.jobs, public.candidates, public.work_items "
                "restart identity cascade"
            )
        )
    factory = sessionmaker(engine, expire_on_commit=False, autoflush=False)
    now = datetime.now(UTC)
    execution_ids: list[UUID] = []
    job_ids: list[UUID] = []
    question_ids: dict[UUID, UUID] = {}
    first_relation_id: UUID | None = None
    first_match_id: UUID | None = None

    with factory.begin() as session:
        for index in range(105):
            job = Job(
                id=uuid4(),
                title=f"Current Mutable Role {index:03d}",
                company_name="Hunar Test",
                description="A sufficiently detailed dashboard qualification role description.",
                requirements={},
                screening_questions=[],
                status="draft",
                revision=0,
            )
            candidate = Candidate(
                id=uuid4(),
                full_name=f"Dashboard Candidate {index:03d}",
                revision=0,
            )
            session.add_all([job, candidate])
            session.flush()

            definition = JobDefinitionVersion(
                id=uuid4(),
                job_id=job.id,
                version=1,
                title=f"Historical Frozen Role {index:03d}",
                company_name="Hunar Test",
                description="A sufficiently detailed frozen role description for qualification.",
                requirements={},
                screening_questions=[],
            )
            relation = JobCandidate(
                id=uuid4(),
                job_id=job.id,
                candidate_id=candidate.id,
                created_source="manual",
                shortlist_status="reviewing",
                revision=0,
            )
            session.add_all([definition, relation])
            session.flush()

            match = JobCandidateMatch(
                id=uuid4(),
                job_candidate_id=relation.id,
                job_id=job.id,
                candidate_id=candidate.id,
                definition_version=1,
                candidate_revision=0,
                input_snapshot={},
                input_hash=f"{index + 1:064x}",
                matcher_version="module8-db-test",
                analysis_key_hash=f"{index + 1000:064x}",
                analysis_mode="deterministic",
                status="completed",
                match_score=50,
                evidence_coverage=50,
                match_reasons=[],
                completed_at=now,
            )
            session.add(match)
            session.flush()
            if index == 0:
                first_relation_id = relation.id
                first_match_id = match.id
            relation.shortlist_status = "shortlisted"
            relation.decision_match_id = match.id
            session.flush()

            question_id = uuid4()
            second_question_id = uuid4()
            outreach = OutreachRequest(
                id=uuid4(),
                job_candidate_id=relation.id,
                decision_match_id=match.id,
                phone_e164_snapshot="+12025550123",
                screening_questions_snapshot=[
                    {
                        "id": str(question_id),
                        "key": "interest",
                        "prompt": f"Are you interested in frozen role {index:03d}?",
                        "answer_type": "yes_no",
                        "required": True,
                        "options": [],
                        "source_job_question_id": None,
                    },
                    {
                        "id": str(second_question_id),
                        "key": "availability",
                        "prompt": f"When could you start frozen role {index:03d}?",
                        "answer_type": "short_text",
                        "required": False,
                        "options": [],
                        "source_job_question_id": None,
                    },
                ],
                screening_context_hash=f"{index + 2000:064x}",
            )
            session.add(outreach)
            session.flush()

            status = ["queued", "submitted", "failed", "unknown"][index % 4]
            execution = VoiceCallExecution(
                id=uuid4(),
                outreach_request_id=outreach.id,
                agent_id=uuid4(),
                provider_call_id=uuid4() if status == "submitted" else None,
                provider_request_id=f"hha-dashboard-{index:03d}",
                status=status,
                language="ENGLISH",
                timezone="Asia/Kolkata",
                agent_contract_version="hunar_voice_screening_en_v1",
                provider_initial_status="SCHEDULED" if status == "submitted" else None,
                provider_payload_snapshot={},
                submitted_at=now if status == "submitted" else None,
                created_at=now - timedelta(minutes=index),
                updated_at=now - timedelta(minutes=index),
            )
            session.add(execution)
            session.flush()

            if index % 10 == 0:
                result = VoiceCallResult(
                    id=uuid4(),
                    voice_call_execution_id=execution.id,
                    provider_call_id=execution.provider_call_id or uuid4(),
                    provider_status="COMPLETED",
                    lifecycle_status="COMPLETED",
                    answered_by="HUMAN",
                    screening_result_state="available",
                    result_failure_code=None,
                    conversation_outcome="completed",
                    candidate_interest="interested",
                    notes="Qualified dashboard evidence",
                    duration_seconds=60.0,
                    started_at=now - timedelta(seconds=60),
                    ended_at=now,
                    recording_url="https://provider.invalid/private-recording",
                    observed_at=now + timedelta(seconds=index),
                    updated_at=now + timedelta(seconds=index),
                )
                session.add(result)
                session.flush()
                session.add_all(
                    [
                        VoiceScreeningAnswer(
                            id=uuid4(),
                            voice_call_result_id=result.id,
                            outreach_question_id=question_id,
                            position=1,
                            answer_state="answered",
                            answer_text="Yes",
                        ),
                        VoiceScreeningAnswer(
                            id=uuid4(),
                            voice_call_result_id=result.id,
                            outreach_question_id=second_question_id,
                            position=2,
                            answer_state="no_clear_answer",
                            answer_text=None,
                        ),
                    ]
                )

            execution_ids.append(execution.id)
            job_ids.append(job.id)
            question_ids[execution.id] = question_id

        assert first_relation_id is not None
        assert first_match_id is not None
        replay_question_id = uuid4()
        replay_outreach = OutreachRequest(
            id=uuid4(),
            job_candidate_id=first_relation_id,
            decision_match_id=first_match_id,
            phone_e164_snapshot="+12025550123",
            screening_questions_snapshot=[
                {
                    "id": str(replay_question_id),
                    "key": "follow_up",
                    "prompt": "Are you still interested in this historical role?",
                    "answer_type": "yes_no",
                    "required": True,
                    "options": [],
                    "source_job_question_id": None,
                }
            ],
            screening_context_hash=f"{999999:064x}",
        )
        session.add(replay_outreach)
        session.flush()
        replay_execution = VoiceCallExecution(
            id=uuid4(),
            outreach_request_id=replay_outreach.id,
            agent_id=uuid4(),
            provider_call_id=uuid4(),
            provider_request_id="hha-dashboard-replay",
            status="submitted",
            language="ENGLISH",
            timezone="Asia/Kolkata",
            agent_contract_version="hunar_voice_screening_en_v1",
            provider_initial_status="SCHEDULED",
            provider_payload_snapshot={},
            submitted_at=now + timedelta(minutes=2),
            created_at=now + timedelta(minutes=2),
            updated_at=now + timedelta(minutes=2),
        )
        session.add(replay_execution)
        session.flush()
        execution_ids.append(replay_execution.id)
        question_ids[replay_execution.id] = replay_question_id

    yield factory, engine, execution_ids, job_ids, question_ids
    engine.dispose()


def test_compiled_query_freezes_historical_join_and_shared_result_first_state() -> None:
    """Compile without a database so authority topology remains visible even in skipped DB runs."""

    repository = DashboardRepository()
    statement = repository._screening_select(include_detail=False).order_by(  # noqa: SLF001
        dashboard_sort_at_expression().desc(), VoiceCallExecution.id.desc()
    )
    sql = str(
        statement.compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    )
    normalized = " ".join(sql.lower().split())
    assert "join outreach_requests" in normalized
    assert "join job_candidates" in normalized
    assert "join candidates" in normalized
    assert "join job_candidate_matches" in normalized
    assert "join job_definition_versions" in normalized
    assert "left outer join voice_call_results" in normalized
    assert "voice_screening_answers" not in normalized
    assert " join jobs " not in f" {normalized} "
    result_state_position = normalized.index(
        "voice_call_results.screening_result_state = 'available'"
    )
    execution_state_position = normalized.index("voice_call_executions.status = 'queued'")
    assert result_state_position < execution_state_position


def test_scale_totals_state_arithmetic_pagination_and_count_parity(dashboard_db) -> None:
    factory, _, execution_ids, job_ids, _ = dashboard_db
    with factory() as session:
        service = DashboardService(session)
        overview = service.get_overview()
        page1 = service.list_screenings(
            job_id=None,
            state=None,
            interest=None,
            q=None,
            limit=100,
            offset=0,
        )
        page2 = service.list_screenings(
            job_id=None,
            state=None,
            interest=None,
            q=None,
            limit=100,
            offset=100,
        )
    assert overview.jobs.total == 105
    assert overview.candidates.total == 105
    assert overview.screenings.total == len(execution_ids) == 106
    exclusive_sum = sum(
        [
            overview.screenings.queued,
            overview.screenings.awaiting_result,
            overview.screenings.dispatch_failed,
            overview.screenings.submission_unknown,
            overview.screenings.result_available,
            overview.screenings.result_unavailable,
            overview.screenings.result_invalid,
        ]
    )
    assert exclusive_sum == overview.screenings.total
    assert overview.screenings.interested == 11
    assert page1.total == page2.total == 106
    assert len(page1.items) == 100 and len(page2.items) == 6
    ids = [row.execution_id for row in [*page1.items, *page2.items]]
    assert len(ids) == len(set(ids)) == 106
    assert len(overview.recent_screenings) == 10
    recent_sort_keys = [
        (row.sort_at, str(row.execution_id)) for row in overview.recent_screenings
    ]
    assert recent_sort_keys == sorted(recent_sort_keys, reverse=True)
    assert any(
        row.screening_state
        in {
            DashboardScreeningState.QUEUED,
            DashboardScreeningState.AWAITING_RESULT,
            DashboardScreeningState.DISPATCH_FAILED,
            DashboardScreeningState.SUBMISSION_UNKNOWN,
        }
        for row in overview.recent_screenings
    )

    first_job_rows = [row for row in [*page1.items, *page2.items] if row.job_id == job_ids[0]]
    assert len(first_job_rows) == 2
    assert len({row.execution_id for row in first_job_rows}) == 2
    assert len({row.job_candidate_id for row in first_job_rows}) == 1


def test_filters_share_count_predicate_and_historical_job_mutation_does_not_rewrite_rows(
    dashboard_db,
) -> None:
    factory, engine, execution_ids, job_ids, _ = dashboard_db
    target_execution = execution_ids[0]
    target_job = job_ids[0]
    replacement_question_id = uuid4()
    with engine.begin() as connection:
        connection.execute(
            text(
                "insert into public.job_definition_versions "
                "(id, job_id, version, title, company_name, description, requirements, "
                "screening_questions) values "
                "(:id, :job_id, 2, 'NEW APPROVED TITLE', 'Hunar Test', :description, "
                "'{}'::jsonb, cast(:questions as jsonb))"
            ),
            {
                "id": uuid4(),
                "job_id": target_job,
                "description": "A sufficiently detailed replacement role description.",
                "questions": (
                    '[{"id":"'
                    + str(replacement_question_id)
                    + '","key":"new_question","prompt":"This is a new question, right?",'
                    '"answer_type":"yes_no","required":true,"options":[]}]'
                ),
            },
        )
        connection.execute(
            text(
                "update public.jobs set title='NEW CURRENT TITLE', status='ready', "
                "approved_version=2, screening_questions=cast(:questions as jsonb) "
                "where id=:job_id"
            ),
            {
                "job_id": target_job,
                "questions": (
                    '[{"id":"'
                    + str(replacement_question_id)
                    + '","key":"new_question","prompt":"This is a new question, right?",'
                    '"answer_type":"yes_no","required":true,"options":[]}]'
                ),
            },
        )
    with factory() as session:
        service = DashboardService(session)
        by_job = service.list_screenings(
            job_id=target_job,
            state=DashboardScreeningState.RESULT_AVAILABLE,
            interest=None,
            q=" frozen role 000 ".strip(),
            limit=20,
            offset=0,
        )
        detail = service.get_screening_detail(target_execution)
    assert by_job.total == len(by_job.items) == 1
    assert by_job.items[0].job_title == "Historical Frozen Role 000"
    assert detail.job_title == "Historical Frozen Role 000"
    assert detail.questions[0].prompt == "Are you interested in frozen role 000?"
    assert detail.questions[0].answer_text == "Yes"
    assert detail.questions[1].answer_state == "no_clear_answer"
    assert detail.questions[1].answer_text is None

    with factory() as session:
        by_candidate_name = DashboardService(session).list_screenings(
            job_id=target_job,
            state=None,
            interest=None,
            q="Dashboard Candidate 000",
            limit=20,
            offset=0,
        )
    assert by_candidate_name.total == len(by_candidate_name.items) == 2


def test_queued_execution_with_result_uses_result_state_without_mutation(dashboard_db) -> None:
    factory, _, execution_ids, _, _ = dashboard_db
    target_execution = execution_ids[0]
    with factory() as session:
        detail = DashboardService(session).get_screening_detail(target_execution)
    assert detail.screening_state == DashboardScreeningState.RESULT_AVAILABLE
    assert detail.submission_status == "queued"
    assert detail.questions[0].answer_state == "answered"
    assert detail.questions[1].answer_state == "no_clear_answer"


def test_unknown_execution_with_available_result_preserves_submission_truth(dashboard_db) -> None:
    factory, engine, execution_ids, _, _ = dashboard_db
    target_execution = execution_ids[3]  # index 3 is UNKNOWN and initially has no result.
    now = datetime.now(UTC)
    with engine.begin() as connection:
        connection.execute(
            text(
                "insert into public.voice_call_results ("
                "id,voice_call_execution_id,provider_call_id,provider_status,lifecycle_status,"
                "answered_by,screening_result_state,conversation_outcome,candidate_interest,"
                "notes,duration_seconds,observed_at,updated_at) values ("
                ":id,:execution,:call,'COMPLETED','COMPLETED','HUMAN','available',"
                "'completed','interested','race proof',10,:observed,:observed)"
            ),
            {
                "id": uuid4(),
                "execution": target_execution,
                "call": uuid4(),
                "observed": now,
            },
        )
    with factory() as session:
        service = DashboardService(session)
        detail = service.get_screening_detail(target_execution)
        overview = service.get_overview()
    assert detail.screening_state == DashboardScreeningState.RESULT_AVAILABLE
    assert detail.submission_status == "unknown"
    assert detail.questions[0].answer_state is None
    assert all(item.execution_id != target_execution for item in overview.needs_attention)


def test_query_plan_is_executed_and_no_speculative_dashboard_index_exists(
    dashboard_db,
) -> None:
    _, engine, _, _, _ = dashboard_db
    repository = DashboardRepository()
    statement = repository._screening_select(include_detail=False).order_by(  # noqa: SLF001
        dashboard_sort_at_expression().desc(), VoiceCallExecution.id.desc()
    ).limit(20)
    compiled = statement.compile(engine, compile_kwargs={"literal_binds": True})
    with engine.connect() as connection:
        plan_rows = connection.execute(
            text("EXPLAIN (ANALYZE, BUFFERS) " + str(compiled))
        ).scalars().all()
        dashboard_indexes = connection.execute(
            text(
                "select indexname from pg_indexes where schemaname='public' "
                "and indexname like '%dashboard%' order by indexname"
            )
        ).scalars().all()
    plan = "\n".join(str(row) for row in plan_rows)
    print("\nMODULE 8 QUERY PLAN\n" + plan)
    assert "Execution Time" in plan
    assert dashboard_indexes == []
    assert inspect(engine).has_table("voice_call_executions")
