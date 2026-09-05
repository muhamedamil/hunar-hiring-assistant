from __future__ import annotations

from app.core.logging import redact


def test_redact_removes_nested_secrets() -> None:
    value = {
        "candidate_id": "abc",
        "authorization": "Bearer secret",
        "nested": {"api_key": "123", "safe": "ok"},
    }
    assert redact(value) == {
        "candidate_id": "abc",
        "authorization": "[REDACTED]",
        "nested": {"api_key": "[REDACTED]", "safe": "ok"},
    }
