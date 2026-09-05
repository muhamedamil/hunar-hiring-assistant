"""Domain-specific API errors for Candidate Core identity and revision rules."""

from __future__ import annotations

from uuid import UUID

from app.core.errors import AppError


class CandidateNotFoundError(AppError):
    """Raised when a requested Candidate does not exist."""

    def __init__(self) -> None:
        super().__init__(
            status_code=404,
            code="CANDIDATE_NOT_FOUND",
            message="Candidate was not found.",
        )


class CandidateAlreadyExistsError(AppError):
    """Raised when manual creation uses a contact owned by an existing Candidate."""

    def __init__(self, *, candidate_id: UUID) -> None:
        super().__init__(
            status_code=409,
            code="CANDIDATE_ALREADY_EXISTS",
            message="A candidate with this contact already exists.",
            details={"existing_candidate_id": str(candidate_id)},
        )


class CandidateIdentityConflictError(AppError):
    """Raised when strong identity signals resolve to different Candidates."""

    def __init__(self, *, candidate_ids: set[UUID]) -> None:
        super().__init__(
            status_code=409,
            code="CANDIDATE_IDENTITY_CONFLICT",
            message="Candidate identity signals conflict and cannot be merged automatically.",
            details={"candidate_ids": sorted(str(candidate_id) for candidate_id in candidate_ids)},
        )


class CandidateRevisionConflictError(AppError):
    """Raised when a stale Candidate editor tries to overwrite newer canonical state."""

    def __init__(self, *, current_revision: int) -> None:
        super().__init__(
            status_code=409,
            code="CANDIDATE_REVISION_CONFLICT",
            message=(
                "Candidate changed since it was loaded. Reload the latest version before saving."
            ),
            details={"current_revision": current_revision},
        )
