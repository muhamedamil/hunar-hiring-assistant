# Module 7 validation and handoff

Module 7 implements terminal call and human-gated screening-result truth while preserving Module 5
question authority and Module 6 submission certainty.

## Qualification evidence from the implementation environment

| Gate | Result |
| --- | --- |
| Module 0–7 structural validators | PASS |
| Python compile | PASS |
| Ruff | PASS |
| Strict mypy | PASS (100 production files) |
| Backend pytest | 302 passed, 46 skipped |
| Frontend lint and strict typecheck | PASS |
| Vitest | 49 passed across 11 files |
| Next production build | PASS |
| Disposable PostgreSQL/Supabase | UNAVAILABLE; no CLI/database target, 46 tests skipped |
| Live Hunar HTTPS callback and controlled calls | UNAVAILABLE; no credentials/runtime supplied |

The two backend warnings are existing FastAPI/Starlette test-client deprecations. No unavailable gate
is represented as passed.

## Automated gates

Run from the repository root unless stated otherwise:

```bash
for validator in scripts/validate_module_{0..7}.py; do python "$validator"; done
cd apps/api
uv sync --extra dev --frozen
.venv/bin/python -m compileall -q app tests
.venv/bin/ruff check app tests ../../scripts/validate_module_7.py
.venv/bin/mypy app
.venv/bin/python -m pytest -q
cd ../..
npm ci
npm run web:lint
npm run web:typecheck
npm run web:test
NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8000/api/v1 npm run web:build
git diff --check
```

PostgreSQL tests require a disposable database migrated through
`20260907170000_module_7_call_results.sql` and `TEST_DATABASE_URL`. Never point destructive fixture
tests at production.

## Manual UI E2E

1. Open an outreach request with a Module 6 execution.
2. Verify queued/submitted shows **Awaiting call outcome…** and only the application result endpoint
   is polled.
3. Verify a valid HUMAN result shows outcome, interest, duration and answers against confirmed
   immutable question text.
4. Verify MACHINE and missing/UNKNOWN `answered_by` show that no answers were accepted.
5. Verify NOT_CONNECTED, FAILED and CANCELLED remain factual call outcomes, not hiring decisions.
6. Verify UNKNOWN with a known call ID offers **Check Hunar safely**; UNKNOWN without one explicitly
   says not to resend and has no recovery action.
7. Verify only **Recording available** appears; inspect network/HTML and confirm no recording URL.

## Live Hunar qualification

1. Configure a public HTTPS `HUNAR_CALL_SUMMARY_CALLBACK_URL`, trusted webhook key(s), reviewed
   English v1 agent, database, and API key.
2. Create a controlled new execution and capture the exact signed summary headers/body without
   logging PII in application logs.
3. Confirm valid signature/timestamp, exact request/call/agent/phone/timezone correlation, and
   `max_retries=retry_count=retries_left=0` with no next retry.
4. Confirm HUMAN result and question UUID mapping, then redeliver the exact webhook and prove one
   result/answer set.
5. Exercise explicit GET reconciliation for a known call ID and prove equivalent stored truth while
   Module 6 status remains unchanged, including UNKNOWN where safely available.
6. Run a controlled machine/voicemail call and prove `COMPLETED + MACHINE` stores the call outcome
   with zero screening answers.

Do not claim the database or live-provider gates passed without their actual environment evidence.
