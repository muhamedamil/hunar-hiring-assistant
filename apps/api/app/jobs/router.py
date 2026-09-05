"""FastAPI routes for recruiter Job definition, approval, and optional JD analysis."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status

from app.jobs.analysis import JobAnalysisService
from app.jobs.dependencies import get_job_analysis_service, get_job_service
from app.jobs.schemas import (
    JobAnalysisProposal,
    JobAnalysisRequest,
    JobCreateRequest,
    JobListResponse,
    JobReadyRequest,
    JobReopenRequest,
    JobResponse,
    JobStatus,
    JobUpdateRequest,
)
from app.jobs.service import JobService

router = APIRouter(prefix="/api/v1/jobs", tags=["jobs"])


@router.post("/analyze", response_model=JobAnalysisProposal)
def analyze_job_description(
    request: JobAnalysisRequest,
    service: Annotated[JobAnalysisService, Depends(get_job_analysis_service)],
) -> JobAnalysisProposal:
    """Return an editable AI proposal without creating or mutating a Job."""

    return service.analyze(title=request.title, description=request.description)


@router.post("", response_model=JobResponse, status_code=status.HTTP_201_CREATED)
def create_job(
    request: JobCreateRequest,
    service: Annotated[JobService, Depends(get_job_service)],
) -> JobResponse:
    """Create a new mutable DRAFT Job."""

    return service.create_draft(request)


@router.get("", response_model=JobListResponse)
def list_jobs(
    service: Annotated[JobService, Depends(get_job_service)],
    job_status: Annotated[JobStatus | None, Query(alias="status")] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> JobListResponse:
    """List Jobs using bounded offset pagination and an optional status filter."""

    return service.list_jobs(status=job_status, limit=limit, offset=offset)


@router.get("/{job_id}", response_model=JobResponse)
def get_job(
    job_id: UUID,
    service: Annotated[JobService, Depends(get_job_service)],
) -> JobResponse:
    """Return the current mutable Job aggregate."""

    return service.get_job(job_id)


@router.patch("/{job_id}", response_model=JobResponse)
def update_job(
    job_id: UUID,
    request: JobUpdateRequest,
    service: Annotated[JobService, Depends(get_job_service)],
) -> JobResponse:
    """Replace a DRAFT definition using optimistic concurrency."""

    return service.save_draft(
        job_id,
        expected_revision=request.expected_revision,
        definition=request.definition,
    )


@router.post("/{job_id}/ready", response_model=JobResponse)
def mark_job_ready(
    job_id: UUID,
    request: JobReadyRequest,
    service: Annotated[JobService, Depends(get_job_service)],
) -> JobResponse:
    """Atomically save and approve the exact visible Job definition."""

    return service.mark_ready(
        job_id,
        expected_revision=request.expected_revision,
        definition=request.definition,
    )


@router.post("/{job_id}/reopen", response_model=JobResponse)
def reopen_job(
    job_id: UUID,
    request: JobReopenRequest,
    service: Annotated[JobService, Depends(get_job_service)],
) -> JobResponse:
    """Reopen a READY Job for editing without altering prior approved snapshots."""

    return service.reopen(job_id, expected_revision=request.expected_revision)
