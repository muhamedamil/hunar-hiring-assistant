"""Business services for Job-bound people search and deliberate enrichment requests."""

from __future__ import annotations

import time
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.retry import (
    ProviderAuthenticationError,
    ProviderError,
    ProviderInvalidResponseError,
    ProviderPermanentError,
    ProviderRateLimitError,
    ProviderTransientError,
    ProviderTransportError,
)
from app.jobs.service import JobService
from app.sourcing.errors import (
    SearchRetryNotAllowedError,
    SourcingEnrichmentNotFoundError,
    SourcingProviderError,
    SourcingProviderNotConfiguredError,
    SourcingResultNotFoundError,
    SourcingRunNotFoundError,
)
from app.sourcing.mapping import MAPPING_VERSION, build_search_mapping
from app.sourcing.models import SourcingEnrichment, SourcingResult, SourcingRun
from app.sourcing.prioritization import assess_enrichment_priority
from app.sourcing.provider import PeopleSearchProvider
from app.sourcing.repository import SourcingRepository
from app.sourcing.schemas import (
    CandidateProfessionalEvidence,
    EnrichmentStatus,
    MatchingProfessionalEvidenceSource,
    PhoneAvailability,
    ProviderSearchPage,
    ProviderSearchQuery,
    ResolvedSourcingCandidateEvidenceSource,
    SourcingEnrichmentResponse,
    SourcingResultResponse,
    SourcingRunDetailResponse,
    SourcingRunListResponse,
    SourcingRunStatus,
    SourcingRunSummaryResponse,
    SourcingSearchCriteria,
)
from app.work_items.schemas import WorkItemCreate
from app.work_items.service import WorkItemService

_SEARCH_RETRY_WAIT_CAP_SECONDS = 10.0


