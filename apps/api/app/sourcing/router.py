"""FastAPI routes for Job-bound search history, enrichment, and signed Apollo callbacks."""

from __future__ import annotations

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, status

from app.core.config import get_settings
from app.integrations.apollo.people import ApolloPeopleProvider
from app.sourcing.dependencies import get_sourcing_service, get_sourcing_webhook_service
from app.sourcing.errors import SourcingProviderNotConfiguredError
from app.sourcing.schemas import (
    SourcingEnrichmentResponse,
    SourcingRunDetailResponse,
    SourcingRunListResponse,
    StartSourcingRunRequest,
)
from app.sourcing.service import SourcingService
from app.sourcing.webhooks import (
    SourcingWebhookService,
    verify_apollo_webhook_signature,
)

router = APIRouter(tags=["sourcing"])


@router.post(
    "/api/v1/jobs/{job_id}/sourcing-runs",
    response_model=SourcingRunDetailResponse,
    status_code=status.HTTP_201_CREATED,
)
def start_sourcing_run(
    job_id: UUID,
    request: StartSourcingRunRequest,
    service: Annotated[SourcingService, Depends(get_sourcing_service)],
) -> SourcingRunDetailResponse:
    """Start one bounded Apollo people search from the currently approved Job definition."""

    return service.start_search(job_id, result_limit=request.result_limit)


@router.get(
    "/api/v1/jobs/{job_id}/sourcing-runs",
    response_model=SourcingRunListResponse,
)
def list_sourcing_runs(
    job_id: UUID,
    service: Annotated[SourcingService, Depends(get_sourcing_service)],
) -> SourcingRunListResponse:
    """List historical sourcing runs for one Job regardless of its current edit state."""

    return service.list_runs_for_job(job_id)


@router.get(
    "/api/v1/sourcing-runs/{run_id}",
    response_model=SourcingRunDetailResponse,
)
def get_sourcing_run(
    run_id: UUID,
    service: Annotated[SourcingService, Depends(get_sourcing_service)],
) -> SourcingRunDetailResponse:
    """Return persisted sourcing mapping diagnostics, evidence, and enrichment states."""

    return service.get_run(run_id)


@router.post(
    "/api/v1/sourcing-runs/{run_id}/retry",
    response_model=SourcingRunDetailResponse,
)
def retry_sourcing_run(
    run_id: UUID,
    service: Annotated[SourcingService, Depends(get_sourcing_service)],
) -> SourcingRunDetailResponse:
    """Safely repeat the exact persisted read-only provider query for an eligible run."""

    return service.retry_search(run_id)


@router.post(
    "/api/v1/sourcing-results/{result_id}/enrich",
    response_model=SourcingEnrichmentResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def enrich_sourcing_result(
    result_id: UUID,
    service: Annotated[SourcingService, Depends(get_sourcing_service)],
) -> SourcingEnrichmentResponse:
    """Enqueue at most one deliberate contact-enrichment operation for a selected result."""

    return service.request_enrichment(result_id)


@router.get(
    "/api/v1/sourcing-enrichments/{enrichment_id}",
    response_model=SourcingEnrichmentResponse,
)
def get_sourcing_enrichment(
    enrichment_id: UUID,
    service: Annotated[SourcingService, Depends(get_sourcing_service)],
) -> SourcingEnrichmentResponse:
    """Return current credit-aware enrichment state without duplicating Candidate contact PII."""

    return service.get_enrichment(enrichment_id)


@router.post(
    "/api/v1/webhooks/apollo/people-enrichment/{enrichment_id}/{signature}",
    response_model=SourcingEnrichmentResponse,
)
def receive_apollo_phone_webhook(
    enrichment_id: UUID,
    signature: str,
    payload: dict[str, Any],
    service: Annotated[SourcingWebhookService, Depends(get_sourcing_webhook_service)],
) -> SourcingEnrichmentResponse:
    """Verify and idempotently finalize an Apollo native phone-enrichment callback."""

    settings = get_settings()
    if not settings.apollo_webhook_signing_secret:
        raise SourcingProviderNotConfiguredError()
    verify_apollo_webhook_signature(
        secret=settings.apollo_webhook_signing_secret,
        enrichment_id=enrichment_id,
        signature=signature,
    )
    normalized = ApolloPeopleProvider.parse_phone_result(payload)
    return service.finalize_phone_result(enrichment_id, normalized)
