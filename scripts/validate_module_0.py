from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

REQUIRED_FILES = [
    "apps/api/app/main.py",
    "apps/api/app/core/config.py",
    "apps/api/app/core/database.py",
    "apps/api/app/core/errors.py",
    "apps/api/app/core/http_client.py",
    "apps/api/app/core/logging.py",
    "apps/api/app/core/retry.py",
    "apps/api/app/work_items/models.py",
    "apps/api/app/work_items/repository.py",
    "apps/api/app/worker/runner.py",
    "apps/web/app/page.tsx",
    "apps/web/lib/api/client.ts",
    "supabase/migrations/20260905115100_create_work_item_queue.sql",
]

SOURCE_SUFFIXES = {".py", ".ts", ".tsx", ".js", ".sql"}
IGNORED_SOURCE_DIRECTORIES = {
    ".git",
    ".next",
    ".venv",
    "env",
    "node_modules",
    "venv",
}
FORBIDDEN_SOURCE_PATTERNS = {
    "Base.metadata.create_all": "Schema creation must remain migration-only.",
    "NEXT_PUBLIC_DATABASE_URL": "Database credentials must never enter the browser.",
    "SUPABASE_SERVICE_ROLE_KEY": "Module 0 does not require a Supabase service-role key.",
}
BUSINESS_TABLES = {
    "jobs",
    "candidates",
    "job_candidates",
    "outreach_calls",
    "screening_results",
    "webhook_events",
}


def fail(message: str, failures: list[str]) -> None:
    failures.append(message)


def main() -> int:
    failures: list[str] = []

    for relative in REQUIRED_FILES:
        if not (ROOT / relative).is_file():
            fail(f"missing required file: {relative}", failures)

    source_files = [
        path
        for path in ROOT.rglob("*")
        if path.is_file()
        and path.suffix in SOURCE_SUFFIXES
        and path.resolve() != Path(__file__).resolve()
        and not any(part in IGNORED_SOURCE_DIRECTORIES for part in path.parts)
    ]
    source = "\n".join(path.read_text(encoding="utf-8", errors="ignore") for path in source_files)

    for pattern, reason in FORBIDDEN_SOURCE_PATTERNS.items():
        if pattern in source:
            fail(f"forbidden source pattern {pattern!r}: {reason}", failures)

    migration_path = ROOT / "supabase/migrations/20260905115100_create_work_item_queue.sql"
    if migration_path.exists():
        migration = migration_path.read_text(encoding="utf-8")
        tables = re.findall(
            r"create\s+table\s+(?:public\.)?([a-zA-Z0-9_]+)", migration, re.IGNORECASE
        )
        if tables != ["work_items"]:
            fail(f"Module 0 migration must create only work_items; found {tables}", failures)
        for table in BUSINESS_TABLES:
            if re.search(
                rf"create\s+table\s+(?:public\.)?{re.escape(table)}\b",
                migration,
                re.IGNORECASE,
            ):
                fail(f"out-of-scope business table created: {table}", failures)
        if "status in ('pending', 'running', 'retry_scheduled', 'unknown')" not in migration:
            fail("active dedupe index does not protect UNKNOWN work", failures)

    repository_path = ROOT / "apps/api/app/work_items/repository.py"
    if repository_path.exists():
        repository = repository_path.read_text(encoding="utf-8")
        stale_method = repository.split("def recover_stale_running", 1)
        if len(stale_method) != 2 or "WorkItemStatus.UNKNOWN.value" not in stale_method[1]:
            fail("stale RUNNING work is not explicitly recovered to UNKNOWN", failures)

    http_path = ROOT / "apps/api/app/core/http_client.py"
    if http_path.exists():
        http_source = http_path.read_text(encoding="utf-8")
        if "retry(" in http_source.lower() or "tenacity" in http_source.lower():
            fail("shared HTTP client appears to contain automatic retry behavior", failures)

    if failures:
        print("Module 0 structural validation: FAIL")
        for item in failures:
            print(f" - {item}")
        return 1

    print("Module 0 structural validation: PASS")
    print(f"Checked {len(source_files)} source files.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
