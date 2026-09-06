"""Typed contracts for Job-bound people search, evidence, and contact enrichment."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Literal
from uuid import UUID

from pydantic import AnyHttpUrl, BaseModel, ConfigDict, EmailStr, Field, field_validator


class SourcingRunStatus(StrEnum):
    """Lifecycle of one synchronous provider people-search execution."""

    SEARCHING = "searching"
    COMPLETED = "completed"
    FAILED = "failed"


class EnrichmentStatus(StrEnum):
    """Lifecycle of one deliberate credit-aware provider enrichment operation."""

    PENDING = "pending"
    AWAITING_PHONE = "awaiting_phone"
    COMPLETED = "completed"
    NOT_FOUND = "not_found"
    FAILED = "failed"
    UNKNOWN = "unknown"
    CONFLICT = "conflict"


class PhoneAvailability(StrEnum):
    """Provider evidence about whether a search hit may have a phone number."""

    AVAILABLE = "available"
    MAYBE = "maybe"
    UNAVAILABLE = "unavailable"
    UNKNOWN = "unknown"


class UnmappedRequirement(BaseModel):
    """Approved Job requirement intentionally not converted into an Apollo filter."""

    model_config = ConfigDict(extra="forbid")

    field: str = Field(min_length=1, max_length=80)
    values: list[str] = Field(min_length=1, max_length=50)


class SourcingSearchCriteria(BaseModel):
    """Provider-neutral frozen search intent derived from an approved Job definition."""

    model_config = ConfigDict(extra="forbid")

    titles: list[str] = Field(min_length=1, max_length=6)
    locations: list[str] = Field(default_factory=list, max_length=10)
    seniorities: list[str] = Field(default_factory=list, max_length=5)
    unmapped_requirements: list[UnmappedRequirement] = Field(default_factory=list)
    result_limit: int = Field(ge=1, le=50)


class ProviderSearchQuery(BaseModel):
    """Exact Apollo search query persisted for historical replay."""

    model_config = ConfigDict(extra="forbid")

    person_titles: list[str] = Field(min_length=1, max_length=6)
    person_locations: list[str] = Field(default_factory=list, max_length=10)
    person_seniorities: list[str] = Field(default_factory=list, max_length=5)
    include_similar_titles: bool = False
    page: Literal[1] = 1
    per_page: int = Field(ge=1, le=50)


class ProviderSearchHit(BaseModel):
    """Provider-neutral search evidence that must not become Candidate truth directly."""

    model_config = ConfigDict(extra="forbid")

    external_person_id: str = Field(min_length=1, max_length=255)
    first_name: str | None = Field(default=None, max_length=200)
    last_name_obfuscated: str | None = Field(default=None, max_length=200)
    title: str | None = Field(default=None, max_length=200)
    organization_name: str | None = Field(default=None, max_length=200)
    email_available: bool = False
    phone_availability: PhoneAvailability = PhoneAvailability.UNKNOWN
    last_refreshed_at: datetime | None = None


class ProviderSearchPage(BaseModel):
    """Validated bounded page returned by a people-search provider."""

    model_config = ConfigDict(extra="forbid")

    hits: list[ProviderSearchHit]
    total_matches: int | None = Field(default=None, ge=0)


class ProviderEnrichedPerson(BaseModel):
    """Synchronous provider-enriched person profile before Candidate Core resolution."""

    model_config = ConfigDict(extra="forbid")

    external_person_id: str = Field(min_length=1, max_length=255)
    full_name: str = Field(min_length=1, max_length=200)
    title: str | None = Field(default=None, max_length=200)
    company: str | None = Field(default=None, max_length=200)
    location: str | None = Field(default=None, max_length=200)
    email: EmailStr | None = None
    linkedin_url: AnyHttpUrl | None = Field(default=None, max_length=1000)


class ProviderEnrichmentResponse(BaseModel):
    """Synchronous enrichment response plus async-phone recovery identity."""

    model_config = ConfigDict(extra="forbid")

    person: ProviderEnrichedPerson | None
    request_id: int | None = None


class ProviderPhoneNumber(BaseModel):
    """Normalized phone candidate from Apollo webhook/poll payload."""

    model_config = ConfigDict(extra="forbid")

    raw_number: str | None = Field(default=None, max_length=100)
    sanitized_number: str | None = Field(default=None, max_length=100)
    type_code: str | None = Field(default=None, max_length=80)
    status_code: str | None = Field(default=None, max_length=80)
    position: int = Field(default=0, ge=0)


class ProviderPhoneResult(BaseModel):
    """Normalized completed Apollo phone-enrichment result."""

    model_config = ConfigDict(extra="forbid")

    request_id: int | None = None
    external_person_id: str = Field(min_length=1, max_length=255)
    phones: list[ProviderPhoneNumber] = Field(default_factory=list)
    credits_consumed: int | None = Field(default=None, ge=0)


class ProviderPollStatus(StrEnum):
    """Semantic status of Apollo's zero-credit webhook-result polling endpoint."""

    PENDING = "pending"
    COMPLETED = "completed"
    TERMINAL_FAILURE = "terminal_failure"


