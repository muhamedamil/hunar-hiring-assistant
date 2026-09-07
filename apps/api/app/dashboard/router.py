"""Read-only recruiter dashboard APIs over existing Modules 0–7 business truth."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query

from app.call_results.schemas import CandidateInterest
from app.dashboard.dependencies import get_dashboard_service
from app.dashboard.schemas import (
    DashboardOverviewResponse,
    DashboardScreeningDetailResponse,
    DashboardScreeningListResponse,
    DashboardScreeningState,
    DashboardSearchQuery,
)
from app.dashboard.service import DashboardService

router = APIRouter(prefix="/api/v1/dashboard", tags=["dashboard"])
Service = Annotated[DashboardService, Depends(get_dashboard_service)]


@router.get("/overview", response_model=DashboardOverviewResponse)
def get_dashboard_overview(service: Service) -> DashboardOverviewResponse:
    """Return recruiter-safe authoritative counts, attention, and recent executions."""

    return service.get_overview()


@router.get("/screenings", response_model=DashboardScreeningListResponse)
def list_dashboard_screenings(
    service: Service,
    job_id: Annotated[UUID | None, Query()] = None,
    state: Annotated[DashboardScreeningState | None, Query()] = None,
    interest: Annotated[CandidateInterest | None, Query()] = None,
    q: Annotated[DashboardSearchQuery | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> DashboardScreeningListResponse:
    """Return one deterministic server-paginated screening execution page."""

    return service.list_screenings(
        job_id=job_id,
        state=state,
        interest=interest,
        q=q,
        limit=limit,
        offset=offset,
    )


@router.get("/screenings/{execution_id}", response_model=DashboardScreeningDetailResponse)
def get_dashboard_screening_detail(
    execution_id: UUID,
    service: Service,
) -> DashboardScreeningDetailResponse:
    """Return exact historical screening detail without provider calls or current-state fallback."""

    return service.get_screening_detail(execution_id)
