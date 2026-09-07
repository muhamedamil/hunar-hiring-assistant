"""Request-scoped construction for the read-only Module 8 dashboard service."""

from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from app.core.database import get_db_session
from app.dashboard.service import DashboardService


def get_dashboard_service(
    session: Annotated[Session, Depends(get_db_session)],
) -> DashboardService:
    """Build a dashboard service with only a database session and no provider dependencies."""

    return DashboardService(session)
