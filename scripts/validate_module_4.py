"""Static invariant validator for Module 4 matching and shortlist ownership boundaries."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def require(path: str, *needles: str) -> None:
    """Require a file and every invariant marker within it."""

    target = ROOT / path
    if not target.exists():
        raise SystemExit(f"Module 4 validation failed: missing {path}")
    text = target.read_text(encoding="utf-8")
    for needle in needles:
        if needle not in text:
            raise SystemExit(f"Module 4 validation failed: {needle!r} missing from {path}")


def forbid(path: str, *needles: str) -> None:
    """Reject prohibited authority leaks from one implementation file."""

    text = (ROOT / path).read_text(encoding="utf-8")
    for needle in needles:
        if needle in text:
            raise SystemExit(f"Module 4 validation failed: prohibited {needle!r} in {path}")


def main() -> None:
    """Validate Module 4 schema, provider, routing, scoring, and boundary invariants."""

    require(
        "supabase/migrations/20260906190000_module_4_candidate_job_matching.sql",
        "create table public.job_candidates",
        "create table public.job_candidate_matches",
        "unique (job_id, candidate_id)",
        "match_score <= evidence_coverage",
        "prevent_completed_job_candidate_match_mutation",
        "enable row level security",
    )
    require(
        "apps/api/app/matching/scoring.py",
        'MATCH_POLICY_VERSION = "candidate_job_match_v1"',
        "No verified Candidate skill evidence exists",
        "complete employment end dates",
    )
    require(
        "apps/api/app/integrations/gemini/candidate_matching.py",
        "Do not infer skills",
        "Do not infer years of experience",
        "Do not calculate a score",
        "do not make a shortlist",
    )
    require(
        "apps/api/app/matching/service.py",
        "lock_ready_definition_for_downstream_binding",
        "lock_matching_snapshot_for_downstream_binding",
        "get_resolved_candidate_evidence_source",
        "decision_match_id",
        "if created:",
        "if matching_context_created:",
        "self.evaluate_match(relation_id)",
    )
    forbid(
        "apps/api/app/matching/service.py",
        "ApolloPeopleProvider",
        "request_enrichment(",
        "resolve_external_candidate(",
    )
    require(
        "apps/api/app/matching/router.py",
        "/api/v1/jobs/{job_id}/job-candidates",
        "/api/v1/sourcing-results/{result_id}/job-candidate",
        "/api/v1/job-candidates/{job_candidate_id}/match",
        "/api/v1/job-candidates/{job_candidate_id}/shortlist",
    )
    require(
        "apps/api/app/candidates/service.py",
        "lock_matching_snapshot_for_downstream_binding",
        "get_summaries_by_ids",
    )
    forbid(
        "apps/api/app/matching/schemas.py",
        "class CandidateMatchingSnapshot",
    )
    require(
        "apps/api/app/sourcing/service.py",
        "get_resolved_candidate_evidence_source",
    )
    require(
        "apps/web/components/matching/job-candidate-workspace.tsx",
        "router.push(`/job-candidates/${relation.id}`)",
    )
    require(
        "apps/web/components/matching/job-candidate-detail.tsx",
        "Initial assessment unavailable",
        "Refresh match",
        "Retry analysis",
    )
    forbid(
        "apps/web/components/matching/job-candidate-detail.tsx",
        "Analyze match",
    )
    print("Module 4 structural validation: PASS (11 invariant groups)")


if __name__ == "__main__":
    main()
