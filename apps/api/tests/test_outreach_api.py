"""HTTP contract tests for Module 5 routes without a live database."""

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.outreach.dependencies import get_outreach_service
from app.outreach.schemas import (
    OutreachPreparationResponse,
    OutreachRequestListResponse,
    OutreachRequestResponse,
)


class FakeOutreachService:
    """Deterministic route double proving browser authority and response masking."""

    def __init__(self) -> None:
        self.relation_id = uuid4()
        self.request_id = uuid4()
        self.job_id = uuid4()
        self.candidate_id = uuid4()
        self.match_id = uuid4()
        self.question_id = uuid4()
        self.now = datetime.now(UTC)

    def _request(self) -> OutreachRequestResponse:
        return OutreachRequestResponse(
            id=self.request_id,
            job_candidate_id=self.relation_id,
            decision_match_id=self.match_id,
            candidate_name="Aisha Khan",
            candidate_location="Bengaluru",
            masked_phone="+91••••••3210",
            screening_questions=[
                {
                    "id": self.question_id,
                    "source_job_question_id": None,
                    "key": "interest",
                    "prompt": "Why are you interested in this role?",
                    "answer_type": "short_text",
                    "required": True,
                    "options": [],
                }
            ],
            screening_context_hash="a" * 64,
            readiness="READY_FOR_EXECUTION",
            stale_reasons=[],
            created_at=self.now,
        )

    def get_preparation(self, job_candidate_id: UUID) -> OutreachPreparationResponse:
        assert job_candidate_id == self.relation_id
        return OutreachPreparationResponse(
            job_candidate_id=self.relation_id,
            candidate_id=self.candidate_id,
            candidate_name="Aisha Khan",
            job_id=self.job_id,
            role="Backend Engineer",
            definition_version=2,
            masked_phone="+91••••••3210",
            default_screening_questions=[],
            preparation_token="b" * 64,
            can_prepare=True,
            blockers=[],
        )

    def prepare_outreach(self, job_candidate_id: UUID, **kwargs):
        assert job_candidate_id == self.relation_id
        assert kwargs["preparation_token"] == "b" * 64
        return self._request()

    def list_outreach_requests(self, *, limit: int, offset: int):
        return OutreachRequestListResponse(items=[self._request()], limit=limit, offset=offset)

    def get_outreach_request(self, request_id: UUID):
        assert request_id == self.request_id
        return self._request()


@pytest.fixture()
def client_and_service():
    service = FakeOutreachService()
    app.dependency_overrides[get_outreach_service] = lambda: service
    try:
        yield TestClient(app, raise_server_exceptions=False), service
    finally:
        app.dependency_overrides.clear()


def test_module_5_routes_expose_masked_phone_only(client_and_service) -> None:
    client, service = client_and_service
    prepared = client.get(f"/api/v1/job-candidates/{service.relation_id}/outreach-preparation")
    assert prepared.status_code == 200
    assert "phone_e164" not in prepared.text

    confirmed = client.post(
        f"/api/v1/job-candidates/{service.relation_id}/outreach-requests",
        json={
            "preparation_token": "b" * 64,
            "screening_questions": [
                {
                    "source_job_question_id": None,
                    "key": "interest",
                    "prompt": "Why are you interested in this role?",
                    "answer_type": "short_text",
                    "required": True,
                    "options": [],
                }
            ],
        },
    )
    assert confirmed.status_code == 201
    assert confirmed.json()["id"] == str(service.request_id)
    assert confirmed.json()["candidate_name"] == "Aisha Khan"
    assert confirmed.json()["candidate_location"] == "Bengaluru"
    assert "+919999999999" not in confirmed.text

    listed = client.get("/api/v1/outreach-requests")
    assert listed.status_code == 200
    assert listed.json()["items"][0]["candidate_name"] == "Aisha Khan"
    assert listed.json()["items"][0]["candidate_location"] == "Bengaluru"


def test_browser_cannot_choose_authoritative_outreach_values(client_and_service) -> None:
    client, service = client_and_service
    response = client.post(
        f"/api/v1/job-candidates/{service.relation_id}/outreach-requests",
        json={
            "preparation_token": "b" * 64,
            "screening_questions": [],
            "candidate_id": str(service.candidate_id),
            "provider": "hunar",
        },
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "REQUEST_VALIDATION_ERROR"
