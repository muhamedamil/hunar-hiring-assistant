"""Signed Apollo webhook verification and idempotent phone-result finalization."""

from __future__ import annotations

import hashlib
import hmac
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.orm import Session, sessionmaker

from app.candidates.errors import CandidateIdentityConflictError
from app.candidates.normalization import normalize_phone_e164
from app.candidates.schemas import CandidateResponse, ExternalCandidateObservation
from app.candidates.service import CandidateService
from app.sourcing.errors import (
    ApolloWebhookSignatureError,
    EnrichmentStateConflictError,
    SourcingEnrichmentNotFoundError,
    SourcingResultNotFoundError,
)
from app.sourcing.models import SourcingEnrichment
from app.sourcing.repository import SourcingRepository
from app.sourcing.schemas import (
    EnrichmentStatus,
    ProviderPhoneNumber,
    ProviderPhoneResult,
    SourcingEnrichmentResponse,
)

_TERMINAL = {
    EnrichmentStatus.COMPLETED,
    EnrichmentStatus.NOT_FOUND,
    EnrichmentStatus.FAILED,
    EnrichmentStatus.UNKNOWN,
    EnrichmentStatus.CONFLICT,
}


@dataclass(frozen=True)
class _FinalizationSnapshot:
    """Minimal persisted state needed before Candidate phone resolution occurs."""

    terminal_response: SourcingEnrichmentResponse | None
    candidate_id: UUID | None
    provider_person_id: str | None


