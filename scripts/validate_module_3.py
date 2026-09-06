"""Dependency-free structural validation for Module 3 sourcing/enrichment invariants."""

from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

REQUIRED_FILES = [
    "doc/MODULE_3_IMPLEMENTATION_PLAN.md",
    "doc/MODULE_3_VALIDATION.md",
    "apps/api/app/sourcing/dependencies.py",
    "apps/api/app/sourcing/errors.py",
    "apps/api/app/sourcing/mapping.py",
    "apps/api/app/sourcing/models.py",
    "apps/api/app/sourcing/provider.py",
    "apps/api/app/sourcing/prioritization.py",
    "apps/api/app/sourcing/repository.py",
    "apps/api/app/sourcing/router.py",
    "apps/api/app/sourcing/schemas.py",
    "apps/api/app/sourcing/service.py",
    "apps/api/app/sourcing/webhooks.py",
    "apps/api/app/sourcing/workers.py",
    "apps/api/app/integrations/apollo/people.py",
    "apps/web/app/jobs/[jobId]/sourcing/page.tsx",
    "apps/web/app/sourcing/[runId]/page.tsx",
    "apps/web/components/sourcing/sourcing-workspace.tsx",
    "apps/web/lib/sourcing/api.ts",
    "apps/web/lib/sourcing/types.ts",
    "apps/web/tests/sourcing-workspace.test.tsx",
    "supabase/migrations/20260906113000_module_3_people_sourcing.sql",
    "supabase/migrations/20260906170000_module_3_evidence_enrichment.sql",
]

MODULE_3_PYTHON = sorted(
    [
        *Path(ROOT / "apps/api/app/sourcing").rglob("*.py"),
        *Path(ROOT / "apps/api/app/integrations/apollo").rglob("*.py"),
    ]
)


def fail(message: str) -> None:
    """Exit validation with one concise invariant failure."""

    raise AssertionError(message)


def read(relative: str) -> str:
    """Read one repository file as UTF-8 text."""

    return (ROOT / relative).read_text(encoding="utf-8")


def validate_required_files() -> None:
    """Require the complete frozen Module 3 implementation/qualification surface."""

    missing = [path for path in REQUIRED_FILES if not (ROOT / path).is_file()]
    if missing:
        fail(f"Missing Module 3 files: {', '.join(missing)}")


def validate_python_quality() -> None:
    """Enforce syntax, module/public docstrings, and the repository line discipline."""

    for path in MODULE_3_PYTHON:
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(path.relative_to(ROOT)))
        if ast.get_docstring(tree) is None:
            fail(f"Missing module docstring: {path.relative_to(ROOT)}")
        for line_number, line in enumerate(source.splitlines(), start=1):
            if len(line) > 100:
                fail(
                    "Line exceeds 100 characters: "
                    f"{path.relative_to(ROOT)}:{line_number}"
                )
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                if not node.name.startswith("_") and ast.get_docstring(node) is None:
                    fail(
                        f"Public symbol lacks docstring: {path.relative_to(ROOT)}:{node.name}"
                    )
            if isinstance(node, ast.ClassDef):
                for child in node.body:
                    if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        if not child.name.startswith("_") and ast.get_docstring(child) is None:
                            fail(
                                "Public method lacks docstring: "
                                f"{path.relative_to(ROOT)}:{node.name}.{child.name}"
                            )


def validate_schema_authority() -> None:
    """Require the three sourcing tables, immutable Job FK, hard bounds, RLS, and revokes."""

    migration = read("supabase/migrations/20260906113000_module_3_people_sourcing.sql").lower()
    required = [
        "create table public.sourcing_runs",
        "create table public.sourcing_results",
        "create table public.sourcing_enrichments",
        "foreign key (job_id, definition_version)",
        "references public.job_definition_versions(job_id, version)",
        "check (result_count <= result_limit)",
        "search_generation integer not null default 1 check (search_generation >= 1)",
        "constraint uq_sourcing_enrichments_result unique (sourcing_result_id)",
        "provider_request_id bigint",
        "alter table public.sourcing_runs enable row level security",
        "alter table public.sourcing_results enable row level security",
        "alter table public.sourcing_enrichments enable row level security",
        "revoke all on table public.sourcing_runs from anon, authenticated",
        "revoke all on table public.sourcing_results from anon, authenticated",
        "revoke all on table public.sourcing_enrichments from anon, authenticated",
    ]
    for fragment in required:
        if fragment not in migration:
            fail(f"Module 3 migration is missing invariant: {fragment}")
    if "email text" in migration or "phone_e164" in migration:
        fail("Sourcing tables must not duplicate Candidate contact truth")

    evidence_migration = read(
        "supabase/migrations/20260906170000_module_3_evidence_enrichment.sql"
    ).lower()
    for fragment in [
        "alter table public.sourcing_enrichments",
        "add column professional_evidence jsonb",
        "add column evidence_version text",
        "jsonb_typeof(professional_evidence) = 'object'",
        "(professional_evidence is null) = (evidence_version is null)",
    ]:
        if fragment not in evidence_migration:
            fail(f"Professional-evidence migration is missing invariant: {fragment}")


