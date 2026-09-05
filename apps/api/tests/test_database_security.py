"""Foundation-level database error hardening required before Candidate PII is persisted."""

from __future__ import annotations

from typing import Any

from app.core import database


def test_sqlalchemy_engine_is_created_with_hidden_bound_parameters(
    monkeypatch,  # type: ignore[no-untyped-def]
) -> None:
    """Ensure DB exception rendering cannot include Candidate contact parameter values."""

    captured: dict[str, Any] = {}

    class DummyEngine:
        pass

    def fake_create_engine(url: str, **kwargs: Any) -> DummyEngine:
        captured["url"] = url
        captured.update(kwargs)
        return DummyEngine()

    database.get_engine.cache_clear()
    monkeypatch.setattr(database, "create_engine", fake_create_engine)
    try:
        database.get_engine()
    finally:
        database.get_engine.cache_clear()

    assert captured["hide_parameters"] is True
