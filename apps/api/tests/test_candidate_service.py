"""Identity, mutation, and idempotency tests for Module 2 CandidateService."""

from __future__ import annotations

from contextlib import nullcontext
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import pytest

from app.candidates.errors import (
    CandidateAlreadyExistsError,
    CandidateIdentityConflictError,
    CandidateRevisionConflictError,
)
from app.candidates.models import Candidate, CandidateExternalIdentity
from app.candidates.schemas import (
    CandidateCreateRequest,
    CandidateProfileInput,
    ExternalCandidateObservation,
)
from app.candidates.service import CandidateService


class FakeSession:
    """Minimal transaction facade sufficient for deterministic service unit testing."""

    def begin(self):  # type: ignore[no-untyped-def]
        return nullcontext()

    def flush(self) -> None:
        return None

    def rollback(self) -> None:
        return None


class FakeCandidateRepository:
    """In-memory Candidate repository with strong-identity lookup behavior."""

    def __init__(self) -> None:
        self.candidates: dict[UUID, Candidate] = {}
        self.identities: dict[tuple[str, str], CandidateExternalIdentity] = {}

    def create(self, session: Any, candidate: Candidate) -> Candidate:
        del session
        candidate.id = uuid4()
        now = datetime.now(UTC)
        candidate.created_at = now
        candidate.updated_at = now
        self.candidates[candidate.id] = candidate
        return candidate

    def get_by_id(self, session: Any, candidate_id: UUID) -> Candidate | None:
        del session
        return self.candidates.get(candidate_id)

    def get_for_update(self, session: Any, candidate_id: UUID) -> Candidate | None:
        del session
        return self.candidates.get(candidate_id)

    def list(self, session: Any, *, query, limit: int, offset: int):  # type: ignore[no-untyped-def]
        del session
        values = list(self.candidates.values())
        if query:
            query_key = query.casefold()
            values = [
                candidate
                for candidate in values
                if any(
                    query_key in (value or "").casefold()
                    for value in (
                        candidate.full_name,
                        candidate.current_title,
                        candidate.current_company,
                        candidate.location,
                    )
                )
            ]
        return values[offset : offset + limit]

    def find_by_email(self, session: Any, email: str | None) -> Candidate | None:
        del session
        if email is None:
            return None
        return next(
            (
                candidate
                for candidate in self.candidates.values()
                if candidate.email is not None and candidate.email.casefold() == email.casefold()
            ),
            None,
        )

    def find_by_phone(self, session: Any, phone_e164: str | None) -> Candidate | None:
        del session
        if phone_e164 is None:
            return None
        return next(
            (
                candidate
                for candidate in self.candidates.values()
                if candidate.phone_e164 == phone_e164
            ),
            None,
        )

    def find_external_identity(
        self,
        session: Any,
        *,
        provider: str,
        external_person_id: str,
    ) -> CandidateExternalIdentity | None:
        del session
        return self.identities.get((provider, external_person_id))

    def list_external_identities(
        self,
        session: Any,
        candidate_id: UUID,
    ) -> list[CandidateExternalIdentity]:
        del session
        return [
            identity
            for identity in self.identities.values()
            if identity.candidate_id == candidate_id
        ]

    def insert_external_identity(
        self,
        session: Any,
        identity: CandidateExternalIdentity,
    ) -> CandidateExternalIdentity:
        del session
        identity.id = uuid4()
        identity.created_at = datetime.now(UTC)
        self.identities[(identity.provider, identity.external_person_id)] = identity
        return identity


def create_service() -> tuple[CandidateService, FakeCandidateRepository]:
    repository = FakeCandidateRepository()
    service = CandidateService(FakeSession(), repository)  # type: ignore[arg-type]
    return service, repository


def create_manual(
    service: CandidateService,
    *,
    name: str = "Sarah Ahmed",
    email: str | None = None,
):
    return service.create_manual_candidate(
        CandidateCreateRequest(full_name=name, email=email)
    )


def external(
    *,
    provider: str = "apollo",
    external_person_id: str = "person-1",
    name: str = "Sarah Ahmed",
    email: str | None = None,
    company: str | None = None,
    title: str | None = None,
) -> ExternalCandidateObservation:
    return ExternalCandidateObservation(
        provider=provider,
        external_person_id=external_person_id,
        full_name=name,
        email=email,
        current_company=company,
        current_title=title,
    )


def test_manual_candidate_can_exist_with_name_only_at_revision_zero() -> None:
    service, _ = create_service()

    candidate = create_manual(service)

    assert candidate.full_name == "Sarah Ahmed"
    assert candidate.email is None
    assert candidate.phone_e164 is None
    assert candidate.revision == 0
    assert candidate.external_identities == []


def test_same_name_without_strong_identity_does_not_auto_merge() -> None:
    service, repository = create_service()

    first = create_manual(service, name="John Smith")
    second = create_manual(service, name="John Smith")

    assert first.id != second.id
    assert len(repository.candidates) == 2