def validate_job_binding() -> None:
    """Require atomic READY binding without bypassing Module 1's Job authority."""

    jobs = read("apps/api/app/jobs/service.py")
    sourcing = read("apps/api/app/sourcing/service.py")
    if "lock_ready_definition_for_downstream_binding" not in jobs:
        fail("Module 1 is missing the downstream READY-lock binding seam")
    if "lock_ready_definition_for_downstream_binding" not in sourcing:
        fail("Sourcing must use the Module 1 READY-lock binding seam")
    if "require_ready_definition(" in sourcing:
        fail("Sourcing must not use a non-locking READY read when creating a new run")


def validate_mapping_and_provider_bounds() -> None:
    """Require exact provider mapping and defense-in-depth result bounds."""

    mapping = read("apps/api/app/sourcing/mapping.py")
    apollo = read("apps/api/app/integrations/apollo/people.py")
    service = read("apps/api/app/sourcing/service.py")
    for fragment in [
        "include_similar_titles=False",
        'UnmappedRequirement(field="required_skills"',
        'UnmappedRequirement(field="preferred_skills"',
        'field="min_years_experience"',
        'field="employment_type"',
        'field="work_arrangement"',
    ]:
        if fragment not in mapping:
            fail(f"Provider mapping is missing explicit semantic boundary: {fragment}")
    if "q_keywords" in mapping:
        fail("Canonical Job skills must not be silently translated into Apollo q_keywords")
    if "len(people) > requested_limit" not in apollo:
        fail("Apollo adapter must reject pages larger than requested")
    for fragment in [
        'phone_signal == "yes"',
        'phone_signal.startswith("maybe")',
        'phone_signal in {"no", "false"}',
        "returned_person_id != expected_person_id",
        "len(people) != 1",
    ]:
        if fragment not in apollo:
            fail(f"Apollo adapter contract normalization is missing: {fragment}")
    if "len(page.hits) > requested_limit" not in service:
        fail("Sourcing service must defend its result bound even behind another provider adapter")
    for fragment in [
        "run.search_generation += 1",
        "_owns_search_generation",
        "search_generation=search_generation",
    ]:
        if fragment not in service:
            fail(f"Stale-search generation guard is missing: {fragment}")

    priority = read("apps/api/app/sourcing/prioritization.py")
    for fragment in [
        "search_evidence_priority_v1",
        "primary_match and contactability_positive",
        "primary_match or alternate_match",
        "EnrichmentPriority.LOW_PRIORITY",
    ]:
        if fragment not in priority:
            fail(f"Pre-enrichment priority boundary is missing: {fragment}")


def validate_candidate_and_pii_boundaries() -> None:
    """Require Candidate Core resolution and prohibit direct contact/provider-payload ownership."""

    sourcing = "\n".join(path.read_text(encoding="utf-8") for path in MODULE_3_PYTHON)
    for fragment in [
        "CandidateService",
        "resolve_external_candidate",
        "ExternalCandidateObservation",
    ]:
        if fragment not in sourcing:
            fail(f"Module 3 is missing Candidate Core integration: {fragment}")
    for forbidden in ["CandidateRepository", "candidate_external_identities"]:
        if forbidden in sourcing:
            fail(f"Module 3 bypasses Candidate Core authority: {forbidden}")
    if "raw_provider_payload" in sourcing:
        fail("Module 3 must not create a raw provider payload warehouse")
    for forbidden in [
        'professional_evidence["email"]',
        'professional_evidence["phone"]',
    ]:
        if forbidden in sourcing:
            fail(f"Professional evidence contains Candidate contact truth: {forbidden}")

    worker = read("apps/api/app/sourcing/workers.py")
    service = read("apps/api/app/sourcing/service.py")
    for fragment in [
        "professional_evidence.model_dump",
        "get_matching_evidence_for_sourcing_result",
        "sourcing_result_id=result.id",
        "definition_version=run.definition_version",
    ]:
        if fragment not in f"{worker}\n{service}":
            fail(f"Professional-evidence provenance seam is missing: {fragment}")