class ProviderPollResult(BaseModel):
    """Normalized result of one zero-credit polling attempt."""

    model_config = ConfigDict(extra="forbid")

    status: ProviderPollStatus
    phone_result: ProviderPhoneResult | None = None
    retry_after_seconds: int | None = Field(default=None, ge=0)
    failure_code: str | None = None


class StartSourcingRunRequest(BaseModel):
    """Recruiter command for one bounded provider search."""

    model_config = ConfigDict(extra="forbid")

    result_limit: int = 25

    @field_validator("result_limit")
    @classmethod
    def validate_result_limit(cls, value: int) -> int:
        """Restrict the assessment UI/API to deliberate 10/25/50-result searches."""

        if value not in {10, 25, 50}:
            raise ValueError("result_limit must be one of 10, 25, or 50")
        return value


class SourcingResultResponse(BaseModel):
    """Recruiter-facing provider search evidence with optional Candidate resolution link."""

    model_config = ConfigDict(from_attributes=True, extra="forbid")

    id: UUID
    sourcing_run_id: UUID
    provider_person_id: str
    result_position: int
    first_name: str | None
    last_name_obfuscated: str | None
    current_title: str | None
    organization_name: str | None
    email_available: bool
    phone_availability: PhoneAvailability
    candidate_id: UUID | None
    created_at: datetime


class SourcingEnrichmentResponse(BaseModel):
    """Recruiter-safe enrichment status without duplicated Candidate contact PII."""

    model_config = ConfigDict(from_attributes=True, extra="forbid")

    id: UUID
    sourcing_result_id: UUID
    provider: str
    status: EnrichmentStatus
    candidate_id: UUID | None
    provider_request_id: int | None
    credits_consumed: int | None
    failure_code: str | None
    retry_after_seconds: int | None
    requested_at: datetime | None
    completed_at: datetime | None
    created_at: datetime
    updated_at: datetime


class SourcingRunSummaryResponse(BaseModel):
    """Compact sourcing-run projection for historical Job sourcing lists."""

    model_config = ConfigDict(extra="forbid")

    id: UUID
    job_id: UUID
    definition_version: int
    provider: str
    status: SourcingRunStatus
    result_limit: int
    result_count: int
    provider_total_matches: int | None
    failure_code: str | None
    retry_after_seconds: int | None
    created_at: datetime
    completed_at: datetime | None


class SourcingRunListResponse(BaseModel):
    """Bounded historical sourcing runs for one Job."""

    model_config = ConfigDict(extra="forbid")

    items: list[SourcingRunSummaryResponse]


class SourcingRunDetailResponse(BaseModel):
    """Complete sourcing-run state including persisted mapping diagnostics and evidence."""

    model_config = ConfigDict(extra="forbid")

    id: UUID
    job_id: UUID
    definition_version: int
    provider: str
    status: SourcingRunStatus
    criteria: SourcingSearchCriteria
    provider_query: ProviderSearchQuery
    mapping_version: str
    result_limit: int
    result_count: int
    provider_total_matches: int | None
    attempt_count: int
    failure_code: str | None
    retry_after_seconds: int | None
    started_at: datetime
    completed_at: datetime | None
    created_at: datetime
    updated_at: datetime
    results: list[SourcingResultResponse]
    enrichments: list[SourcingEnrichmentResponse]
