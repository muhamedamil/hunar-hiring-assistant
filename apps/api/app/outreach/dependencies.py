"""FastAPI dependency constructor for request-scoped Module 5 services."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from app.core.database import get_db_session
from app.outreach.service import OutreachService


def get_outreach_service(
    session: Annotated[Session, Depends(get_db_session)],
) -> OutreachService:
    """Build a request-scoped outreach service over current upstream authorities."""

    return OutreachService(session)
