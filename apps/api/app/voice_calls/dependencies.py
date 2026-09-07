"""Composition of request-scoped voice services and backend-only provider clients."""

from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.database import get_db_session
from app.integrations.hunar.client import HunarVoiceProvider
from app.voice_calls.service import VoiceCallService


def build_voice_provider(settings: Settings) -> HunarVoiceProvider | None:
    """Construct a client without HTTP; missing configuration remains an explicit service gate."""
    if not settings.hunar_api_key:
        return None
    return HunarVoiceProvider(
        api_key=settings.hunar_api_key,
        base_url=settings.hunar_api_base_url,
        read_timeout_seconds=settings.hunar_read_timeout_seconds,
    )


def get_voice_call_service(
    session: Annotated[Session, Depends(get_db_session)],
) -> Iterator[VoiceCallService]:
    """Close the request client after use; provider HTTP never occurs during construction."""
    settings = get_settings()
    provider = build_voice_provider(settings)
    try:
        yield VoiceCallService(session, settings=settings, provider=provider)
    finally:
        if provider is not None:
            provider.close()
