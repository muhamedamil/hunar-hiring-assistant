#!/usr/bin/env python3
"""Structurally validate Module 7 ownership, security order, schema, and forbidden dependencies."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(relative: str) -> str:
    """Read one required repository file and fail clearly if it is absent."""

    return (ROOT / relative).read_text(encoding="utf-8")


def require(text: str, *needles: str) -> None:
    """Require every structural invariant marker in one authoritative source."""

    missing = [needle for needle in needles if needle not in text]
    if missing:
        raise AssertionError(f"Missing Module 7 invariants: {missing}")


def main() -> None:
    """Run bounded checks without interpreting runtime secrets or provider data."""

    migration = read("supabase/migrations/20260907170000_module_7_call_results.sql")
    require(
        migration,
        "create table public.voice_call_results",
        "create table public.voice_screening_answers",
        "uq_voice_call_results_execution",
        "uq_voice_call_results_provider_call",
        "trg_voice_call_result_mutation_guard",
        "trg_voice_screening_answers_immutable",
        "enable row level security",
        "revoke all",
    )
    webhook = read("apps/api/app/call_results/router.py")
    require(
        webhook,
        "raw_body = await request.body()",
        "verify_hunar_webhook_signature(",
        "json.loads(raw_body.decode",
        '"/api/v1/webhooks/hunar/call-summary"',
    )
    if webhook.index("verify_hunar_webhook_signature(") > webhook.index("json.loads("):
        raise AssertionError("Webhook JSON parsing precedes signature verification")
    security = read("apps/api/app/integrations/hunar/webhook_security.py")
    require(security, "MAX_WEBHOOK_CLOCK_SKEW_SECONDS = 300", "hmac.compare_digest", "base64")
    service = read("apps/api/app/call_results/service.py")
    require(
        service,
        "HUNAR_RETRY_POLICY_CONFLICT",
        "HUNAR_SCREENING_ANSWERED_BY_MACHINE",
        "HUNAR_SCREENING_HUMAN_NOT_CONFIRMED",
        "get_screening_result_contract(binding.agent_contract_version)",
        "get_result_context(",
    )
    domain = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (ROOT / "apps/api/app/call_results").glob("*.py")
    )
    forbidden = (
        "from app.candidates",
        "from app.matching",
        "create_call(",
        'request_json("POST"',
        "GET /calls/",
        "Apollo",
    )
    found = [marker for marker in forbidden if marker in domain]
    if found:
        raise AssertionError(f"Forbidden Module 7 ownership markers: {found}")
    frontend = read("apps/web/lib/call-results/types.ts") + read(
        "apps/web/components/outreach/voice-call-result.tsx"
    )
    if "recording_url" in frontend:
        raise AssertionError("Frontend exposes recording_url")
    print("Module 7 structural validation: PASS (security, authority, recovery, privacy)")


if __name__ == "__main__":
    main()
