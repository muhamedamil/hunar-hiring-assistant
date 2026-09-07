"""Compose request-scoped Module 7 services and close backend-only provider clients."""

from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from app.call_results.service import CallResultService
from app.core.config import get_settings
from app.core.database import get_db_session
from app.voice_calls.dependencies import build_voice_provider


def get_call_result_service(
    session: Annotated[Session, Depends(get_db_session)],
) -> Iterator[CallResultService]:
    """Yield a result service whose provider is used only by explicit reconciliation."""

    settings = get_settings()
    provider = build_voice_provider(settings)
    try:
        yield CallResultService(session, settings=settings, provider=provider)
    finally:
        if provider is not None:
            provider.close()
