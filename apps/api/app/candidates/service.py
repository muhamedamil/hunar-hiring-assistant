"""Candidate Core service for identity resolution, profile mutation, and safe deduplication."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.candidates.errors import (
    CandidateAlreadyExistsError,
    CandidateIdentityConflictError,
    CandidateNotFoundError,
    CandidateRevisionConflictError,
)
from app.candidates.models import Candidate, CandidateExternalIdentity
from app.candidates.repository import CandidateRepository
from app.candidates.schemas import (
    CandidateCreateRequest,
    CandidateExternalIdentityResponse,
    CandidateListResponse,
    CandidateMatchingSnapshot,
    CandidateProfileInput,
    CandidateResponse,
    CandidateSummaryResponse,
    ExternalCandidateObservation,
)

_IDENTITY_CONSTRAINTS = {
    "uq_candidates_email_ci",
    "uq_candidates_phone_e164",
    "uq_candidate_external_identities_provider_person",
}


class CandidateService:
    """Own canonical Candidate mutation and strong-identity convergence rules."""

    def __init__(self, session: Session, repository: CandidateRepository | None = None) -> None:
        self._session = session
        self._repository = repository or CandidateRepository()

    def create_manual_candidate(self, command: CandidateCreateRequest) -> CandidateResponse:
        """Create one manual Candidate without silently merging an existing strong identity."""

        try:
            with self._session.begin():
                matches = self._candidate_ids_for_contacts(
                    email=self._email_value(command.email),
                    phone_e164=command.phone,
                )
                self._raise_manual_identity_result(matches)
                candidate = Candidate(
                    full_name=command.full_name,
                    current_title=command.current_title,
                    current_company=command.current_company,
                    location=command.location,
                    email=self._email_value(command.email),
                    phone_e164=command.phone,
                    revision=0,
                    updated_at=datetime.now(UTC),
                )
                self._repository.create(self._session, candidate)
        except IntegrityError as exc:
            if not self._is_identity_integrity_error(exc):
                raise
            self._session.rollback()
            matches = self._candidate_ids_for_contacts(
                email=self._email_value(command.email),
                phone_e164=command.phone,
            )
            self._raise_manual_identity_result(matches)
            raise

        return self._to_candidate_response(candidate, [])

    def list_candidates(
        self,
        *,
        query: str | None,
        limit: int,
        offset: int,
    ) -> CandidateListResponse:
        """Return a PII-minimized recruiter-facing Candidate list."""

        candidates = self._repository.list(
            self._session,
            query=query,
            limit=limit,
            offset=offset,
        )
        return CandidateListResponse(
            items=[self._to_summary_response(candidate) for candidate in candidates],
            limit=limit,
            offset=offset,
        )

    def get_candidate(self, candidate_id: UUID) -> CandidateResponse:
        """Return one Candidate detail including canonical contacts and provider identities."""

        candidate = self._repository.get_by_id(self._session, candidate_id)
        if candidate is None:
            raise CandidateNotFoundError()
        identities = self._repository.list_external_identities(self._session, candidate.id)
        return self._to_candidate_response(candidate, identities)

    def lock_matching_snapshot_for_downstream_binding(
        self,
        candidate_id: UUID,
    ) -> CandidateMatchingSnapshot:
        """Lock a Candidate and return only evidence Module 4 is allowed to consume.

        The caller must already own the surrounding transaction. Contact values are deliberately
        excluded; only callable presence is projected for downstream call-readiness display.
        """

        candidate = self._require_locked_candidate(candidate_id)
        return self._to_matching_snapshot(candidate)

    def get_matching_snapshot(self, candidate_id: UUID) -> CandidateMatchingSnapshot:
        """Return current matching evidence without exposing Candidate contact PII."""

        candidate = self._repository.get_by_id(self._session, candidate_id)
        if candidate is None:
            raise CandidateNotFoundError()
        return self._to_matching_snapshot(candidate)

    def get_summaries_by_ids(
        self,
        candidate_ids: set[UUID],
    ) -> dict[UUID, CandidateSummaryResponse]:
        """Return PII-minimized Candidate summaries keyed by canonical identifier."""

        candidates = self._repository.list_by_ids(self._session, candidate_ids)
        return {candidate.id: self._to_summary_response(candidate) for candidate in candidates}

    def update_candidate(
        self,
        candidate_id: UUID,
        *,
        expected_revision: int,
        profile: CandidateProfileInput,
    ) -> CandidateResponse:
        """Replace the current Candidate profile using optimistic concurrency."""

        try:
            with self._session.begin():
                candidate = self._require_locked_candidate(candidate_id)
                self._assert_revision(candidate, expected_revision)
                conflicts = self._other_candidate_ids_for_contacts(
                    candidate.id,
                    email=self._email_value(profile.email),
                    phone_e164=profile.phone,
                )
                if conflicts:
                    raise CandidateIdentityConflictError(candidate_ids=conflicts | {candidate.id})

                candidate.full_name = profile.full_name
                candidate.current_title = profile.current_title
                candidate.current_company = profile.current_company
                candidate.location = profile.location
                candidate.email = self._email_value(profile.email)
                candidate.phone_e164 = profile.phone
                candidate.revision += 1
                candidate.updated_at = datetime.now(UTC)
                self._session.flush()
                identities = self._repository.list_external_identities(
                    self._session, candidate.id
                )
                response = self._to_candidate_response(candidate, identities)
        except IntegrityError as exc:
            if not self._is_identity_integrity_error(exc):
                raise
            self._session.rollback()
            conflicts = self._other_candidate_ids_for_contacts(
                candidate_id,
                email=self._email_value(profile.email),
                phone_e164=profile.phone,
            )
            if conflicts:
                raise CandidateIdentityConflictError(
                    candidate_ids=conflicts | {candidate_id}
                ) from exc
            raise

        return response

    def resolve_external_candidate(
        self,
        observation: ExternalCandidateObservation,
    ) -> CandidateResponse:
        """Resolve or create a Candidate from one provider-neutral person observation.

        Strong identity signals must converge to at most one Candidate. Existing canonical
        fields are never overwritten by provider observations; only missing fields and new
        provider identities are added.
        """

        try:
            return self._resolve_external_candidate_once(observation)
        except IntegrityError as exc:
            if not self._is_identity_integrity_error(exc):
                raise
            self._session.rollback()
            response = self._resolve_after_identity_race(observation)
            if response is None:
                raise
            return response

    def _resolve_external_candidate_once(
        self,
        observation: ExternalCandidateObservation,
    ) -> CandidateResponse:
        with self._session.begin():
            candidate_ids = self._candidate_ids_for_observation(observation)
            if len(candidate_ids) > 1:
                raise CandidateIdentityConflictError(candidate_ids=candidate_ids)

            if not candidate_ids:
                candidate = Candidate(
                    full_name=observation.full_name,
                    current_title=observation.current_title,
                    current_company=observation.current_company,
                    location=observation.location,
                    email=self._email_value(observation.email),
                    phone_e164=observation.phone,
                    revision=0,
                    updated_at=datetime.now(UTC),
                )
                self._repository.create(self._session, candidate)
                self._repository.insert_external_identity(
                    self._session,
                    CandidateExternalIdentity(
                        candidate_id=candidate.id,
                        provider=observation.provider,
                        external_person_id=observation.external_person_id,
                        profile_url=self._url_value(observation.profile_url),
                    ),
                )
                identities = self._repository.list_external_identities(
                    self._session, candidate.id
                )
                response = self._to_candidate_response(candidate, identities)
                return response

            candidate_id = next(iter(candidate_ids))
            response = self._resolve_existing_candidate(candidate_id, observation)

        return response

    def _resolve_existing_candidate(
        self,
        candidate_id: UUID,
        observation: ExternalCandidateObservation,
    ) -> CandidateResponse:
        """Converge one observation onto an already-identified Candidate inside a transaction."""

        candidate = self._require_locked_candidate(candidate_id)
        self._assert_observation_still_consistent(candidate, observation)
        changed = self._apply_external_observation(candidate, observation)

        identity = self._repository.find_external_identity(
            self._session,
            provider=observation.provider,
            external_person_id=observation.external_person_id,
        )
        if identity is None:
            self._repository.insert_external_identity(
                self._session,
                CandidateExternalIdentity(
                    candidate_id=candidate.id,
                    provider=observation.provider,
                    external_person_id=observation.external_person_id,
                    profile_url=self._url_value(observation.profile_url),
                ),
            )
            changed = True
        elif identity.candidate_id != candidate.id:
            raise CandidateIdentityConflictError(
                candidate_ids={candidate.id, identity.candidate_id}
            )

        if changed:
            candidate.revision += 1
            candidate.updated_at = datetime.now(UTC)
            self._session.flush()

        identities = self._repository.list_external_identities(
            self._session,
            candidate.id,
        )
        return self._to_candidate_response(candidate, identities)

    def _candidate_ids_for_observation(
        self,
        observation: ExternalCandidateObservation,
    ) -> set[UUID]:
        candidate_ids: set[UUID] = set()
        identity = self._repository.find_external_identity(
            self._session,
            provider=observation.provider,
            external_person_id=observation.external_person_id,
        )
        if identity is not None:
            candidate_ids.add(identity.candidate_id)
        candidate_ids.update(
            self._candidate_ids_for_contacts(
                email=self._email_value(observation.email),
                phone_e164=observation.phone,
            )
        )
        return candidate_ids

    def _candidate_ids_for_contacts(
        self,
        *,
        email: str | None,
        phone_e164: str | None,
    ) -> set[UUID]:
        candidates = {
            candidate.id
            for candidate in (
                self._repository.find_by_email(self._session, email),
                self._repository.find_by_phone(self._session, phone_e164),
            )
            if candidate is not None
        }
        return candidates

    def _other_candidate_ids_for_contacts(
        self,
        candidate_id: UUID,
        *,
        email: str | None,
        phone_e164: str | None,
    ) -> set[UUID]:
        return self._candidate_ids_for_contacts(
            email=email,
            phone_e164=phone_e164,
        ) - {candidate_id}

    def _raise_manual_identity_result(self, candidate_ids: set[UUID]) -> None:
        if len(candidate_ids) > 1:
            raise CandidateIdentityConflictError(candidate_ids=candidate_ids)
        if len(candidate_ids) == 1:
            raise CandidateAlreadyExistsError(candidate_id=next(iter(candidate_ids)))

    def _assert_observation_still_consistent(
        self,
        candidate: Candidate,
        observation: ExternalCandidateObservation,
    ) -> None:
        candidate_ids = self._candidate_ids_for_observation(observation)
        candidate_ids.add(candidate.id)
        if len(candidate_ids) > 1:
            raise CandidateIdentityConflictError(candidate_ids=candidate_ids)

    @staticmethod
    def _apply_external_observation(
        candidate: Candidate,
        observation: ExternalCandidateObservation,
    ) -> bool:
        changed = False
        pairs = (
            ("current_title", observation.current_title),
            ("current_company", observation.current_company),
            ("location", observation.location),
            ("email", CandidateService._email_value(observation.email)),
            ("phone_e164", observation.phone),
        )
        for attribute, observed in pairs:
            if getattr(candidate, attribute) is None and observed is not None:
                setattr(candidate, attribute, observed)
                changed = True
        return changed

    def _resolve_after_identity_race(
        self,
        observation: ExternalCandidateObservation,
    ) -> CandidateResponse | None:
        """Perform one bounded DB-only convergence pass after a known uniqueness race."""

        with self._session.begin():
            candidate_ids = self._candidate_ids_for_observation(observation)
            if len(candidate_ids) > 1:
                raise CandidateIdentityConflictError(candidate_ids=candidate_ids)
            if len(candidate_ids) == 1:
                return self._resolve_existing_candidate(
                    next(iter(candidate_ids)),
                    observation,
                )
        return None

    def _require_locked_candidate(self, candidate_id: UUID) -> Candidate:
        candidate = self._repository.get_for_update(self._session, candidate_id)
        if candidate is None:
            raise CandidateNotFoundError()
        return candidate

    @staticmethod
    def _assert_revision(candidate: Candidate, expected_revision: int) -> None:
        if candidate.revision != expected_revision:
            raise CandidateRevisionConflictError(current_revision=candidate.revision)

    @staticmethod
    def _email_value(email: object) -> str | None:
        return None if email is None else str(email)

    @staticmethod
    def _url_value(url: object) -> str | None:
        return None if url is None else str(url)

    @staticmethod
    def _constraint_name(exc: IntegrityError) -> str | None:
        original = getattr(exc, "orig", None)
        diagnostic = getattr(original, "diag", None)
        value = getattr(diagnostic, "constraint_name", None)
        return str(value) if value else None

    @classmethod
    def _is_identity_integrity_error(cls, exc: IntegrityError) -> bool:
        return cls._constraint_name(exc) in _IDENTITY_CONSTRAINTS

    @staticmethod
    def _to_matching_snapshot(candidate: Candidate) -> CandidateMatchingSnapshot:
        """Project the exact canonical Candidate evidence consumed by Module 4."""

        return CandidateMatchingSnapshot(
            candidate_id=candidate.id,
            candidate_revision=candidate.revision,
            current_title=candidate.current_title,
            location=candidate.location,
            has_phone=candidate.phone_e164 is not None,
        )

    @staticmethod
    def _to_candidate_response(
        candidate: Candidate,
        identities: list[CandidateExternalIdentity],
    ) -> CandidateResponse:
        return CandidateResponse(
            id=candidate.id,
            full_name=candidate.full_name,
            current_title=candidate.current_title,
            current_company=candidate.current_company,
            location=candidate.location,
            email=candidate.email,
            phone_e164=candidate.phone_e164,
            external_identities=[
                CandidateExternalIdentityResponse.model_validate(identity)
                for identity in identities
            ],
            revision=candidate.revision,
            created_at=candidate.created_at,
            updated_at=candidate.updated_at,
        )

    @staticmethod
    def _to_summary_response(candidate: Candidate) -> CandidateSummaryResponse:
        return CandidateSummaryResponse(
            id=candidate.id,
            full_name=candidate.full_name,
            current_title=candidate.current_title,
            current_company=candidate.current_company,
            location=candidate.location,
            has_email=candidate.email is not None,
            has_phone=candidate.phone_e164 is not None,
            revision=candidate.revision,
            updated_at=candidate.updated_at,
        )
