"""Authenticate Hunar webhook bytes before parsing; keys and payloads never leave the backend."""

from __future__ import annotations

import base64
import hashlib
import hmac
from datetime import UTC, datetime

from app.core.errors import AppError

MAX_WEBHOOK_CLOCK_SKEW_SECONDS = 300


class HunarWebhookAuthenticationError(AppError):
    """Expose one safe authentication failure without revealing signing material."""

    def __init__(self) -> None:
        super().__init__(
            status_code=401,
            code="HUNAR_WEBHOOK_AUTHENTICATION_FAILED",
            message="Hunar webhook authentication failed.",
        )


def verify_hunar_webhook_signature(
    *,
    raw_body: bytes,
    timestamp: str | None,
    signature_header: str | None,
    trusted_keys: tuple[str, ...],
    now: datetime | None = None,
) -> None:
    """Verify timestamped Base64 HMAC-SHA256 against every active key in constant time."""

    if timestamp is None or not timestamp.isdigit():
        raise HunarWebhookAuthenticationError()
    timestamp_seconds = int(timestamp)
    current = now or datetime.now(UTC)
    if abs(current.timestamp() - timestamp_seconds) > MAX_WEBHOOK_CLOCK_SKEW_SECONDS:
        raise HunarWebhookAuthenticationError()
    received = [part.strip() for part in (signature_header or "").split(",") if part.strip()]
    if not received or not trusted_keys:
        raise HunarWebhookAuthenticationError()
    message = (timestamp + ".").encode("ascii") + raw_body
    matched = False
    for key in trusted_keys:
        expected = base64.b64encode(
            hmac.new(key.encode("utf-8"), message, hashlib.sha256).digest()
        ).decode("ascii")
        for candidate in received:
            matched = hmac.compare_digest(expected, candidate) or matched
    if not matched:
        raise HunarWebhookAuthenticationError()
