"""Stable public errors that never include provider payloads or Candidate PII."""

from app.core.errors import AppError


class VoiceCallError(AppError):
    """Expose a bounded failure code without provider body or sensitive input."""

    def __init__(self, code: str, status_code: int = 409) -> None:
        super().__init__(
            status_code=status_code,
            code=code,
            message="Voice call submission could not proceed. Check configuration or state.",
        )
