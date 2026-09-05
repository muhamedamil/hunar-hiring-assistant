"""FastAPI dependency constructors for request-scoped Candidate Core services."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from app.candidates.service import CandidateService
from app.core.database import get_db_session


def get_candidate_service(
    session: Annotated[Session, Depends(get_db_session)],
) -> CandidateService:
    """Build a request-scoped Candidate service over the shared SQLAlchemy session."""

    return CandidateService(session)
