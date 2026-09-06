"""Worker composition root registering durable Module 3 provider-side-effect handlers."""

from __future__ import annotations

from app.core.config import get_settings
from app.core.database import get_session_factory
from app.core.logging import configure_logging
from app.integrations.apollo.people import ApolloPeopleProvider
from app.sourcing.workers import SourcingWorkHandlers
from app.worker.registry import WorkHandlerRegistry
from app.worker.runner import WorkerRunner


def build_handlers() -> SourcingWorkHandlers:
    """Build Module 3 work handlers from the current backend-only integration settings."""

    settings = get_settings()
    provider = None
    if settings.apollo_api_key:
        provider = ApolloPeopleProvider(
            api_key=settings.apollo_api_key,
            base_url=settings.apollo_api_base_url,
            search_read_timeout_seconds=settings.apollo_search_read_timeout_seconds,
            enrichment_read_timeout_seconds=settings.apollo_enrichment_read_timeout_seconds,
        )
    return SourcingWorkHandlers(
        session_factory=get_session_factory(),
        provider=provider,
        settings=settings,
    )


def build_registry(handlers: SourcingWorkHandlers | None = None) -> WorkHandlerRegistry:
    """Build the worker registry using the currently configured backend integrations."""

    resolved_handlers = handlers or build_handlers()
    registry = WorkHandlerRegistry()
    registry.register(
        "apollo_people_enrichment", resolved_handlers.handle_people_enrichment
    )
    registry.register("apollo_enrichment_poll", resolved_handlers.handle_enrichment_poll)
    return registry


def main() -> None:
    """Configure logging and run the durable worker loop until interrupted."""

    settings = get_settings()
    configure_logging(settings.log_level)
    handlers = build_handlers()
    WorkerRunner(
        registry=build_registry(handlers),
        settings=settings,
        after_stale_recovery=handlers.reconcile_unknown_work,
    ).run_forever()


if __name__ == "__main__":
    main()
