"""Stable API errors for Candidate↔Job matching and shortlist workflow invariants."""

from __future__ import annotations

from app.core.errors import AppError


class JobCandidateNotFoundError(AppError):
    """Raised when a Candidate↔Job relationship does not exist."""

    def __init__(self) -> None:
        super().__init__(
            status_code=404,
            code="JOB_CANDIDATE_NOT_FOUND",
            message="Job candidate relationship was not found.",
        )


class MatchNotFoundError(AppError):
    """Raised when a requested match evaluation does not exist."""

    def __init__(self) -> None:
        super().__init__(
            status_code=404,
            code="CANDIDATE_MATCH_NOT_FOUND",
            message="Candidate match evaluation was not found.",
        )


class MatchAnalysisInProgressError(AppError):
    """Raised when an equivalent semantic match analysis is already running."""

    def __init__(self) -> None:
        super().__init__(
            status_code=409,
            code="MATCH_ANALYSIS_IN_PROGRESS",
            message="An equivalent candidate match analysis is already in progress.",
        )


class MatchStateConflictError(AppError):
    """Raised when a Module 4 command is invalid for the current relationship state."""

    def __init__(self, *, code: str, message: str) -> None:
        super().__init__(status_code=409, code=code, message=message)


class JobCandidateRevisionConflictError(AppError):
    """Raised when a stale recruiter view attempts to change shortlist truth."""

    def __init__(self, *, current_revision: int) -> None:
        super().__init__(
            status_code=409,
            code="JOB_CANDIDATE_REVISION_CONFLICT",
            message="Candidate review state changed. Reload before saving this decision.",
            details={"current_revision": current_revision},
        )
