"""Transaction-owning composition service for read-only Module 8 dashboard projections."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.call_results.schemas import (
    CandidateInterest,
    ConversationOutcome,
    ScreeningAnswerState,
)
from app.core.errors import AppError
from app.dashboard.repository import (
    DashboardAttentionRecord,
    DashboardHistoricalContextError,
    DashboardRepository,
    DashboardScreeningAnswerRecord,
    DashboardScreeningContextRecord,
    DashboardScreeningRecord,
)
from app.dashboard.schemas import (
    DashboardAttentionItem,
    DashboardAttentionKind,
    DashboardCandidateMetrics,
    DashboardJobMetrics,
    DashboardOverviewResponse,
    DashboardPipelineMetrics,
    DashboardQuestionAnswer,
    DashboardScreeningDetailResponse,
    DashboardScreeningListResponse,
    DashboardScreeningMetrics,
    DashboardScreeningState,
    DashboardScreeningSummary,
)
from app.integrations.hunar.schemas import HunarAnsweredBy, HunarCallStatus, HunarLifecycleStatus
from app.outreach.schemas import OutreachScreeningQuestion
from app.voice_calls.errors import VoiceCallError
from app.voice_calls.schemas import VoiceCallExecutionStatus

_ATTENTION_PRIORITY = {
    "submission_unknown": 0,
    "dispatch_failed": 1,
    "result_invalid": 2,
    "result_unavailable": 3,
    "review_candidate": 4,
}


class DashboardService:
    """Compose existing authoritative state into recruiter-safe read responses only."""

    def __init__(
        self,
        session: Session,
        *,
        repository: DashboardRepository | None = None,
    ) -> None:
        self._session = session
        self._repository = repository or DashboardRepository()

    def get_overview(self) -> DashboardOverviewResponse:
        """Return authoritative metrics plus bounded attention and recent execution projections."""

        with self._session.begin():
            jobs = self._repository.count_jobs_by_status(self._session)
            candidates = self._repository.count_candidates(self._session)
            pipeline = self._repository.count_job_candidates_by_shortlist_status(self._session)
            screening_total, screening_states = self._repository.count_screening_states(
                self._session
            )
            interested = self._repository.count_interested_screenings(self._session)
            execution_attention = self._repository.list_attention_executions(
                self._session,
                limit=20,
            )
            candidate_attention = self._repository.list_attention_candidates(
                self._session,
                limit=20,
            )
            recent = self._repository.list_recent_screenings(self._session, limit=10)

        needs_attention = self._merge_attention(execution_attention, candidate_attention)
        return DashboardOverviewResponse(
            generated_at=datetime.now(UTC),
            jobs=DashboardJobMetrics(
                total=sum(jobs.values()),
                draft=jobs.get("draft", 0),
                ready=jobs.get("ready", 0),
            ),
            candidates=DashboardCandidateMetrics(total=candidates),
            pipeline=DashboardPipelineMetrics(
                reviewing=pipeline.get("reviewing", 0),
                shortlisted=pipeline.get("shortlisted", 0),
                not_selected=pipeline.get("not_selected", 0),
            ),
            screenings=DashboardScreeningMetrics(
                total=screening_total,
                queued=screening_states.get(DashboardScreeningState.QUEUED.value, 0),
                awaiting_result=screening_states.get(
                    DashboardScreeningState.AWAITING_RESULT.value, 0
                ),
                dispatch_failed=screening_states.get(
                    DashboardScreeningState.DISPATCH_FAILED.value, 0
                ),
                submission_unknown=screening_states.get(
                    DashboardScreeningState.SUBMISSION_UNKNOWN.value, 0
                ),
                result_available=screening_states.get(
                    DashboardScreeningState.RESULT_AVAILABLE.value, 0
                ),
                result_unavailable=screening_states.get(
                    DashboardScreeningState.RESULT_UNAVAILABLE.value, 0
                ),
                result_invalid=screening_states.get(
                    DashboardScreeningState.RESULT_INVALID.value, 0
                ),
                interested=interested,
            ),
            needs_attention=needs_attention,
            recent_screenings=[self._summary(row) for row in recent],
        )

    def list_screenings(
        self,
        *,
        job_id: UUID | None,
        state: DashboardScreeningState | None,
        interest: CandidateInterest | None,
        q: str | None,
        limit: int,
        offset: int,
    ) -> DashboardScreeningListResponse:
        """Return a deterministic page and authoritative count under one read transaction."""

        with self._session.begin():
            rows = self._repository.list_screenings(
                self._session,
                job_id=job_id,
                state=state,
                interest=interest,
                q=q,
                limit=limit,
                offset=offset,
            )
            total = self._repository.count_screenings(
                self._session,
                job_id=job_id,
                state=state,
                interest=interest,
                q=q,
            )
        return DashboardScreeningListResponse(
            items=[self._summary(row) for row in rows],
            total=total,
            limit=limit,
            offset=offset,
        )

    def get_screening_detail(self, execution_id: UUID) -> DashboardScreeningDetailResponse:
        """Return one exact historical screening context without provider recovery or fallback."""

        try:
            with self._session.begin():
                context = self._repository.get_screening_context(self._session, execution_id)
                if context is None:
                    raise VoiceCallError("VOICE_CALL_NOT_FOUND", 404)
                questions = self._compose_questions(context)
        except DashboardHistoricalContextError as exc:
            raise self._historical_context_error() from exc
        return DashboardScreeningDetailResponse(
            execution_id=context.execution_id,
            outreach_request_id=context.outreach_request_id,
            job_candidate_id=context.job_candidate_id,
            candidate_id=context.candidate_id,
            candidate_name=context.candidate_name,
            job_id=context.job_id,
            job_title=context.job_title,
            job_definition_version=context.job_definition_version,
            screening_state=DashboardScreeningState(context.screening_state),
            submission_status=VoiceCallExecutionStatus(context.submission_status),
            provider_status=(
                HunarCallStatus(context.provider_status)
                if context.provider_status is not None
                else None
            ),
            lifecycle_status=(
                HunarLifecycleStatus(context.lifecycle_status)
                if context.lifecycle_status is not None
                else None
            ),
            answered_by=(
                HunarAnsweredBy(context.answered_by) if context.answered_by is not None else None
            ),
            conversation_outcome=(
                ConversationOutcome(context.conversation_outcome)
                if context.conversation_outcome is not None
                else None
            ),
            candidate_interest=(
                CandidateInterest(context.candidate_interest)
                if context.candidate_interest is not None
                else None
            ),
            duration_seconds=context.duration_seconds,
            observed_at=context.observed_at,
            recording_available=context.recording_available,
            notes=context.notes,
            questions=questions,
        )

    def _compose_questions(
        self,
        context: DashboardScreeningContextRecord,
    ) -> list[DashboardQuestionAnswer]:
        """Map exact frozen outreach UUIDs to accepted Module 7 rows without inventing answers."""

        try:
            frozen_questions = [
                OutreachScreeningQuestion.model_validate(value)
                for value in context.screening_questions_snapshot
            ]
        except ValidationError as exc:
            raise DashboardHistoricalContextError(
                "Frozen screening-question snapshot cannot be validated"
            ) from exc

        question_positions = {
            question.id: position for position, question in enumerate(frozen_questions, start=1)
        }
        if len(question_positions) != len(frozen_questions):
            raise DashboardHistoricalContextError("Frozen screening-question UUIDs are not unique")

        answers_by_question: dict[UUID, DashboardScreeningAnswerRecord] = {}
        if self._human_answers_may_display(context):
            if context.result_id is None:
                raise DashboardHistoricalContextError(
                    "Available human screening result is missing its result identity"
                )
            answers = self._repository.list_screening_answers(self._session, context.result_id)
            for stored_answer in answers:
                expected_position = question_positions.get(stored_answer.outreach_question_id)
                if expected_position is None or expected_position != stored_answer.position:
                    raise DashboardHistoricalContextError(
                        "Accepted answer identity does not match the frozen outreach question"
                    )
                if stored_answer.outreach_question_id in answers_by_question:
                    raise DashboardHistoricalContextError("Accepted answer UUIDs are not unique")
                answers_by_question[stored_answer.outreach_question_id] = stored_answer

        output: list[DashboardQuestionAnswer] = []
        for position, question in enumerate(frozen_questions, start=1):
            answer = answers_by_question.get(question.id)
            output.append(
                DashboardQuestionAnswer(
                    question_id=question.id,
                    position=position,
                    prompt=question.prompt,
                    answer_state=(
                        ScreeningAnswerState(answer.answer_state) if answer is not None else None
                    ),
                    answer_text=answer.answer_text if answer is not None else None,
                )
            )
        return output

    @staticmethod
    def _human_answers_may_display(context: DashboardScreeningContextRecord) -> bool:
        """Enforce the exact Module 7 HUMAN/available/completed safety gate."""

        return (
            context.screening_state == DashboardScreeningState.RESULT_AVAILABLE.value
            and context.lifecycle_status == "COMPLETED"
            and context.answered_by == "HUMAN"
        )

    @staticmethod
    def _summary(row: DashboardScreeningRecord) -> DashboardScreeningSummary:
        """Convert an internal row to the only recruiter-safe screening-list projection."""

        return DashboardScreeningSummary(
            execution_id=row.execution_id,
            outreach_request_id=row.outreach_request_id,
            job_candidate_id=row.job_candidate_id,
            candidate_id=row.candidate_id,
            candidate_name=row.candidate_name,
            job_id=row.job_id,
            job_title=row.job_title,
            job_definition_version=row.job_definition_version,
            screening_state=DashboardScreeningState(row.screening_state),
            submission_status=VoiceCallExecutionStatus(row.submission_status),
            conversation_outcome=(
                ConversationOutcome(row.conversation_outcome)
                if row.conversation_outcome is not None
                else None
            ),
            candidate_interest=(
                CandidateInterest(row.candidate_interest)
                if row.candidate_interest is not None
                else None
            ),
            duration_seconds=row.duration_seconds,
            observed_at=row.observed_at,
            sort_at=row.sort_at,
        )

    @staticmethod
    def _merge_attention(
        execution_rows: list[DashboardAttentionRecord],
        candidate_rows: list[DashboardAttentionRecord],
    ) -> list[DashboardAttentionItem]:
        """Apply frozen category priority, newest-first order, stable UUID tie-break, and cap 20."""

        rows = [*execution_rows, *candidate_rows]
        rows.sort(
            key=lambda row: (
                _ATTENTION_PRIORITY[row.kind],
                -row.occurred_at.timestamp(),
                str(row.execution_id or row.job_candidate_id),
            )
        )
        return [
            DashboardAttentionItem(
                kind=DashboardAttentionKind(row.kind),
                candidate_id=row.candidate_id,
                candidate_name=row.candidate_name,
                job_id=row.job_id,
                job_candidate_id=row.job_candidate_id,
                job_title=row.job_title,
                execution_id=row.execution_id,
                outreach_request_id=row.outreach_request_id,
                occurred_at=row.occurred_at,
            )
            for row in rows[:20]
        ]

    @staticmethod
    def _historical_context_error() -> AppError:
        """Return the bounded fail-closed error for corrupt immutable screening history."""

        return AppError(
            status_code=409,
            code="DASHBOARD_HISTORICAL_CONTEXT_INVALID",
            message="Screening historical context is inconsistent.",
        )
