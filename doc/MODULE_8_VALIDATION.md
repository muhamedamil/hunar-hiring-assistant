# Module 8 — STEP 2 Backend Read Projection Validation

## Final status

This document records the **final executed STEP 2 qualification** for the Module 8 backend dashboard
read projection. STEP 3 recruiter frontend/dashboard code was not started during this step.

```text
STEP 2 STATUS: COMPLETE / QUALIFIED / FROZEN

STEP 3 DECISION: GO
```

Authoritative baseline: `hunar-hiring-assistant-main (3)(2).zip`

Frozen contracts preserved:

- `doc/MODULE_8_IMPLEMENTATION_PLAN.md`
- `doc/MODULE_8_IMPLEMENTATION_LEDGER.md`

## Implemented STEP 2 boundary

STEP 2 added only the read/composition backend package:

```text
apps/api/app/dashboard/__init__.py
apps/api/app/dashboard/dependencies.py
apps/api/app/dashboard/repository.py
apps/api/app/dashboard/router.py
apps/api/app/dashboard/schemas.py
apps/api/app/dashboard/service.py
```

The public API surface is exactly:

```text
GET /api/v1/dashboard/overview
GET /api/v1/dashboard/screenings
GET /api/v1/dashboard/screenings/{execution_id}
```

No dashboard POST/PATCH/PUT/DELETE endpoint, business-state table, worker, provider integration, webhook,
or new business authority was introduced.

Backend version after STEP 2: `0.9.0`.

Current migration head:

```text
20260907170000_module_7_call_results.sql
```

No Module 8 migration was created.

## Authority and historical-context validation

The final implementation preserves the frozen authority chain:

```text
voice_call_executions.outreach_request_id
    -> outreach_requests.id
    -> outreach_requests.decision_match_id
    -> job_candidate_matches.id
    -> (job_candidate_matches.job_id, job_candidate_matches.definition_version)
    -> job_definition_versions(job_id, version)
```

The selected match is also required to belong to the same `outreach_requests.job_candidate_id`.
Current Candidate identity may be displayed, but historical Job title/version never falls back to current
mutable Job truth.

Screening prompts come only from `outreach_requests.screening_questions_snapshot`. Accepted Module 7
answers are mapped to the exact frozen question UUIDs. Answer rows are not joined into list pagination,
so multiple accepted answers cannot multiply one execution into multiple screening-list rows.

## Canonical screening-state validation

`dashboard_screening_state_expression()` remains the single result-first SQLAlchemy projection reused by:

- screening-state counts;
- list projection;
- state filtering;
- count filtering;
- Needs Attention execution projection;
- recent-screening projection.

Precedence remains:

```text
result available   -> result_available
result unavailable -> result_unavailable
result invalid     -> result_invalid
otherwise execution queued    -> queued
otherwise execution submitted -> awaiting_result
otherwise execution failed    -> dispatch_failed
otherwise execution unknown   -> submission_unknown
```

Module 6 execution status is still returned independently as `submission_status`. Therefore UNKNOWN
submission truth survives even when a later Module 7 result controls the recruiter display state.

`count_interested_screenings()` remains an independent subset metric and is not added to the seven mutually
exclusive screening-state total.

## Search, ordering, pagination, and recent-screening validation

Final qualification proves:

- absent/null `q` means no search predicate;
- supplied `q` is trimmed before validation;
- trimmed length `1..100` is accepted;
- whitespace-only or >100 characters after trim returns HTTP 422;
- search uses only current Candidate full name and exact historical Job-definition title;
- database `total` uses the same filter semantics as the paginated list;
- one execution remains one list row;
- ordering is
  `coalesce(voice_call_results.observed_at, voice_call_executions.updated_at) desc, execution.id desc`;
- `recent_screenings` is exactly the latest 10 executions under that ordering and may include unresolved
  executions;
- `job_id` remains a backend/deep-link filter only.

## Answer-safety validation

Candidate answers are exposed only when Module 7 truth is simultaneously:

```text
result state = available
lifecycle    = COMPLETED
answered_by  = HUMAN
```

The final focused tests prove MACHINE, UNKNOWN-human, unavailable, invalid, not-connected, failed, and
cancelled cases cannot become Candidate answers.