def validate_retry_and_recovery() -> None:
    """Require certainty-aware credit handling and queue/domain UNKNOWN convergence."""

    worker = read("apps/api/app/sourcing/workers.py")
    runner = read("apps/api/app/worker/runner.py")
    for fragment in [
        "ApolloAmbiguousEnrichmentError",
        "_retry_or_fail_enrichment",
        "APOLLO_ENRICHMENT_ATTEMPTS_EXHAUSTED",
        "APOLLO_POLL_NOT_CONFIGURED",
        "APOLLO_POLL_ATTEMPTS_EXHAUSTED",
        "signed webhook remains authoritative",
        "reconcile_unknown_work",
        "WORKER_LEASE_EXPIRED",
        "apollo-enrichment-poll-recovery:",
    ]:
        if fragment not in worker:
            fail(f"Module 3 retry/recovery invariant missing: {fragment}")
    if "after_stale_recovery" not in runner:
        fail("Worker runner must invoke domain reconciliation after generic stale recovery")


def validate_webhook_security_and_finalization() -> None:
    """Require HTTPS callback config, HMAC capability verification, and one finalizer authority."""

    config = read("apps/api/app/core/config.py")
    router = read("apps/api/app/sourcing/router.py")
    webhook = read("apps/api/app/sourcing/webhooks.py")
    if "APOLLO_WEBHOOK_BASE_URL must use HTTPS" not in config:
        fail("Apollo callback base must require HTTPS")
    for fragment in ["hmac.compare_digest", "sign_apollo_webhook", "finalize_phone_result"]:
        if fragment not in webhook:
            fail(f"Webhook finalization invariant missing: {fragment}")
    if "ApolloPeopleProvider.parse_phone_result(payload)" not in router:
        fail("Webhook must parse provider payload without requiring a new external API call")


def validate_frontend_scope() -> None:
    """Require sourcing reachability while prohibiting future matching/outreach actions."""

    frontend = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (ROOT / "apps/web").rglob("*.tsx")
        if "node_modules" not in path.parts and ".next" not in path.parts
    )
    for fragment in [
        "Find people",
        "Search criteria actually used",
        "Not directly filtered by Apollo",
        "Enrich contact",
        "Waiting for Apollo phone result",
        "Candidate identity conflict",
        "outcome is uncertain",
        "persistedRunId",
    ]:
        if fragment not in frontend:
            fail(f"Module 3 frontend is missing workflow state: {fragment}")
    for forbidden in ["92% match", "Shortlist candidate", "Call candidate"]:
        if forbidden in frontend:
            fail(f"Module 3 frontend contains later-module action: {forbidden}")


def validate_regression_tests() -> None:
    """Require the meaningful provider/state/concurrency proof files before freeze."""

    tests = "\n".join(
        read(path)
        for path in [
            "apps/api/tests/test_sourcing_mapping.py",
            "apps/api/tests/test_sourcing_prioritization.py",
            "apps/api/tests/test_apollo_people.py",
            "apps/api/tests/test_sourcing_service.py",
            "apps/api/tests/test_sourcing_workers.py",
            "apps/api/tests/test_sourcing_webhooks.py",
            "apps/api/tests/test_sourcing_postgres.py",
            "apps/api/tests/test_job_service.py",
        ]
    )
    for fragment in [
        "over_limit",
        "lock_ready_definition_for_downstream_binding",
        "CANDIDATE_IDENTITY_CONFLICT",
        "APOLLO_ENRICHMENT_ATTEMPTS_EXHAUSTED",
        "unknown_work_reconciles",
        "mismatched_provider_person_id",
        "multiple_people_for_single_enrichment",
        "poll_retry_exhaustion_leaves_webhook_authority_open",
        "does_not_hide_normalization_runtime_failure",
        "stale_search_retry_advances_generation",
        "superseded_search_generation_cannot_overwrite",
        "priority_uses_historical_run_criteria_after_job_reapproval",
        "normalizes_documented_professional_evidence_without_contact_data",
        "professional_evidence_constraints_and_async_finalization_preserve_snapshot",
    ]:
        if fragment not in tests:
            fail(f"Module 3 proof surface is missing: {fragment}")


def main() -> int:
    """Run all dependency-free Module 3 structural invariant checks."""

    checks = [
        validate_required_files,
        validate_python_quality,
        validate_schema_authority,
        validate_job_binding,
        validate_mapping_and_provider_bounds,
        validate_candidate_and_pii_boundaries,
        validate_retry_and_recovery,
        validate_webhook_security_and_finalization,
        validate_frontend_scope,
        validate_regression_tests,
    ]
    for check in checks:
        check()
    print(f"Module 3 structural validation: PASS ({len(checks)} invariant groups)")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except AssertionError as exc:
        print(f"Module 3 structural validation: FAIL: {exc}", file=sys.stderr)
        sys.exit(1)
