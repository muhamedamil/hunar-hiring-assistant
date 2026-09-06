"""FastAPI routes for shared Candidate↔Job matching and recruiter shortlist decisions."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status

from app.matching.dependencies import get_matching_service
from app.matching.schemas import (
    AddJobCandidateRequest,
    JobCandidateDetailResponse,
    JobCandidateListResponse,
    MatchEvaluationResponse,
    MatchHistoryResponse,
    ShortlistStatus,
    ShortlistUpdateRequest,
)
from app.matching.service import MatchingService

router = APIRouter(tags=["matching"])


@router.post(
    "/api/v1/jobs/{job_id}/job-candidates",
    response_model=JobCandidateDetailResponse,
    status_code=status.HTTP_201_CREATED,
)
def add_manual_job_candidate(
    job_id: UUID,
    request: AddJobCandidateRequest,
    service: Annotated[MatchingService, Depends(get_matching_service)],
) -> JobCandidateDetailResponse:
    """Attach an existing canonical Candidate to one currently READY Job."""

    return service.add_manual_candidate(job_id, request.candidate_id)


@router.post(
    "/api/v1/sourcing-results/{result_id}/job-candidate",
    response_model=JobCandidateDetailResponse,
    status_code=status.HTTP_201_CREATED,
)
def add_sourced_job_candidate(
    result_id: UUID,
    service: Annotated[MatchingService, Depends(get_matching_service)],
) -> JobCandidateDetailResponse:
    """Converge one resolved sourcing result onto the shared Candidate↔Job relation."""

    return service.add_sourced_candidate(result_id)


@router.get(
    "/api/v1/jobs/{job_id}/job-candidates",
    response_model=JobCandidateListResponse,
)
def list_job_candidates(
    job_id: UUID,
    service: Annotated[MatchingService, Depends(get_matching_service)],
    shortlist_status: Annotated[ShortlistStatus | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> JobCandidateListResponse:
    """List Candidate↔Job relationships using evidence-first review ordering."""

    return service.list_job_candidates(
        job_id,
        shortlist_status=shortlist_status,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/api/v1/job-candidates/{job_candidate_id}",
    response_model=JobCandidateDetailResponse,
)
def get_job_candidate(
    job_candidate_id: UUID,
    service: Annotated[MatchingService, Depends(get_matching_service)],
) -> JobCandidateDetailResponse:
    """Return one Candidate↔Job relationship with match and decision freshness."""

    return service.get_job_candidate(job_candidate_id)


@router.post(
    "/api/v1/job-candidates/{job_candidate_id}/match",
    response_model=MatchEvaluationResponse,
)
def evaluate_candidate_match(
    job_candidate_id: UUID,
    service: Annotated[MatchingService, Depends(get_matching_service)],
) -> MatchEvaluationResponse:
    """Evaluate current Candidate evidence against the current READY Job definition."""

    return service.evaluate_match(job_candidate_id)


@router.get(
    "/api/v1/job-candidates/{job_candidate_id}/matches",
    response_model=MatchHistoryResponse,
)
def list_candidate_match_history(
    job_candidate_id: UUID,
    service: Annotated[MatchingService, Depends(get_matching_service)],
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> MatchHistoryResponse:
    """Return immutable historical match attempts for one Candidate↔Job relation."""

    return service.list_match_history(job_candidate_id, limit=limit, offset=offset)


@router.patch(
    "/api/v1/job-candidates/{job_candidate_id}/shortlist",
    response_model=JobCandidateDetailResponse,
)
def update_shortlist(
    job_candidate_id: UUID,
    request: ShortlistUpdateRequest,
    service: Annotated[MatchingService, Depends(get_matching_service)],
) -> JobCandidateDetailResponse:
    """Apply an explicit revision-protected recruiter shortlist decision."""

    return service.update_shortlist(
        job_candidate_id,
        expected_revision=request.expected_revision,
        status=request.status,
    )
