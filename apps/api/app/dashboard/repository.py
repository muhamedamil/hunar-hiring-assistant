"""Read-only SQL composition for Module 8 recruiter dashboard projections."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, cast
from uuid import UUID

from sqlalchemy import ColumnElement, case, func, literal, or_, select
from sqlalchemy.engine import RowMapping
from sqlalchemy.orm import Session

from app.call_results.models import VoiceCallResult, VoiceScreeningAnswer
from app.call_results.schemas import CandidateInterest
from app.candidates.models import Candidate
from app.dashboard.schemas import DashboardScreeningState
from app.jobs.models import Job, JobDefinitionVersion
from app.matching.models import JobCandidate, JobCandidateMatch
from app.outreach.models import OutreachRequest
from app.voice_calls.models import VoiceCallExecution


class DashboardHistoricalContextError(RuntimeError):
    """Signal that an execution exists but its required immutable context cannot be resolved."""


@dataclass(frozen=True)
class DashboardScreeningRecord:
    """Internal read row for one voice execution and its frozen recruiter context."""

    execution_id: UUID
    outreach_request_id: UUID
    job_candidate_id: UUID
    candidate_id: UUID
    candidate_name: str
    job_id: UUID
    job_title: str
    job_definition_version: int
    screening_state: str
    submission_status: str
    conversation_outcome: str | None
    candidate_interest: str | None
    duration_seconds: float | None
    observed_at: datetime | None
    sort_at: datetime


@dataclass(frozen=True)
class DashboardScreeningContextRecord(DashboardScreeningRecord):
    """Internal detail row including only safe terminal fields and frozen question JSON."""

    result_id: UUID | None
    provider_status: str | None
    lifecycle_status: str | None
    answered_by: str | None
    recording_available: bool
    notes: str | None
    screening_questions_snapshot: list[dict[str, Any]]


@dataclass(frozen=True)
class DashboardScreeningAnswerRecord:
    """Internal immutable Module 7 answer identity and display state."""

    outreach_question_id: UUID
    position: int
    answer_state: str
    answer_text: str | None


@dataclass(frozen=True)
class DashboardOutreachProjectionRecord:
    """Historical Job context plus optional execution/result display state for Outreach UX."""

    job_id: UUID
    job_title: str
    job_definition_version: int
    execution_id: UUID | None
    screening_state: str | None
    submission_status: str | None


@dataclass(frozen=True)
class DashboardAttentionRecord:
    """Internal attention row projected from an existing authoritative owner."""

    kind: str
    candidate_id: UUID
    candidate_name: str
    job_id: UUID
    job_candidate_id: UUID
    job_title: str
    execution_id: UUID | None
    outreach_request_id: UUID | None
    occurred_at: datetime


def dashboard_screening_state_expression() -> ColumnElement[str]:
    """Return the single result-first display-state expression used by every screening query."""

    return cast(
        ColumnElement[str],
        case(
            (
                VoiceCallResult.screening_result_state == "available",
                literal(DashboardScreeningState.RESULT_AVAILABLE.value),
            ),
            (
                VoiceCallResult.screening_result_state == "unavailable",
                literal(DashboardScreeningState.RESULT_UNAVAILABLE.value),
            ),
            (
                VoiceCallResult.screening_result_state == "invalid",
                literal(DashboardScreeningState.RESULT_INVALID.value),
            ),
            (
                VoiceCallExecution.status == "queued",
                literal(DashboardScreeningState.QUEUED.value),
            ),
            (
                VoiceCallExecution.status == "submitted",
                literal(DashboardScreeningState.AWAITING_RESULT.value),
            ),
            (
                VoiceCallExecution.status == "failed",
                literal(DashboardScreeningState.DISPATCH_FAILED.value),
            ),
            else_=literal(DashboardScreeningState.SUBMISSION_UNKNOWN.value),
        ),
    )


def dashboard_sort_at_expression() -> ColumnElement[datetime]:
    """Return the frozen deterministic activity-time expression for screening ordering."""

    return cast(
        ColumnElement[datetime],
        func.coalesce(VoiceCallResult.observed_at, VoiceCallExecution.updated_at),
    )


def _escape_like(value: str) -> str:
    """Escape LIKE wildcards so dashboard search is a literal case-insensitive substring query."""

    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


class DashboardRepository:
    """Compose read-efficient Module 8 SQL without transactions, commits, or external calls."""

    def count_jobs_by_status(self, session: Session) -> dict[str, int]:
        """Count current Jobs by authoritative status."""

        statement = select(Job.status, func.count(Job.id)).group_by(Job.status)
        return {str(status): int(count) for status, count in session.execute(statement).all()}

    def count_candidates(self, session: Session) -> int:
        """Count canonical Candidates directly from Candidate Core."""

        return int(session.execute(select(func.count(Candidate.id))).scalar_one())

    def count_job_candidates_by_shortlist_status(self, session: Session) -> dict[str, int]:
        """Count JobCandidate pipeline units by recruiter-owned shortlist status."""

        statement = select(JobCandidate.shortlist_status, func.count(JobCandidate.id)).group_by(
            JobCandidate.shortlist_status
        )
        return {str(status): int(count) for status, count in session.execute(statement).all()}

    def count_screening_states(self, session: Session) -> tuple[int, dict[str, int]]:
        """Count the seven mutually exclusive display states over all voice executions."""

        state = dashboard_screening_state_expression()
        statement = (
            select(state.label("screening_state"), func.count(VoiceCallExecution.id))
            .select_from(VoiceCallExecution)
            .outerjoin(
                VoiceCallResult,
                VoiceCallResult.voice_call_execution_id == VoiceCallExecution.id,
            )
            .group_by(state)
        )
        counts = {
            str(screening_state): int(count)
            for screening_state, count in session.execute(statement).all()
        }
        return sum(counts.values()), counts

    def count_interested_screenings(self, session: Session) -> int:
        """Count interested available results independently from mutually-exclusive states."""

        statement = select(func.count(VoiceCallResult.id)).where(
            VoiceCallResult.screening_result_state == "available",
            VoiceCallResult.candidate_interest == CandidateInterest.INTERESTED.value,
        )
        return int(session.execute(statement).scalar_one())

    def list_attention_candidates(
        self,
        session: Session,
        *,
        limit: int,
    ) -> list[DashboardAttentionRecord]:
        """Return current JobCandidate review items using current Job/Candidate display truth."""

        statement = (
            select(
                Candidate.id.label("candidate_id"),
                Candidate.full_name.label("candidate_name"),
                Job.id.label("job_id"),
                JobCandidate.id.label("job_candidate_id"),
                Job.title.label("job_title"),
                JobCandidate.updated_at.label("occurred_at"),
            )
            .select_from(JobCandidate)
            .join(Candidate, Candidate.id == JobCandidate.candidate_id)
            .join(Job, Job.id == JobCandidate.job_id)
            .where(JobCandidate.shortlist_status == "reviewing")
            .order_by(JobCandidate.updated_at.desc(), JobCandidate.id.desc())
            .limit(limit)
        )
        return [
            DashboardAttentionRecord(
                kind="review_candidate",
                candidate_id=row.candidate_id,
                candidate_name=row.candidate_name,
                job_id=row.job_id,
                job_candidate_id=row.job_candidate_id,
                job_title=row.job_title,
                execution_id=None,
                outreach_request_id=None,
                occurred_at=row.occurred_at,
            )
            for row in session.execute(statement).mappings().all()
        ]

    def list_attention_executions(
        self,
        session: Session,
        *,
        limit: int,
    ) -> list[DashboardAttentionRecord]:
        """Return result/submission attention using the canonical screening-state expression."""

        state = dashboard_screening_state_expression()
        sort_at = dashboard_sort_at_expression()
        attention_states = {
            DashboardScreeningState.SUBMISSION_UNKNOWN.value,
            DashboardScreeningState.DISPATCH_FAILED.value,
            DashboardScreeningState.RESULT_INVALID.value,
            DashboardScreeningState.RESULT_UNAVAILABLE.value,
        }
        priority = case(
            (state == DashboardScreeningState.SUBMISSION_UNKNOWN.value, 0),
            (state == DashboardScreeningState.DISPATCH_FAILED.value, 1),
            (state == DashboardScreeningState.RESULT_INVALID.value, 2),
            (state == DashboardScreeningState.RESULT_UNAVAILABLE.value, 3),
            else_=4,
        )
        statement = (
            self._screening_select(include_detail=False)
            .where(state.in_(attention_states))
            .order_by(priority, sort_at.desc(), VoiceCallExecution.id.desc())
            .limit(limit)
        )
        records = self._screening_records(session, statement)
        kind_by_state = {
            DashboardScreeningState.SUBMISSION_UNKNOWN.value: "submission_unknown",
            DashboardScreeningState.DISPATCH_FAILED.value: "dispatch_failed",
            DashboardScreeningState.RESULT_INVALID.value: "result_invalid",
            DashboardScreeningState.RESULT_UNAVAILABLE.value: "result_unavailable",
        }
        return [
            DashboardAttentionRecord(
                kind=kind_by_state[row.screening_state],
                candidate_id=row.candidate_id,
                candidate_name=row.candidate_name,
                job_id=row.job_id,
                job_candidate_id=row.job_candidate_id,
                job_title=row.job_title,
                execution_id=row.execution_id,
                outreach_request_id=row.outreach_request_id,
                occurred_at=row.sort_at,
            )
            for row in records
        ]

    def list_recent_screenings(
        self,
        session: Session,
        *,
        limit: int,
    ) -> list[DashboardScreeningRecord]:
        """Return the latest voice executions under the frozen shared activity ordering."""

        statement = self._screening_select(include_detail=False).order_by(
            dashboard_sort_at_expression().desc(), VoiceCallExecution.id.desc()
        ).limit(limit)
        return self._screening_records(session, statement)

    def list_screenings(
        self,
        session: Session,
        *,
        job_id: UUID | None,
        state: DashboardScreeningState | None,
        interest: CandidateInterest | None,
        q: str | None,
        limit: int,
        offset: int,
    ) -> list[DashboardScreeningRecord]:
        """Return one execution row per screening with frozen history and server paging."""

        statement = self._apply_screening_filters(
            self._screening_select(include_detail=False),
            job_id=job_id,
            state=state,
            interest=interest,
            q=q,
        )
        statement = statement.order_by(
            dashboard_sort_at_expression().desc(), VoiceCallExecution.id.desc()
        ).limit(limit).offset(offset)
        return self._screening_records(session, statement)

    def count_screenings(
        self,
        session: Session,
        *,
        job_id: UUID | None,
        state: DashboardScreeningState | None,
        interest: CandidateInterest | None,
        q: str | None,
    ) -> int:
        """Count screenings with exactly the same filter predicates as the paginated item query."""

        statement = self._apply_screening_filters(
            self._screening_identity_select(),
            job_id=job_id,
            state=state,
            interest=interest,
            q=q,
        )
        count_statement = select(func.count()).select_from(statement.subquery())
        return int(session.execute(count_statement).scalar_one())

    def get_screening_context(
        self,
        session: Session,
        execution_id: UUID,
    ) -> DashboardScreeningContextRecord | None:
        """Return one exact historical context, distinguishing absence from broken history."""

        exists = session.execute(
            select(VoiceCallExecution.id).where(VoiceCallExecution.id == execution_id)
        ).scalar_one_or_none()
        if exists is None:
            return None
        statement = self._screening_select(include_detail=True).where(
            VoiceCallExecution.id == execution_id
        )
        row = session.execute(statement).mappings().one_or_none()
        if row is None:
            raise DashboardHistoricalContextError(
                "Voice execution exists but required immutable historical context is missing"
            )
        return self._mapping_to_context_record(row)

    def get_outreach_projection(
        self,
        session: Session,
        outreach_request_id: UUID,
    ) -> DashboardOutreachProjectionRecord | None:
        """Return exact historical Job context and optional canonical screening state."""

        state = dashboard_screening_state_expression()
        statement = (
            select(
                JobCandidateMatch.job_id.label("job_id"),
                JobDefinitionVersion.title.label("job_title"),
                JobCandidateMatch.definition_version.label("job_definition_version"),
                VoiceCallExecution.id.label("execution_id"),
                state.label("screening_state"),
                VoiceCallExecution.status.label("submission_status"),
            )
            .select_from(OutreachRequest)
            .join(JobCandidate, JobCandidate.id == OutreachRequest.job_candidate_id)
            .join(
                JobCandidateMatch,
                (JobCandidateMatch.id == OutreachRequest.decision_match_id)
                & (JobCandidateMatch.job_candidate_id == OutreachRequest.job_candidate_id)
                & (JobCandidateMatch.job_id == JobCandidate.job_id)
                & (JobCandidateMatch.candidate_id == JobCandidate.candidate_id),
            )
            .join(
                JobDefinitionVersion,
                (JobDefinitionVersion.job_id == JobCandidateMatch.job_id)
                & (JobDefinitionVersion.version == JobCandidateMatch.definition_version),
            )
            .outerjoin(
                VoiceCallExecution,
                VoiceCallExecution.outreach_request_id == OutreachRequest.id,
            )
            .outerjoin(
                VoiceCallResult,
                VoiceCallResult.voice_call_execution_id == VoiceCallExecution.id,
            )
            .where(OutreachRequest.id == outreach_request_id)
        )
        row = session.execute(statement).mappings().one_or_none()
        if row is None:
            return None
        has_execution = row.execution_id is not None
        return DashboardOutreachProjectionRecord(
            job_id=row.job_id,
            job_title=row.job_title,
            job_definition_version=row.job_definition_version,
            execution_id=row.execution_id,
            screening_state=str(row.screening_state) if has_execution else None,
            submission_status=str(row.submission_status) if has_execution else None,
        )

    def list_screening_answers(
        self,
        session: Session,
        result_id: UUID,
    ) -> list[DashboardScreeningAnswerRecord]:
        """Load immutable accepted answer rows for exactly one terminal result."""

        statement = (
            select(
                VoiceScreeningAnswer.outreach_question_id,
                VoiceScreeningAnswer.position,
                VoiceScreeningAnswer.answer_state,
                VoiceScreeningAnswer.answer_text,
            )
            .where(VoiceScreeningAnswer.voice_call_result_id == result_id)
            .order_by(VoiceScreeningAnswer.position.asc())
        )
        return [
            DashboardScreeningAnswerRecord(
                outreach_question_id=row.outreach_question_id,
                position=row.position,
                answer_state=row.answer_state,
                answer_text=row.answer_text,
            )
            for row in session.execute(statement).mappings().all()
        ]

    @staticmethod
    def _historical_joins(statement: Any) -> Any:
        """Apply the exact execution→outreach→match→immutable-definition join once."""

        return (
            statement.select_from(VoiceCallExecution)
            .join(OutreachRequest, OutreachRequest.id == VoiceCallExecution.outreach_request_id)
            .join(JobCandidate, JobCandidate.id == OutreachRequest.job_candidate_id)
            .join(Candidate, Candidate.id == JobCandidate.candidate_id)
            .join(
                JobCandidateMatch,
                (JobCandidateMatch.id == OutreachRequest.decision_match_id)
                & (JobCandidateMatch.job_candidate_id == OutreachRequest.job_candidate_id)
                & (JobCandidateMatch.job_id == JobCandidate.job_id)
                & (JobCandidateMatch.candidate_id == JobCandidate.candidate_id),
            )
            .join(
                JobDefinitionVersion,
                (JobDefinitionVersion.job_id == JobCandidateMatch.job_id)
                & (JobDefinitionVersion.version == JobCandidateMatch.definition_version),
            )
            .outerjoin(
                VoiceCallResult,
                VoiceCallResult.voice_call_execution_id == VoiceCallExecution.id,
            )
        )

    def _screening_select(self, *, include_detail: bool) -> Any:
        """Build the shared recruiter-safe screening select without answer-row multiplication."""

        state = dashboard_screening_state_expression()
        sort_at = dashboard_sort_at_expression()
        columns: list[Any] = [
            VoiceCallExecution.id.label("execution_id"),
            VoiceCallExecution.outreach_request_id.label("outreach_request_id"),
            OutreachRequest.job_candidate_id.label("job_candidate_id"),
            Candidate.id.label("candidate_id"),
            Candidate.full_name.label("candidate_name"),
            JobCandidateMatch.job_id.label("job_id"),
            JobDefinitionVersion.title.label("job_title"),
            JobDefinitionVersion.version.label("job_definition_version"),
            state.label("screening_state"),
            VoiceCallExecution.status.label("submission_status"),
            VoiceCallResult.conversation_outcome.label("conversation_outcome"),
            VoiceCallResult.candidate_interest.label("candidate_interest"),
            VoiceCallResult.duration_seconds.label("duration_seconds"),
            VoiceCallResult.observed_at.label("observed_at"),
            sort_at.label("sort_at"),
        ]
        if include_detail:
            columns.extend(
                [
                    VoiceCallResult.id.label("result_id"),
                    VoiceCallResult.provider_status.label("provider_status"),
                    VoiceCallResult.lifecycle_status.label("lifecycle_status"),
                    VoiceCallResult.answered_by.label("answered_by"),
                    VoiceCallResult.recording_url.is_not(None).label("recording_available"),
                    VoiceCallResult.notes.label("notes"),
                    OutreachRequest.screening_questions_snapshot.label(
                        "screening_questions_snapshot"
                    ),
                ]
            )
        return self._historical_joins(select(*columns))

    def _screening_identity_select(self) -> Any:
        """Build the same historical join as list rows while selecting only execution identity."""

        return self._historical_joins(select(VoiceCallExecution.id.label("execution_id")))

    @staticmethod
    def _apply_screening_filters(
        statement: Any,
        *,
        job_id: UUID | None,
        state: DashboardScreeningState | None,
        interest: CandidateInterest | None,
        q: str | None,
    ) -> Any:
        """Apply the canonical list/count predicates so pagination totals cannot drift."""

        if job_id is not None:
            statement = statement.where(JobCandidateMatch.job_id == job_id)
        if state is not None:
            statement = statement.where(dashboard_screening_state_expression() == state.value)
        if interest is not None:
            statement = statement.where(VoiceCallResult.candidate_interest == interest.value)
        if q is not None:
            escaped = _escape_like(q)
            pattern = f"%{escaped}%"
            statement = statement.where(
                or_(
                    Candidate.full_name.ilike(pattern, escape="\\"),
                    JobDefinitionVersion.title.ilike(pattern, escape="\\"),
                )
            )
        return statement

    @staticmethod
    def _screening_records(session: Session, statement: Any) -> list[DashboardScreeningRecord]:
        """Convert SQL row mappings to stable internal screening records."""

        return [
            DashboardRepository._mapping_to_screening_record(row)
            for row in session.execute(statement).mappings().all()
        ]

    @staticmethod
    def _mapping_to_screening_record(row: RowMapping) -> DashboardScreeningRecord:
        """Project one mapping without leaking any selected-but-unsafe provider field."""

        return DashboardScreeningRecord(
            execution_id=cast(UUID, row["execution_id"]),
            outreach_request_id=cast(UUID, row["outreach_request_id"]),
            job_candidate_id=cast(UUID, row["job_candidate_id"]),
            candidate_id=cast(UUID, row["candidate_id"]),
            candidate_name=str(row["candidate_name"]),
            job_id=cast(UUID, row["job_id"]),
            job_title=str(row["job_title"]),
            job_definition_version=int(row["job_definition_version"]),
            screening_state=str(row["screening_state"]),
            submission_status=str(row["submission_status"]),
            conversation_outcome=(
                str(row["conversation_outcome"])
                if row["conversation_outcome"] is not None
                else None
            ),
            candidate_interest=(
                str(row["candidate_interest"]) if row["candidate_interest"] is not None else None
            ),
            duration_seconds=(
                float(row["duration_seconds"]) if row["duration_seconds"] is not None else None
            ),
            observed_at=cast(datetime | None, row["observed_at"]),
            sort_at=cast(datetime, row["sort_at"]),
        )

    @staticmethod
    def _mapping_to_context_record(row: RowMapping) -> DashboardScreeningContextRecord:
        """Project one detail mapping, retaining only the boolean recording availability signal."""

        summary = DashboardRepository._mapping_to_screening_record(row)
        snapshot = row["screening_questions_snapshot"]
        if not isinstance(snapshot, list):
            raise DashboardHistoricalContextError("Frozen screening-question snapshot is invalid")
        return DashboardScreeningContextRecord(
            **summary.__dict__,
            result_id=cast(UUID | None, row["result_id"]),
            provider_status=(
                str(row["provider_status"]) if row["provider_status"] is not None else None
            ),
            lifecycle_status=(
                str(row["lifecycle_status"]) if row["lifecycle_status"] is not None else None
            ),
            answered_by=str(row["answered_by"]) if row["answered_by"] is not None else None,
            recording_available=bool(row["recording_available"]),
            notes=str(row["notes"]) if row["notes"] is not None else None,
            screening_questions_snapshot=cast(list[dict[str, Any]], snapshot),
        )
