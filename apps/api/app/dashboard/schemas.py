"""Typed, recruiter-safe Module 8 dashboard read contracts."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Annotated
from uuid import UUID

from pydantic import AfterValidator, BaseModel, ConfigDict, Field

from app.call_results.schemas import (
    CandidateInterest,
    ConversationOutcome,
    ScreeningAnswerState,
)
from app.integrations.hunar.schemas import HunarAnsweredBy, HunarCallStatus, HunarLifecycleStatus
from app.voice_calls.schemas import VoiceCallExecutionStatus


class DashboardAttentionKind(StrEnum):
    """Derived recruiter attention categories; these values are never persisted."""

    REVIEW_CANDIDATE = "review_candidate"
    DISPATCH_FAILED = "dispatch_failed"
    SUBMISSION_UNKNOWN = "submission_unknown"
    RESULT_INVALID = "result_invalid"
    RESULT_UNAVAILABLE = "result_unavailable"


class DashboardScreeningState(StrEnum):
    """Result-first display projection independent of Module 6 submission certainty."""

    QUEUED = "queued"
    AWAITING_RESULT = "awaiting_result"
    DISPATCH_FAILED = "dispatch_failed"
    SUBMISSION_UNKNOWN = "submission_unknown"
    RESULT_AVAILABLE = "result_available"
    RESULT_UNAVAILABLE = "result_unavailable"
    RESULT_INVALID = "result_invalid"


def _normalize_search_query(value: str) -> str:
    """Trim a supplied search value and enforce the frozen 1..100-character contract."""

    normalized = value.strip()
    if not normalized:
        raise ValueError("Search query must contain at least one non-whitespace character")
    if len(normalized) > 100:
        raise ValueError("Search query must contain at most 100 characters after trimming")
    return normalized


DashboardSearchQuery = Annotated[str, AfterValidator(_normalize_search_query)]


class DashboardJobMetrics(BaseModel):
    """Authoritative current Job counts."""

    model_config = ConfigDict(extra="forbid")
    total: int = Field(ge=0)
    draft: int = Field(ge=0)
    ready: int = Field(ge=0)


class DashboardCandidateMetrics(BaseModel):
    """Authoritative canonical Candidate count."""

    model_config = ConfigDict(extra="forbid")
    total: int = Field(ge=0)


class DashboardPipelineMetrics(BaseModel):
    """Authoritative JobCandidate-scoped recruiter workflow counts."""

    model_config = ConfigDict(extra="forbid")
    reviewing: int = Field(ge=0)
    shortlisted: int = Field(ge=0)
    not_selected: int = Field(ge=0)


class DashboardScreeningMetrics(BaseModel):
    """Execution-based screening counts plus the independent interested subset metric."""

    model_config = ConfigDict(extra="forbid")
    total: int = Field(ge=0)
    queued: int = Field(ge=0)
    awaiting_result: int = Field(ge=0)
    dispatch_failed: int = Field(ge=0)
    submission_unknown: int = Field(ge=0)
    result_available: int = Field(ge=0)
    result_unavailable: int = Field(ge=0)
    result_invalid: int = Field(ge=0)
    interested: int = Field(ge=0)


class DashboardAttentionItem(BaseModel):
    """One bounded derived attention item pointing back to an existing workflow authority."""

    model_config = ConfigDict(extra="forbid")
    kind: DashboardAttentionKind
    candidate_id: UUID
    candidate_name: str
    job_id: UUID
    job_candidate_id: UUID
    job_title: str
    execution_id: UUID | None = None
    outreach_request_id: UUID | None = None
    occurred_at: datetime


class DashboardScreeningSummary(BaseModel):
    """Recruiter-safe execution row with immutable historical Job context."""

    model_config = ConfigDict(extra="forbid")
    execution_id: UUID
    outreach_request_id: UUID
    job_candidate_id: UUID
    candidate_id: UUID
    candidate_name: str
    job_id: UUID
    job_title: str
    job_definition_version: int = Field(ge=1)
    screening_state: DashboardScreeningState
    submission_status: VoiceCallExecutionStatus
    conversation_outcome: ConversationOutcome | None = None
    candidate_interest: CandidateInterest | None = None
    duration_seconds: float | None = Field(default=None, ge=0)
    observed_at: datetime | None = None
    sort_at: datetime


class DashboardScreeningListResponse(BaseModel):
    """Server-paginated screening list whose total comes from an authoritative count query."""

    model_config = ConfigDict(extra="forbid")
    items: list[DashboardScreeningSummary]
    total: int = Field(ge=0)
    limit: int = Field(ge=1, le=100)
    offset: int = Field(ge=0)


class DashboardQuestionAnswer(BaseModel):
    """Frozen outreach question with an optional authoritative Module 7 answer state."""

    model_config = ConfigDict(extra="forbid")
    question_id: UUID
    position: int = Field(ge=1, le=10)
    prompt: str = Field(min_length=1, max_length=500)
    answer_state: ScreeningAnswerState | None = None
    answer_text: str | None = None


class DashboardScreeningDetailResponse(BaseModel):
    """Safe historical screening detail without provider identifiers, PII, or raw recording URL."""

    model_config = ConfigDict(extra="forbid")
    execution_id: UUID
    outreach_request_id: UUID
    job_candidate_id: UUID
    candidate_id: UUID
    candidate_name: str
    job_id: UUID
    job_title: str
    job_definition_version: int = Field(ge=1)
    screening_state: DashboardScreeningState
    submission_status: VoiceCallExecutionStatus
    provider_status: HunarCallStatus | None = None
    lifecycle_status: HunarLifecycleStatus | None = None
    answered_by: HunarAnsweredBy | None = None
    conversation_outcome: ConversationOutcome | None = None
    candidate_interest: CandidateInterest | None = None
    duration_seconds: float | None = Field(default=None, ge=0)
    observed_at: datetime | None = None
    recording_available: bool
    notes: str | None = None
    questions: list[DashboardQuestionAnswer]


class DashboardOverviewResponse(BaseModel):
    """Authoritative database metrics plus bounded operational recruiter projections."""

    model_config = ConfigDict(extra="forbid")
    generated_at: datetime
    jobs: DashboardJobMetrics
    candidates: DashboardCandidateMetrics
    pipeline: DashboardPipelineMetrics
    screenings: DashboardScreeningMetrics
    needs_attention: list[DashboardAttentionItem]
    recent_screenings: list[DashboardScreeningSummary]
