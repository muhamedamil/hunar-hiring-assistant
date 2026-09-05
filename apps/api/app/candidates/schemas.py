"""Typed Candidate Core contracts shared by manual and provider-sourced workflows."""

from __future__ import annotations

import re
from datetime import datetime
from uuid import UUID

from pydantic import AnyHttpUrl, BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.candidates.normalization import (
    normalize_optional_text,
    normalize_phone_e164,
    normalize_required_text,
)

_PROVIDER_PATTERN = re.compile(r"^[a-z][a-z0-9_]{1,39}$")


class CandidateProfileInput(BaseModel):
    """Complete mutable Candidate profile supplied by recruiter-facing operations."""

    model_config = ConfigDict(extra="forbid")

    full_name: str = Field(min_length=1, max_length=200)
    current_title: str | None = Field(default=None, max_length=200)
    current_company: str | None = Field(default=None, max_length=200)
    location: str | None = Field(default=None, max_length=200)
    email: EmailStr | None = None
    phone: str | None = None

    @field_validator("full_name", mode="before")
    @classmethod
    def normalize_full_name(cls, value: object) -> object:
        """Trim the required Candidate name before length validation."""

        return normalize_required_text(value)

    @field_validator("current_title", "current_company", "location", mode="before")
    @classmethod
    def normalize_optional_profile_text(cls, value: object) -> object:
        """Trim optional profile text and collapse blank values to null."""

        return normalize_optional_text(value)

    @field_validator("email", mode="before")
    @classmethod
    def normalize_email(cls, value: object) -> object:
        """Trim optional email input before standards-based validation."""

        return normalize_optional_text(value)

    @field_validator("phone", mode="before")
    @classmethod
    def normalize_phone(cls, value: object) -> object:
        """Normalize optional international phone input to E.164."""

        return normalize_phone_e164(value)


class CandidateCreateRequest(CandidateProfileInput):
    """Public command for manually creating one global Candidate."""


class CandidateUpdateRequest(BaseModel):
    """Revision-protected complete replacement of the canonical Candidate profile."""

    model_config = ConfigDict(extra="forbid")

    expected_revision: int = Field(ge=0)
    profile: CandidateProfileInput


class CandidateExternalIdentityResponse(BaseModel):
    """Provider identity metadata attached to one canonical Candidate."""

    model_config = ConfigDict(from_attributes=True, extra="forbid")

    id: UUID
    provider: str
    external_person_id: str
    profile_url: AnyHttpUrl | None
    created_at: datetime


class CandidateResponse(BaseModel):
    """Recruiter-facing Candidate detail including canonical contacts and provider identities."""

    model_config = ConfigDict(extra="forbid")

    id: UUID
    full_name: str
    current_title: str | None
    current_company: str | None
    location: str | None
    email: EmailStr | None
    phone_e164: str | None
    external_identities: list[CandidateExternalIdentityResponse]
    revision: int
    created_at: datetime
    updated_at: datetime


class CandidateSummaryResponse(BaseModel):
    """PII-minimized Candidate projection used by the list UI."""

    model_config = ConfigDict(extra="forbid")

    id: UUID
    full_name: str
    current_title: str | None
    current_company: str | None
    location: str | None
    has_email: bool
    has_phone: bool
    revision: int
    updated_at: datetime


class CandidateListResponse(BaseModel):
    """Bounded Candidate list response."""

    model_config = ConfigDict(extra="forbid")

    items: list[CandidateSummaryResponse]
    limit: int
    offset: int


class ExternalCandidateObservation(BaseModel):
    """Provider-neutral person observation consumed internally by future sourcing modules."""

    model_config = ConfigDict(extra="forbid")

    provider: str = Field(min_length=2, max_length=40)
    external_person_id: str = Field(min_length=1, max_length=255)
    profile_url: AnyHttpUrl | None = Field(default=None, max_length=1000)
    full_name: str = Field(min_length=1, max_length=200)
    current_title: str | None = Field(default=None, max_length=200)
    current_company: str | None = Field(default=None, max_length=200)
    location: str | None = Field(default=None, max_length=200)
    email: EmailStr | None = None
    phone: str | None = None

    @field_validator("provider", mode="before")
    @classmethod
    def normalize_provider(cls, value: object) -> object:
        """Normalize provider keys to the bounded lower-case identifier contract."""

        if not isinstance(value, str):
            return value
        normalized = value.strip().lower()
        if not _PROVIDER_PATTERN.fullmatch(normalized):
            raise ValueError("Provider must be a lower-case identifier such as 'apollo'")
        return normalized

    @field_validator("external_person_id", "full_name", mode="before")
    @classmethod
    def normalize_required_fields(cls, value: object) -> object:
        """Trim provider-required identity fields before validation."""

        return normalize_required_text(value)

    @field_validator("current_title", "current_company", "location", mode="before")
    @classmethod
    def normalize_optional_fields(cls, value: object) -> object:
        """Trim optional provider profile fields."""

        return normalize_optional_text(value)

    @field_validator("profile_url", mode="before")
    @classmethod
    def normalize_profile_url(cls, value: object) -> object:
        """Trim optional provider profile URLs before HTTP/HTTPS validation."""

        return normalize_optional_text(value)

    @field_validator("email", mode="before")
    @classmethod
    def normalize_observed_email(cls, value: object) -> object:
        """Trim optional observed email before standards-based validation."""

        return normalize_optional_text(value)

    @field_validator("phone", mode="before")
    @classmethod
    def normalize_observed_phone(cls, value: object) -> object:
        """Normalize an optional observed phone to E.164."""

        return normalize_phone_e164(value)