def test_manual_create_duplicate_email_returns_existing_candidate_id() -> None:
    service, _ = create_service()
    first = create_manual(service, email="sarah@example.com")

    with pytest.raises(CandidateAlreadyExistsError) as exc_info:
        create_manual(service, name="Different Name", email="SARAH@example.com")

    assert exc_info.value.details == {"existing_candidate_id": str(first.id)}


def test_manual_contacts_pointing_to_different_candidates_fail_closed() -> None:
    service, repository = create_service()
    first = create_manual(service, name="First", email="first@example.com")
    second = create_manual(service, name="Second", email="second@example.com")
    repository.candidates[first.id].phone_e164 = "+919111111111"
    repository.candidates[second.id].phone_e164 = "+919222222222"

    matches = service._candidate_ids_for_contacts(  # noqa: SLF001
        email="first@example.com",
        phone_e164="+919222222222",
    )
    with pytest.raises(CandidateIdentityConflictError):
        service._raise_manual_identity_result(matches)  # noqa: SLF001


def test_update_is_revision_protected_and_replaces_profile() -> None:
    service, _ = create_service()
    created = create_manual(service, email="sarah@example.com")

    updated = service.update_candidate(
        created.id,
        expected_revision=0,
        profile=CandidateProfileInput(
            full_name="Sarah Ahmed",
            current_title="Senior Backend Engineer",
            email="sarah@example.com",
        ),
    )

    assert updated.revision == 1
    assert updated.current_title == "Senior Backend Engineer"

    with pytest.raises(CandidateRevisionConflictError):
        service.update_candidate(
            created.id,
            expected_revision=0,
            profile=CandidateProfileInput(full_name="Stale Sarah"),
        )


def test_external_new_person_creates_candidate_and_provider_identity() -> None:
    service, _ = create_service()

    candidate = service.resolve_external_candidate(external())

    assert candidate.revision == 0
    assert len(candidate.external_identities) == 1
    assert candidate.external_identities[0].provider == "apollo"
    assert candidate.external_identities[0].external_person_id == "person-1"


def test_external_replay_is_idempotent_without_revision_increment() -> None:
    service, _ = create_service()
    observation = external(company="Acme")

    first = service.resolve_external_candidate(observation)
    second = service.resolve_external_candidate(observation)

    assert second.id == first.id
    assert second.revision == first.revision == 0
    assert len(second.external_identities) == 1


def test_new_provider_identity_attaches_to_existing_email_candidate() -> None:
    service, _ = create_service()
    manual = create_manual(service, email="sarah@example.com")

    resolved = service.resolve_external_candidate(
        external(email="sarah@example.com", company="Acme")
    )

    assert resolved.id == manual.id
    assert resolved.revision == 1
    assert resolved.current_company == "Acme"
    assert len(resolved.external_identities) == 1


def test_bounded_identity_race_recovery_completes_provider_convergence() -> None:
    service, _ = create_service()
    manual = create_manual(service, email="sarah@example.com")
    observation = external(
        provider="pdl",
        external_person_id="pdl-person-1",
        email="sarah@example.com",
        company="Acme",
    )

    resolved = service._resolve_after_identity_race(observation)  # noqa: SLF001

    assert resolved is not None
    assert resolved.id == manual.id
    assert resolved.current_company == "Acme"
    assert resolved.revision == 1
    assert [(item.provider, item.external_person_id) for item in resolved.external_identities] == [
        ("pdl", "pdl-person-1")
    ]


def test_provider_fills_missing_fields_but_never_overwrites_populated_profile() -> None:
    service, _ = create_service()
    created = service.create_manual_candidate(
        CandidateCreateRequest(
            full_name="Sarah Ahmed",
            current_company="Canonical Co",
            email="sarah@example.com",
        )
    )

    resolved = service.resolve_external_candidate(
        external(
            name="Different Provider Name",
            email="sarah@example.com",
            company="Stale Provider Co",
            title="Backend Engineer",
        )
    )

    assert resolved.id == created.id
    assert resolved.full_name == "Sarah Ahmed"
    assert resolved.current_company == "Canonical Co"
    assert resolved.current_title == "Backend Engineer"


def test_external_identity_and_email_disagreement_fails_without_merging() -> None:
    service, _ = create_service()
    first = create_manual(service, name="First", email="first@example.com")
    second = create_manual(service, name="Second", email="second@example.com")
    linked = service.resolve_external_candidate(
        external(external_person_id="person-a", email="first@example.com")
    )
    assert linked.id == first.id

    with pytest.raises(CandidateIdentityConflictError) as exc_info:
        service.resolve_external_candidate(
            external(external_person_id="person-a", email="second@example.com")
        )

    assert set(exc_info.value.details["candidate_ids"]) == {
        str(first.id),
        str(second.id),
    }


def test_second_provider_can_attach_to_same_candidate_via_strong_email() -> None:
    service, _ = create_service()
    first = service.resolve_external_candidate(
        external(provider="apollo", external_person_id="a-1", email="sarah@example.com")
    )

    second = service.resolve_external_candidate(
        external(provider="pdl", external_person_id="p-9", email="sarah@example.com")
    )

    assert second.id == first.id
    assert second.revision == 1
    assert {identity.provider for identity in second.external_identities} == {"apollo", "pdl"}
