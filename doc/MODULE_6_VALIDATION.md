# Module 6 validation and handoff

Module 6 implements durable Hunar submission truth and is frozen as the upstream authority for
Module 7. Historical qualification limitations below remain recorded rather than reclassified.

## Authoritative baseline and changes

Patch baseline: `hunar-hiring-assistant-main (2)(1).zip`, explicitly authorized by the user after the
prompt/plan named `(2)(2).zip`. The original upload is unchanged. Backend version is now `0.7.0`.

| Area | Changes |
| --- | --- |
| Domain | `app/voice_calls/`: immutable agent contract, DTOs, model, repository, service, worker, routes, dependencies, errors |
| Provider | `app/integrations/hunar/`: exact provider enums, GET-agent/POST-call adapter, ambiguous response identity salvage |
| Persistence | One migration and one `voice_call_executions` business table; unique outreach/request/call identity, immutable input trigger, RLS/revokes |
| Composition | Settings, API router/version, worker registration and composite UNKNOWN reconciliation |
| UI | Existing outreach detail gains language/timezone choice and four submission states; no new global navigation |
| Qualification | Module 6 validator, provider/service/worker/API/PostgreSQL tests, captured public provider schema, frontend tests |
| Documentation | Frozen implementation plan, agent contract, ledger, this validation guide, README and environment example |
| Metadata | `pyproject.toml` and application entry in `uv.lock` updated to 0.7.0; dependency pins unchanged |

## Automated evidence

The frozen `uv.lock` dependency set installed successfully on Python 3.12.13.

| Gate | Result |
| --- | --- |
| Baseline validators 0–5 | PASS |
| Baseline backend pytest | 171 passed; 26 database tests skipped |
| Implemented validators 0–6 | PASS |
| Python compile | PASS |
| Ruff (`app`, all backend tests, new validator) | PASS |
| Strict mypy, all 91 production Python files | PASS |
| Full implemented backend pytest | 269 passed; 40 database tests skipped |
| Frontend lint and strict typecheck | PASS |
| Vitest | 45 passed across 10 files |
| Next production build | PASS with `NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8000/api/v1` |
| Disposable PostgreSQL migration/constraint/concurrency tests | UNAVAILABLE; 14 Module 6 tests plus 26 upstream database tests skipped |
| Live configured Hunar agent/call qualification | UNAVAILABLE; no credentials, private ACTIVE agent, or controlled recipient supplied |
| Fresh patch application and byte comparison | See accompanying delivery report for final run evidence |

The first Next build omitted the required API URL and failed during prerendering; the corrected
build passed. The environment could not install a PostgreSQL server because its setgroups/setuid
operations were unavailable. These are environment gates, not passing database evidence.
Two existing FastAPI/Starlette test-client deprecation warnings remain; no test failed.

## Producer/consumer and blast-radius audit

- Module 5 `OutreachService.lock_dispatchable_outreach()` is the only upstream execution authority.
  Both create and worker dispatch consume its frozen phone/questions; explicit retry revalidates it.
- Module 1 exact bound definition contributes only compact role facts. Current Job questions are
  never read for payload construction. Candidate Core summary contributes only display name.
- SQLAlchemy mapping and migration have the same 15 columns and the same check expressions;
  captured provider enums/required echoes are tested independently. Real DB enforcement is gated.
- Provider `request_id` is reused only as correlation. Logical idempotency comes from the outreach
  unique constraint and active queue dedupe. No code looks up UNKNOWN by request ID or resends it.
- Worker revalidates in a short transaction, closes it, checks the exact ACTIVE frozen agent, then
  POSTs with no open DB transaction. Another short transaction persists acceptance/uncertainty.
- Safe retry exhaustion raises PermanentWorkError after domain FAILED. Ambiguity tries to persist
  UNKNOWN and always raises AmbiguousWorkError even if that domain write fails. Reconciliation
  converts queue UNKNOWN/domain QUEUED, never downgrading SUBMITTED or FAILED.
- Explicit retry rejects any still-active queue item before resetting FAILED. This closes the
  proven domain-FAILED/queue-RUNNING race. UNKNOWN also remains an active dedupe blocker.
- The worker composition root calls both sourcing and voice UNKNOWN reconcilers through the one
  existing callback. WorkerRunner, WorkItemRepository, shared transport and Modules 1–5 remain
  unchanged. Baseline regression suites stay green.
- The public DTO excludes phone, Candidate name, agent ID, API key and raw payload. Queue payload
  is empty. Provider parse errors discard raw validation details; Module 6 emits no payload logs.
- No Apollo origin branch, matching/scoring, outreach editing, agent creation/mutation, webhook
  receiver, lifecycle/result/recording/transcript persistence, or Module 7 recovery was added.
