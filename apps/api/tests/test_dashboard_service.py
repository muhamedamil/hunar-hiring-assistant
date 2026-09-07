"""Focused Module 8 service tests for authority, history, answer safety, and projections."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import UTC, datetime
from uuid import uuid4

import pytest

from app.core.errors import AppError
from app.dashboard.repository import (
    DashboardAttentionRecord,
    DashboardHistoricalContextError,
    DashboardScreeningAnswerRecord,
    DashboardScreeningContextRecord,
    DashboardScreeningRecord,
)
from app.dashboard.service import DashboardService
from app.voice_calls.errors import VoiceCallError


class Session:
    """Minimal transaction seam proving the service, not repository, owns transactions."""

    def __init__(self) -> None:
        self.active = False

    @contextmanager
    def begin(self):
        assert not self.active
        self.active = True
        try:
            yield self
        finally:
            self.active = False


class Repository:
    """Pure in-memory repository seam that records answer reads and frozen outputs."""

    def __init__(self) -> None:
        now = datetime.now(UTC)
        self.execution_id = uuid4()
        self.outreach_id = uuid4()
        self.relation_id = uuid4()
        self.candidate_id = uuid4()
        self.job_id = uuid4()
        self.result_id = uuid4()
        self.question_id = uuid4()
        self.answer_reads = 0
        self.context: DashboardScreeningContextRecord | None = DashboardScreeningContextRecord(
            execution_id=self.execution_id,
            outreach_request_id=self.outreach_id,
            job_candidate_id=self.relation_id,
            candidate_id=self.candidate_id,
            candidate_name="Current Candidate Name",
            job_id=self.job_id,
            job_title="Historical Role v1",
            job_definition_version=1,
            screening_state="result_available",
            submission_status="unknown",
            conversation_outcome="completed",
            candidate_interest="interested",
            duration_seconds=91.0,
            observed_at=now,
            sort_at=now,
            result_id=self.result_id,
            provider_status="COMPLETED",
            lifecycle_status="COMPLETED",
            answered_by="HUMAN",
            recording_available=True,
            notes="Interested in the role.",
            screening_questions_snapshot=[
                {
                    "id": str(self.question_id),
                    "key": "interest",
                    "prompt": "Are you interested in this role?",
                    "answer_type": "yes_no",
                    "required": True,
                    "options": [],
                    "source_job_question_id": None,
                }
            ],
        )
        self.answers = [
            DashboardScreeningAnswerRecord(
                outreach_question_id=self.question_id,
                position=1,
                answer_state="answered",
                answer_text="Yes",
            )
        ]
        self.recent = [self._summary(self.context)]

    @staticmethod
    def _summary(context: DashboardScreeningContextRecord) -> DashboardScreeningRecord:
        return DashboardScreeningRecord(
            execution_id=context.execution_id,
            outreach_request_id=context.outreach_request_id,
            job_candidate_id=context.job_candidate_id,
            candidate_id=context.candidate_id,
            candidate_name=context.candidate_name,
            job_id=context.job_id,
            job_title=context.job_title,
            job_definition_version=context.job_definition_version,
            screening_state=context.screening_state,
            submission_status=context.submission_status,
            conversation_outcome=context.conversation_outcome,
            candidate_interest=context.candidate_interest,
            duration_seconds=context.duration_seconds,
            observed_at=context.observed_at,
            sort_at=context.sort_at,
        )

    def count_jobs_by_status(self, _session):
        return {"draft": 2, "ready": 3}

    def count_candidates(self, _session):
        return 7

    def count_job_candidates_by_shortlist_status(self, _session):
        return {"reviewing": 4, "shortlisted": 2, "not_selected": 1}

    def count_screening_states(self, _session):
        return 7, {
            "queued": 1,
            "awaiting_result": 1,
            "dispatch_failed": 1,
            "submission_unknown": 1,
            "result_available": 1,
            "result_unavailable": 1,
            "result_invalid": 1,
        }

    def count_interested_screenings(self, _session):
        return 1

    def list_attention_executions(self, _session, *, limit):
        assert limit == 20
        return []

    def list_attention_candidates(self, _session, *, limit):
        assert limit == 20
        return []

    def list_recent_screenings(self, _session, *, limit):
        assert limit == 10
        return self.recent

    def list_screenings(self, _session, **kwargs):
        assert kwargs["limit"] >= 1
        return self.recent

    def count_screenings(self, _session, **_kwargs):
        return 101

    def get_screening_context(self, _session, execution_id):
        if execution_id != self.execution_id:
            return None
        return self.context

    def list_screening_answers(self, _session, result_id):
        assert result_id == self.result_id
        self.answer_reads += 1
        return self.answers


def service(repo: Repository | None = None) -> tuple[DashboardService, Repository]:
    actual = repo or Repository()
    return DashboardService(Session(), repository=actual), actual  # type: ignore[arg-type]


def test_overview_counts_interested_independently_and_preserves_unknown_recent_summary() -> None:
    dashboard, repo = service()
    response = dashboard.get_overview()
    assert response.jobs.total == 5
    assert response.screenings.total == 7
    assert sum(
        [
            response.screenings.queued,
            response.screenings.awaiting_result,
            response.screenings.dispatch_failed,
            response.screenings.submission_unknown,
            response.screenings.result_available,
            response.screenings.result_unavailable,
            response.screenings.result_invalid,
        ]
    ) == response.screenings.total
    assert response.screenings.interested == 1
    assert response.recent_screenings[0].screening_state == "result_available"
    assert response.recent_screenings[0].submission_status == "unknown"
    assert response.recent_screenings[0].job_title == "Historical Role v1"
    assert response.recent_screenings[0].candidate_name == "Current Candidate Name"
    assert repo.answer_reads == 0


def test_list_uses_authoritative_database_total_not_page_length() -> None:
    dashboard, _ = service()
    response = dashboard.list_screenings(
        job_id=None,
        state=None,
        interest=None,
        q="candidate",
        limit=20,
        offset=0,
    )
    assert len(response.items) == 1
    assert response.total == 101


def test_human_available_detail_maps_exact_frozen_question_uuid_and_answer() -> None:
    dashboard, repo = service()
    detail = dashboard.get_screening_detail(repo.execution_id)
    assert detail.job_title == "Historical Role v1"
    assert detail.job_definition_version == 1
    assert detail.submission_status == "unknown"
    assert detail.screening_state == "result_available"
    assert detail.recording_available is True
    assert detail.questions[0].question_id == repo.question_id
    assert detail.questions[0].prompt == "Are you interested in this role?"
    assert detail.questions[0].answer_state == "answered"
    assert detail.questions[0].answer_text == "Yes"
    assert repo.answer_reads == 1


@pytest.mark.parametrize(
    ("screening_state", "lifecycle_status", "answered_by"),
    [
        ("result_unavailable", "COMPLETED", "MACHINE"),
        ("result_unavailable", "COMPLETED", "UNKNOWN"),
        ("result_unavailable", "NOT_CONNECTED", None),
        ("result_unavailable", "FAILED", None),
        ("result_unavailable", "CANCELLED", None),
        ("result_invalid", "COMPLETED", "HUMAN"),
    ],
)
def test_nonaccepted_results_never_read_or_invent_candidate_answers(
    screening_state: str,
    lifecycle_status: str,
    answered_by: str | None,
) -> None:
    dashboard, repo = service()
    assert repo.context is not None
    repo.context = DashboardScreeningContextRecord(
        **{
            **repo.context.__dict__,
            "screening_state": screening_state,
            "lifecycle_status": lifecycle_status,
            "answered_by": answered_by,
        }
    )
    detail = dashboard.get_screening_detail(repo.execution_id)
    assert detail.questions[0].answer_state is None
    assert detail.questions[0].answer_text is None
    assert repo.answer_reads == 0


def test_authoritative_not_asked_remains_distinct_from_missing_answer_row() -> None:
    dashboard, repo = service()
    repo.answers = [
        DashboardScreeningAnswerRecord(
            outreach_question_id=repo.question_id,
            position=1,
            answer_state="not_asked",
            answer_text=None,
        )
    ]
    detail = dashboard.get_screening_detail(repo.execution_id)
    assert detail.questions[0].answer_state == "not_asked"
    assert detail.questions[0].answer_text is None

    repo.answers = []
    detail = dashboard.get_screening_detail(repo.execution_id)
    assert detail.questions[0].answer_state is None


def test_inconsistent_answer_identity_fails_closed() -> None:
    dashboard, repo = service()
    repo.answers = [
        DashboardScreeningAnswerRecord(
            outreach_question_id=uuid4(),
            position=1,
            answer_state="answered",
            answer_text="Unsafe",
        )
    ]
    with pytest.raises(AppError) as caught:
        dashboard.get_screening_detail(repo.execution_id)
    assert caught.value.code == "DASHBOARD_HISTORICAL_CONTEXT_INVALID"
    assert caught.value.status_code == 409


def test_missing_execution_uses_existing_voice_execution_404_contract() -> None:
    dashboard, _ = service()
    with pytest.raises(VoiceCallError) as caught:
        dashboard.get_screening_detail(uuid4())
    assert caught.value.code == "VOICE_CALL_NOT_FOUND"
    assert caught.value.status_code == 404


def test_broken_historical_context_is_explicit_409_and_never_current_state_fallback() -> None:
    repo = Repository()

    def broken(_session, execution_id):
        assert execution_id == repo.execution_id
        raise DashboardHistoricalContextError("broken immutable history")

    repo.get_screening_context = broken  # type: ignore[method-assign]
    dashboard, _ = service(repo)
    with pytest.raises(AppError) as caught:
        dashboard.get_screening_detail(repo.execution_id)
    assert caught.value.code == "DASHBOARD_HISTORICAL_CONTEXT_INVALID"
    assert caught.value.status_code == 409


def test_attention_priority_is_derived_and_bounded() -> None:
    dashboard, repo = service()
    now = datetime.now(UTC)
    rows = [
        DashboardAttentionRecord(
            kind=kind,
            candidate_id=repo.candidate_id,
            candidate_name="Candidate",
            job_id=repo.job_id,
            job_candidate_id=uuid4(),
            job_title="Role",
            execution_id=uuid4() if kind != "review_candidate" else None,
            outreach_request_id=repo.outreach_id if kind != "review_candidate" else None,
            occurred_at=now,
        )
        for kind in [
            "review_candidate",
            "result_unavailable",
            "result_invalid",
            "dispatch_failed",
            "submission_unknown",
        ]
    ]
    output = dashboard._merge_attention(rows[:4], rows[4:])
    assert [item.kind.value for item in output] == [
        "submission_unknown",
        "dispatch_failed",
        "result_invalid",
        "result_unavailable",
        "review_candidate",
    ]
