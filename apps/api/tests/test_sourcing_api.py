"""HTTP contract tests for Module 3 sourcing and enrichment routes without live Apollo/Postgres."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.sourcing.dependencies import get_sourcing_service
from app.sourcing.schemas import (
    SourcingEnrichmentResponse,
    SourcingRunDetailResponse,
    SourcingRunListResponse,
)


class FakeSourcingService:
    """Deterministic service used to verify Module 3 router paths and response shapes."""

    def __init__(self) -> None:
        self.job_id = uuid4()
        self.run_id = uuid4()
        self.result_id = uuid4()
        self.enrichment_id = uuid4()

    def _run(self) -> SourcingRunDetailResponse:
        now = datetime.now(UTC)
        return SourcingRunDetailResponse(
            id=self.run_id,
            job_id=self.job_id,
            definition_version=2,
            provider="apollo",
            status="completed",
            criteria={
                "titles": ["Backend Engineer"],
                "locations": ["Bangalore"],
                "seniorities": ["senior"],
                "unmapped_requirements": [],
                "result_limit": 10,
            },
            provider_query={
                "person_titles": ["Backend Engineer"],
                "person_locations": ["Bangalore"],
                "person_seniorities": ["senior"],
                "include_similar_titles": False,
                "page": 1,
                "per_page": 10,
            },
            mapping_version="apollo_people_search_v1",
            result_limit=10,
            result_count=1,
            provider_total_matches=100,
            attempt_count=1,
            failure_code=None,
            retry_after_seconds=None,
            started_at=now,
            completed_at=now,
            created_at=now,
            updated_at=now,
            results=[
                {
                    "id": self.result_id,
                    "sourcing_run_id": self.run_id,
                    "provider_person_id": "person-1",
                    "result_position": 1,
                    "first_name": "Sarah",
                    "last_name_obfuscated": "Ah***d",
                    "current_title": "Backend Engineer",
                    "organization_name": "Acme",
                    "email_available": True,
                    "phone_availability": "available",
                    "candidate_id": None,
                    "created_at": now,
                }
            ],
            enrichments=[],
        )

    def start_search(self, job_id: UUID, *, result_limit: int) -> SourcingRunDetailResponse:
        assert job_id == self.job_id
        assert result_limit == 10
        return self._run()

    def list_runs_for_job(self, job_id: UUID) -> SourcingRunListResponse:
        assert job_id == self.job_id
        run = self._run()
        return SourcingRunListResponse(
            items=[
                {
                    "id": run.id,
                    "job_id": run.job_id,
                    "definition_version": run.definition_version,
                    "provider": run.provider,
                    "status": run.status,
                    "result_limit": run.result_limit,
                    "result_count": run.result_count,
                    "provider_total_matches": run.provider_total_matches,
                    "failure_code": run.failure_code,
                    "retry_after_seconds": run.retry_after_seconds,
                    "created_at": run.created_at,
                    "completed_at": run.completed_at,
                }
            ]
        )

    def get_run(self, run_id: UUID) -> SourcingRunDetailResponse:
        assert run_id == self.run_id
        return self._run()

    def retry_search(self, run_id: UUID) -> SourcingRunDetailResponse:
        assert run_id == self.run_id
        return self._run()

    def request_enrichment(self, result_id: UUID) -> SourcingEnrichmentResponse:
        assert result_id == self.result_id
        now = datetime.now(UTC)
        return SourcingEnrichmentResponse(
            id=self.enrichment_id,
            sourcing_result_id=self.result_id,
            provider="apollo",
            status="pending",
            candidate_id=None,
            provider_request_id=None,
            credits_consumed=None,
            failure_code=None,
            retry_after_seconds=None,
            requested_at=None,
            completed_at=None,
            created_at=now,
            updated_at=now,
        )

    def get_enrichment(self, enrichment_id: UUID) -> SourcingEnrichmentResponse:
        assert enrichment_id == self.enrichment_id
        return self.request_enrichment(self.result_id)


@pytest.fixture()
def client_and_service():  # type: ignore[no-untyped-def]
    service = FakeSourcingService()
    app.dependency_overrides[get_sourcing_service] = lambda: service
    client = TestClient(app, raise_server_exceptions=False)
    try:
        yield client, service
    finally:
        app.dependency_overrides.clear()


def test_start_list_get_retry_and_enrich_routes(
    client_and_service,  # type: ignore[no-untyped-def]
) -> None:
    client, service = client_and_service

    started = client.post(
        f"/api/v1/jobs/{service.job_id}/sourcing-runs",
        json={"result_limit": 10},
    )
    assert started.status_code == 201
    assert started.json()["definition_version"] == 2
    assert started.json()["results"][0]["candidate_id"] is None

    listed = client.get(f"/api/v1/jobs/{service.job_id}/sourcing-runs")
    assert listed.status_code == 200
    assert listed.json()["items"][0]["result_count"] == 1

    fetched = client.get(f"/api/v1/sourcing-runs/{service.run_id}")
    assert fetched.status_code == 200

    retried = client.post(f"/api/v1/sourcing-runs/{service.run_id}/retry")
    assert retried.status_code == 200

    enriched = client.post(f"/api/v1/sourcing-results/{service.result_id}/enrich")
    assert enriched.status_code == 202
    assert enriched.json()["status"] == "pending"


def test_result_limit_is_restricted_to_assessment_choices(
    client_and_service,  # type: ignore[no-untyped-def]
) -> None:
    client, service = client_and_service

    response = client.post(
        f"/api/v1/jobs/{service.job_id}/sourcing-runs",
        json={"result_limit": 37},
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "REQUEST_VALIDATION_ERROR"
