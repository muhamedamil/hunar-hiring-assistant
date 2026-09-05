"""FastAPI dependency constructors for Job services and optional Gemini analysis."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db_session
from app.integrations.gemini.job_analysis import GeminiJobAnalysisProvider
from app.jobs.analysis import JobAnalysisService
from app.jobs.errors import JobAnalysisNotConfiguredError
from app.jobs.service import JobService


def get_job_service(
    session: Annotated[Session, Depends(get_db_session)],
) -> JobService:
    """Build a request-scoped Job service over the shared SQLAlchemy session."""

    return JobService(session)


def get_job_analysis_service() -> JobAnalysisService:
    """Build the optional Gemini analysis service or fail with a recoverable config error."""

    settings = get_settings()
    if not settings.gemini_api_key:
        raise JobAnalysisNotConfiguredError()
    provider = GeminiJobAnalysisProvider(
        api_key=settings.gemini_api_key,
        model=settings.gemini_model,
        thinking_level=settings.gemini_thinking_level,
        read_timeout_seconds=settings.gemini_read_timeout_seconds,
    )
    return JobAnalysisService(provider)
