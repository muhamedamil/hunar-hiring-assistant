"""Dependency-free structural validation for Module 1 implementation invariants."""

from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

REQUIRED_FILES = [
    "doc/MODULE_1_IMPLEMENTATION_PLAN.md",
    "apps/api/app/jobs/analysis.py",
    "apps/api/app/jobs/dependencies.py",
    "apps/api/app/jobs/errors.py",
    "apps/api/app/jobs/models.py",
    "apps/api/app/jobs/repository.py",
    "apps/api/app/jobs/router.py",
    "apps/api/app/jobs/schemas.py",
    "apps/api/app/jobs/service.py",
    "apps/api/app/integrations/gemini/job_analysis.py",
    "apps/web/app/jobs/page.tsx",
    "apps/web/app/jobs/new/page.tsx",
    "apps/web/app/jobs/[jobId]/page.tsx",
    "apps/web/components/jobs/job-editor.tsx",
    "apps/web/lib/jobs/api.ts",
    "apps/web/lib/jobs/types.ts",
    "supabase/migrations/20260905190000_module_1_job_definition.sql",
]

MODULE_1_PYTHON = [
    "apps/api/app/jobs/analysis.py",
    "apps/api/app/jobs/dependencies.py",
    "apps/api/app/jobs/errors.py",
    "apps/api/app/jobs/models.py",
    "apps/api/app/jobs/repository.py",
    "apps/api/app/jobs/router.py",
    "apps/api/app/jobs/schemas.py",
    "apps/api/app/jobs/service.py",
    "apps/api/app/integrations/gemini/__init__.py",
    "apps/api/app/integrations/gemini/job_analysis.py",
]


def fail(message: str) -> None:
    """Exit validation with a concise invariant failure."""

    raise AssertionError(message)


def read(relative: str) -> str:
    """Read one repository file as UTF-8 text."""

    return (ROOT / relative).read_text(encoding="utf-8")


def validate_required_files() -> None:
    """Require every frozen Module 1 implementation artifact."""

    missing = [path for path in REQUIRED_FILES if not (ROOT / path).is_file()]
    if missing:
        fail(f"Missing Module 1 files: {', '.join(missing)}")


def validate_python_quality() -> None:
    """Check module docstrings, syntax, and the configured 100-character line limit."""

    for relative in MODULE_1_PYTHON:
        source = read(relative)
        tree = ast.parse(source, filename=relative)
        if ast.get_docstring(tree) is None:
            fail(f"Missing module docstring: {relative}")
        for line_number, line in enumerate(source.splitlines(), start=1):
            if len(line) > 100:
                fail(f"Line exceeds 100 characters: {relative}:{line_number}")


def validate_schema_authority() -> None:
    """Prove migrations remain schema authority and Module 1 adds only its intended tables."""

    api_source = ROOT / "apps/api/app"
    all_python = "\n".join(
        path.read_text(encoding="utf-8") for path in api_source.rglob("*.py")
    )
    if "create_all(" in all_python:
        fail("SQLAlchemy create_all() is forbidden; Supabase migrations own schema")

    migration = read("supabase/migrations/20260905190000_module_1_job_definition.sql").lower()
    required_sql = [
        "create table public.jobs",
        "create table public.job_definition_versions",
        "foreign key (id, approved_version)",
        "trg_job_definition_versions_immutable",
        "before update or delete on public.job_definition_versions",
        "alter table public.jobs enable row level security",
        "alter table public.job_definition_versions enable row level security",
        "revoke all on table public.jobs from anon, authenticated",
        "revoke all on table public.job_definition_versions from anon, authenticated",
    ]
    for fragment in required_sql:
        if fragment not in migration:
            fail(f"Migration is missing invariant: {fragment}")


def validate_state_boundaries() -> None:
    """Check the shared Task-1/Task-2 authority and historical snapshot boundaries."""

    schemas = read("apps/api/app/jobs/schemas.py")
    service = read("apps/api/app/jobs/service.py")
    repository = read("apps/api/app/jobs/repository.py")
    analysis = read("apps/api/app/jobs/analysis.py")

    if "alternate_titles" not in schemas:
        fail("Job requirements must expose alternate_titles")
    if "\n    titles:" in schemas:
        fail("Primary title must have one authority; do not reintroduce requirements.titles")
    if "require_ready_definition" not in service:
        fail("Missing approved-definition downstream gate")
    if "JobStatus.READY" not in service or "JobNotReadyError" not in service:
        fail("DRAFT jobs must block new downstream work")
    if "insert_definition_version" not in repository:
        fail("Repository must support immutable snapshot insertion")
    forbidden_snapshot_mutations = ["update_definition_version", "delete_definition_version"]
    if any(name in repository for name in forbidden_snapshot_mutations):
        fail("Approved definition repository must not expose snapshot mutation methods")
    if "Session" in analysis or "JobRepository" in analysis or "work_items" in analysis:
        fail("AI analysis must remain non-mutating and outside the worker path")


def validate_provider_and_secret_boundaries() -> None:
    """Check Gemini remains backend-only and uses the existing no-auto-retry HTTP boundary."""

    gemini = read("apps/api/app/integrations/gemini/job_analysis.py")
    config = read("apps/api/app/core/config.py")
    web_source_suffixes = {".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx"}
    web_source = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (ROOT / "apps/web").rglob("*")
        if path.is_file()
        and path.suffix in web_source_suffixes
        and not any(part in {"node_modules", ".next"} for part in path.parts)
    )

    if "ProviderHttpClient" not in gemini or "/v1beta/interactions" not in gemini:
        fail("Gemini adapter must use the shared provider client and Interactions API")
    if "JobAnalysisProviderOutput.model_json_schema()" not in gemini:
        fail("Gemini adapter must request structured output using the typed schema")
    if "gemini_api_key" not in config or "gemini-3.7-flash" not in config:
        fail("Backend Gemini configuration is incomplete")
    if "NEXT_PUBLIC_GEMINI" in web_source or "GEMINI_API_KEY" in web_source:
        fail("Gemini secret/config must not be exposed to the browser")


def validate_frontend_contract() -> None:
    """Check the UI exposes the explicit approve/reopen workflow rather than silent mutation."""

    frontend = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (ROOT / "apps/web").rglob("*.tsx")
    ) + "\n" + read("apps/web/lib/jobs/api.ts")
    for fragment in [
        "Analyze with AI",
        "Save draft",
        "Mark ready",
        "Reopen to edit",
        "expectedRevision",
    ]:
        if fragment not in frontend:
            fail(f"Frontend is missing workflow contract: {fragment}")


def main() -> int:
    """Run all dependency-free Module 1 structural checks."""

    checks = [
        validate_required_files,
        validate_python_quality,
        validate_schema_authority,
        validate_state_boundaries,
        validate_provider_and_secret_boundaries,
        validate_frontend_contract,
    ]
    for check in checks:
        check()
    print(f"Module 1 structural validation: PASS ({len(checks)} invariant groups)")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except AssertionError as exc:
        print(f"Module 1 structural validation: FAIL: {exc}", file=sys.stderr)
        sys.exit(1)
