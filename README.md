# Hunar Hiring Assistant — Modules 0 + 1 + 2

This repository contains the application foundation, shared **Job & Screening Definition** authority, and global **Candidate Core** for the Hunar.ai hiring-assistant assessment.

Current scope:

- **Module 0 — Application Foundation:** complete foundation for FastAPI, Supabase Postgres, migrations, provider HTTP conventions, durable work items, logging, request IDs, and the Next.js frontend shell.
- **Module 1 — Job & Screening Definition:** one recruiter-approved hiring definition shared by Task 1 (voice screening) and Task 2 (people search / reachout).
- **Module 2 — Candidate Core:** one global Candidate identity shared by manual Task-1 candidates and future Task-2 provider-sourced people.

## Core Module 1 invariant

```text
Raw Job Description
        |
        v
Optional Gemini analysis
        |
        v
Editable proposal only
        |
        v
Mutable DRAFT Job
        |
    Mark Ready
        |
        v
Immutable approved definition vN
        |
        +--------------------+
        |                    |
        v                    v
Task 1 voice screening   Task 2 people search
```

The raw JD and AI output are **not** downstream business truth. Only an immutable approved definition for a currently READY Job may start new sourcing, matching, or screening work.

## Core Module 2 invariant

```text
Task 1 manual candidate ─┐
                         ├─> one canonical Candidate
Task 2 sourced person ───┘            |
                                      +─ provider identities
```

Candidate Core is global and Job-independent. Email/phone are optional strong identifiers, provider identity is stored separately, and name/title/company/location similarity never auto-merges people.

## Architecture

```text
Next.js / React / TypeScript / shadcn-style UI
                    |
                    v
                 FastAPI
                    |
          SQLAlchemy 2.x + psycopg
                    |
             Supabase Postgres
          /          |             \
    work_items      jobs         candidates
                    |               |
          job_definition_versions  candidate_external_identities
          (immutable snapshots)    (provider identity links)
```

## State ownership

- `jobs` owns the current mutable working copy.
- `job_definition_versions` owns immutable approved historical truth.
- `status` answers whether **new** downstream work may start: `draft | ready`.
- `revision` is the optimistic-concurrency token for the mutable Job aggregate.
- `approved_version` points to the latest immutable approved snapshot.
- Reopening a READY Job blocks new downstream work but never mutates or invalidates previously approved versions.
- `candidates` owns the mutable global Candidate profile and `revision` concurrency token.
- `candidate_external_identities` separates provider/person identity from canonical Candidate truth.
- Candidate contact values are optional; contact readiness is derived rather than persisted as another state machine.

## AI analysis

Module 1 optionally uses Gemini for:

```text
Job Description -> typed requirements + suggested screening questions
```

The provider is isolated under `apps/api/app/integrations/gemini/` and uses the shared Module 0 `ProviderHttpClient`. There are no automatic provider retries and no database mutation from the analysis path.

Default model:

```text
GEMINI_MODEL=gemini-3.7-flash
GEMINI_THINKING_LEVEL=low
GEMINI_READ_TIMEOUT_SECONDS=60
```

Manual Job creation remains fully usable when Gemini is not configured or unavailable.

## Repository layout

```text
apps/
  api/
    app/
      core/
      jobs/
      candidates/
      integrations/
        gemini/
      work_items/
      worker/
    tests/
  web/
    app/
      jobs/
      candidates/
    components/
      jobs/
      candidates/
      ui/
    lib/
      jobs/
      candidates/
supabase/
  migrations/
scripts/
  validate_module_0.py
  validate_module_1.py
  validate_module_2.py
doc/
  MODULE_1_IMPLEMENTATION_PLAN.md
  MODULE_1_VALIDATION.md
  MODULE_2_IMPLEMENTATION_PLAN.md
  MODULE_2_VALIDATION.md
```

## 1. Prerequisites

- Python 3.12+
- Node.js 20+
- npm 10+
- Supabase CLI
- Docker for local Supabase

## 2. Start local Supabase

From the repository root:

```bash
supabase start
supabase db reset
supabase status
```

`supabase db reset` must apply all Module 0–2 migration files from an empty local database.

Use the local Postgres URL from `supabase status`, for example:

```text
postgresql+psycopg://postgres:postgres@127.0.0.1:54322/postgres
```

## 3. Backend setup

```bash
cd apps/api
python -m venv .venv
```

Windows PowerShell:

```powershell
.\.venv\Scripts\Activate.ps1
```

macOS/Linux:

```bash
source .venv/bin/activate
```

Install:

```bash
python -m pip install -e ".[dev]"
```

Copy configuration:

```bash
cp .env.example .env
```

Configure at minimum:

```env
DATABASE_URL=postgresql+psycopg://postgres:postgres@127.0.0.1:54322/postgres
```

