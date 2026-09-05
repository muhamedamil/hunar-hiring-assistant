"""FastAPI routes for global Candidate creation, listing, detail, and profile editing."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status

from app.candidates.dependencies import get_candidate_service
from app.candidates.schemas import (
    CandidateCreateRequest,
    CandidateListResponse,
    CandidateResponse,
    CandidateUpdateRequest,
)
from app.candidates.service import CandidateService

router = APIRouter(prefix="/api/v1/candidates", tags=["candidates"])


@router.post("", response_model=CandidateResponse, status_code=status.HTTP_201_CREATED)
def create_candidate(
    request: CandidateCreateRequest,
    service: Annotated[CandidateService, Depends(get_candidate_service)],
) -> CandidateResponse:
    """Create one manual Candidate without attaching it to a Job."""

    return service.create_manual_candidate(request)


@router.get("", response_model=CandidateListResponse)
def list_candidates(
    service: Annotated[CandidateService, Depends(get_candidate_service)],
    query: Annotated[str | None, Query(alias="q", min_length=1, max_length=100)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> CandidateListResponse:
    """List Candidates using a contact-minimized projection and optional profile search."""

    normalized_query = query.strip() if query else None
    return service.list_candidates(query=normalized_query or None, limit=limit, offset=offset)


@router.get("/{candidate_id}", response_model=CandidateResponse)
def get_candidate(
    candidate_id: UUID,
    service: Annotated[CandidateService, Depends(get_candidate_service)],
) -> CandidateResponse:
    """Return full Candidate detail including canonical contact values."""

    return service.get_candidate(candidate_id)


@router.patch("/{candidate_id}", response_model=CandidateResponse)
def update_candidate(
    candidate_id: UUID,
    request: CandidateUpdateRequest,
    service: Annotated[CandidateService, Depends(get_candidate_service)],
) -> CandidateResponse:
    """Replace the Candidate profile using the caller's optimistic-concurrency revision."""

    return service.update_candidate(
        candidate_id,
        expected_revision=request.expected_revision,
        profile=request.profile,
    )
