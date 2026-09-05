"""Schema and normalization tests for Module 2 Candidate Core contracts."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.candidates.normalization import phone_library_available
from app.candidates.schemas import (
    CandidateCreateRequest,
    CandidateExternalIdentityResponse,
    ExternalCandidateObservation,
)


def test_candidate_profile_trims_text_and_collapses_optional_blanks() -> None:
    candidate = CandidateCreateRequest(
        full_name="  Sarah Ahmed  ",
        current_title=" Backend Engineer ",
        current_company="   ",
        location=" Bangalore ",
        email=" Sarah@example.com ",
    )

    assert candidate.full_name == "Sarah Ahmed"
    assert candidate.current_title == "Backend Engineer"
    assert candidate.current_company is None
    assert candidate.location == "Bangalore"
    assert str(candidate.email) == "Sarah@example.com"


def test_blank_candidate_name_is_rejected_after_normalization() -> None:
    with pytest.raises(ValidationError):
        CandidateCreateRequest(full_name="   ")


def test_invalid_email_is_rejected() -> None:
    with pytest.raises(ValidationError):
        CandidateCreateRequest(full_name="Sarah Ahmed", email="not-an-email")


def test_phone_without_country_code_is_rejected_without_guessing_region() -> None:
    with pytest.raises(ValidationError) as exc_info:
        CandidateCreateRequest(full_name="Sarah Ahmed", phone="9876543210")

    assert "international country code" in str(exc_info.value)


@pytest.mark.skipif(not phone_library_available(), reason="phonenumbers package unavailable")
def test_phone_is_normalized_to_e164_when_library_is_available() -> None:
    candidate = CandidateCreateRequest(
        full_name="Sarah Ahmed",
        phone="+91 98765 43210",
    )

    assert candidate.phone == "+919876543210"


def test_external_observation_normalizes_provider_and_allows_missing_contacts() -> None:
    observation = ExternalCandidateObservation(
        provider=" Apollo ",
        external_person_id=" person-123 ",
        full_name=" Sarah Ahmed ",
        current_company=" ",
    )

    assert observation.provider == "apollo"
    assert observation.external_person_id == "person-123"
    assert observation.full_name == "Sarah Ahmed"
    assert observation.current_company is None
    assert observation.email is None
    assert observation.phone is None


def test_external_identity_response_rejects_non_http_profile_url() -> None:
    with pytest.raises(ValidationError):
        CandidateExternalIdentityResponse(
            id=uuid4(),
            provider="apollo",
            external_person_id="person-1",
            profile_url="javascript:alert(1)",
            created_at=datetime.now(UTC),
        )
