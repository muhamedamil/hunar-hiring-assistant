from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_settings
from app.core.database import check_database_connection
from app.core.errors import DatabaseUnavailableError, register_exception_handlers
from app.core.logging import configure_logging
from app.core.request_context import RequestIdMiddleware


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level)

    app = FastAPI(
        title="Hunar Hiring Assistant API",
        version="0.1.0",
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

    @app.get("/api/v1/health/live", tags=["health"])
    def live() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/api/v1/health/ready", tags=["health"])
    def ready() -> dict[str, str]:
        try:
            check_database_connection()
        except Exception as exc:
            raise DatabaseUnavailableError() from exc
        return {"status": "ready", "database": "ok"}

    return app


app = create_app()