class SourcingService:
    """Own sourcing search state, approved-Job binding, and enrichment enqueue semantics."""

    def __init__(
        self,
        session: Session,
        *,
        search_provider: PeopleSearchProvider | None,
        repository: SourcingRepository | None = None,
        work_items: WorkItemService | None = None,
        search_stale_seconds: int = 300,
        enrichment_configured: bool | None = None,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        self._session = session
        self._search_provider = search_provider
        self._repository = repository or SourcingRepository()
        self._work_items = work_items or WorkItemService()
        self._search_stale_seconds = search_stale_seconds
        self._enrichment_configured = (
            search_provider is not None
            if enrichment_configured is None
            else enrichment_configured
        )
        self._sleeper = sleeper

    def start_search(self, job_id: UUID, *, result_limit: int) -> SourcingRunDetailResponse:
        """Atomically bind a run to a currently READY Job, then search outside the transaction."""

        provider = self._require_search_provider()
        with self._session.begin():
            definition = JobService(self._session).lock_ready_definition_for_downstream_binding(
                job_id
            )
            criteria, query = build_search_mapping(definition, result_limit=result_limit)
            now = datetime.now(UTC)
            run = SourcingRun(
                job_id=definition.job_id,
                definition_version=definition.version,
                provider="apollo",
                status=SourcingRunStatus.SEARCHING.value,
                criteria=criteria.model_dump(mode="json"),
                provider_query=query.model_dump(mode="json"),
                mapping_version=MAPPING_VERSION,
                result_limit=result_limit,
                result_count=0,
                attempt_count=1,
                search_generation=1,
                started_at=now,
                updated_at=now,
            )
            self._repository.create_run(self._session, run)
            run_id = run.id
            search_generation = run.search_generation

        self._execute_search(
            run_id,
            query,
            provider=provider,
            allow_auto_retry=True,
            search_generation=search_generation,
        )
        return self.get_run(run_id)

    def retry_search(self, run_id: UUID) -> SourcingRunDetailResponse:
        """Safely repeat the exact persisted read-only provider query for an eligible run."""

        provider = self._require_search_provider()
        with self._session.begin():
            run = self._require_locked_run(run_id)
            if not self._is_retryable_search_state(run):
                raise SearchRetryNotAllowedError()
            query = ProviderSearchQuery.model_validate(run.provider_query)
            run.status = SourcingRunStatus.SEARCHING.value
            run.failure_code = None
            run.retry_after_seconds = None
            run.completed_at = None
            run.attempt_count += 1
            run.search_generation += 1
            run.started_at = datetime.now(UTC)
            run.updated_at = run.started_at
            search_generation = run.search_generation
            self._session.flush()

        self._execute_search(
            run_id,
            query,
            provider=provider,
            allow_auto_retry=True,
            search_generation=search_generation,
        )
        return self.get_run(run_id)

    def list_runs_for_job(self, job_id: UUID) -> SourcingRunListResponse:
        """Return historical sourcing runs for one Job without rechecking current Job status."""

        runs = self._repository.list_runs_for_job(self._session, job_id)
        return SourcingRunListResponse(
            items=[self._to_run_summary(run) for run in runs]
        )

    def get_run(self, run_id: UUID) -> SourcingRunDetailResponse:
        """Return one run with persisted mapping diagnostics, evidence, and enrichment state."""

        run = self._repository.get_run(self._session, run_id)
        if run is None:
            raise SourcingRunNotFoundError()
        results = self._repository.list_results(self._session, run.id)
        enrichments = self._repository.list_enrichments_for_run(self._session, run.id)
        return self._to_run_detail(run, results, enrichments)

    def request_enrichment(self, result_id: UUID) -> SourcingEnrichmentResponse:
        """Create at most one logical enrichment and enqueue its provider side effect once."""

        try:
            with self._session.begin():
                result = self._repository.get_result_for_update(self._session, result_id)
                if result is None:
                    raise SourcingResultNotFoundError()
                existing = self._repository.get_enrichment_by_result(self._session, result.id)
                if existing is not None:
                    return self._to_enrichment_response(existing)
                if not self._enrichment_configured:
                    raise SourcingProviderNotConfiguredError()

                now = datetime.now(UTC)
                enrichment = SourcingEnrichment(
                    sourcing_result_id=result.id,
                    provider="apollo",
                    status=EnrichmentStatus.PENDING.value,
                    attempt_count=0,
                    updated_at=now,
                )
                self._repository.create_enrichment(self._session, enrichment)
                self._work_items.enqueue(
                    self._session,
                    WorkItemCreate(
                        work_type="apollo_people_enrichment",
                        entity_type="sourcing_enrichment",
                        entity_id=enrichment.id,
                        payload={},
                        dedupe_key=f"apollo-people-enrichment:{enrichment.id}",
                        max_attempts=2,
                    ),
                )
                response = self._to_enrichment_response(enrichment)
        except IntegrityError:
            self._session.rollback()
            existing = self._repository.get_enrichment_by_result(self._session, result_id)
            if existing is None:
                raise
            return self._to_enrichment_response(existing)

        return response

    def get_enrichment(self, enrichment_id: UUID) -> SourcingEnrichmentResponse:
        """Return one enrichment state without exposing Candidate contact PII."""

        enrichment = self._repository.get_enrichment(self._session, enrichment_id)
        if enrichment is None:
            raise SourcingEnrichmentNotFoundError()
        return self._to_enrichment_response(enrichment)

    def get_resolved_candidate_evidence_source(
        self,
        result_id: UUID,
    ) -> ResolvedSourcingCandidateEvidenceSource | None:
        """Return resolved Candidate provenance even when professional evidence is absent."""

        result = self._repository.get_result(self._session, result_id)
        if result is None:
            raise SourcingResultNotFoundError()
        if result.candidate_id is None:
            return None
        run = self._repository.get_run(self._session, result.sourcing_run_id)
        if run is None:
            raise RuntimeError("Sourcing result references a missing sourcing run")
        enrichment = self._repository.get_enrichment_by_result(self._session, result.id)
        professional_evidence = None
        evidence_version = None
        if enrichment is not None:
            professional_evidence = (
                CandidateProfessionalEvidence.model_validate(enrichment.professional_evidence)
                if enrichment.professional_evidence is not None
                else None
            )
            evidence_version = enrichment.evidence_version
        return ResolvedSourcingCandidateEvidenceSource(
            candidate_id=result.candidate_id,
            sourcing_result_id=result.id,
            sourcing_run_id=run.id,
            job_id=run.job_id,
            definition_version=run.definition_version,
            professional_evidence=professional_evidence,
            evidence_version=evidence_version,
        )

    def get_matching_evidence_for_sourcing_result(
        self,
        result_id: UUID,
    ) -> MatchingProfessionalEvidenceSource | None:
        """Return normalized professional evidence with its exact sourcing provenance."""

        source = self._repository.get_evidence_source_for_result(self._session, result_id)
        if source is None:
            return None
        enrichment, result, run = source
        if (
            enrichment.candidate_id is None
            or enrichment.professional_evidence is None
            or enrichment.evidence_version is None
        ):
            return None
        return MatchingProfessionalEvidenceSource(
            candidate_id=enrichment.candidate_id,
            sourcing_result_id=result.id,
            sourcing_run_id=run.id,
            job_id=run.job_id,
            definition_version=run.definition_version,
            professional_evidence=CandidateProfessionalEvidence.model_validate(
                enrichment.professional_evidence
            ),
            evidence_version=enrichment.evidence_version,
        )

    def _execute_search(
        self,
        run_id: UUID,
        query: ProviderSearchQuery,
        *,
        provider: PeopleSearchProvider,
        allow_auto_retry: bool,
        search_generation: int,
    ) -> None:
        attempts_this_execution = 0
        while True:
            attempts_this_execution += 1
            try:
                page = provider.search_people(query)
                self._validate_search_page(page, requested_limit=query.per_page)
            except ProviderRateLimitError as exc:
                retry_after = exc.retry_after_seconds
                should_retry = (
                    allow_auto_retry
                    and attempts_this_execution == 1
                    and retry_after is not None
                    and retry_after <= _SEARCH_RETRY_WAIT_CAP_SECONDS
                )
                if should_retry and retry_after is not None:
                    if not self._record_additional_search_attempt(run_id, search_generation):
                        return
                    self._sleeper(retry_after)
                    continue
                if not self._fail_run(
                    run_id,
                    search_generation=search_generation,
                    code="APOLLO_SEARCH_RATE_LIMITED",
                    retry_after_seconds=self._seconds(retry_after),
                ):
                    return
                raise SourcingProviderError(
                    code="APOLLO_SEARCH_RATE_LIMITED",
                    message="Apollo people search is rate limited.",
                    status_code=429,
                    details={"run_id": str(run_id), "retry_after_seconds": retry_after},
                ) from exc
            except (ProviderTransientError, ProviderTransportError) as exc:
                if allow_auto_retry and attempts_this_execution == 1:
                    if not self._record_additional_search_attempt(run_id, search_generation):
                        return
                    continue
                if not self._fail_run(
                    run_id,
                    search_generation=search_generation,
                    code="APOLLO_SEARCH_UNAVAILABLE",
                ):
                    return
                raise SourcingProviderError(
                    code="APOLLO_SEARCH_UNAVAILABLE",
                    message="Apollo people search is temporarily unavailable.",
                    details={"run_id": str(run_id)},
                ) from exc
            except ProviderAuthenticationError as exc:
                if not self._fail_run(
                    run_id,
                    search_generation=search_generation,
                    code="APOLLO_AUTHENTICATION_ERROR",
                ):
                    return
                raise SourcingProviderError(
                    code="APOLLO_AUTHENTICATION_ERROR",
                    message="Apollo authentication failed.",
                    details={"run_id": str(run_id)},
                ) from exc
            except (ProviderPermanentError, ProviderInvalidResponseError) as exc:
                if not self._fail_run(
                    run_id,
                    search_generation=search_generation,
                    code=exc.code,
                ):
                    return
                raise SourcingProviderError(
                    code=exc.code,
                    message="Apollo rejected the people search or returned invalid results.",
                    status_code=502,
                    details={"run_id": str(run_id)},
                ) from exc
            except ProviderError as exc:
                if not self._fail_run(
                    run_id,
                    search_generation=search_generation,
                    code=exc.code,
                ):
                    return
                raise SourcingProviderError(
                    code=exc.code,
                    message="Apollo people search failed.",
                    details={"run_id": str(run_id)},
                ) from exc
            else:
                self._complete_run(run_id, page, search_generation=search_generation)
                return

    @staticmethod
    def _validate_search_page(page: ProviderSearchPage, *, requested_limit: int) -> None:
        if len(page.hits) > requested_limit:
            raise ProviderInvalidResponseError(
                code="APOLLO_SEARCH_RESULT_LIMIT_EXCEEDED",
                message="Provider returned more search results than requested.",
            )
        ids = [hit.external_person_id for hit in page.hits]
        if len(ids) != len(set(ids)):
            raise ProviderInvalidResponseError(
                code="APOLLO_SEARCH_DUPLICATE_PERSON",
                message="Provider returned duplicate people in one search page.",
            )

    def _complete_run(
        self,
        run_id: UUID,
        page: ProviderSearchPage,
        *,
        search_generation: int,
    ) -> bool:
        with self._session.begin():
            run = self._require_locked_run(run_id)
            if not self._owns_search_generation(run, search_generation):
                return False
            results = [
                SourcingResult(
                    sourcing_run_id=run.id,
                    provider_person_id=hit.external_person_id,
                    result_position=position,
                    first_name=hit.first_name,
                    last_name_obfuscated=hit.last_name_obfuscated,
                    current_title=hit.title,
                    organization_name=hit.organization_name,
                    email_available=hit.email_available,
                    phone_availability=hit.phone_availability.value,
                    provider_last_refreshed_at=hit.last_refreshed_at,
                    updated_at=datetime.now(UTC),
                )
                for position, hit in enumerate(page.hits, start=1)
            ]
            self._repository.insert_results(self._session, results)
            now = datetime.now(UTC)
            run.status = SourcingRunStatus.COMPLETED.value
            run.result_count = len(results)
            run.provider_total_matches = page.total_matches
            run.completed_at = now
            run.updated_at = now
            run.failure_code = None
            run.retry_after_seconds = None
            self._session.flush()
            return True

    def _fail_run(
        self,
        run_id: UUID,
        *,
        search_generation: int,
        code: str,
        retry_after_seconds: int | None = None,
    ) -> bool:
        with self._session.begin():
            run = self._require_locked_run(run_id)
            if not self._owns_search_generation(run, search_generation):
                return False
            run.status = SourcingRunStatus.FAILED.value
            now = datetime.now(UTC)
            run.failure_code = code
            run.retry_after_seconds = retry_after_seconds
            run.completed_at = now
            run.updated_at = now
            self._session.flush()
            return True

    def _record_additional_search_attempt(
        self,
        run_id: UUID,
        search_generation: int,
    ) -> bool:
        with self._session.begin():
            run = self._require_locked_run(run_id)
            if not self._owns_search_generation(run, search_generation):
                return False
            run.attempt_count += 1
            run.updated_at = datetime.now(UTC)
            self._session.flush()
            return True

    @staticmethod
    def _owns_search_generation(run: SourcingRun, search_generation: int) -> bool:
        return (
            SourcingRunStatus(run.status) is SourcingRunStatus.SEARCHING
            and run.search_generation == search_generation
        )

    def _is_retryable_search_state(self, run: SourcingRun) -> bool:
        if SourcingRunStatus(run.status) is SourcingRunStatus.FAILED:
            return True
        if SourcingRunStatus(run.status) is not SourcingRunStatus.SEARCHING:
            return False
        cutoff = datetime.now(UTC) - timedelta(seconds=self._search_stale_seconds)
        return run.started_at < cutoff

    def _require_search_provider(self) -> PeopleSearchProvider:
        if self._search_provider is None:
            raise SourcingProviderNotConfiguredError()
        return self._search_provider

    def _require_locked_run(self, run_id: UUID) -> SourcingRun:
        run = self._repository.get_run_for_update(self._session, run_id)
        if run is None:
            raise SourcingRunNotFoundError()
        return run

    @staticmethod
    def _seconds(value: float | None) -> int | None:
        return None if value is None else max(0, int(round(value)))

    @staticmethod
    def _to_run_summary(run: SourcingRun) -> SourcingRunSummaryResponse:
        return SourcingRunSummaryResponse(
            id=run.id,
            job_id=run.job_id,
            definition_version=run.definition_version,
            provider=run.provider,
            status=SourcingRunStatus(run.status),
            result_limit=run.result_limit,
            result_count=run.result_count,
            provider_total_matches=run.provider_total_matches,
            failure_code=run.failure_code,
            retry_after_seconds=run.retry_after_seconds,
            created_at=run.created_at,
            completed_at=run.completed_at,
        )

    @staticmethod
    def _to_result_response(
        result: SourcingResult,
        criteria: SourcingSearchCriteria,
    ) -> SourcingResultResponse:
        assessment = assess_enrichment_priority(
            current_title=result.current_title,
            target_titles=criteria.titles,
            phone_availability=PhoneAvailability(result.phone_availability),
            email_available=result.email_available,
            locations_requested=bool(criteria.locations),
        )
        return SourcingResultResponse(
            id=result.id,
            sourcing_run_id=result.sourcing_run_id,
            provider_person_id=result.provider_person_id,
            result_position=result.result_position,
            first_name=result.first_name,
            last_name_obfuscated=result.last_name_obfuscated,
            current_title=result.current_title,
            organization_name=result.organization_name,
            email_available=result.email_available,
            phone_availability=PhoneAvailability(result.phone_availability),
            enrichment_priority=assessment.priority,
            enrichment_priority_reasons=assessment.reasons,
            enrichment_priority_algorithm_version=assessment.algorithm_version,
            candidate_id=result.candidate_id,
            created_at=result.created_at,
        )

    @staticmethod
    def _to_enrichment_response(
        enrichment: SourcingEnrichment,
    ) -> SourcingEnrichmentResponse:
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

    def _to_run_detail(
        self,
        run: SourcingRun,
        results: list[SourcingResult],
        enrichments: list[SourcingEnrichment],
    ) -> SourcingRunDetailResponse:
        criteria = SourcingSearchCriteria.model_validate(run.criteria)
        return SourcingRunDetailResponse(
            id=run.id,
            job_id=run.job_id,
            definition_version=run.definition_version,
            provider=run.provider,
            status=SourcingRunStatus(run.status),
            criteria=criteria,
            provider_query=ProviderSearchQuery.model_validate(run.provider_query),
            mapping_version=run.mapping_version,
            result_limit=run.result_limit,
            result_count=run.result_count,
            provider_total_matches=run.provider_total_matches,
            attempt_count=run.attempt_count,
            failure_code=run.failure_code,
            retry_after_seconds=run.retry_after_seconds,
            started_at=run.started_at,
            completed_at=run.completed_at,
            created_at=run.created_at,
            updated_at=run.updated_at,
            results=[self._to_result_response(result, criteria) for result in results],
            enrichments=[self._to_enrichment_response(item) for item in enrichments],
        )