A missing Module 7 answer row remains `answer_state = null`; it is never fabricated as authoritative
`not_asked`.

## Error validation

Final tests preserve the frozen distinction:

```text
missing voice_call_execution
    -> stable VOICE_CALL_NOT_FOUND contract
    -> HTTP 404

existing execution + broken immutable historical context
    -> DASHBOARD_HISTORICAL_CONTEXT_INVALID
    -> HTTP 409
```

Broken historical context never falls back to a current Job, current questions, another outreach, or
another match.

## Security and provider-isolation validation

Final qualification proves dashboard GETs cause:

```text
0 Gemini calls
0 Apollo calls
0 Hunar calls
0 provider reconciliation
0 work-item creation
0 dashboard write paths
```

Public dashboard serialization exposes no:

```text
phone / phone_e164
email
raw recording_url
provider_call_id
provider_request_id
provider payload/snapshot
webhook/signature data
work-item internals
Candidate origin/created_source
```

Only `recording_available: bool` is exposed for recording presence.

## Final executed qualification results

### Structural/static/backend gates

```text
validators 0–8:                 PASS
Ruff:                           PASS
mypy:                           PASS
full backend regression:        PASS
final diff/whitespace audit:    PASS
final scope/authority audit:    PASS
Modules 0–7 regression status:  PASS
```

The final local full-backend run was reported as PASS. Its aggregate passed/skipped numeric summary was
not included in the retained local output supplied for this freeze, so this document does not invent one.
For reproducibility, the verified pre-local-DB patch tree had previously completed with
`323 passed / 54 skipped / 0 failed`; the final local DB-qualified run subsequently completed with zero
reported failures.

### Focused Module 8 qualification

```text
Focused Module 8 service/router/database tests: PASS
Disposable PostgreSQL qualification:           PASS
PostgreSQL database test result:                6 passed in 7.75s
```

The disposable PostgreSQL fixture qualifies:

```text
Jobs:                105
Candidates:          105
Screening executions:106
```

It proves:

```text
>100 Jobs/Candidates/executions                       PASS
seven-state total == execution total                  PASS
count_interested_screenings() subset independence     PASS
pagination/count parity                               PASS
stable deterministic ordering                         PASS
one execution = one list row                          PASS
multiple historical outreaches remain distinct        PASS
multiple answer rows do not duplicate list rows       PASS
historical Job v1 -> v2 mutation safety               PASS
frozen outreach question/answer context                PASS
QUEUED + available-result race                        PASS
UNKNOWN + available-result preservation               PASS
UNKNOWN + result removed from stale attention          PASS
recent 10 execution projection                         PASS
q trim/validation semantics                            PASS
HUMAN/MACHINE/UNKNOWN-human answer safety              PASS
provider isolation                                     PASS
unsafe-field serialization                             PASS
```

## PostgreSQL EXPLAIN / index qualification

Before the final representative plan, the local disposable database was analyzed for:

```text
public.voice_call_executions
public.outreach_requests
public.job_candidates
public.candidates
public.job_candidate_matches
public.job_definition_versions
public.voice_call_results
```

The final `EXPLAIN (ANALYZE, BUFFERS)` for the representative screening-list query reported:

```text
Planning Time:   10.139 ms
Execution Time:   0.768 ms
Shared hits:      771
Top-N sort:       heapsort, 30 kB
Returned rows:    20
Execution rows:   106
```

Existing indexes used by the final analyzed plan include:

```text
uq_voice_call_executions_outreach
candidates_pkey
job_definition_versions_job_id_version_key
uq_voice_call_results_execution
```

The remaining small-table access used efficient sequential/hash plans. The analyzed plan reduced execution
time from the earlier pre-ANALYZE `3.867 ms` run to `0.768 ms` without introducing a Module 8 index.

**Final index decision:** no new Module 8 read index is materially justified by the representative query
plan. Do not create `20260907194500_module_8_recruiter_dashboard_read_indexes.sql`.

Migration head therefore remains:

```text
20260907170000_module_7_call_results.sql
```

## Final blast-radius result