- SUBMITTED means provider acceptance only. Provider initial status is an observation, not a local
  lifecycle decision. UNKNOWN may retain an observed call ID/status for future Module 7 evidence.

## Apply the patch (PowerShell, repository root)

Place `MODULE_6_HUNAR_VOICE_AI_INTEGRATION.patch` in the root of the exact supplied baseline.

```powershell
git status --short
git apply --check .\MODULE_6_HUNAR_VOICE_AI_INTEGRATION.patch
if ($LASTEXITCODE -ne 0) { throw "Patch does not match this baseline" }
git apply .\MODULE_6_HUNAR_VOICE_AI_INTEGRATION.patch
if ($LASTEXITCODE -ne 0) { throw "Patch application failed" }
git diff --check
```

Do not force-apply to a different repository snapshot. An existing applied patch will fail the
forward check; inspect your tree rather than applying it twice.

## Backend qualification (PowerShell, repository root)

Requires Python 3.12+, uv, Node/npm and Git.

```powershell
uv sync --project .\apps\api --all-extras --frozen
if ($LASTEXITCODE -ne 0) { throw "Dependency sync failed" }
0..6 | ForEach-Object {
    uv run --project .\apps\api --frozen python ".\scripts\validate_module_$_.py"
    if ($LASTEXITCODE -ne 0) { throw "Module $_ validator failed" }
}
uv run --project .\apps\api --frozen python -m compileall -q .\apps\api\app .\apps\api\tests .\scripts
uv run --project .\apps\api --frozen ruff check .\apps\api\app .\apps\api\tests .\scripts\validate_module_6.py
uv run --project .\apps\api --frozen mypy --config-file .\apps\api\pyproject.toml .\apps\api\app
uv run --project .\apps\api --frozen pytest -q .\apps\api\tests
```

Inspect each exit status. Without TEST_DATABASE_URL, the database tests skip.

## Disposable hosted PostgreSQL/Supabase qualification

**Use a disposable qualification database only. The existing test fixtures truncate application
tables with CASCADE. Never point TEST_DATABASE_URL at production or a database whose data matters.**

Set `TEST_DATABASE_URL` locally to the direct PostgreSQL connection string. Do not paste secrets
into reports. If this disposable database already has Modules 0–5 migrations applied, apply only:

```powershell
psql "$env:TEST_DATABASE_URL" --set ON_ERROR_STOP=1 --file .\supabase\migrations\20260907113000_module_6_hunar_voice_execution.sql
if ($LASTEXITCODE -ne 0) { throw "Module 6 migration failed" }
uv run --project .\apps\api --frozen pytest -q .\apps\api\tests
```

For migration rebuild, use a brand-new disposable Supabase database with no application tables,
then apply every migration in filename order:

```powershell
Get-ChildItem .\supabase\migrations\*.sql | Sort-Object Name | ForEach-Object {
    psql "$env:TEST_DATABASE_URL" --set ON_ERROR_STOP=1 --file $_.FullName
    if ($LASTEXITCODE -ne 0) { throw "Migration failed: $($_.Name)" }
}
uv run --project .\apps\api --frozen pytest -q .\apps\api\tests
```

The migrations assume Supabase's `anon` and `authenticated` roles. Running files directly with
psql does not register Supabase CLI migration-history entries; use your existing migration workflow
for deployed environments. The commands above target disposable rebuild/qualification only.

The new PostgreSQL tests cover concurrent Start, real active dedupe, named constraint/model parity,
unique outreach/request/call IDs, immutable inputs, status/acceptance checks, UNKNOWN with a known
call ID, permitted operational changes, RLS/revokes, and stale-work reconciliation.

## Frontend qualification (PowerShell, repository root)

```powershell
npm ci
npm run web:lint
npm run web:typecheck
npm run web:test
$env:NEXT_PUBLIC_API_BASE_URL = "http://127.0.0.1:8000/api/v1"
npm run web:build
git diff --check
```

## Configure and start a controlled environment

Create `apps/api/.env` from `.env.example` if it does not already exist. Keep existing configuration.
Set DATABASE_URL for your controlled application database, and configure:

```text
HUNAR_API_KEY=<private backend key>
HUNAR_API_BASE_URL=https://api.voice.hunar.ai/external/v1
HUNAR_SCREENING_AGENT_IDS_JSON={"ENGLISH":"<pre-provisioned ACTIVE agent UUID>"}
HUNAR_DEFAULT_LANGUAGE=ENGLISH
HUNAR_DEFAULT_TIMEZONE=Asia/Kolkata
HUNAR_READ_TIMEOUT_SECONDS=30
HUNAR_CALL_SUMMARY_CALLBACK_URL=
```

