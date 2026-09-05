"""Structured logging redaction tests for secrets and Candidate contact PII."""

from __future__ import annotations

from app.core.logging import redact


def test_redact_removes_nested_secrets_and_candidate_contacts() -> None:
    value = {
        "candidate_id": "abc",
        "authorization": "Bearer secret",
        "email": "sarah@example.com",
        "nested": {
            "api_key": "123",
            "phone_e164": "+919876543210",
            "safe": "ok",
        },
    }
    assert redact(value) == {
        "candidate_id": "abc",
        "authorization": "[REDACTED]",
        "email": "[REDACTED]",
        "nested": {
            "api_key": "[REDACTED]",
            "phone_e164": "[REDACTED]",
            "safe": "ok",
        },
    }
