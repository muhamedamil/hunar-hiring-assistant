"""Stable application errors for Module 3 sourcing and enrichment workflows."""

from __future__ import annotations

from typing import Any

from app.core.errors import AppError


class SourcingRunNotFoundError(AppError):
    """Raised when a sourcing run does not exist."""

    def __init__(self) -> None:
        super().__init__(
            status_code=404,
            code="SOURCING_RUN_NOT_FOUND",
            message="Sourcing run not found.",
        )


class SourcingResultNotFoundError(AppError):
    """Raised when a sourcing result does not exist."""

    def __init__(self) -> None:
        super().__init__(
            status_code=404,
            code="SOURCING_RESULT_NOT_FOUND",
            message="Sourcing result not found.",
        )


class SourcingEnrichmentNotFoundError(AppError):
    """Raised when an enrichment operation does not exist."""

    def __init__(self) -> None:
        super().__init__(
            status_code=404,
            code="SOURCING_ENRICHMENT_NOT_FOUND",
            message="Sourcing enrichment not found.",
        )


class SourcingProviderNotConfiguredError(AppError):
    """Raised when Apollo-backed sourcing is requested without backend provider config."""

    def __init__(self) -> None:
        super().__init__(
            status_code=503,
            code="SOURCING_PROVIDER_NOT_CONFIGURED",
            message="People search provider is not configured.",
        )


class SourcingProviderError(AppError):
    """Controlled provider failure after the sourcing run state has been persisted."""

    def __init__(
        self,
        *,
        code: str,
        message: str,
        status_code: int = 503,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(status_code=status_code, code=code, message=message, details=details)


class SearchRetryNotAllowedError(AppError):
    """Raised when a caller attempts to retry a run that is not safely retryable."""

    def __init__(self) -> None:
        super().__init__(
            status_code=409,
            code="SOURCING_SEARCH_RETRY_NOT_ALLOWED",
            message="This sourcing run is not currently eligible for a safe search retry.",
        )


class EnrichmentStateConflictError(AppError):
    """Raised when enrichment cannot be started from the current sourcing-result state."""

    def __init__(self, *, code: str, message: str) -> None:
        super().__init__(status_code=409, code=code, message=message)


class ApolloWebhookSignatureError(AppError):
    """Raised before processing an Apollo callback with an invalid capability signature."""

    def __init__(self) -> None:
        super().__init__(
            status_code=403,
            code="APOLLO_WEBHOOK_SIGNATURE_INVALID",
            message="Webhook signature is invalid.",
        )
