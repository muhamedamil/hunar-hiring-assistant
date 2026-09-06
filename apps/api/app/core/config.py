"""Application configuration loaded from backend-only environment variables."""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Validated runtime configuration shared by the API and worker processes."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_env: Literal["development", "test", "production"] = "development"
    database_url: str = Field(min_length=1)
    cors_origins: str = "http://localhost:3000"
    log_level: str = "INFO"
    worker_poll_interval_seconds: float = Field(default=1.0, gt=0)
    worker_lease_seconds: int = Field(default=300, ge=30)
    gemini_api_key: str | None = None
    gemini_model: str = "gemini-3.7-flash"
    gemini_thinking_level: Literal["low", "medium", "high"] = "low"
    gemini_read_timeout_seconds: float = Field(default=60.0, gt=0, le=300)
    apollo_api_key: str | None = None
    apollo_api_base_url: str = "https://api.apollo.io/api/v1"
    apollo_webhook_base_url: str | None = None
    apollo_webhook_signing_secret: str | None = None
    apollo_search_read_timeout_seconds: float = Field(default=30.0, gt=0, le=120)
    apollo_enrichment_read_timeout_seconds: float = Field(default=60.0, gt=0, le=300)
    sourcing_search_stale_seconds: int = Field(default=300, ge=60, le=3600)

    @field_validator("database_url")
    @classmethod
    def validate_database_url(cls, value: str) -> str:
        """Require the direct PostgreSQL URL used by the SQLAlchemy backend."""

        allowed = ("postgresql://", "postgresql+psycopg://")
        if not value.startswith(allowed):
            raise ValueError("DATABASE_URL must be a PostgreSQL URL")
        return value

    @field_validator("log_level")
    @classmethod
    def normalize_log_level(cls, value: str) -> str:
        """Normalize and validate the process logging level."""

        normalized = value.upper()
        if normalized not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
            raise ValueError("LOG_LEVEL must be a standard Python logging level")
        return normalized

    @field_validator(
        "gemini_api_key",
        "apollo_api_key",
        "apollo_webhook_base_url",
        "apollo_webhook_signing_secret",
    )
    @classmethod
    def normalize_optional_secret(cls, value: str | None) -> str | None:
        """Trim optional backend-only integration values and collapse blanks to ``None``."""

        if value is None:
            return None
        normalized = value.strip()
        return normalized or None

    @field_validator("apollo_api_base_url")
    @classmethod
    def validate_apollo_api_base_url(cls, value: str) -> str:
        """Normalize the backend-only Apollo API base URL."""

        normalized = value.strip().rstrip("/")
        if not normalized.startswith("https://"):
            raise ValueError("APOLLO_API_BASE_URL must use HTTPS")
        return normalized

    @field_validator("apollo_webhook_base_url")
    @classmethod
    def validate_apollo_webhook_base_url(cls, value: str | None) -> str | None:
        """Require a public HTTPS-capable base URL when Apollo callbacks are configured."""

        if value is None:
            return None
        normalized = value.rstrip("/")
        if not normalized.startswith("https://"):
            raise ValueError("APOLLO_WEBHOOK_BASE_URL must use HTTPS")
        return normalized

    @field_validator("gemini_model")
    @classmethod
    def validate_gemini_model(cls, value: str) -> str:
        """Reject a blank Gemini model identifier."""

        normalized = value.strip()
        if not normalized:
            raise ValueError("GEMINI_MODEL cannot be blank")
        return normalized

    @property
    def cors_origin_list(self) -> list[str]:
        """Return normalized CORS origins from the comma-separated environment value."""

        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def sqlalchemy_database_url(self) -> str:
        """Return the configured PostgreSQL URL using SQLAlchemy's psycopg dialect name."""

        if self.database_url.startswith("postgresql+psycopg://"):
            return self.database_url
        return self.database_url.replace("postgresql://", "postgresql+psycopg://", 1)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process-wide cached validated settings instance."""

    return Settings()  # type: ignore[call-arg]
