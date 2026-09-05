# Module 1 Validation Record

## Scope

Module 1 implements the shared Job & Screening Definition authority for both assignment streams on top of the completed Module 0 foundation.

## Implementation invariants

- one primary Job title authority: `jobs.title`
- provider-neutral alternate titles only in `requirements.alternate_titles`
- AI analysis is synchronous, optional, and non-mutating
- DRAFT is mutable working state
- READY requires an immutable approved snapshot
- approved snapshots cannot be updated or deleted through application repository methods
- PostgreSQL trigger rejects snapshot UPDATE/DELETE
- every mutation uses `expected_revision` plus a locked Job row
- READY jobs must be explicitly reopened before definition edits
- reopening blocks new downstream work without altering prior approved history
- future downstream modules must use `JobService.require_ready_definition()`

## Validation completed in this environment

```text
python scripts/validate_module_1.py
PASS — 6 invariant groups

python -m compileall -q apps/api/app
PASS

pytest -q
50 passed, 6 skipped
```

The six skipped tests require `TEST_DATABASE_URL` pointing to a migrated PostgreSQL/Supabase database.

A dependency-free TypeScript/TSX transpilation pass using the available TypeScript compiler reported:

```text
0 syntax diagnostics across 35 TS/TSX source files
```

## Environment-limited gates

The current sandbox cannot complete these because package downloads / local Supabase runtime are unavailable:

```text
ruff check .
mypy app
supabase db reset
npm run web:lint
npm run web:typecheck
npm run web:test
npm run web:build
```

Run all of them locally before freezing Module 1.

## Local database qualification

From repository root:

```powershell
supabase start
supabase db reset
supabase status
```

Then:

```powershell
cd apps\api
.\.venv\Scripts\Activate.ps1
$env:TEST_DATABASE_URL="postgresql://postgres:postgres@127.0.0.1:54322/postgres"
python -m pytest -q
```

All six previously skipped PostgreSQL tests should execute.

Do not point `TEST_DATABASE_URL` at a normal hosted/production database.

## Backend quality gates

```powershell
cd apps\api
ruff check .
mypy app
python -m pytest -q
```

## Frontend quality gates

From repository root:

```powershell
npm install
npm run web:lint
npm run web:typecheck
npm run web:test
npm run web:build
```

## Live Gemini smoke test

Set in `apps/api/.env`:

```env
GEMINI_API_KEY=<your server-side key>
GEMINI_MODEL=gemini-3.7-flash
GEMINI_THINKING_LEVEL=low
GEMINI_READ_TIMEOUT_SECONDS=60
```

Run API and frontend, then:

1. open `/jobs/new`
2. paste a realistic JD
3. click **Analyze with AI**
4. verify a structured proposal appears
5. verify no Job is created until Save Draft / Mark Ready
6. confirm recruiter edits are preserved when AI analysis is run again
7. remove/blank the key and confirm manual editing still works

## State-consistency smoke

After creating READY v1, inspect:

```sql
select id, status, revision, approved_version
from public.jobs
order by created_at desc
limit 5;
```

Then:

```sql
select job_id, version, title, requirements, screening_questions, created_at
from public.job_definition_versions
order by created_at desc;
```

Reopen, edit, and approve again. Verify v1 is unchanged and v2 is added.

Attempting this must fail:

```sql
update public.job_definition_versions
set title = 'should fail'
where version = 1;
```

## Freeze criterion

Module 1 can be marked COMPLETE / FROZEN after:

- `supabase db reset` passes from a clean local database
- all PostgreSQL tests run and pass
- Ruff passes
- strict mypy passes
- frontend lint/typecheck/tests/build pass
- one real Gemini analysis smoke passes when a key is available
- manual DRAFT -> READY v1 -> reopen -> edit -> READY v2 workflow behaves as documented