```text
Existing Modules 0–7 business authority changed:       NO
Existing production write path changed:                 NO
Dashboard mutation endpoint added:                      NO
Dashboard business-state table added:                   NO
Dashboard worker/work-item side effect added:           NO
Dashboard provider integration added:                   NO
Current Job used to rewrite historical screening:       NO
Current questions used to remap historical answers:     NO
Module 6 UNKNOWN rewritten:                              NO
MACHINE/UNKNOWN-human result exposed as Candidate answer:NO
Candidate-origin downstream branch introduced:          NO
Module 8 migration added:                               NO
STEP 3 frontend implementation started:                  NO
```

Remaining STEP 2 blockers: **NONE**.

```text
STEP 2 STATUS: COMPLETE / QUALIFIED / FROZEN

STEP 3 DECISION: GO
```

---

## STEP 3 implementation validation checkpoint

The STEP 3 implementation was cross-verified against the frozen Module 8 read contracts and Modules
0–7 authority map before patch generation.

### Implemented frontend validation surface

Tests now cover or explicitly assert:

```text
dashboard empty state
backend-owned dashboard metrics
Needs Attention routing/copy
Recent Voice Screenings including unresolved rows and backend sort_at
screening state / interest / search filters
server pagination
no first-100 Jobs dropdown
programmatic job_id filter in the dashboard API client
historical Job and frozen question rendering
answered / no_clear_answer / not_asked / no-answer-row rendering
MACHINE / UNKNOWN-human answer safety
UNKNOWN submission + available-result display
missing execution 404 presentation
historical-integrity fail-closed presentation
Outreach Candidate + historical Job/role cards
Outreach result-first state display while readiness remains independent
organized recruiter-safe Outreach result rendering
local Outreach/dashboard query invalidation after result convergence
no recruiter-side provider reconciliation action
AppShell Dashboard / Jobs / Candidates / Outreach / Screenings navigation
no recruiter-facing Module-number copy
```

### Bounded backend read extension validation

Focused tests prove the Outreach response extension preserves separate truth for:

```text
Module 5 readiness
Module 6 submission status
Module 8 result-first display state
historical immutable Job definition
```

A new disposable-PostgreSQL qualification test additionally mutates the current Job title after
Outreach creation, inserts an `UNKNOWN` execution with an available terminal result, and verifies the
Outreach read still returns the historical role, `screening_state=result_available`,
`submission_status=unknown`, and unchanged `READY_FOR_EXECUTION` readiness.

### Query-plan reproducibility correction

`test_dashboard_database.py` now executes `ANALYZE` for the dashboard relations after its >100-row
fixture is seeded and before `EXPLAIN (ANALYZE, BUFFERS)`. The query-plan gate therefore no longer
requires a manual statistics refresh to obtain representative planner estimates.

### Executed results in this build environment

```text
validators 0–8:                         PASS
Module 0 source files checked:          266
focused Outreach + Dashboard backend:   32 passed / 8 skipped / 0 failed
full backend pytest:                    324 passed / 55 skipped / 0 failed
Python compileall:                       PASS
changed TypeScript/TSX syntax:           25 files / 0 syntax errors
```

No failure was observed in an executable gate.

### Environment-gated qualification

A complete frontend `node_modules` tree is unavailable in this build environment and npm registry DNS
is unavailable. Ruff/mypy are also unavailable here. Therefore the following remain mandatory target
gates rather than inferred passes:

```text
cd apps/api
ruff check .
mypy app
python -m pytest -q

# repository root
npm run web:lint
npm run web:typecheck
npm run web:test
npm run web:build

# with disposable migrated PostgreSQL
TEST_DATABASE_URL=<disposable-url> python -m pytest \
  apps/api/tests/test_outreach_postgres.py \
  apps/api/tests/test_dashboard_database.py -q -s
```

Hosted qualification must still run Task 1, Task 2, historical Job mutation, MACHINE/voicemail, and
UNKNOWN/result convergence scenarios before final Module 8 product freeze.

### Security / authority result

Static structural validation confirms:

```text
Dashboard frontend provider calls:                     0
Dashboard frontend mutation calls:                     0
Recruiter provider reconciliation actions:             0
New dashboard/outreach business-state tables:          0
New worker/work-item behavior:                          0
Current Job fallback for historical screening:          0
Current-question fallback for historical answers:       0
Candidate-origin downstream branches:                   0
```

The STEP 3 patch is ready for target-environment qualification. It must not be labeled fully hosted/E2E
qualified until the environment-gated commands and scenarios above pass.
