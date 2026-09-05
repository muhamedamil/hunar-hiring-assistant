"""HTTP contract tests for Module 2 Candidate routes without a live database."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from app.candidates.dependencies import get_candidate_service
from app.candidates.errors import CandidateRevisionConflictError
from app.candidates.schemas import CandidateListResponse, CandidateResponse
from app.main import app


class FakeCandidateService:
    """Deterministic Candidate service used to verify router request/response behavior."""

    def __init__(self) -> None:
        self.candidate_id = uuid4()

    def _candidate(self, *, revision: int = 0) -> CandidateResponse:
        now = datetime.now(UTC)
        return CandidateResponse(
            id=self.candidate_id,
            full_name="Sarah Ahmed",
            current_title="Backend Engineer",
            current_company="Acme",
            location="Bangalore",
            email="sarah@example.com",
            phone_e164=None,
            external_identities=[],
            revision=revision,
            created_at=now,
            updated_at=now,
        )

    def create_manual_candidate(self, request):  # type: ignore[no-untyped-def]
        assert request.full_name == "Sarah Ahmed"
        return self._candidate()

    def list_candidates(self, *, query, limit: int, offset: int):  # type: ignore[no-untyped-def]
        assert query == "Sarah"
        assert limit == 20
        assert offset == 0
        candidate = self._candidate()
        return CandidateListResponse(
            items=[
                {
                    "id": candidate.id,
                    "full_name": candidate.full_name,
                    "current_title": candidate.current_title,
                    "current_company": candidate.current_company,
                    "location": candidate.location,
                    "has_email": True,
                    "has_phone": False,
                    "revision": candidate.revision,
                    "updated_at": candidate.updated_at,
                }
            ],
            limit=limit,
            offset=offset,
        )

    def get_candidate(self, candidate_id: UUID) -> CandidateResponse:
        assert candidate_id == self.candidate_id
        return self._candidate()

    def update_candidate(
        self,
        candidate_id: UUID,
        *,
        expected_revision: int,
        profile,
    ) -> CandidateResponse:  # type: ignore[no-untyped-def]
        assert candidate_id == self.candidate_id
        assert profile.full_name == "Sarah Ahmed"
        if expected_revision != 0:
            raise CandidateRevisionConflictError(current_revision=0)
        return self._candidate(revision=1)


@pytest.fixture()
def client_and_service():  # type: ignore[no-untyped-def]
    service = FakeCandidateService()
    app.dependency_overrides[get_candidate_service] = lambda: service
    client = TestClient(app, raise_server_exceptions=False)
    try:
        yield client, service
    finally:
        app.dependency_overrides.clear()


def _profile_payload() -> dict[str, object]:
    return {
        "full_name": "Sarah Ahmed",
        "current_title": "Backend Engineer",
        "current_company": "Acme",
        "location": "Bangalore",
        "email": "sarah@example.com",
        "phone": None,
    }


def test_create_list_and_get_candidate_routes(  # type: ignore[no-untyped-def]
    client_and_service,
) -> None:
    client, service = client_and_service

    created = client.post("/api/v1/candidates", json=_profile_payload())
    assert created.status_code == 201
    assert created.json()["full_name"] == "Sarah Ahmed"

    listed = client.get("/api/v1/candidates?q=Sarah")
    assert listed.status_code == 200
    assert listed.json()["items"][0]["has_email"] is True
    assert "email" not in listed.json()["items"][0]

    fetched = client.get(f"/api/v1/candidates/{service.candidate_id}")
    assert fetched.status_code == 200
    assert fetched.json()["email"] == "sarah@example.com"


def test_update_revision_conflict_uses_standard_error_envelope(  # type: ignore[no-untyped-def]
    client_and_service,
) -> None:
    client, service = client_and_service

    response = client.patch(
        f"/api/v1/candidates/{service.candidate_id}",
        json={"expected_revision": 99, "profile": _profile_payload()},
    )

    assert response.status_code == 409
    payload = response.json()
    assert payload["error"]["code"] == "CANDIDATE_REVISION_CONFLICT"
    assert payload["error"]["details"]["current_revision"] == 0
    assert payload["error"]["request_id"] == response.headers["X-Request-ID"]


def test_invalid_candidate_contact_uses_shared_validation_envelope(  # type: ignore[no-untyped-def]
    client_and_service,
) -> None:
    client, _ = client_and_service
    payload = _profile_payload()
    payload["email"] = "not-an-email"

    response = client.post("/api/v1/candidates", json=payload)

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "REQUEST_VALIDATION_ERROR"
