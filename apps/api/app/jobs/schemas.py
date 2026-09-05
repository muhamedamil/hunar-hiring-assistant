"""Typed contracts for job definitions, screening questions, and approved snapshots."""

from __future__ import annotations

import re
from datetime import datetime
from enum import StrEnum
from typing import Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

QUESTION_KEY_PATTERN = re.compile(r"^[a-z][a-z0-9_]{1,39}$")


def _normalize_string_list(values: list[str]) -> list[str]:
    """Trim, drop blanks, and case-insensitively deduplicate display strings."""

    normalized: list[str] = []
    seen: set[str] = set()
    for raw in values:
        value = raw.strip()
        if not value:
            continue
        key = value.casefold()
        if key in seen:
            continue
        seen.add(key)
        normalized.append(value)
    return normalized


class JobStatus(StrEnum):
    """Whether a job may start new downstream work."""

    DRAFT = "draft"
    READY = "ready"


class SeniorityLevel(StrEnum):
    """Provider-neutral seniority values used by the approved job definition."""

    INTERN = "intern"
    ENTRY = "entry"
    MID = "mid"
    SENIOR = "senior"
    LEAD = "lead"
    MANAGER = "manager"
    DIRECTOR = "director"
    EXECUTIVE = "executive"


class EmploymentType(StrEnum):
    """Provider-neutral employment types."""

    FULL_TIME = "full_time"
    PART_TIME = "part_time"
    CONTRACT = "contract"
    INTERNSHIP = "internship"
    TEMPORARY = "temporary"
    OTHER = "other"


class WorkArrangement(StrEnum):
    """Supported work-location arrangements; ``None`` means unspecified."""

    ONSITE = "onsite"
    HYBRID = "hybrid"
    REMOTE = "remote"


class ScreeningAnswerType(StrEnum):
    """Bounded answer types that can later map cleanly into Hunar result fields."""

    YES_NO = "yes_no"
    SHORT_TEXT = "short_text"
    NUMBER = "number"
    CHOICE = "choice"


class _JobRequirementsBase(BaseModel):
    """Shared normalized shape used by canonical requirements and provider proposals."""

    model_config = ConfigDict(extra="forbid")

    alternate_titles: list[str] = Field(default_factory=list, max_length=5)
    required_skills: list[str] = Field(default_factory=list, max_length=20)
    preferred_skills: list[str] = Field(default_factory=list, max_length=20)
    locations: list[str] = Field(default_factory=list, max_length=10)
    min_years_experience: int | None = Field(default=None, ge=0, le=50)
    seniority: list[SeniorityLevel] = Field(default_factory=list, max_length=5)
    employment_type: EmploymentType | None = None
    work_arrangement: WorkArrangement | None = None

    @field_validator(
        "alternate_titles", "required_skills", "preferred_skills", "locations", mode="before"
    )
    @classmethod
    def normalize_string_lists(cls, value: object) -> object:
        if value is None:
            return []
        if not isinstance(value, list):
            return value
        if not all(isinstance(item, str) for item in value):
            return value
        return _normalize_string_list(value)

    @field_validator("seniority", mode="before")
    @classmethod
    def deduplicate_seniority(cls, value: object) -> object:
        if value is None:
            return []
        if not isinstance(value, list):
            return value
        result: list[object] = []
        seen: set[str] = set()
        for item in value:
            key = str(item).casefold()
            if key in seen:
                continue
            seen.add(key)
            result.append(item)
        return result


class ProposedJobRequirements(_JobRequirementsBase):
    """AI-provider requirement proposal before deterministic cross-field cleanup."""

    # Provider output must explicitly include every field, including null/empty values.
    # Without these overrides Pydantic's canonical defaults make every JSON Schema
    # property optional, allowing a model to return only a title and still pass validation.
    alternate_titles: list[str] = Field(max_length=5)
    required_skills: list[str] = Field(max_length=20)
    preferred_skills: list[str] = Field(max_length=20)
    locations: list[str] = Field(max_length=10)
    min_years_experience: int | None = Field(ge=0, le=50)
    seniority: list[SeniorityLevel] = Field(max_length=5)
    employment_type: EmploymentType | None
    work_arrangement: WorkArrangement | None


class JobRequirements(_JobRequirementsBase):
    """Canonical provider-neutral hiring requirements shared by Tasks 1 and 2."""

    @model_validator(mode="after")
    def validate_skill_sets(self) -> Self:
        required = {skill.casefold() for skill in self.required_skills}
        preferred = {skill.casefold() for skill in self.preferred_skills}
        if required & preferred:
            raise ValueError("Required and preferred skills cannot overlap")
        return self


