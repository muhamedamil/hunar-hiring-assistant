"""FastAPI application factory and shared operational endpoints."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.call_results.router import router as call_results_router
from app.candidates.router import router as candidates_router
from app.core.config import get_settings
from app.core.database import check_database_connection
from app.core.errors import DatabaseUnavailableError, register_exception_handlers
from app.core.logging import configure_logging
from app.core.request_context import RequestIdMiddleware
from app.jobs.router import router as jobs_router
from app.matching.router import router as matching_router
from app.outreach.router import router as outreach_router
from app.sourcing.router import router as sourcing_router
from app.voice_calls.router import router as voice_calls_router


def create_app() -> FastAPI:
    """Create the API application and register shared middleware, errors, and routers."""

    settings = get_settings()
    configure_logging(settings.log_level)

    app = FastAPI(
        title="Hunar Hiring Assistant API",
        version="0.8.0",
        docs_url="/docs" if settings.app_env != "production" else None,
        redoc_url=None,
    )

    app.add_middleware(RequestIdMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=False,
        allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", "X-Request-ID"],
    )

    register_exception_handlers(app)
    app.include_router(jobs_router)
    app.include_router(candidates_router)
    app.include_router(sourcing_router)
    app.include_router(matching_router)
    app.include_router(outreach_router)
    app.include_router(voice_calls_router)
    app.include_router(call_results_router)

    @app.get("/api/v1/health/live", tags=["health"])
    def live() -> dict[str, str]:
        """Return process liveness without contacting external dependencies."""

        return {"status": "ok"}

    @app.get("/api/v1/health/ready", tags=["health"])
    def ready() -> dict[str, str]:
        """Return readiness only when the configured PostgreSQL database is reachable."""

        try:
            check_database_connection()
        except Exception as exc:
            raise DatabaseUnavailableError() from exc
        return {"status": "ready", "database": "ok"}

    return app


app = create_app()