def sign_apollo_webhook(secret: str, enrichment_id: UUID) -> str:
    """Return the HMAC capability signature embedded in one Apollo callback URL."""

    return hmac.new(
        secret.encode("utf-8"),
        str(enrichment_id).encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def verify_apollo_webhook_signature(
    *,
    secret: str,
    enrichment_id: UUID,
    signature: str,
) -> None:
    """Reject a callback whose HMAC capability does not match the enrichment identifier."""

    expected = sign_apollo_webhook(secret, enrichment_id)
    if not hmac.compare_digest(expected, signature):
        raise ApolloWebhookSignatureError()


class SourcingWebhookService:
    """Converge webhook and polling results onto one Candidate and one terminal enrichment."""

    def __init__(
        self,
        session_factory: sessionmaker[Session],
        *,
        repository: SourcingRepository | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._repository = repository or SourcingRepository()

    def finalize_phone_result(
        self,
        enrichment_id: UUID,
        result: ProviderPhoneResult,
    ) -> SourcingEnrichmentResponse:
        """Idempotently finalize one phone result from either webhook or zero-credit polling."""

        snapshot = self._load_finalization_snapshot(enrichment_id, result)
        if snapshot.terminal_response is not None:
            return snapshot.terminal_response

        candidate_id = snapshot.candidate_id
        provider_person_id = snapshot.provider_person_id
        if not isinstance(candidate_id, UUID) or not isinstance(provider_person_id, str):
            raise EnrichmentStateConflictError(
                code="ENRICHMENT_CANDIDATE_NOT_READY",
                message="Enrichment candidate resolution is not ready for phone finalization.",
            )

        phone = self._select_phone(result.phones)
        if phone is not None:
            try:
                candidate = self._resolve_phone_candidate(
                    candidate_id=candidate_id,
                    provider_person_id=provider_person_id,
                    phone=phone,
                )
                candidate_id = candidate.id
            except CandidateIdentityConflictError:
                return self._mark_terminal(
                    enrichment_id,
                    status=EnrichmentStatus.CONFLICT,
                    candidate_id=candidate_id,
                    failure_code="CANDIDATE_IDENTITY_CONFLICT",
                    credits_consumed=result.credits_consumed,
                )

        return self._mark_terminal(
            enrichment_id,
            status=EnrichmentStatus.COMPLETED,
            candidate_id=candidate_id,
            failure_code=None,
            credits_consumed=result.credits_consumed,
        )

    def _load_finalization_snapshot(
        self,
        enrichment_id: UUID,
        result: ProviderPhoneResult,
    ) -> _FinalizationSnapshot:
        with self._session_factory() as session, session.begin():
            enrichment = self._repository.get_enrichment_for_update(session, enrichment_id)
            if enrichment is None:
                raise SourcingEnrichmentNotFoundError()
            status = EnrichmentStatus(enrichment.status)
            if status in _TERMINAL:
                return _FinalizationSnapshot(
                    terminal_response=self._response(enrichment),
                    candidate_id=enrichment.candidate_id,
                    provider_person_id=None,
                )
            sourcing_result = self._repository.get_result(
                session,
                enrichment.sourcing_result_id,
            )
            if sourcing_result is None:
                raise SourcingResultNotFoundError()
            if result.external_person_id != sourcing_result.provider_person_id:
                raise EnrichmentStateConflictError(
                    code="APOLLO_WEBHOOK_PERSON_MISMATCH",
                    message="Apollo webhook person does not match the enrichment target.",
                )
            if (
                result.request_id is not None
                and enrichment.provider_request_id is not None
                and result.request_id != enrichment.provider_request_id
            ):
                raise EnrichmentStateConflictError(
                    code="APOLLO_WEBHOOK_REQUEST_MISMATCH",
                    message="Apollo webhook request ID does not match the enrichment request.",
                )
            return _FinalizationSnapshot(
                terminal_response=None,
                candidate_id=enrichment.candidate_id,
                provider_person_id=sourcing_result.provider_person_id,
            )

    def _resolve_phone_candidate(
        self,
        *,
        candidate_id: UUID,
        provider_person_id: str,
        phone: str,
    ) -> CandidateResponse:
        with self._session_factory() as read_session:
            candidate = CandidateService(read_session).get_candidate(candidate_id)
        with self._session_factory() as mutation_session:
            return CandidateService(mutation_session).resolve_external_candidate(
                ExternalCandidateObservation(
                    provider="apollo",
                    external_person_id=provider_person_id,
                    full_name=candidate.full_name,
                    current_title=candidate.current_title,
                    current_company=candidate.current_company,
                    location=candidate.location,
                    email=candidate.email,
                    phone=phone,
                )
            )

    def _mark_terminal(
        self,
        enrichment_id: UUID,
        *,
        status: EnrichmentStatus,
        candidate_id: UUID | None,
        failure_code: str | None,
        credits_consumed: int | None,
    ) -> SourcingEnrichmentResponse:
        with self._session_factory() as session, session.begin():
            enrichment = self._repository.get_enrichment_for_update(session, enrichment_id)
            if enrichment is None:
                raise SourcingEnrichmentNotFoundError()
            current = EnrichmentStatus(enrichment.status)
            if current in _TERMINAL:
                return self._response(enrichment)
            now = datetime.now(UTC)
            enrichment.status = status.value
            enrichment.candidate_id = candidate_id
            enrichment.failure_code = failure_code
            enrichment.credits_consumed = credits_consumed
            enrichment.completed_at = now
            enrichment.updated_at = now
            sourcing_result = self._repository.get_result_for_update(
                session,
                enrichment.sourcing_result_id,
            )
            if sourcing_result is not None and candidate_id is not None:
                sourcing_result.candidate_id = candidate_id
                sourcing_result.updated_at = now
            session.flush()
            return self._response(enrichment)

    @staticmethod
    def _select_phone(phones: list[ProviderPhoneNumber]) -> str | None:
        priority = {"mobile": 0, "work_direct": 1}
        ordered = sorted(
            phones,
            key=lambda phone: (priority.get(phone.type_code or "", 2), phone.position),
        )
        for phone in ordered:
            if phone.status_code != "valid_number":
                continue
            value = phone.sanitized_number or phone.raw_number
            if value is None:
                continue
            try:
                normalized = normalize_phone_e164(value)
            except ValueError:
                continue
            if isinstance(normalized, str):
                return normalized
        return None

    @staticmethod
    def _response(enrichment: SourcingEnrichment) -> SourcingEnrichmentResponse:
        return SourcingEnrichmentResponse(
            id=enrichment.id,
            sourcing_result_id=enrichment.sourcing_result_id,
            provider=enrichment.provider,
            status=EnrichmentStatus(enrichment.status),
            candidate_id=enrichment.candidate_id,
            provider_request_id=enrichment.provider_request_id,
            credits_consumed=enrichment.credits_consumed,
            failure_code=enrichment.failure_code,
            retry_after_seconds=enrichment.retry_after_seconds,
            requested_at=enrichment.requested_at,
            completed_at=enrichment.completed_at,
            created_at=enrichment.created_at,
            updated_at=enrichment.updated_at,
        )
