from __future__ import annotations

from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app, raise_server_exceptions=False)


def test_liveness_does_not_require_database() -> None:
    response = client.get("/api/v1/health/live")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert response.headers["X-Request-ID"]


def test_request_id_is_propagated() -> None:
    response = client.get(
        "/api/v1/health/live",
        headers={"X-Request-ID": "assessment-test-123"},
    )
    assert response.headers["X-Request-ID"] == "assessment-test-123"


def test_invalid_request_id_is_replaced() -> None:
    response = client.get(
        "/api/v1/health/live",
        headers={"X-Request-ID": "bad request id with spaces"},
    )
    assert response.headers["X-Request-ID"] != "bad request id with spaces"


def test_readiness_success() -> None:
    with patch("app.main.check_database_connection"):
        response = client.get("/api/v1/health/ready")
    assert response.status_code == 200
    assert response.json() == {"status": "ready", "database": "ok"}


def test_readiness_failure_uses_standard_error_contract() -> None:
    with patch("app.main.check_database_connection", side_effect=RuntimeError("down")):
        response = client.get("/api/v1/health/ready")
    assert response.status_code == 503
    payload = response.json()
    assert payload["error"]["code"] == "DATABASE_UNAVAILABLE"
    assert payload["error"]["message"] == "Database is temporarily unavailable."
    assert payload["error"]["request_id"] == response.headers["X-Request-ID"]


def test_not_found_uses_standard_error_envelope() -> None:
    response = client.get("/api/v1/does-not-exist")

    assert response.status_code == 404
    payload = response.json()
    assert payload["error"]["code"] == "RESOURCE_NOT_FOUND"
    assert payload["error"]["message"] == "The requested resource was not found."
    assert payload["error"]["request_id"]
    assert response.headers["X-Request-ID"] == payload["error"]["request_id"]


def test_method_not_allowed_uses_standard_error_envelope() -> None:
    response = client.post("/api/v1/health/live")

    assert response.status_code == 405
    payload = response.json()
    assert payload["error"]["code"] == "METHOD_NOT_ALLOWED"
    assert payload["error"]["request_id"]
