"""HTTP contract tests for Module 4 matching and shortlist routes without live DB/Gemini."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.matching.dependencies import get_matching_service
from app.matching.schemas import (
    JobCandidateDetailResponse,
    JobCandidateListResponse,
    MatchEvaluationResponse,
    MatchHistoryResponse,
    ShortlistStatus,
)


class FakeMatchingService:
    """Deterministic Module 4 service used to verify route paths and response shapes."""

    def __init__(self) -> None:
        self.job_id = uuid4()
        self.candidate_id = uuid4()
        self.result_id = uuid4()
        self.relation_id = uuid4()
        self.match_id = uuid4()
        self.now = datetime.now(UTC)

    def _match(self) -> MatchEvaluationResponse:
        return MatchEvaluationResponse(
            id=self.match_id,
            job_candidate_id=self.relation_id,
            definition_version=2,
            source_sourcing_result_id=self.result_id,
            source_sourcing_run_id=uuid4(),
            source_definition_version=1,
            source_evidence_version="apollo_professional_evidence_v1",
            candidate_revision=3,
            matcher_version="candidate_job_match_v1",
            analysis_mode="hybrid_gemini",
            status="completed",
            semantic_model="gemini-test",
            semantic_prompt_version="candidate_match_semantic_v1",
            semantic_failure_code=None,
            retry_after_seconds=None,
            match_score=50,
            evidence_coverage=67,
            match_reasons=[
                {
                    "key": "role_alignment",
                    "label": "Role alignment",
                    "category": "role",
                    "weight": 2,
                    "status": "supported",
                    "reason": "Explicit title evidence supports role alignment.",
                    "evidence_ids": ["E1"],
                }
            ],
            started_at=self.now,
            completed_at=self.now,
            created_at=self.now,
        )

    def _detail(self, status: str = "reviewing") -> JobCandidateDetailResponse:
        return JobCandidateDetailResponse(
            id=self.relation_id,
            job_id=self.job_id,
            candidate={
                "id": self.candidate_id,
                "full_name": "Candidate Example",
                "current_title": "Platform Engineer",
                "current_company": "Example Co",
                "location": "Bangalore",
                "has_email": True,
                "has_phone": True,
                "revision": 3,
                "updated_at": self.now,
            },
            created_source="sourcing",
            preferred_sourcing_result_id=self.result_id,
            shortlist_status=status,
            revision=4,
            current_match=self._match(),
            match_freshness={"is_fresh": True, "stale_reasons": []},
            decision_is_current=status != "reviewing",
            call_readiness="ready",
            created_at=self.now,
            updated_at=self.now,
            current_job_status="ready",
            current_job_definition_version=2,
            decision_match_id=self.match_id if status != "reviewing" else None,
        )

    def add_manual_candidate(self, job_id: UUID, candidate_id: UUID):
        assert job_id == self.job_id
        assert candidate_id == self.candidate_id
        return self._detail()

    def add_sourced_candidate(self, result_id: UUID):
        assert result_id == self.result_id
        return self._detail()

    def list_job_candidates(self, job_id: UUID, *, shortlist_status, limit, offset):
        assert job_id == self.job_id
        assert shortlist_status is None
        return JobCandidateListResponse(items=[self._detail()], limit=limit, offset=offset)

    def get_job_candidate(self, relation_id: UUID):
        assert relation_id == self.relation_id
        return self._detail()

    def evaluate_match(self, relation_id: UUID):
        assert relation_id == self.relation_id
        return self._match()

    def list_match_history(self, relation_id: UUID, *, limit: int, offset: int):
        assert relation_id == self.relation_id
        return MatchHistoryResponse(items=[self._match()], limit=limit, offset=offset)

    def update_shortlist(self, relation_id: UUID, *, expected_revision: int, status):
        assert relation_id == self.relation_id
        assert expected_revision == 4
        assert status is ShortlistStatus.SHORTLISTED
        return self._detail("shortlisted")


@pytest.fixture()
def client_and_service():
    service = FakeMatchingService()
    app.dependency_overrides[get_matching_service] = lambda: service
    client = TestClient(app, raise_server_exceptions=False)
    try:
        yield client, service
    finally:
        app.dependency_overrides.clear()


def test_shared_task1_task2_match_and_shortlist_routes(client_and_service) -> None:
    client, service = client_and_service

    manual = client.post(
        f"/api/v1/jobs/{service.job_id}/job-candidates",
        json={"candidate_id": str(service.candidate_id)},
    )
    assert manual.status_code == 201

    sourced = client.post(
        f"/api/v1/sourcing-results/{service.result_id}/job-candidate"
    )
    assert sourced.status_code == 201
    assert sourced.json()["id"] == manual.json()["id"]

    listed = client.get(f"/api/v1/jobs/{service.job_id}/job-candidates")
    assert listed.status_code == 200
    assert listed.json()["items"][0]["call_readiness"] == "ready"
    assert "phone_e164" not in listed.text

    matched = client.post(f"/api/v1/job-candidates/{service.relation_id}/match")
    assert matched.status_code == 200
    assert matched.json()["match_score"] == 50
    assert matched.json()["evidence_coverage"] == 67

    history = client.get(f"/api/v1/job-candidates/{service.relation_id}/matches")
    assert history.status_code == 200
    assert history.json()["items"][0]["definition_version"] == 2

    shortlisted = client.patch(
        f"/api/v1/job-candidates/{service.relation_id}/shortlist",
        json={"expected_revision": 4, "status": "shortlisted"},
    )
    assert shortlisted.status_code == 200
    assert shortlisted.json()["shortlist_status"] == "shortlisted"
    assert shortlisted.json()["decision_is_current"] is True