Optional Module 1 AI analysis:

```env
GEMINI_API_KEY=
GEMINI_MODEL=gemini-3.7-flash
GEMINI_THINKING_LEVEL=low
GEMINI_READ_TIMEOUT_SECONDS=60
```

Run API:

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Run the Module 0 worker separately when required by later modules:

```bash
python -m app.worker.main
```

Module 1 JD analysis does **not** use the worker.

## 4. Frontend setup

From repository root:

```bash
npm install
cp apps/web/.env.local.example apps/web/.env.local
npm run web:dev
```

Open:

```text
http://localhost:3000/jobs
http://localhost:3000/candidates
```

## 5. Module 1 validation

Dependency-free structural validation:

```bash
python scripts/validate_module_1.py
```

Backend:

```bash
cd apps/api
ruff check .
mypy app
python -m pytest -q
```

For the real Postgres tests, set a **disposable/local** migrated database explicitly:

PowerShell:

```powershell
$env:TEST_DATABASE_URL="postgresql://postgres:postgres@127.0.0.1:54322/postgres"
python -m pytest -q
```

macOS/Linux:

```bash
export TEST_DATABASE_URL="postgresql://postgres:postgres@127.0.0.1:54322/postgres"
python -m pytest -q
```

The six `TEST_DATABASE_URL` tests cover:

- Module 0 work-item dedupe, stale execution, and `SKIP LOCKED` claiming.
- Module 1 approved-version FK, snapshot immutability, reopen/reapprove history, and concurrent approval.

Frontend:

```bash
npm run web:lint
npm run web:typecheck
npm run web:test
npm run web:build
```

Database:

```bash
supabase db reset
```

## 6. Manual Module 1 smoke test

1. Open `/jobs/new`.
2. Enter a Job title and a JD of at least 20 characters.
3. With `GEMINI_API_KEY` configured, click **Analyze with AI**.
4. Confirm suggestions populate editable fields but no Job is automatically created.
5. Edit requirements/questions manually.
6. Click **Save draft** and verify the Job is `DRAFT`, `revision=0`, `approved_version=null` on first create.
7. Add at least one valid screening question and click **Mark ready**.
8. Verify the Job becomes `READY`, `approved_version=1` and an immutable `job_definition_versions` v1 row exists.
9. Click **Reopen to edit**. Confirm status becomes DRAFT while v1 still exists unchanged.
10. Edit the definition, save, and mark ready again. Confirm v2 is created and v1 is unchanged.
11. Open the same Job in two browser tabs, save in one, then attempt to save the stale other tab. Confirm `JOB_REVISION_CONFLICT` prevents silent overwrite.
12. Stop/remove Gemini configuration and verify manual Job editing remains usable.

## 7. Security

Backend-only secrets:

```text
DATABASE_URL
GEMINI_API_KEY
```

Never expose them through `NEXT_PUBLIC_*`.

Module 1 still does not use Supabase Data API/Auth/Storage/Realtime, so it does not require Supabase publishable/secret API keys (or legacy anon/service-role keys).

New tables have RLS enabled and browser roles revoked; the frontend accesses them only through FastAPI.

## 8. Explicitly not implemented yet

- Candidate identity/core
- Candidate↔Job relationship
- People-search/enrichment providers
- Candidate matching / shortlisting
- Hunar Voice API calls
- outreach lifecycle
- webhooks / call-result recovery
- screening answers dashboard
- authentication / RBAC

These belong to later modules and must consume the immutable approved Job definition rather than reparsing the raw JD.


## 7. Module 2 validation

Structural validation:

```bash
python scripts/validate_module_2.py
```

Backend/local Supabase:

```powershell
cd apps\api
.\.venv\Scripts\Activate.ps1
$env:TEST_DATABASE_URL="postgresql://postgres:postgres@127.0.0.1:54322/postgres"
python -m pytest -q
```

With backend dependencies and migrated local Supabase available, all 83 current backend tests should execute rather than environment-skip.

Manual Candidate Core smoke:

1. Open `/candidates/new` and create a name-only Candidate.
2. Create another Candidate with email and international phone; confirm phone is stored as E.164.
3. Attempt the same email with different case; confirm `CANDIDATE_ALREADY_EXISTS` and the UI links to the existing Candidate.
4. Open the same Candidate in two tabs, save one, then save the stale tab; confirm revision conflict instead of overwrite.
5. Confirm `/candidates` shows only contact availability badges, while `/candidates/{id}` shows actual contact details.
6. Verify Candidate creation/editing has no Job, match, shortlist, sourcing-provider, or outreach state.

Full frontend gate remains:

```bash
npm run web:lint
npm run web:typecheck
npm run web:test
npm run web:build
```
