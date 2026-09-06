"""Typed contracts for Candidate↔Job matching, evidence, and recruiter shortlisting."""

from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.candidates.schemas import CandidateSummaryResponse
from app.jobs.schemas import EmploymentType, SeniorityLevel, WorkArrangement


class JobCandidateSource(StrEnum):
    """Origin that first created the stable Candidate↔Job relationship."""

    MANUAL = "manual"
    SOURCING = "sourcing"


class ShortlistStatus(StrEnum):
    """Recruiter-owned workflow state for one Candidate↔Job relationship."""

    REVIEWING = "reviewing"
    SHORTLISTED = "shortlisted"
    NOT_SELECTED = "not_selected"


class MatchStatus(StrEnum):
    """Lifecycle of one immutable match evaluation attempt."""

    ANALYZING = "analyzing"
    COMPLETED = "completed"
    FAILED = "failed"


class MatchAnalysisMode(StrEnum):
    """How the completed match evaluation was produced."""

    DETERMINISTIC = "deterministic"
    HYBRID_GEMINI = "hybrid_gemini"
    DETERMINISTIC_FALLBACK = "deterministic_fallback"


class MatchCriterionStatus(StrEnum):
    """Evidence-grounded state for one configured Job criterion."""

    SUPPORTED = "supported"
    CONTRADICTED = "contradicted"
    UNKNOWN = "unknown"


class CallReadiness(StrEnum):
    """Whether current Candidate truth contains a callable canonical phone number."""

    READY = "ready"
    NOT_READY = "not_ready"


class MatchProfessionalExperience(BaseModel):
    """Normalized professional-title evidence copied from Module 3 read contracts."""

    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(default=None, max_length=200)
    started_at: date | None = None
    is_current: bool | None = None


class MatchProfessionalEvidence(BaseModel):
    """Professional evidence subset that Module 4 is explicitly allowed to consume."""

    model_config = ConfigDict(extra="forbid")

    current_title: str | None = Field(default=None, max_length=200)
    location: str | None = Field(default=None, max_length=200)
    employment_history: list[MatchProfessionalExperience] = Field(
        default_factory=list,
        max_length=100,
    )


class MatchInputSnapshot(BaseModel):
    """Canonical, hashable match input captured before any external semantic analysis."""

    model_config = ConfigDict(extra="forbid")

    job_id: UUID
    definition_version: int = Field(ge=1)
    job_title: str = Field(min_length=1, max_length=200)
    alternate_titles: list[str] = Field(default_factory=list, max_length=5)
    locations: list[str] = Field(default_factory=list, max_length=10)
    seniority: list[SeniorityLevel] = Field(default_factory=list, max_length=5)
    required_skills: list[str] = Field(default_factory=list, max_length=20)
    preferred_skills: list[str] = Field(default_factory=list, max_length=20)
    min_years_experience: int | None = Field(default=None, ge=0, le=50)
    employment_type: EmploymentType | None = None
    work_arrangement: WorkArrangement | None = None

    candidate_id: UUID
    candidate_current_title: str | None = Field(default=None, max_length=200)
    candidate_location: str | None = Field(default=None, max_length=200)

    source_sourcing_result_id: UUID | None = None
    source_sourcing_run_id: UUID | None = None
    source_definition_version: int | None = Field(default=None, ge=1)
    source_evidence_version: str | None = Field(default=None, max_length=80)
    professional_evidence: MatchProfessionalEvidence | None = None


class MatchCriterion(BaseModel):
    """One weighted evidence result contributing to deterministic Module 4 scoring."""

    model_config = ConfigDict(extra="forbid")

    key: str = Field(min_length=1, max_length=120)
    label: str = Field(min_length=1, max_length=200)
    category: str = Field(min_length=1, max_length=80)
    weight: int = Field(ge=1, le=10)
    status: MatchCriterionStatus
    reason: str = Field(min_length=1, max_length=500)
    evidence_ids: list[str] = Field(default_factory=list, max_length=20)


class SemanticEvidenceItem(BaseModel):
    """Explicit title evidence item made available to the constrained semantic provider."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=40)
    title: str = Field(min_length=1, max_length=200)
    source: Literal["candidate_current_title", "professional_current_title", "employment_history"]
    started_at: date | None = None
    is_current: bool | None = None


class SemanticCriterionVerdict(BaseModel):
    """Provider classification for one semantic criterion without any numeric score."""

    model_config = ConfigDict(extra="forbid")

    status: MatchCriterionStatus
    evidence_ids: list[str] = Field(default_factory=list, max_length=20)
    reason: str = Field(min_length=1, max_length=500)


class SemanticMatchOutput(BaseModel):
    """Strict Gemini output limited to role and seniority evidence classification."""

    model_config = ConfigDict(extra="forbid")

    role_alignment: SemanticCriterionVerdict
    seniority_alignment: SemanticCriterionVerdict


class AddJobCandidateRequest(BaseModel):
    """Recruiter command for attaching an existing canonical Candidate to a Job."""

    model_config = ConfigDict(extra="forbid")

    candidate_id: UUID


class ShortlistUpdateRequest(BaseModel):
    """Revision-protected recruiter shortlist decision command."""

    model_config = ConfigDict(extra="forbid")

    expected_revision: int = Field(ge=0)
    status: ShortlistStatus


class MatchFreshness(BaseModel):
    """Currentness of one match relative to live Job, Candidate, evidence, and policy truth."""

    model_config = ConfigDict(extra="forbid")

    is_fresh: bool
    stale_reasons: list[str]


class MatchEvaluationResponse(BaseModel):
    """Recruiter-facing immutable match assessment and its evidence limits."""

    model_config = ConfigDict(extra="forbid")

    id: UUID
    job_candidate_id: UUID
    definition_version: int
    source_sourcing_result_id: UUID | None
    source_sourcing_run_id: UUID | None
    source_definition_version: int | None
    source_evidence_version: str | None
    candidate_revision: int
    matcher_version: str
    analysis_mode: MatchAnalysisMode
    status: MatchStatus
    semantic_model: str | None
    semantic_prompt_version: str | None
    semantic_failure_code: str | None
    retry_after_seconds: int | None
    match_score: int | None
    evidence_coverage: int | None
    match_reasons: list[MatchCriterion]
    started_at: datetime
    completed_at: datetime | None
    created_at: datetime


class JobCandidateSummaryResponse(BaseModel):
    """PII-minimized Candidate↔Job summary used by the shared review workspace."""

    model_config = ConfigDict(extra="forbid")

    id: UUID
    job_id: UUID
    candidate: CandidateSummaryResponse
    created_source: JobCandidateSource
    preferred_sourcing_result_id: UUID | None
    shortlist_status: ShortlistStatus
    revision: int
    current_match: MatchEvaluationResponse | None
    match_freshness: MatchFreshness
    decision_is_current: bool
    call_readiness: CallReadiness
    created_at: datetime
    updated_at: datetime


class JobCandidateDetailResponse(JobCandidateSummaryResponse):
    """Detailed Module 4 relationship response without duplicating contact PII."""

    current_job_status: str
    current_job_definition_version: int | None
    decision_match_id: UUID | None


class JobCandidateListResponse(BaseModel):
    """Bounded Candidate↔Job list response."""

    model_config = ConfigDict(extra="forbid")

    items: list[JobCandidateSummaryResponse]
    limit: int
    offset: int


class MatchHistoryResponse(BaseModel):
    """Bounded immutable match history for one Candidate↔Job relationship."""

    model_config = ConfigDict(extra="forbid")

    items: list[MatchEvaluationResponse]
    limit: int
    offset: int
