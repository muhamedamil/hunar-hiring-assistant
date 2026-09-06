"""FastAPI dependency constructors for Module 3 sourcing services and Apollo callbacks."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db_session, get_session_factory
from app.integrations.apollo.people import ApolloPeopleProvider
from app.sourcing.service import SourcingService
from app.sourcing.webhooks import SourcingWebhookService


def _apollo_provider() -> ApolloPeopleProvider | None:
    settings = get_settings()
    if not settings.apollo_api_key:
        return None
    return ApolloPeopleProvider(
        api_key=settings.apollo_api_key,
        base_url=settings.apollo_api_base_url,
        search_read_timeout_seconds=settings.apollo_search_read_timeout_seconds,
        enrichment_read_timeout_seconds=settings.apollo_enrichment_read_timeout_seconds,
    )


def get_sourcing_service(
    session: Annotated[Session, Depends(get_db_session)],
) -> Iterator[SourcingService]:
    """Yield one sourcing service and close its request-scoped Apollo clients afterward."""

    settings = get_settings()
    provider = _apollo_provider()
    try:
        yield SourcingService(
            session,
            search_provider=provider,
            search_stale_seconds=settings.sourcing_search_stale_seconds,
            enrichment_configured=bool(
                settings.apollo_api_key
                and settings.apollo_webhook_base_url
                and settings.apollo_webhook_signing_secret
            ),
        )
    finally:
        if provider is not None:
            provider.close()


def get_sourcing_webhook_service() -> SourcingWebhookService:
    """Build the callback finalizer with independent sessions for Candidate convergence."""

    return SourcingWebhookService(get_session_factory())
