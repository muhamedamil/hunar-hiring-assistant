"""Stable Module 5 API errors for outreach preparation and immutable requests."""

from __future__ import annotations

from app.core.errors import AppError


class OutreachNotFoundError(AppError):
    """Raised when an immutable outreach request does not exist."""

    def __init__(self) -> None:
        super().__init__(
            status_code=404,
            code="OUTREACH_REQUEST_NOT_FOUND",
            message="Outreach request was not found.",
        )


class OutreachStateError(AppError):
    """Raised when current upstream authority cannot support outreach."""

    def __init__(self, *, code: str, message: str) -> None:
        super().__init__(status_code=409, code=code, message=message)


class OutreachPreparationStaleError(AppError):
    """Raised when confirmation no longer matches the reviewed preparation state."""

    def __init__(self) -> None:
        super().__init__(
            status_code=409,
            code="OUTREACH_PREPARATION_STALE",
            message="Outreach inputs changed. Reload preparation before confirming.",
        )


class OutreachQuestionProvenanceError(AppError):
    """Raised when a claimed Job-question identity is outside the approved version."""

    def __init__(self) -> None:
        super().__init__(
            status_code=422,
            code="OUTREACH_QUESTION_PROVENANCE_INVALID",
            message="A source question does not belong to the approved Job version.",
        )


class OutreachQuestionCountError(AppError):
    """Raised when an internal caller bypasses the browser question-count DTO."""

    def __init__(self) -> None:
        super().__init__(
            status_code=422,
            code="OUTREACH_QUESTION_COUNT_INVALID",
            message="Outreach requires between one and ten screening questions.",
        )


class OutreachNotDispatchableError(AppError):
    """Raised for a historical request whose upstream authority is now stale."""

    def __init__(self, *, reasons: list[str]) -> None:
        super().__init__(
            status_code=409,
            code="OUTREACH_REQUEST_STALE",
            message="Outreach request is no longer ready for execution.",
            details={"reasons": reasons},
        )
