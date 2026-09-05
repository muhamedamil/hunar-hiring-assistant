"""Dependency-free structural validation for Module 2 Candidate Core invariants."""

from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

REQUIRED_FILES = [
    "doc/MODULE_2_IMPLEMENTATION_PLAN.md",
    "apps/api/app/candidates/dependencies.py",
    "apps/api/app/candidates/errors.py",
    "apps/api/app/candidates/models.py",
    "apps/api/app/candidates/normalization.py",
    "apps/api/app/candidates/repository.py",
    "apps/api/app/candidates/router.py",
    "apps/api/app/candidates/schemas.py",
    "apps/api/app/candidates/service.py",
    "apps/web/app/candidates/page.tsx",
    "apps/web/app/candidates/new/page.tsx",
    "apps/web/app/candidates/[candidateId]/page.tsx",
    "apps/web/components/candidates/candidate-editor.tsx",
    "apps/web/lib/candidates/api.ts",
    "apps/web/lib/candidates/types.ts",
    "apps/web/tests/candidate-pages.test.tsx",
    "supabase/migrations/20260905234000_module_2_candidate_core.sql",
]

MODULE_2_PYTHON = [
    "apps/api/app/candidates/__init__.py",
    "apps/api/app/candidates/dependencies.py",
    "apps/api/app/candidates/errors.py",
    "apps/api/app/candidates/models.py",
    "apps/api/app/candidates/normalization.py",
    "apps/api/app/candidates/repository.py",
    "apps/api/app/candidates/router.py",
    "apps/api/app/candidates/schemas.py",
    "apps/api/app/candidates/service.py",
]


def fail(message: str) -> None:
    """Exit validation with one concise invariant failure."""

    raise AssertionError(message)


def read(relative: str) -> str:
    """Read a repository file as UTF-8 text."""

    return (ROOT / relative).read_text(encoding="utf-8")


def validate_required_files() -> None:
    """Require every frozen Candidate Core implementation artifact."""

    missing = [path for path in REQUIRED_FILES if not (ROOT / path).is_file()]
    if missing:
        fail(f"Missing Module 2 files: {', '.join(missing)}")


def validate_python_quality() -> None:
    """Check Candidate modules for syntax, module docstrings, and line-length discipline."""

    for relative in MODULE_2_PYTHON:
        source = read(relative)
        tree = ast.parse(source, filename=relative)
        if ast.get_docstring(tree) is None:
            fail(f"Missing module docstring: {relative}")
        for line_number, line in enumerate(source.splitlines(), start=1):
            if len(line) > 100:
                fail(f"Line exceeds 100 characters: {relative}:{line_number}")


def validate_schema_authority() -> None:
    """Check that Module 2 adds only Candidate Core tables through Supabase migration."""

    migration = read("supabase/migrations/20260905234000_module_2_candidate_core.sql").lower()
    required = [
        "create table public.candidates",
        "create table public.candidate_external_identities",
        "create unique index uq_candidates_email_ci",
        "create unique index uq_candidates_phone_e164",
        "unique (provider, external_person_id)",
        "create trigger trg_candidate_external_identities_immutable",
        "before update or delete on public.candidate_external_identities",
        "alter table public.candidates enable row level security",
        "alter table public.candidate_external_identities enable row level security",
        "revoke all on table public.candidates from anon, authenticated",
        "revoke all on table public.candidate_external_identities from anon, authenticated",
    ]
    for fragment in required:
        if fragment not in migration:
            fail(f"Module 2 migration is missing invariant: {fragment}")
    if "job_id" in migration:
        fail("Candidate Core migration must not introduce a Job relationship")


def validate_identity_boundaries() -> None:
    """Prove Candidate Core remains global, provider-neutral, and fail-closed on identity."""

    schemas = read("apps/api/app/candidates/schemas.py")
    service = read("apps/api/app/candidates/service.py")
    repository = read("apps/api/app/candidates/repository.py")
    candidates_source = "\n".join(read(path) for path in MODULE_2_PYTHON)

    for fragment in [
        "ExternalCandidateObservation",
        "resolve_external_candidate",
        "CandidateIdentityConflictError",
        "expected_revision",
    ]:
        if fragment not in schemas + service:
            fail(f"Candidate Core is missing shared identity contract: {fragment}")
    if "work_items" in candidates_source:
        fail("Candidate Core must not use the durable external-side-effect worker")
    if "ProviderHttpClient" in candidates_source or "httpx" in candidates_source:
        fail("Candidate Core must perform zero external HTTP calls")
    if "app.jobs" in candidates_source or "job_id" in candidates_source:
        fail("Candidate Core must not depend on Job state or own Job/Candidate relationships")
    if "source:" in schemas or "source =" in service:
        fail("Candidate must not collapse provider provenance into one source field")
    if "update_external_identity" in repository or "delete_external_identity" in repository:
        fail("External provider identity links must not expose generic mutation methods")
    if "_resolve_existing_candidate" not in service or "_resolve_after_identity_race" not in service:
        fail("External identity race recovery must converge the complete Candidate operation")


def validate_contact_and_pii_boundaries() -> None:
    """Check optional contact identity, PII minimization, and shared foundation hardening."""

    schemas = read("apps/api/app/candidates/schemas.py")
    database = read("apps/api/app/core/database.py")
    logging = read("apps/api/app/core/logging.py")
    pyproject = read("apps/api/pyproject.toml")

    for fragment in ["EmailStr | None", "phone: str | None = None", "has_email", "has_phone"]:
        if fragment not in schemas:
            fail(f"Candidate contact contract is missing: {fragment}")
    if "phonenumbers" not in pyproject or "email-validator" not in pyproject:
        fail("Candidate contact validation dependencies are incomplete")
    if "hide_parameters=True" not in database:
        fail("SQLAlchemy must hide bound parameters before Candidate PII is persisted")
    if '"email"' not in logging or '"phone"' not in logging:
        fail("Structured logging must redact Candidate email and phone fields")


def validate_frontend_contract() -> None:
    """Check Candidate UI remains global and exposes only Module 2 actions."""

    frontend = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (ROOT / "apps/web").rglob("*.tsx")
    )
    for fragment in [
        "Add candidate",
        "Create candidate",
        "Save changes",
        "Open existing candidate",
        "international country code",
    ]:
        if fragment not in frontend:
            fail(f"Candidate frontend is missing workflow contract: {fragment}")
    for forbidden in ["Match score", "Shortlist candidate", "Call candidate"]:
        if forbidden in frontend:
            fail(f"Candidate Core frontend contains later-module behavior: {forbidden}")


def validate_baseline_regression_guards() -> None:
    """Ensure repaired Module 0/1 validators still point at the current repository layout."""

    module_0 = read("scripts/validate_module_0.py")
    module_1 = read("scripts/validate_module_1.py")
    if "20260905115100_create_work_item_queue.sql" not in module_0:
        fail("Module 0 validator still points at a stale migration filename")
    if "doc/MODULE_1_IMPLEMENTATION_PLAN.md" not in module_1:
        fail("Module 1 validator still points at the stale root document path")


def main() -> int:
    """Run all dependency-free Module 2 structural checks."""

    checks = [
        validate_required_files,
        validate_python_quality,
        validate_schema_authority,
        validate_identity_boundaries,
        validate_contact_and_pii_boundaries,
        validate_frontend_contract,
        validate_baseline_regression_guards,
    ]
    for check in checks:
        check()
    print(f"Module 2 structural validation: PASS ({len(checks)} invariant groups)")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except AssertionError as exc:
        print(f"Module 2 structural validation: FAIL: {exc}", file=sys.stderr)
        sys.exit(1)