class ScreeningQuestionCreate(BaseModel):
    """Question input used when a new canonical server-owned UUID is required."""

    model_config = ConfigDict(extra="forbid")

    key: str = Field(min_length=2, max_length=40)
    prompt: str = Field(min_length=5, max_length=500)
    answer_type: ScreeningAnswerType
    required: bool = True
    options: list[str] = Field(default_factory=list, max_length=10)

    @field_validator("key", mode="before")
    @classmethod
    def normalize_key(cls, value: object) -> object:
        if not isinstance(value, str):
            return value
        normalized = value.strip().lower()
        if not QUESTION_KEY_PATTERN.fullmatch(normalized):
            raise ValueError("Question key must match ^[a-z][a-z0-9_]{1,39}$")
        return normalized

    @field_validator("prompt", mode="before")
    @classmethod
    def normalize_prompt(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value

    @field_validator("options", mode="before")
    @classmethod
    def normalize_options(cls, value: object) -> object:
        if value is None:
            return []
        if not isinstance(value, list):
            return value
        if not all(isinstance(item, str) for item in value):
            return value
        return _normalize_string_list(value)

    @model_validator(mode="after")
    def validate_options(self) -> Self:
        if self.answer_type is ScreeningAnswerType.CHOICE:
            if len(self.options) < 2:
                raise ValueError("Choice questions require at least two options")
        elif self.options:
            raise ValueError("Only choice questions may define options")
        return self


class ScreeningQuestionEdit(ScreeningQuestionCreate):
    """Editable question where an existing canonical UUID may be preserved."""

    id: UUID | None = None


class ScreeningQuestion(ScreeningQuestionCreate):
    """Canonical persisted screening question with server-owned identity."""

    id: UUID


class JobDefinitionCreate(BaseModel):
    """Complete new DRAFT definition; question identities are assigned server-side."""

    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=200)
    company_name: str | None = Field(default=None, max_length=200)
    description: str = Field(min_length=20, max_length=20000)
    requirements: JobRequirements = Field(default_factory=JobRequirements)
    screening_questions: list[ScreeningQuestionCreate] = Field(default_factory=list, max_length=10)

    @field_validator("title", "description", mode="before")
    @classmethod
    def normalize_required_text(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value

    @field_validator("company_name", mode="before")
    @classmethod
    def normalize_optional_text(cls, value: object) -> object:
        if not isinstance(value, str):
            return value
        normalized = value.strip()
        return normalized or None


class JobDefinitionEdit(BaseModel):
    """Complete replacement of the mutable Job definition used by save/ready commands."""

    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=200)
    company_name: str | None = Field(default=None, max_length=200)
    description: str = Field(min_length=20, max_length=20000)
    requirements: JobRequirements = Field(default_factory=JobRequirements)
    screening_questions: list[ScreeningQuestionEdit] = Field(default_factory=list, max_length=10)

    @field_validator("title", "description", mode="before")
    @classmethod
    def normalize_required_text(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value

    @field_validator("company_name", mode="before")
    @classmethod
    def normalize_optional_text(cls, value: object) -> object:
        if not isinstance(value, str):
            return value
        normalized = value.strip()
        return normalized or None


class JobCreateRequest(JobDefinitionCreate):
    """HTTP request for creating a mutable DRAFT Job."""


class JobUpdateRequest(BaseModel):
    """Revision-protected complete replacement of a DRAFT Job definition."""

    model_config = ConfigDict(extra="forbid")

    expected_revision: int = Field(ge=0)
    definition: JobDefinitionEdit


class JobReadyRequest(JobUpdateRequest):
    """Atomic save-and-approve command for the exact visible Job definition."""


class JobReopenRequest(BaseModel):
    """Revision-protected command to reopen a READY Job for editing."""

    model_config = ConfigDict(extra="forbid")

    expected_revision: int = Field(ge=0)


class JobResponse(BaseModel):
    """Canonical API representation of the current mutable Job aggregate."""

    id: UUID
    title: str
    company_name: str | None
    description: str
    requirements: JobRequirements
    screening_questions: list[ScreeningQuestion]
    status: JobStatus
    revision: int
    approved_version: int | None
    created_at: datetime
    updated_at: datetime


class JobSummaryResponse(BaseModel):
    """Compact Job projection used by the list screen."""

    id: UUID
    title: str
    company_name: str | None
    status: JobStatus
    revision: int
    approved_version: int | None
    updated_at: datetime


class JobListResponse(BaseModel):
    """Offset-paginated Job list response."""

    items: list[JobSummaryResponse]
    limit: int
    offset: int


class SuggestedScreeningQuestion(ScreeningQuestionCreate):
    """Non-authoritative screening question proposed by the AI provider."""


class JobAnalysisProviderOutput(BaseModel):
    """Relaxed provider payload before deterministic canonical normalization."""

    model_config = ConfigDict(extra="forbid")

    suggested_title: str | None = Field(max_length=200)
    requirements: ProposedJobRequirements
    suggested_screening_questions: list[SuggestedScreeningQuestion] = Field(max_length=10)

    @field_validator("suggested_title", mode="before")
    @classmethod
    def normalize_suggested_title(cls, value: object) -> object:
        if not isinstance(value, str):
            return value
        normalized = value.strip()
        return normalized or None


class JobAnalysisProposal(BaseModel):
    """Normalized non-authoritative proposal returned to the recruiter UI."""

    model_config = ConfigDict(extra="forbid")

    suggested_title: str | None = Field(default=None, max_length=200)
    requirements: JobRequirements = Field(default_factory=JobRequirements)
    suggested_screening_questions: list[SuggestedScreeningQuestion] = Field(
        default_factory=list, max_length=10
    )


class JobAnalysisRequest(BaseModel):
    """Request for optional non-mutating structured JD analysis."""

    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(default=None, max_length=200)
    description: str = Field(min_length=20, max_length=20000)

    @field_validator("title", mode="before")
    @classmethod
    def normalize_title(cls, value: object) -> object:
        if not isinstance(value, str):
            return value
        normalized = value.strip()
        return normalized or None

    @field_validator("description", mode="before")
    @classmethod
    def normalize_description(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value


class ApprovedJobDefinition(BaseModel):
    """Immutable approved definition returned to future downstream modules."""

    id: UUID
    job_id: UUID
    version: int
    title: str
    company_name: str | None
    description: str
    requirements: JobRequirements
    screening_questions: list[ScreeningQuestion]
    created_at: datetime
