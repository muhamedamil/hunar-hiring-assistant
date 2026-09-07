"""Dependency-free structural validator for Module 5 outreach boundaries."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def require(path: str, *needles: str) -> None:
    """Require a file and every named Module 5 invariant marker."""

    target = ROOT / path
    if not target.exists():
        raise SystemExit(f"Module 5 validation failed: missing {path}")
    source = target.read_text(encoding="utf-8")
    for needle in needles:
        if needle not in source:
            raise SystemExit(f"Module 5 validation failed: {needle!r} missing from {path}")


def forbid_tree(path: str, *needles: str) -> None:
    """Reject Module 6/7/provider ownership leaks from the Module 5 package."""

    source = "\n".join(
        candidate.read_text(encoding="utf-8")
        for candidate in (ROOT / path).glob("*.py")
    ).casefold()
    for needle in needles:
        if needle.casefold() in source:
            raise SystemExit(f"Module 5 validation failed: prohibited {needle!r} in {path}")


def main() -> None:
    """Validate schema parity, hashing, routes, UI reuse, and architecture boundaries."""

    require(
        "supabase/migrations/20260906213000_module_5_outreach.sql",
        "create table public.outreach_requests",
        "fk_outreach_requests_decision_match",
        "uq_outreach_requests_exact_context",
        "enable row level security",
        "before update or delete",
    )
    require(
        "apps/api/app/outreach/models.py",
        "job_candidate_id: Mapped[UUID]",
        "decision_match_id: Mapped[UUID]",
        "phone_e164_snapshot: Mapped[str]",
        "screening_questions_snapshot: Mapped",
        "screening_context_hash: Mapped[str]",
    )
    require(
        "apps/api/app/outreach/service.py",
        "canonical_screening_context_hash",
        "preparation_state_fingerprint",
        "assert_unique_screening_question_keys",
        "lock_current_shortlist_for_downstream_outreach",
        "lock_outreach_contact_for_downstream_binding",
        "find_exact",
        "id=uuid4()",
        "lock_dispatchable_outreach",
    )
    require(
        "apps/api/app/jobs/service.py",
        "assert_unique_screening_question_keys",
    )
    require(
        "apps/api/app/outreach/router.py",
        "/api/v1/job-candidates/{job_candidate_id}/outreach-preparation",
        "/api/v1/job-candidates/{job_candidate_id}/outreach-requests",
        "/api/v1/outreach-requests",
    )
    require(
        "apps/web/components/outreach/outreach-preparation.tsx",
        "ScreeningQuestionEditor",
        "Reset to Job defaults",
        "Edit Job defaults",
        "source_job_question_id",
    )
    require(
        "apps/web/components/matching/job-candidate-detail.tsx",
        "Prepare voice outreach",
    )
    forbid_tree(
        "apps/api/app/outreach",
        "ApolloPeopleProvider",
        "Gemini",
        "HunarProvider",
        "ProviderHttpClient",
        "work_items",
        "enqueue",
        "call_result",
        "webhook",
        "created_source",
        "preferred_sourcing",
    )
    print("Module 5 structural validation: PASS (7 invariant groups)")


if __name__ == "__main__":
    main()
