"""Module 8 router tests for exact GET contracts, q semantics, privacy, and error behavior."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from fastapi.testclient import TestClient

from app.dashboard.dependencies import get_dashboard_service
from app.dashboard.schemas import (
    DashboardCandidateMetrics,
    DashboardJobMetrics,
    DashboardOverviewResponse,
    DashboardPipelineMetrics,
    DashboardQuestionAnswer,
    DashboardScreeningDetailResponse,
    DashboardScreeningListResponse,
    DashboardScreeningMetrics,
    DashboardScreeningSummary,
)
from app.main import create_app
from app.voice_calls.errors import VoiceCallError


class Service:
    """Capture normalized router inputs while returning only safe Module 8 schemas."""

    def __init__(self) -> None:
        self.execution_id = uuid4()
        self.outreach_id = uuid4()
        self.relation_id = uuid4()
        self.candidate_id = uuid4()
        self.job_id = uuid4()
        self.question_id = uuid4()
        self.q_seen: str | None = None
        self.now = datetime.now(UTC)

    def summary(self) -> DashboardScreeningSummary:
        return DashboardScreeningSummary(
            execution_id=self.execution_id,
            outreach_request_id=self.outreach_id,
            job_candidate_id=self.relation_id,
            candidate_id=self.candidate_id,
            candidate_name="Safe Candidate",
            job_id=self.job_id,
            job_title="Historical Engineer",
            job_definition_version=2,
            screening_state="result_available",
            submission_status="unknown",
            conversation_outcome="completed",
            candidate_interest="interested",
            duration_seconds=42.0,
            observed_at=self.now,
            sort_at=self.now,
        )

    def get_overview(self) -> DashboardOverviewResponse:
        return DashboardOverviewResponse(
            generated_at=self.now,
            jobs=DashboardJobMetrics(total=1, draft=0, ready=1),
            candidates=DashboardCandidateMetrics(total=1),
            pipeline=DashboardPipelineMetrics(reviewing=0, shortlisted=1, not_selected=0),
            screenings=DashboardScreeningMetrics(
                total=1,
                queued=0,
                awaiting_result=0,
                dispatch_failed=0,
                submission_unknown=0,
                result_available=1,
                result_unavailable=0,
                result_invalid=0,
                interested=1,
            ),
            needs_attention=[],
            recent_screenings=[self.summary()],
        )

    def list_screenings(self, **kwargs) -> DashboardScreeningListResponse:
        self.q_seen = kwargs["q"]
        return DashboardScreeningListResponse(
            items=[self.summary()],
            total=123,
            limit=kwargs["limit"],
            offset=kwargs["offset"],
        )

    def get_screening_detail(self, execution_id):
        if execution_id != self.execution_id:
            raise VoiceCallError("VOICE_CALL_NOT_FOUND", 404)
        return DashboardScreeningDetailResponse(
            **self.summary().model_dump(exclude={"sort_at"}),
            provider_status="COMPLETED",
            lifecycle_status="COMPLETED",
            answered_by="HUMAN",
            recording_available=True,
            notes="Safe normalized note",
            questions=[
                DashboardQuestionAnswer(
                    question_id=self.question_id,
                    position=1,
                    prompt="Are you interested?",
                    answer_state="answered",
                    answer_text="Yes",
                )
            ],
        )


def _json_keys(value: object) -> set[str]:
    """Collect every serialized key recursively so nested dashboard DTOs are privacy-checked."""

    if isinstance(value, dict):
        keys = {str(key) for key in value}
        for nested in value.values():
            keys.update(_json_keys(nested))
        return keys
    if isinstance(value, list):
        keys: set[str] = set()
        for nested in value:
            keys.update(_json_keys(nested))
        return keys
    return set()


def client_context() -> tuple[TestClient, Service]:
    app = create_app()
    service = Service()
    app.dependency_overrides[get_dashboard_service] = lambda: service
    return TestClient(app), service


def test_overview_and_list_return_authoritative_safe_contracts() -> None:
    client, service = client_context()
    overview = client.get("/api/v1/dashboard/overview")
    assert overview.status_code == 200
    assert overview.json()["screenings"]["result_available"] == 1
    response = client.get("/api/v1/dashboard/screenings?limit=20&offset=0")
    assert response.status_code == 200
    assert response.json()["total"] == 123
    assert len(response.json()["items"]) == 1
    assert service.q_seen is None


def test_q_is_trimmed_before_filtering_and_rejects_empty_or_too_long_after_trim() -> None:
    client, service = client_context()
    response = client.get("/api/v1/dashboard/screenings", params={"q": "  Engineer  "})
    assert response.status_code == 200
    assert service.q_seen == "Engineer"

    response = client.get("/api/v1/dashboard/screenings", params={"q": "   "})
    assert response.status_code == 422
    response = client.get("/api/v1/dashboard/screenings", params={"q": "  " + "x" * 101 + "  "})
    assert response.status_code == 422


def test_list_validates_limit_offset_state_interest_and_keeps_job_id_programmatic() -> None:
    client, service = client_context()
    response = client.get(
        "/api/v1/dashboard/screenings",
        params={
            "job_id": str(service.job_id),
            "state": "result_available",
            "interest": "interested",
            "limit": 100,
            "offset": 3,
        },
    )
    assert response.status_code == 200
    assert response.json()["limit"] == 100 and response.json()["offset"] == 3
    assert client.get("/api/v1/dashboard/screenings?limit=0").status_code == 422
    assert client.get("/api/v1/dashboard/screenings?limit=101").status_code == 422
    assert client.get("/api/v1/dashboard/screenings?offset=-1").status_code == 422
    assert client.get("/api/v1/dashboard/screenings?state=completed").status_code == 422


def test_all_dashboard_serialization_omits_forbidden_provider_and_candidate_fields() -> None:
    client, service = client_context()
    responses = [
        client.get("/api/v1/dashboard/overview"),
        client.get("/api/v1/dashboard/screenings"),
        client.get(f"/api/v1/dashboard/screenings/{service.execution_id}"),
    ]
    assert all(response.status_code == 200 for response in responses)
    forbidden = {
        "phone",
        "phone_e164",
        "mobile_number",
        "email",
        "recording_url",
        "provider_call_id",
        "provider_request_id",
        "provider_initial_status",
        "provider_payload",
        "provider_payload_snapshot",
        "webhook_signature",
        "work_item",
        "created_source",
        "external_identity",
    }
    for response in responses:
        assert not forbidden.intersection(_json_keys(response.json()))

    payload = responses[-1].json()
    assert payload["recording_available"] is True
    assert payload["submission_status"] == "unknown"
    assert payload["screening_state"] == "result_available"


def test_missing_execution_uses_existing_voice_call_404_contract() -> None:
    client, _ = client_context()
    response = client.get(f"/api/v1/dashboard/screenings/{uuid4()}")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "VOICE_CALL_NOT_FOUND"


def test_dashboard_exposes_only_three_get_routes_and_no_mutation_route() -> None:
    app = create_app()
    http_methods = {"get", "post", "put", "patch", "delete", "options", "head", "trace"}
    routes = {
        (
            path,
            frozenset(method.upper() for method in operations if method in http_methods),
        )
        for path, operations in app.openapi()["paths"].items()
        if path.startswith("/api/v1/dashboard")
    }
    assert routes == {
        ("/api/v1/dashboard/overview", frozenset({"GET"})),
        ("/api/v1/dashboard/screenings", frozenset({"GET"})),
        ("/api/v1/dashboard/screenings/{execution_id}", frozenset({"GET"})),
    }