Copy the exact objective, introduction, prompt, result prompt/schema and persona from
`doc/MODULE_6_HUNAR_AGENT_CONTRACT.md` using Hunar-supported provisioning tools. Activate through
Hunar's supported account process. Runtime exposes no create/update/activate-agent method.
Agent custom variables must be exactly `job_role`, `role_context`, `screening_plan`.
Leave the optional callback blank for Module 6-only testing.

Use separate terminals, each starting at the repository root:

```powershell
# API terminal
Set-Location .\apps\api
uv run --frozen uvicorn app.main:app --host 127.0.0.1 --port 8000
```

```powershell
# Worker terminal
Set-Location .\apps\api
uv run --frozen python -m app.worker.main
```

```powershell
# Frontend terminal
$env:NEXT_PUBLIC_API_BASE_URL = "http://127.0.0.1:8000/api/v1"
npm run web:dev
```

## Read-only live agent qualification

From `apps/api`, run this before making any real call:

```powershell
@'
from app.core.config import get_settings
from app.voice_calls.agent_contract import get_contract
from app.voice_calls.dependencies import build_voice_provider
from app.voice_calls.service import preflight
s = get_settings()
c = get_contract()
p = build_voice_provider(s)
try:
    preflight(p, s.hunar_agent_ids[c.language], c)
    print("ACTIVE English v1 contract: PASS")
finally:
    if p is not None:
        p.close()
'@ | uv run --frozen python -
```

This GET does not create an execution or place a call. A failure is not permission to weaken drift
checks. Only line endings and outer whitespace may normalize.

## Manual UI and controlled live call E2E

1. Use an explicitly consenting controlled test recipient/number. Do not test against ordinary
   Candidates. Confirm the Hunar organization calling guardrails and test timezone are appropriate.
2. Prepare one manual Candidate and one Apollo-resolved Candidate through the existing shared
   matching, shortlist and Module 5 preparation flow. Use separate controlled contexts as needed.
3. For each, open the existing outreach detail page. Confirm frozen masked phone/questions;
   Start appears only when outreach is READY_FOR_EXECUTION. No contact/questions/agent re-entry.
4. Verify only configured English and documented timezones appear, with Automatic redials Off.
5. Click Start once. Verify QUEUED: "Preparing voice call…". A repeated/concurrent Start request
   must return the same execution ID with one active work item, never a duplicate call intent.
6. With the worker running, verify SUBMITTED: "Call submitted to Hunar" and the acceptance-only
   explanation. The backend stores call UUID, initial provider status and submitted_at.
7. Read the known call UUID operationally in Hunar's supported tools or GET
   `/external/v1/calls/{provider_call_id}/` using X-API-Key. Verify existence and request correlation
   without adding a production polling method or local lifecycle state. Request ID must match the
   frozen `hha-{execution_uuid.hex}`; confirm actual provider retry config is 0/0.
8. Listen for AI disclosure, identity confirmation, permission, then role identification. Verify
   ordered supplied questions, one at a time, natural acknowledgements and no invented role facts.
9. Confirm provider result schema shape in the controlled provider environment. Do not persist
   answers/recordings/results in Module 6.
10. In a mocked/test environment, prove FAILED shows Retry dispatch, reuses exact payload/request
    ID and revalidates upstream. An active-work race can return VOICE_CALL_WORK_STILL_ACTIVE;
    refresh after the runner finishes. Never edit the execution row to force a retry.
11. In a mocked/test environment, prove UNKNOWN has no Retry button and retry API returns 409.
    Test read/write/protocol timeout and malformed success there; do not deliberately create an
    ambiguous real call to test UI. UNKNOWN remains non-replayable.
12. Change phone, shortlist, or Job readiness before dispatch in a controlled environment;
    worker must fail before POST. After acceptance, history remains frozen.
13. Verify browser responses/logs contain no full phone, provider payload or API key.

Qualify all twelve conversation cases from the frozen plan using controlled participants:
normal completion; bad time; wrong person; not interested; interruption; later answer given early;
one ambiguous answer needing clarification; refused question; unknown salary/benefits question;
"did I pass?"; silence; and a request to stop. Record pass/fail and remediation evidence for each.
Verify the agent makes no hiring decision or unsupported next-step promise. Evaluate actual
silence/conclusion behavior and persona naturalness. If the prompt/persona needs changing, add a
new reviewed contract version and update the plan before freeze; never silently mutate v1.

Final authority: Module 5 recruiter-confirmed outreach; Module 6 durable submission certainty;
Module 7 lifecycle/results/recovery. Passing local automated tests does not waive live or DB gates.
