"""Internal helpers for validating Apollo JSON without leaking provider payloads downstream."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any


def optional_text(value: object) -> str | None:
    """Return a trimmed provider string or ``None`` for blank/non-string values."""

    if not isinstance(value, str):
        return None
    normalized = value.strip()
    return normalized or None


def parse_datetime(value: object) -> datetime | None:
    """Parse a provider ISO timestamp defensively without making optional metadata fatal."""

    text = optional_text(value)
    if text is None:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None


def parse_date(value: object) -> date | None:
    """Parse one optional ISO date without making malformed professional metadata fatal."""

    text = optional_text(value)
    if text is None:
        return None
    try:
        return date.fromisoformat(text)
    except ValueError:
        return None


def require_object(value: object, *, context: str) -> dict[str, Any]:
    """Require one JSON object at a provider response boundary."""

    if not isinstance(value, dict):
        raise ValueError(f"{context} must be a JSON object")
    return value


def require_list(value: object, *, context: str) -> list[object]:
    """Require one JSON list at a provider response boundary."""

    if not isinstance(value, list):
        raise ValueError(f"{context} must be a JSON array")
    return list(value)
