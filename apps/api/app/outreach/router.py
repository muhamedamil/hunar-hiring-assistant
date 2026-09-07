"""FastAPI routes for Module 5 preparation and immutable outreach requests."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status

from app.outreach.dependencies import get_outreach_service
from app.outreach.schemas import (
    OutreachPreparationResponse,
    OutreachRequestListResponse,
    OutreachRequestResponse,
    PrepareOutreachRequest,
)
from app.outreach.service import OutreachService

router = APIRouter(tags=["outreach"])


@router.get(
    "/api/v1/job-candidates/{job_candidate_id}/outreach-preparation",
    response_model=OutreachPreparationResponse,
)
def get_outreach_preparation(
    job_candidate_id: UUID,
    service: Annotated[OutreachService, Depends(get_outreach_service)],
) -> OutreachPreparationResponse:
    """Return current non-persisted outreach preparation with masked contact."""

    return service.get_preparation(job_candidate_id)


@router.post(
    "/api/v1/job-candidates/{job_candidate_id}/outreach-requests",
    response_model=OutreachRequestResponse,
    status_code=status.HTTP_201_CREATED,
)
def prepare_outreach(
    job_candidate_id: UUID,
    request: PrepareOutreachRequest,
    service: Annotated[OutreachService, Depends(get_outreach_service)],
) -> OutreachRequestResponse:
    """Confirm one immutable, idempotent outreach execution context."""

    return service.prepare_outreach(
        job_candidate_id,
        preparation_token=request.preparation_token,
        screening_questions=request.screening_questions,
    )


@router.get("/api/v1/outreach-requests", response_model=OutreachRequestListResponse)
def list_outreach_requests(
    service: Annotated[OutreachService, Depends(get_outreach_service)],
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> OutreachRequestListResponse:
    """List immutable outreach requests with derived readiness."""

    return service.list_outreach_requests(limit=limit, offset=offset)


@router.get(
    "/api/v1/outreach-requests/{outreach_request_id}",
    response_model=OutreachRequestResponse,
)
def get_outreach_request(
    outreach_request_id: UUID,
    service: Annotated[OutreachService, Depends(get_outreach_service)],
) -> OutreachRequestResponse:
    """Return one immutable outreach request with derived readiness."""

    return service.get_outreach_request(outreach_request_id)
