from __future__ import annotations

from app.core.config import Settings


def test_settings_normalizes_postgres_url_for_psycopg() -> None:
    settings = Settings(database_url="postgresql://user:pass@localhost/db")
    assert settings.sqlalchemy_database_url == "postgresql+psycopg://user:pass@localhost/db"


def test_cors_origins_are_comma_separated() -> None:
    settings = Settings(
        database_url="postgresql://user:pass@localhost/db",
        cors_origins="http://localhost:3000,https://example.com",
    )
    assert settings.cors_origin_list == ["http://localhost:3000", "https://example.com"]
