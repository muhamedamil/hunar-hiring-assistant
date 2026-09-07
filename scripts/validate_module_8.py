#!/usr/bin/env python3
"""Structurally validate the read-only Module 8 dashboard boundary and frozen contracts."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DASHBOARD = ROOT / "apps/api/app/dashboard"


def read(relative: str) -> str:
    """Read one required repository file and fail clearly when it is missing."""

    return (ROOT / relative).read_text(encoding="utf-8")


def require(text: str, *needles: str) -> None:
    """Require every structural invariant marker in one authoritative source."""

    missing = [needle for needle in needles if needle not in text]
    if missing:
        raise AssertionError(f"Missing Module 8 invariants: {missing}")


def main() -> None:
    """Prove the dashboard is read-only composition with no new business/provider authority."""

    required_files = [
        "apps/api/app/dashboard/__init__.py",
        "apps/api/app/dashboard/dependencies.py",
        "apps/api/app/dashboard/repository.py",
        "apps/api/app/dashboard/router.py",
        "apps/api/app/dashboard/schemas.py",
        "apps/api/app/dashboard/service.py",
        "apps/api/tests/test_dashboard_service.py",
        "apps/api/tests/test_dashboard_router.py",
        "apps/api/tests/test_dashboard_database.py",
        "doc/MODULE_8_IMPLEMENTATION_LEDGER.md",
        "doc/MODULE_8_IMPLEMENTATION_PLAN.md",
        "doc/MODULE_8_VALIDATION.md",
        "apps/web/lib/dashboard/api.ts",
        "apps/web/lib/dashboard/queries.ts",
        "apps/web/lib/dashboard/types.ts",
        "apps/web/lib/dashboard/presentation.ts",
        "apps/web/components/dashboard/dashboard-overview.tsx",
        "apps/web/components/dashboard/screenings-workspace.tsx",
        "apps/web/components/dashboard/screening-detail.tsx",
        "apps/web/components/dashboard/screening-detail-content.tsx",
        "apps/web/components/dashboard/screening-state-badge.tsx",
        "apps/web/app/screenings/page.tsx",
        "apps/web/app/screenings/[executionId]/page.tsx",
        "apps/web/tests/dashboard.test.tsx",
        "apps/web/tests/screenings-dashboard.test.tsx",
    ]
    missing = [path for path in required_files if not (ROOT / path).exists()]
    if missing:
        raise AssertionError(f"Missing Module 8 files: {missing}")

    forbidden_files = [
        DASHBOARD / "models.py",
        DASHBOARD / "workers.py",
        DASHBOARD / "provider.py",
        DASHBOARD / "webhooks.py",
    ]
    present = [str(path.relative_to(ROOT)) for path in forbidden_files if path.exists()]
    if present:
        raise AssertionError(f"Forbidden Module 8 authority files exist: {present}")

    router = read("apps/api/app/dashboard/router.py")
    require(
        router,
        'router = APIRouter(prefix="/api/v1/dashboard"',
        '@router.get("/overview"',
        '@router.get("/screenings"',
        '@router.get("/screenings/{execution_id}"',
    )
    for marker in ("@router.post", "@router.put", "@router.patch", "@router.delete"):
        if marker in router:
            raise AssertionError(f"Dashboard mutation route found: {marker}")
    if router.count("@router.get(") != 3:
        raise AssertionError("Dashboard router must expose exactly three GET operations")

    repository = read("apps/api/app/dashboard/repository.py")
    require(
        repository,
        "def dashboard_screening_state_expression()",
        "VoiceCallResult.screening_result_state == \"available\"",
        "VoiceCallExecution.status == \"queued\"",
        "def count_interested_screenings(",
        "OutreachRequest.id == VoiceCallExecution.outreach_request_id",
        "JobCandidateMatch.id == OutreachRequest.decision_match_id",
        "JobCandidateMatch.job_candidate_id == OutreachRequest.job_candidate_id",
        "JobDefinitionVersion.version == JobCandidateMatch.definition_version",
        "OutreachRequest.screening_questions_snapshot",
        "VoiceScreeningAnswer.voice_call_result_id == result_id",
        "dashboard_sort_at_expression().desc()",
        "func.coalesce(VoiceCallResult.observed_at, VoiceCallExecution.updated_at)",
        "Candidate.full_name.ilike(pattern",
        "JobDefinitionVersion.title.ilike(pattern",
        "JobCandidateMatch.job_id == JobCandidate.job_id",
        "JobCandidateMatch.candidate_id == JobCandidate.candidate_id",
    )
    if repository.count("dashboard_screening_state_expression()") < 5:
        raise AssertionError("Canonical screening-state expression is not reused across read paths")
    screening_select = repository.split("def _screening_select", 1)[1].split(
        "def _screening_identity_select", 1
    )[0]
    if "VoiceScreeningAnswer" in screening_select:
        raise AssertionError(
            "Screening list projection joins answer rows and can multiply executions"
        )
    if 'Job.title.label("job_title")' in screening_select:
        raise AssertionError(
            "Screening projection uses current Job title instead of immutable history"
        )
    if "session.commit" in repository or ".commit()" in repository:
        raise AssertionError("DashboardRepository owns a commit")

    service = read("apps/api/app/dashboard/service.py")
    require(
        service,
        "with self._session.begin():",
        "DASHBOARD_HISTORICAL_CONTEXT_INVALID",
        'context.lifecycle_status == "COMPLETED"',
        'context.answered_by == "HUMAN"',
        "ScreeningAnswerState(answer.answer_state) if answer is not None else None",
    )

    schemas = read("apps/api/app/dashboard/schemas.py")
    require(
        schemas,
        'QUEUED = "queued"',
        'RESULT_AVAILABLE = "result_available"',
        "answer_state: ScreeningAnswerState | None = None",
        "recording_available: bool",
        "DashboardSearchQuery = Annotated[str, AfterValidator(_normalize_search_query)]",
    )
    forbidden_public_fields = (
        "phone:",
        "phone_e164:",
        "mobile_number:",
        "email:",
        "recording_url:",
        "provider_call_id:",
        "provider_request_id:",
        "provider_initial_status:",
        "provider_payload",
        "webhook_signature",
        "work_item",
        "created_source:",
        "external_identity",
    )
    leaked = [marker for marker in forbidden_public_fields if marker in schemas]
    if leaked:
        raise AssertionError(f"Unsafe dashboard public fields found: {leaked}")

    dashboard_domain = "\n".join(
        path.read_text(encoding="utf-8") for path in DASHBOARD.glob("*.py")
    )
    forbidden_dependencies = (
        "app.integrations.apollo.people",
        "app.integrations.gemini",
        "app.integrations.hunar.client",
        "app.sourcing.provider",
        "app.work_items",
        "app.worker",
        "import httpx",
        "from httpx",
        "import requests",
        "from requests",
        "urllib.request",
        "aiohttp",
        "create_call(",
        "enqueue(",
    )
    found = [marker for marker in forbidden_dependencies if marker in dashboard_domain]
    if found:
        raise AssertionError(f"Forbidden dashboard provider/worker dependency: {found}")

    if "from app.jobs.models import Job," in repository:
        # Current Job is allowed for metrics/review attention; screening title must use JDV.
        require(repository, "JobDefinitionVersion.title.label(\"job_title\")")
    if "Job.screening_questions" in dashboard_domain:
        raise AssertionError("Dashboard remaps historical screening questions from current Job")

    dashboard_api = read("apps/web/lib/dashboard/api.ts")
    presentation = read("apps/web/lib/dashboard/presentation.ts")
    overview_ui = read("apps/web/components/dashboard/dashboard-overview.tsx")
    screenings_ui = read("apps/web/components/dashboard/screenings-workspace.tsx")
    screening_detail_ui = read("apps/web/components/dashboard/screening-detail-content.tsx")
    outreach_list_ui = read("apps/web/components/outreach/outreach-list.tsx")
    outreach_detail_ui = read("apps/web/components/outreach/outreach-detail.tsx")
    outreach_result_ui = read("apps/web/components/outreach/voice-call-result.tsx")
    shell = read("apps/web/components/layout/app-shell.tsx")
    screenings_page = read("apps/web/app/screenings/page.tsx")

    require(
        dashboard_api,
        'api.get("/dashboard/overview")',
        'api.get(`/dashboard/screenings?${params.toString()}`)',
        'api.get(`/dashboard/screenings/${executionId}`)',
        'params.set("job_id", filters.jobId)',
    )
    for marker in ("api.post(", "api.patch(", "api.put(", "api.delete("):
        if marker in dashboard_api:
            raise AssertionError(f"Dashboard frontend added a mutation call: {marker}")

    require(
        presentation,
        'submission_unknown: "Submission uncertain"',
        'result_available: "Result available"',
        'if (state === null) return "No authoritative answer recorded"',
        'state === "queued" || state === "awaiting_result" || state === "submission_unknown"',
    )
    require(
        overview_ui,
        'data.screenings.result_available',
        'data.recent_screenings.map',
        'dateTime={row.sort_at}',
        'humanize(row.conversation_outcome)',
        'humanize(row.candidate_interest)',
    )
    require(
        screenings_ui,
        'const jobId = params.get("job_id") ?? undefined',
        'listDashboardScreenings(filters)',
        'isUnresolvedScreeningState(row.screening_state)',
        'row.duration_seconds',
        'row.observed_at',
    )
    if 'aria-label="Job"' in screenings_ui or 'All jobs' in screenings_ui:
        raise AssertionError("Screenings UI introduced a capped/global Job dropdown")
    require(
        screening_detail_ui,
        'submissionStatusLabels[detail.submission_status]',
        '<ScreeningStateBadge state={detail.screening_state}',
        'humanize(detail.lifecycle_status)',
        'answerDisplay(question.answer_state, question.answer_text)',
        'No human screening answers are available for this call.',
        'Screening result could not be safely normalized.',
    )
    require(screenings_page, '<Suspense fallback=')

    require(
        outreach_list_ui,
        'request.job_title',
        '<ScreeningStateBadge state={request.screening_state}',
        'Ready for execution',
    )
    require(
        outreach_detail_ui,
        'request.job_title',
        'request.job_definition_version',
        '<ScreeningStateBadge state={request.screening_state}',
    )
    require(
        outreach_result_ui,
        'getDashboardScreeningDetail(execution.id)',
        '<ScreeningDetailContent detail={query.data} showIdentity={false}',
        'invalidateQueries({ queryKey: outreachKeys.all })',
    )
    for marker in ("reconcileCallResult", "Refresh result from Hunar", "Check Hunar safely"):
        if marker in outreach_result_ui:
            raise AssertionError(f"Recruiter result UI retained provider reconciliation: {marker}")

    require(
        shell,
        '["Dashboard", "/"]',
        '["Jobs", "/jobs"]',
        '["Candidates", "/candidates"]',
        '["Outreach", "/outreach"]',
        '["Screenings", "/screenings"]',
    )

    recruiter_sources = "\n".join(
        path.read_text(encoding="utf-8")
        for root in (ROOT / "apps/web/app", ROOT / "apps/web/components")
        for path in root.rglob("*.tsx")
    )
    for marker in (
        "Module 1",
        "Module 2",
        "Module 3",
        "Module 4",
        "Module 5",
        "Module 6",
        "Module 7",
        "future Module",
    ):
        if marker in recruiter_sources:
            raise AssertionError(f"Recruiter-facing Module language remains: {marker}")

    dashboard_frontend = "\n".join(
        path.read_text(encoding="utf-8")
        for root in (ROOT / "apps/web/lib/dashboard", ROOT / "apps/web/components/dashboard")
        for path in root.rglob("*.ts*")
    )
    forbidden_frontend_dependencies = (
        "HUNAR_API_KEY",
        "APOLLO_API_KEY",
        "GEMINI_API_KEY",
        "provider_call_id",
        "provider_request_id",
        "recording_url",
        "phone_e164",
        "masked_phone",
        "work_item",
        "reconcile",
    )
    found_frontend = [
        marker for marker in forbidden_frontend_dependencies if marker in dashboard_frontend
    ]
    if found_frontend:
        raise AssertionError(f"Unsafe dashboard frontend dependency/field found: {found_frontend}")

    main = read("apps/api/app/main.py")
    pyproject = read("apps/api/pyproject.toml")
    lockfile = read("apps/api/uv.lock")
    require(main, 'version="0.9.0"', "app.include_router(dashboard_router)")
    require(pyproject, 'version = "0.9.0"')
    require(
        lockfile,
        'name = "hunar-hiring-assistant-api"\nversion = "0.9.0"',
    )

    migrations = sorted((ROOT / "supabase/migrations").glob("*.sql"))
    if migrations[-1].name != "20260907170000_module_7_call_results.sql":
        raise AssertionError(
            "Module 8 migration exists without a separately proven index qualification"
        )

    print(
        "Module 8 structural validation: PASS "
        "(read-only authority, history, state reuse, provider isolation, privacy)"
    )


if __name__ == "__main__":
    main()
