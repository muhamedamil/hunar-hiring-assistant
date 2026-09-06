"""FastAPI dependency constructors for request-scoped Module 4 matching services."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db_session
from app.integrations.gemini.candidate_matching import GeminiCandidateMatchProvider
from app.matching.analysis import CandidateMatchProvider
from app.matching.service import MatchingService


def _matching_provider() -> CandidateMatchProvider | None:
    settings = get_settings()
    if not settings.gemini_api_key:
        return None
    return GeminiCandidateMatchProvider(
        api_key=settings.gemini_api_key,
        model=settings.gemini_model,
        thinking_level=settings.gemini_thinking_level,
        read_timeout_seconds=settings.gemini_read_timeout_seconds,
    )


def get_matching_service(
    session: Annotated[Session, Depends(get_db_session)],
) -> MatchingService:
    """Build a request-scoped matching service over current Job/Candidate/evidence truth."""

    settings = get_settings()
    return MatchingService(
        session,
        semantic_provider=_matching_provider(),
        analysis_stale_seconds=settings.gemini_read_timeout_seconds + 30.0,
    )
