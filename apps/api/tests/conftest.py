from __future__ import annotations

import os

os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+psycopg://postgres:postgres@127.0.0.1:54322/postgres",
)
os.environ.setdefault("APP_ENV", "test")
