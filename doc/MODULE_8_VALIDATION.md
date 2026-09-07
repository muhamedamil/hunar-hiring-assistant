# Module 8 — STEP 2 Backend Read Projection Validation

## Scope

This document qualifies **STEP 2 only**. Recruiter frontend/dashboard UI is intentionally not part
of this patch.

The backend exposes exactly:

```text
GET /api/v1/dashboard/overview
GET /api/v1/dashboard/screenings
GET /api/v1/dashboard/screenings/{execution_id}
```

No Module 8 mutation endpoint, provider integration, worker, business-state table, or migration is
introduced by this qualification patch.

## Frozen authority checks

The implementation must continue to prove:

- current Job metrics/current review attention read `jobs`;
- current Candidate display identity reads `candidates`;
- pipeline truth remains `job_candidates`;
- match truth remains `job_candidate_matches`;
- execution screening history joins through
  `execution -> outreach -> decision match -> immutable job_definition_versions`;
- frozen screening prompts come only from `outreach_requests.screening_questions_snapshot`;
- terminal truth remains `voice_call_results`;
- accepted answers remain `voice_screening_answers` keyed by frozen outreach question UUID;
- Module 6 submission status remains independent from result-first display state;
- dashboard GETs perform zero Gemini/Apollo/Hunar/work-item actions.

## Required local qualification

From the repository root, run validators 0–8:

```bash
python scripts/validate_module_0.py
python scripts/validate_module_1.py
python scripts/validate_module_2.py
python scripts/validate_module_3.py
python scripts/validate_module_4.py
python scripts/validate_module_5.py
python scripts/validate_module_6.py
python scripts/validate_module_7.py
python scripts/validate_module_8.py
```

Backend static/type/test gates:

```bash
cd apps/api
ruff check .
mypy app
python -m pytest -q
```

Focused Module 8 gates:

```bash
python -m pytest tests/test_dashboard_service.py -q
python -m pytest tests/test_dashboard_router.py -q
python -m pytest tests/test_dashboard_database.py -q
```

## Disposable PostgreSQL qualification

Use only a disposable database migrated through
`20260907170000_module_7_call_results.sql`.

If using the repository's local Supabase topology:

```bash
# repository root
supabase db reset
```

Then set `TEST_DATABASE_URL` to that disposable PostgreSQL database and run:

```bash
cd apps/api
TEST_DATABASE_URL='postgresql://postgres:postgres@127.0.0.1:54322/postgres' \
  python -m pytest tests/test_dashboard_database.py -q -s
```

The PostgreSQL test seeds **105 Jobs, 105 Candidates, and 106 historical screening executions**
(including two distinct outreaches for one JobCandidate) and proves:

- authoritative totals stay correct above 100 rows;
- the seven screening states sum exactly to execution total;
- interested remains an independent subset metric;
- pagination returns 100 + 6 rows with one row per execution;
- list total and page filters remain aligned;
- multiple historical outreaches for one JobCandidate remain distinct execution rows;
- multiple Module 7 answers do not multiply screening list rows;
- a current Job v2 title/question mutation cannot rewrite historical v1 Job/question meaning;
- QUEUED/UNKNOWN executions with available results use result-first display state while preserving
  their original Module 6 submission status;
- UNKNOWN plus available result is removed from stale submission attention without rewriting UNKNOWN;
- recent screenings are exactly 10 execution rows under the frozen `sort_at` order and can include
  unresolved executions;
- a real `EXPLAIN (ANALYZE, BUFFERS)` executes for the final screening-list query;
- no speculative `%dashboard%` index exists in the database.

Do not create `20260907194500_module_8_recruiter_dashboard_read_indexes.sql` unless a representative
query plan on realistic data proves a candidate index materially improves an actual Module 8 read
path. If no index is justified, migration head remains Module 7.

## Security/provider-isolation checks

`validate_module_8.py` and focused tests must prove:

```text
0 Gemini calls
0 Apollo calls
0 Hunar calls
0 provider reconciliation
0 work-item creation
0 dashboard write paths
```

Public dashboard schemas must not expose:

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

Only `recording_available: bool` is permitted for recording visibility.

## STEP 3 gate

STEP 3 remains **NO-GO** until all of these are green on the final patch-applied tree:

1. validators 0–8;
2. Ruff;
3. mypy;
4. full backend pytest;
5. disposable PostgreSQL Module 8 qualification;
6. real query-plan/index qualification;
7. final provider-isolation/privacy scan;
8. final blast-radius/authority-drift review.

## Qualification-patch results in the build environment

The exact qualification-patch tree was run with the tooling available in the build environment:

```text
validators 0–8: PASS
Module 0 source files checked: 253
focused Module 8 tests: 21 passed / 5 skipped / 0 failed
full backend pytest: 323 passed / 54 skipped / 0 failed
Python compileall: PASS
```

The five Module 8 skips are exclusively the disposable PostgreSQL scale/history/race/query-plan
tests gated by `TEST_DATABASE_URL`. Other full-suite skips are pre-existing PostgreSQL and optional
`phonenumbers` environment gates.

Ruff and mypy are declared development dependencies but are not installed in this build container;
an offline install was unavailable. They remain mandatory local qualification commands below. The
build container also has no disposable PostgreSQL/Supabase server, so real `EXPLAIN (ANALYZE,
BUFFERS)` remains a mandatory local gate before STEP 3.
