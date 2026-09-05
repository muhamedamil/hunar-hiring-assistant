"""Domain-specific API errors for the Job & Screening Definition module."""

from __future__ import annotations

from typing import Any

from app.core.errors import AppError


class JobNotFoundError(AppError):
    """Raised when a requested Job does not exist."""

    def __init__(self) -> None:
        super().__init__(status_code=404, code="JOB_NOT_FOUND", message="Job was not found.")


class JobNotEditableError(AppError):
    """Raised when a READY Job is edited without first being reopened."""

    def __init__(self) -> None:
        super().__init__(
            status_code=409,
            code="JOB_NOT_EDITABLE",
            message="Ready jobs must be reopened before their definition can be edited.",
        )


class JobAlreadyReadyError(AppError):
    """Raised when a READY transition is requested for an already READY Job."""

    def __init__(self) -> None:
        super().__init__(
            status_code=409,
            code="JOB_ALREADY_READY",
            message="Job is already ready.",
        )


class JobAlreadyDraftError(AppError):
    """Raised when a DRAFT transition is requested for an already DRAFT Job."""

    def __init__(self) -> None:
        super().__init__(
            status_code=409,
            code="JOB_ALREADY_DRAFT",
            message="Job is already a draft.",
        )


class JobNotReadyError(AppError):
    """Raised when new downstream work requests a Job that is currently DRAFT."""

    def __init__(self) -> None:
        super().__init__(
            status_code=409,
            code="JOB_NOT_READY",
            message="Job must be ready before new downstream work can start.",
        )


class JobRevisionConflictError(AppError):
    """Raised when a stale browser revision attempts to overwrite current state."""

    def __init__(self, *, current_revision: int) -> None:
        super().__init__(
            status_code=409,
            code="JOB_REVISION_CONFLICT",
            message="Job changed since it was loaded. Reload the latest version before saving.",
            details={"current_revision": current_revision},
        )


class JobDefinitionIncompleteError(AppError):
    """Raised when a DRAFT does not satisfy the minimum READY contract."""

    def __init__(self, *, missing: list[str]) -> None:
        super().__init__(
            status_code=422,
            code="JOB_DEFINITION_INCOMPLETE",
            message="Job definition is incomplete and cannot be marked ready.",
            details={"missing": missing},
        )


class ScreeningQuestionIdentityError(AppError):
    """Raised when canonical screening-question identity cannot be reconciled safely."""

    def __init__(self, *, code: str, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(status_code=422, code=code, message=message, details=details)


class JobAnalysisNotConfiguredError(AppError):
    """Raised when optional Gemini analysis is requested without a configured key."""

    def __init__(self) -> None:
        super().__init__(
            status_code=503,
            code="JOB_ANALYSIS_NOT_CONFIGURED",
            message="AI job analysis is not configured. You can continue manually.",
        )


class JobAnalysisConfigError(AppError):
    """Raised when Gemini rejects the configured credentials or authorization."""

    def __init__(self) -> None:
        super().__init__(
            status_code=503,
            code="JOB_ANALYSIS_CONFIG_ERROR",
            message="AI job analysis is temporarily unavailable. You can continue manually.",
        )


class JobAnalysisRateLimitedError(AppError):
    """Raised when Gemini rate-limits an analysis request."""

    def __init__(self) -> None:
        super().__init__(
            status_code=429,
            code="JOB_ANALYSIS_RATE_LIMITED",
            message="AI job analysis is rate limited. Retry later or continue manually.",
        )


class JobAnalysisUnavailableError(AppError):
    """Raised for transient/network Gemini failures where manual editing remains available."""

    def __init__(self) -> None:
        super().__init__(
            status_code=503,
            code="JOB_ANALYSIS_UNAVAILABLE",
            message="AI job analysis is temporarily unavailable. You can continue manually.",
        )


class JobAnalysisInvalidResponseError(AppError):
    """Raised when Gemini returns a response that cannot satisfy the proposal contract."""

    def __init__(self) -> None:
        super().__init__(
            status_code=502,
            code="JOB_ANALYSIS_INVALID_RESPONSE",
            message="AI job analysis returned an invalid response. You can continue manually.",
        )
