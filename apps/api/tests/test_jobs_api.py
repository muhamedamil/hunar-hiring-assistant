"""HTTP contract tests for Module 1 Job routes without a live database/provider."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from app.jobs.dependencies import get_job_analysis_service, get_job_service
from app.jobs.errors import JobRevisionConflictError
from app.jobs.schemas import (
    JobAnalysisProposal,
    JobListResponse,
    JobResponse,
    JobStatus,
)
from app.main import app


class FakeJobService:
    """Minimal deterministic service used to exercise router request/response wiring."""

    def __init__(self) -> None:
        self.job_id = uuid4()

    def _job(self, *, status: JobStatus = JobStatus.DRAFT, revision: int = 0) -> JobResponse:
        now = datetime.now(UTC)
        return JobResponse(
            id=self.job_id,
            title="Senior Python Engineer",
            company_name="Hunar.ai",
            description="Build reliable Python APIs for an AI hiring product.",
            requirements={"required_skills": ["Python"]},
            screening_questions=[],
            status=status,
            revision=revision,
            approved_version=1 if status is JobStatus.READY else None,
            created_at=now,
            updated_at=now,
        )

    def create_draft(self, request):  # type: ignore[no-untyped-def]
        assert request.title == "Senior Python Engineer"
        return self._job()

    def list_jobs(self, *, status, limit: int, offset: int):  # type: ignore[no-untyped-def]
        assert limit == 20
        assert offset == 0
        job = self._job(status=status or JobStatus.DRAFT)
        return JobListResponse(
            items=[
                {
                    "id": job.id,
                    "title": job.title,
                    "company_name": job.company_name,
                    "status": job.status,
                    "revision": job.revision,
                    "approved_version": job.approved_version,
                    "updated_at": job.updated_at,
                }
            ],
            limit=limit,
            offset=offset,
        )

    def get_job(self, job_id: UUID) -> JobResponse:
        assert job_id == self.job_id
        return self._job()

    def save_draft(self, job_id: UUID, *, expected_revision: int, definition):  # type: ignore[no-untyped-def]
        assert job_id == self.job_id
        if expected_revision != 0:
            raise JobRevisionConflictError(current_revision=0)
        assert definition.title
        return self._job(revision=1)

    def mark_ready(self, job_id: UUID, *, expected_revision: int, definition):  # type: ignore[no-untyped-def]
        assert job_id == self.job_id
        assert expected_revision == 0
        assert definition.screening_questions
        return self._job(status=JobStatus.READY, revision=1)

    def reopen(self, job_id: UUID, *, expected_revision: int):  # type: ignore[no-untyped-def]
        assert job_id == self.job_id
        assert expected_revision == 1
        return self._job(status=JobStatus.DRAFT, revision=2)


class FakeAnalysisService:
    """Return one proposal and prove the analyze route remains non-mutating."""

    def analyze(self, *, title: str | None, description: str) -> JobAnalysisProposal:
        assert description
        return JobAnalysisProposal(
            suggested_title=title or "Senior Python Engineer",
            requirements={"required_skills": ["Python"]},
            suggested_screening_questions=[],
        )


@pytest.fixture()
def client_and_service():  # type: ignore[no-untyped-def]
    service = FakeJobService()
    app.dependency_overrides[get_job_service] = lambda: service
    app.dependency_overrides[get_job_analysis_service] = lambda: FakeAnalysisService()
    client = TestClient(app, raise_server_exceptions=False)
    try:
        yield client, service
    finally:
        app.dependency_overrides.clear()


def _definition_payload(*, include_question: bool = False) -> dict[str, object]:
    questions: list[dict[str, object]] = []
    if include_question:
        questions.append(
            {
                "key": "interest",
                "prompt": "Are you interested in this role?",
                "answer_type": "yes_no",
                "required": True,
                "options": [],
            }
        )
    return {
        "title": "Senior Python Engineer",
        "company_name": "Hunar.ai",
        "description": "Build reliable Python APIs for an AI hiring product.",
        "requirements": {"required_skills": ["Python"]},
        "screening_questions": questions,
    }


def test_analyze_returns_proposal_without_job_creation(client_and_service) -> None:  # type: ignore[no-untyped-def]
    client, _ = client_and_service
    response = client.post(
        "/api/v1/jobs/analyze",
        json={
            "title": "Senior Python Engineer",
            "description": "Build reliable Python APIs for an AI hiring product.",
        },
    )
    assert response.status_code == 200
    assert response.json()["suggested_title"] == "Senior Python Engineer"


def test_create_list_and_get_job_routes(client_and_service) -> None:  # type: ignore[no-untyped-def]
    client, service = client_and_service
    created = client.post("/api/v1/jobs", json=_definition_payload())
    assert created.status_code == 201
    assert created.json()["status"] == "draft"

    listed = client.get("/api/v1/jobs")
    assert listed.status_code == 200
    assert len(listed.json()["items"]) == 1

    fetched = client.get(f"/api/v1/jobs/{service.job_id}")
    assert fetched.status_code == 200
    assert fetched.json()["id"] == str(service.job_id)


def test_update_revision_conflict_uses_standard_error_envelope(client_and_service) -> None:  # type: ignore[no-untyped-def]
    client, service = client_and_service
    response = client.patch(
        f"/api/v1/jobs/{service.job_id}",
        json={"expected_revision": 99, "definition": _definition_payload()},
    )
    assert response.status_code == 409
    payload = response.json()
    assert payload["error"]["code"] == "JOB_REVISION_CONFLICT"
    assert payload["error"]["details"]["current_revision"] == 0
    assert payload["error"]["request_id"] == response.headers["X-Request-ID"]


def test_ready_and_reopen_routes(client_and_service) -> None:  # type: ignore[no-untyped-def]
    client, service = client_and_service
    ready = client.post(
        f"/api/v1/jobs/{service.job_id}/ready",
        json={"expected_revision": 0, "definition": _definition_payload(include_question=True)},
    )
    assert ready.status_code == 200
    assert ready.json()["status"] == "ready"

    reopened = client.post(
        f"/api/v1/jobs/{service.job_id}/reopen",
        json={"expected_revision": 1},
    )
    assert reopened.status_code == 200
    assert reopened.json()["status"] == "draft"
