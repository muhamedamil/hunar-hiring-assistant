"""Dependency-free Module 6 boundary, schema, public surface and frozen-contract validator."""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def require(path: str, *markers: str) -> None:
    """Require real production boundary markers without claiming behavioral qualification."""
    content = (ROOT / path).read_text(encoding="utf-8")
    for marker in markers:
        if marker not in content:
            raise SystemExit(f"Module 6 failed: {marker!r} missing in {path}")


def main() -> None:
    """Reject ownership leaks and missing contract/route/schema composition points."""
    packages = [
        ROOT / "apps/api/app/voice_calls",
        ROOT / "apps/api/app/integrations/hunar",
    ]
    for package in packages:
        for path in package.glob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            assert ast.get_docstring(tree), f"Module docstring missing: {path}"
            for node in ast.walk(tree):
                if isinstance(
                    node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
                ) and not node.name.startswith("_"):
                    assert ast.get_docstring(node), (
                        f"Public docstring missing: {path}:{node.name}"
                    )
            content = path.read_text(encoding="utf-8")
            for forbidden in (
                "Apollo",
                "created_source",
                "create_agent(",
                "update_agent(",
                "activate_agent(",
                "dispatch_generation",
                "call_result",
                "recording_url",
                "transcript",
                "webhooks",
                "match_score",
            ):
                assert forbidden not in content, f"Ownership leak: {path}:{forbidden}"
    require(
        "apps/api/app/voice_calls/service.py",
        "lock_dispatchable_outreach",
        "snapshot.phone_e164",
        "snapshot.screening_questions",
        "get_definition_version",
        "max_attempts=3",
        'f"hunar-voice-call:{execution_id}"',
        'f"hha-{execution_id.hex}"',
    )
    require(
        "apps/api/app/voice_calls/workers.py",
        "AmbiguousWorkError",
        "RetryableWorkError",
        "PermanentWorkError",
        "reconcile_unknown_work",
        "_lease_expired",
    )
    require(
        "apps/api/app/worker/main.py",
        "handlers.reconcile_unknown_work()",
        "voice_handlers.reconcile_unknown_work()",
        '"hunar_voice_call_dispatch"',
    )
    migration = "supabase/migrations/20260907113000_module_6_hunar_voice_execution.sql"
    require(
        migration,
        "create table public.voice_call_executions",
        "enable row level security",
        "before update",
        "unique (outreach_request_id)",
        "unique (provider_request_id)",
        "unique (provider_call_id)",
        "provider_payload_snapshot",
        "submitted_at is null",
    )
    assert (ROOT / migration).read_text(encoding="utf-8").count("create table ") == 1
    require(
        "apps/api/app/voice_calls/router.py",
        "status_code=202",
        '"/api/v1/voice-screening/options"',
        '"/api/v1/voice-call-executions/{execution_id}"',
    )
    require(
        "apps/web/components/outreach/voice-call-execution.tsx",
        "Preparing voice call…",
        "Call submitted to Hunar",
        "Call could not be submitted",
        "Call submission outcome is uncertain.",
        'row.status === "failed"',
    )
    require("apps/api/pyproject.toml", 'version = "0.7.0"')
    require(
        "apps/api/app/main.py",
        'version="0.7.0"',
        "app.include_router(voice_calls_router)",
    )
    print("Module 6 structural validation: PASS (behavioral/live gates are separate)")


if __name__ == "__main__":
    main()
