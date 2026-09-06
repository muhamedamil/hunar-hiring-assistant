"""Worker handlers for credit-aware Apollo enrichment and zero-credit poll recovery."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.candidates.errors import CandidateIdentityConflictError
from app.candidates.schemas import CandidateResponse, ExternalCandidateObservation
from app.candidates.service import CandidateService
from app.core.config import Settings
from app.core.retry import (
    AmbiguousWorkError,
    PermanentWorkError,
    ProviderAuthenticationError,
    ProviderInvalidResponseError,
    ProviderPermanentError,
    ProviderRateLimitError,
    ProviderTransientError,
    ProviderTransportError,
    RetryableWorkError,
)
from app.integrations.apollo.errors import ApolloAmbiguousEnrichmentError
from app.sourcing.errors import SourcingEnrichmentNotFoundError, SourcingResultNotFoundError
from app.sourcing.models import SourcingEnrichment
from app.sourcing.provider import PeopleEnrichmentProvider
from app.sourcing.repository import SourcingRepository
from app.sourcing.schemas import (
    PROFESSIONAL_EVIDENCE_VERSION,
    CandidateProfessionalEvidence,
    EnrichmentStatus,
    ProviderEnrichedPerson,
    ProviderPollStatus,
)
from app.sourcing.webhooks import SourcingWebhookService, sign_apollo_webhook
from app.work_items.models import WorkItem
from app.work_items.schemas import WorkItemCreate, WorkItemStatus
from app.work_items.service import WorkItemService

_TERMINAL = {
    EnrichmentStatus.COMPLETED,
    EnrichmentStatus.NOT_FOUND,
    EnrichmentStatus.FAILED,
    EnrichmentStatus.UNKNOWN,
    EnrichmentStatus.CONFLICT,
}


class SourcingWorkHandlers:
    """Execute Module 3 work items while preserving provider outcome certainty."""

    def __init__(
        self,
        *,
        session_factory: sessionmaker[Session],
        provider: PeopleEnrichmentProvider | None,
        settings: Settings,
        repository: SourcingRepository | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._provider = provider
        self._settings = settings
        self._repository = repository or SourcingRepository()
        self._webhooks = SourcingWebhookService(
            session_factory,
            repository=self._repository,
        )

    def handle_people_enrichment(self, item: WorkItem) -> None:
        """Start one credit-aware Apollo enrichment and persist a recoverable async state."""

        enrichment_id = self._entity_id(item)
        if self._provider is None:
            self._mark_failed(enrichment_id, code="APOLLO_NOT_CONFIGURED")
            raise PermanentWorkError(
                code="APOLLO_NOT_CONFIGURED",
                message="Apollo integration is not configured.",
            )
        provider = self._provider
        target = self._load_enrichment_target(enrichment_id)
        if target is None:
            return
        self._mark_requested(enrichment_id)
        webhook_url = self._webhook_url(enrichment_id)

        try:
            response = provider.enrich_person(
                external_person_id=target["provider_person_id"],
                webhook_url=webhook_url,
            )
        except ProviderRateLimitError as exc:
            self._retry_or_fail_enrichment(
                item,
                enrichment_id,
                code="APOLLO_ENRICHMENT_RATE_LIMITED",
                message="Apollo enrichment is rate limited.",
                retry_after_seconds=exc.retry_after_seconds,
            )
            return
        except ProviderTransportError as exc:
            if exc.operation_may_have_completed:
                self._mark_unknown(enrichment_id, code=exc.code)
                raise AmbiguousWorkError(
                    code=exc.code,
                    message="Apollo enrichment transport outcome is uncertain.",
                ) from exc
            self._retry_or_fail_enrichment(
                item,
                enrichment_id,
                code=exc.code,
                message="Apollo enrichment did not reach the provider.",
                retry_after_seconds=None,
            )
            return
        except (ProviderTransientError, ProviderInvalidResponseError) as exc:
            self._mark_unknown(enrichment_id, code=exc.code)
            raise AmbiguousWorkError(
                code=exc.code,
                message="Apollo enrichment may have completed; it was not retried.",
            ) from exc
        except ApolloAmbiguousEnrichmentError as exc:
            self._mark_unknown(enrichment_id, code=exc.code)
            raise AmbiguousWorkError(code=exc.code, message=exc.message) from exc
        except (ProviderAuthenticationError, ProviderPermanentError) as exc:
            self._mark_failed(enrichment_id, code=exc.code)
            raise PermanentWorkError(
                code=exc.code,
                message="Apollo rejected the enrichment request.",
            ) from exc

        if response.person is None:
            self._mark_not_found(enrichment_id)
            return

        try:
            candidate = self._resolve_candidate(response.person)
        except CandidateIdentityConflictError as exc:
            self._mark_conflict(enrichment_id)
            raise PermanentWorkError(
                code="CANDIDATE_IDENTITY_CONFLICT",
                message="Enriched Apollo identity conflicts with Candidate Core.",
            ) from exc

        assert response.request_id is not None
        self._mark_awaiting_phone(
            enrichment_id,
            candidate_id=candidate.id,
            request_id=response.request_id,
            professional_evidence=response.professional_evidence,
        )

    def handle_enrichment_poll(self, item: WorkItem) -> None:
        """Poll Apollo's zero-credit recovery endpoint until one terminal phone result exists."""

        enrichment_id = self._entity_id(item)
        if self._provider is None:
            self._record_retryable_failure(
                enrichment_id,
                code="APOLLO_POLL_NOT_CONFIGURED",
            )
            raise PermanentWorkError(
                code="APOLLO_POLL_NOT_CONFIGURED",
                message=(
                    "Apollo polling is not configured; the signed webhook remains authoritative."
                ),
            )
        provider = self._provider
        request_id = self._load_poll_request_id(enrichment_id)
        if request_id is None:
            return

        try:
            result = provider.poll_enrichment(request_id)
        except ProviderRateLimitError as exc:
            self._retry_or_fail_poll(
                item,
                enrichment_id,
                code="APOLLO_POLL_RATE_LIMITED",
                retry_after_seconds=exc.retry_after_seconds,
            )
            return
        except (ProviderTransientError, ProviderTransportError) as exc:
            self._retry_or_fail_poll(
                item,
                enrichment_id,
                code=exc.code,
                retry_after_seconds=None,
            )
            return
        except (
            ProviderAuthenticationError,
            ProviderPermanentError,
            ProviderInvalidResponseError,
        ) as exc:
            self._record_retryable_failure(enrichment_id, code=exc.code)
            raise PermanentWorkError(
                code=exc.code,
                message=(
                    "Apollo polling observer failed; the signed webhook remains authoritative."
                ),
            ) from exc

        if result.status is ProviderPollStatus.PENDING:
            self._retry_or_fail_poll(
                item,
                enrichment_id,
                code="APOLLO_POLL_RESULT_PENDING",
                retry_after_seconds=float(result.retry_after_seconds or 30),
            )
            return
        if result.status is ProviderPollStatus.TERMINAL_FAILURE:
            code = result.failure_code or "APOLLO_POLL_TERMINAL_FAILURE"
            self._mark_failed(enrichment_id, code=code)
            raise PermanentWorkError(
                code=code,
                message="Apollo can no longer recover this enrichment result.",
            )
        if result.phone_result is None:
            self._record_retryable_failure(
                enrichment_id,
                code="APOLLO_POLL_RESULT_INVALID",
            )
            raise PermanentWorkError(
                code="APOLLO_POLL_RESULT_INVALID",
                message=(
                    "Apollo poll completed without a usable result; the webhook may still arrive."
                ),
            )
        self._webhooks.finalize_phone_result(enrichment_id, result.phone_result)

    def reconcile_unknown_work(self) -> tuple[int, int]:
        """Converge stale UNKNOWN queue items into Module 3's operation-specific truth.

        Credit-consuming enrichment remains UNKNOWN and is never replayed. Polling is
        read-only, so a crashed poll may enqueue one new recovery generation keyed by
        the UNKNOWN work-item identifier.
        """

        unknown_enrichments = 0
        recovered_polls = 0
        with self._session_factory() as session, session.begin():
            statement = (
                select(WorkItem)
                .where(
                    WorkItem.status == WorkItemStatus.UNKNOWN.value,
                    WorkItem.work_type.in_(
                        ["apollo_people_enrichment", "apollo_enrichment_poll"]
                    ),
                    WorkItem.entity_type == "sourcing_enrichment",
                    WorkItem.entity_id.is_not(None),
                )
                .order_by(WorkItem.updated_at.asc(), WorkItem.id.asc())
            )
            for item in session.execute(statement).scalars():
                assert item.entity_id is not None
                enrichment = self._repository.get_enrichment_for_update(
                    session, item.entity_id
                )
                if enrichment is None:
                    continue
                status = EnrichmentStatus(enrichment.status)
                if item.work_type == "apollo_people_enrichment":
                    if status is EnrichmentStatus.PENDING:
                        now = datetime.now(UTC)
                        enrichment.status = EnrichmentStatus.UNKNOWN.value
                        enrichment.failure_code = "WORKER_LEASE_EXPIRED"
                        enrichment.completed_at = now
                        enrichment.updated_at = now
                        unknown_enrichments += 1
                    continue
                if status is not EnrichmentStatus.AWAITING_PHONE:
                    continue
                WorkItemService().enqueue(
                    session,
                    WorkItemCreate(
                        work_type="apollo_enrichment_poll",
                        entity_type="sourcing_enrichment",
                        entity_id=enrichment.id,
                        payload={},
                        dedupe_key=(
                            "apollo-enrichment-poll-recovery:"
                            f"{enrichment.id}:{item.id}"
                        ),
                        max_attempts=20,
                    ),
                )
                recovered_polls += 1
            session.flush()
        return unknown_enrichments, recovered_polls

    def _retry_or_fail_enrichment(
        self,
        item: WorkItem,
        enrichment_id: UUID,
        *,
        code: str,
        message: str,
        retry_after_seconds: float | None,
    ) -> None:
        """Retry a known-not-sent enrichment only while its bounded work budget remains."""

        if item.attempt_count >= item.max_attempts:
            self._mark_failed(
                enrichment_id,
                code="APOLLO_ENRICHMENT_ATTEMPTS_EXHAUSTED",
            )
            raise PermanentWorkError(
                code="APOLLO_ENRICHMENT_ATTEMPTS_EXHAUSTED",
                message="Apollo enrichment exhausted its safe bounded attempts.",
            )
        self._record_retryable_failure(
            enrichment_id,
            code=code,
            retry_after_seconds=self._seconds(retry_after_seconds),
        )
        raise RetryableWorkError(
            code=code,
            message=message,
            retry_after_seconds=retry_after_seconds,
        )

    def _load_enrichment_target(self, enrichment_id: UUID) -> dict[str, str] | None:
        with self._session_factory() as session, session.begin():
            enrichment = self._repository.get_enrichment_for_update(session, enrichment_id)
            if enrichment is None:
                raise SourcingEnrichmentNotFoundError()
            if EnrichmentStatus(enrichment.status) in _TERMINAL:
                return None
            if EnrichmentStatus(enrichment.status) is EnrichmentStatus.AWAITING_PHONE:
                return None
            result = self._repository.get_result(session, enrichment.sourcing_result_id)
            if result is None:
                raise SourcingResultNotFoundError()
            return {"provider_person_id": result.provider_person_id}

    def _load_poll_request_id(self, enrichment_id: UUID) -> int | None:
        with self._session_factory() as session:
            enrichment = self._repository.get_enrichment(session, enrichment_id)
            if enrichment is None:
                raise SourcingEnrichmentNotFoundError()
            status = EnrichmentStatus(enrichment.status)
            if status in _TERMINAL:
                return None
            if status is not EnrichmentStatus.AWAITING_PHONE:
                raise PermanentWorkError(
                    code="ENRICHMENT_NOT_AWAITING_PHONE",
                    message="Poll work does not belong to an awaiting-phone enrichment.",
                )
            if enrichment.provider_request_id is None:
                raise PermanentWorkError(
                    code="APOLLO_REQUEST_ID_MISSING",
                    message="Awaiting-phone enrichment has no Apollo request ID.",
                )
            return enrichment.provider_request_id

    def _resolve_candidate(self, person: ProviderEnrichedPerson) -> CandidateResponse:
        """Resolve one validated Apollo person through Candidate Core only."""
        with self._session_factory() as session:
            return CandidateService(session).resolve_external_candidate(
                ExternalCandidateObservation(
                    provider="apollo",
                    external_person_id=person.external_person_id,
                    profile_url=person.linkedin_url,
                    full_name=person.full_name,
                    current_title=person.title,
                    current_company=person.company,
                    location=person.location,
                    email=person.email,
                    phone=None,
                )
            )

    def _mark_requested(self, enrichment_id: UUID) -> None:
        with self._session_factory() as session, session.begin():
            enrichment = self._require_locked_enrichment(session, enrichment_id)
            if EnrichmentStatus(enrichment.status) is not EnrichmentStatus.PENDING:
                return
            now = datetime.now(UTC)
            enrichment.requested_at = enrichment.requested_at or now
            enrichment.attempt_count += 1
            enrichment.failure_code = None
            enrichment.retry_after_seconds = None
            enrichment.updated_at = now
            session.flush()

    def _mark_awaiting_phone(
        self,
        enrichment_id: UUID,
        *,
        candidate_id: UUID,
        request_id: int,
        professional_evidence: CandidateProfessionalEvidence | None,
    ) -> None:
        with self._session_factory() as session, session.begin():
            enrichment = self._require_locked_enrichment(session, enrichment_id)
            if EnrichmentStatus(enrichment.status) in _TERMINAL:
                return
            now = datetime.now(UTC)
            enrichment.status = EnrichmentStatus.AWAITING_PHONE.value
            enrichment.candidate_id = candidate_id
            enrichment.provider_request_id = request_id
            if professional_evidence is not None:
                enrichment.professional_evidence = professional_evidence.model_dump(mode="json")
                enrichment.evidence_version = PROFESSIONAL_EVIDENCE_VERSION
            enrichment.failure_code = None
            enrichment.retry_after_seconds = None
            enrichment.updated_at = now
            result = self._repository.get_result_for_update(
                session,
                enrichment.sourcing_result_id,
            )
            if result is not None:
                result.candidate_id = candidate_id
                result.updated_at = now
            WorkItemService().enqueue(
                session,
                WorkItemCreate(
                    work_type="apollo_enrichment_poll",
                    entity_type="sourcing_enrichment",
                    entity_id=enrichment.id,
                    payload={},
                    dedupe_key=f"apollo-enrichment-poll:{enrichment.id}",
                    max_attempts=20,
                ),
            )
            session.flush()

    def _mark_not_found(self, enrichment_id: UUID) -> None:
        self._mark_terminal(
            enrichment_id,
            status=EnrichmentStatus.NOT_FOUND,
            code="APOLLO_PERSON_NOT_FOUND",
        )

    def _mark_conflict(self, enrichment_id: UUID) -> None:
        self._mark_terminal(
            enrichment_id,
            status=EnrichmentStatus.CONFLICT,
            code="CANDIDATE_IDENTITY_CONFLICT",
        )

    def _mark_failed(self, enrichment_id: UUID, *, code: str) -> None:
        self._mark_terminal(enrichment_id, status=EnrichmentStatus.FAILED, code=code)

    def _mark_unknown(self, enrichment_id: UUID, *, code: str) -> None:
        self._mark_terminal(enrichment_id, status=EnrichmentStatus.UNKNOWN, code=code)

    def _mark_terminal(
        self,
        enrichment_id: UUID,
        *,
        status: EnrichmentStatus,
        code: str,
    ) -> None:
        with self._session_factory() as session, session.begin():
            enrichment = self._require_locked_enrichment(session, enrichment_id)
            if EnrichmentStatus(enrichment.status) in _TERMINAL:
                return
            now = datetime.now(UTC)
            enrichment.status = status.value
            enrichment.failure_code = code
            enrichment.completed_at = now
            enrichment.updated_at = now
            session.flush()

    def _record_retryable_failure(
        self,
        enrichment_id: UUID,
        *,
        code: str,
        retry_after_seconds: int | None = None,
    ) -> None:
        with self._session_factory() as session, session.begin():
            enrichment = self._require_locked_enrichment(session, enrichment_id)
            enrichment.failure_code = code
            enrichment.retry_after_seconds = retry_after_seconds
            enrichment.updated_at = datetime.now(UTC)
            session.flush()

    def _retry_or_fail_poll(
        self,
        item: WorkItem,
        enrichment_id: UUID,
        *,
        code: str,
        retry_after_seconds: float | None,
    ) -> None:
        if item.attempt_count >= item.max_attempts:
            self._record_retryable_failure(
                enrichment_id,
                code="APOLLO_POLL_ATTEMPTS_EXHAUSTED",
            )
            raise PermanentWorkError(
                code="APOLLO_POLL_ATTEMPTS_EXHAUSTED",
                message=(
                    "Apollo polling exhausted its bounded attempts; the webhook remains valid."
                ),
            )
        self._record_retryable_failure(
            enrichment_id,
            code=code,
            retry_after_seconds=self._seconds(retry_after_seconds),
        )
        raise RetryableWorkError(
            code=code,
            message="Apollo phone-enrichment result is not ready yet.",
            retry_after_seconds=retry_after_seconds,
        )

    def _webhook_url(self, enrichment_id: UUID) -> str:
        base_url = self._settings.apollo_webhook_base_url
        secret = self._settings.apollo_webhook_signing_secret
        if not base_url or not secret:
            self._mark_failed(enrichment_id, code="APOLLO_WEBHOOK_NOT_CONFIGURED")
            raise PermanentWorkError(
                code="APOLLO_WEBHOOK_NOT_CONFIGURED",
                message="Apollo webhook base URL/signing secret is not configured.",
            )
        signature = sign_apollo_webhook(secret, enrichment_id)
        return (
            f"{base_url.rstrip('/')}/api/v1/webhooks/apollo/people-enrichment/"
            f"{enrichment_id}/{signature}"
        )

    def _require_locked_enrichment(
        self, session: Session, enrichment_id: UUID
    ) -> SourcingEnrichment:
        """Return one locked enrichment or fail with the stable Module 3 not-found error."""
        enrichment = self._repository.get_enrichment_for_update(session, enrichment_id)
        if enrichment is None:
            raise SourcingEnrichmentNotFoundError()
        return enrichment

    @staticmethod
    def _entity_id(item: WorkItem) -> UUID:
        if item.entity_type != "sourcing_enrichment" or item.entity_id is None:
            raise PermanentWorkError(
                code="INVALID_SOURCING_WORK_ITEM",
                message="Sourcing worker item is missing its enrichment identifier.",
            )
        return item.entity_id

    @staticmethod
    def _seconds(value: float | None) -> int | None:
        return None if value is None else max(0, int(round(value)))
