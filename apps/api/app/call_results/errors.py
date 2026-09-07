"""Stable Module 7 failures that exclude provider payloads, PII, and recording references."""

from app.core.errors import AppError


class CallResultError(AppError):
    """Expose a bounded result/recovery code without sensitive evidence."""

    def __init__(self, code: str, status_code: int = 409) -> None:
        super().__init__(
            status_code=status_code,
            code=code,
            message="Call result could not be safely processed.",
        )
