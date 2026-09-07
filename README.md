# Hunar Hiring Assistant — Modules 0 + 1 + 2 + 3 + 4 + 5

This repository contains the application foundation, shared **Job & Screening Definition** authority, global **Candidate Core**, Job-bound **People Search & Contact Enrichment**, and shared **Candidate ↔ Job Matching & Shortlisting** workflow for the Hunar.ai hiring-assistant assessment.

Current scope:

- **Module 0 — Application Foundation:** complete foundation for FastAPI, Supabase Postgres, migrations, provider HTTP conventions, durable work items, logging, request IDs, and the Next.js frontend shell.
- **Module 1 — Job & Screening Definition:** one recruiter-approved hiring definition shared by Task 1 (voice screening) and Task 2 (people search / reachout).
- **Module 2 — Candidate Core:** one global Candidate identity shared by manual Task-1 candidates and Task-2 provider-sourced people.
- **Module 3 — People Search & Contact Enrichment:** READY-Job-bound Apollo search evidence, deliberate enrichment, asynchronous phone recovery, and Candidate Core resolution.
- **Module 4 — Candidate ↔ Job Matching & Shortlisting:** one shared manual/sourced Candidate↔Job relation, immutable version-bound evidence assessment, optional constrained Gemini role/seniority classification, call readiness, and recruiter-owned shortlist truth.
- **Module 5 — Outreach:** one shared preparation flow that freezes canonical phone and customized screening questions into an immutable, execution-ready context without calling Hunar.

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


## Core Module 3 invariant

```text
Approved Job vN
      |
      v
Apollo People Search
      |
      v
Sourcing evidence only
      | recruiter explicitly enriches
      v
Apollo enrichment + phone recovery
      |
      v
Module 2 canonical Candidate
```

Raw search hits never create Candidates, unsupported Job requirements remain visible rather than
being silently mapped to different Apollo semantics, and uncertain credit-consuming enrichment is
never automatically replayed.


## Core Module 4 invariant

```text
Task 1 Add to READY Job ───────┐
                               |
Task 2 Review match ───────────┤
   (resolved sourcing evidence) v
                        one job_candidate
                               |
                    current READY Job vN
                               +
                 available Candidate evidence
                               |
                               v
              automatic initial assessment
                               |
                  recruiter shortlist decision
```

Module 3's pre-enrichment recommendation answers **which search results are worth enriching**. Module 4 answers **how the resolved Candidate fits the approved Job evidence that actually exists**. Missing skills/experience remain `unknown`; phone affects call readiness only and never increases fit score.

## Core Module 5 invariant

```text
Task 1 manual Candidate ─┐
                         ├─> current Module 4 shortlist
Task 2 Apollo Candidate ─┘              |
                                        v
                         immutable outreach request
                         phone + exact screening snapshot
                                        |
                                        v
                         future Module 6 execution
```

Module 5 never branches on Candidate origin. It owns the immutable execution context and derives
`READY_FOR_EXECUTION` or `STALE`; it does not call Hunar or persist call events/results.

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
                    |
              sourcing_runs
                 /      \
       sourcing_results  sourcing_enrichments
                    \        /
                     job_candidates
                          |
                  job_candidate_matches
                          |
                  outreach_requests
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
- `sourcing_runs` owns historical search execution bound to one immutable approved Job version.
- `sourcing_results` owns contact-free provider search evidence only.
- `sourcing_enrichments` owns one logical credit-aware enrichment per selected search result.
- Candidate contact truth remains in Module 2; Module 3 stores only Candidate links and provider workflow state.
- `job_candidates` owns the one stable Candidate↔Job relationship plus current recruiter shortlist state.
- `job_candidate_matches` owns immutable historical evidence assessments tied to exact approved Job versions and evidence inputs.
- Module 4 call readiness is derived from canonical Candidate phone truth and does not affect match score.
- `outreach_requests` owns immutable recruiter-confirmed phone and question snapshots; readiness remains derived from current Module 1/2/4 truth.

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

Optional Module 3 Apollo search/enrichment:

```env
APOLLO_API_KEY=
APOLLO_API_BASE_URL=https://api.apollo.io/api/v1
APOLLO_WEBHOOK_BASE_URL=https://your-public-api.example.com
APOLLO_WEBHOOK_SIGNING_SECRET=
APOLLO_SEARCH_READ_TIMEOUT_SECONDS=30
APOLLO_ENRICHMENT_READ_TIMEOUT_SECONDS=60
SOURCING_SEARCH_STALE_SECONDS=300
```

`APOLLO_WEBHOOK_BASE_URL` must be public HTTPS when asynchronous phone reveal is exercised.

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
        apollo/
      sourcing/
      matching/
      work_items/
      worker/
    tests/
  web/
    app/
      jobs/
      candidates/
      sourcing/
      job-candidates/
    components/
      jobs/
      candidates/
      sourcing/
      matching/
      ui/
    lib/
      jobs/
      candidates/
      sourcing/
      matching/
supabase/
  migrations/
scripts/
  validate_module_0.py
  validate_module_1.py
  validate_module_2.py
  validate_module_3.py
  validate_module_4.py
doc/
  MODULE_1_IMPLEMENTATION_PLAN.md
  MODULE_1_VALIDATION.md
  MODULE_2_IMPLEMENTATION_PLAN.md
  MODULE_2_VALIDATION.md
  MODULE_3_IMPLEMENTATION_PLAN.md
  MODULE_3_VALIDATION.md
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

`supabase db reset` must apply all Module 0–3 migration files from an empty local database.

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

Run the durable worker separately for Module 3 enrichment/poll recovery:

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
http://localhost:3000/jobs
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
APOLLO_API_KEY
APOLLO_WEBHOOK_SIGNING_SECRET
```

Never expose them through `NEXT_PUBLIC_*`.

Module 1 still does not use Supabase Data API/Auth/Storage/Realtime, so it does not require Supabase publishable/secret API keys (or legacy anon/service-role keys).

New tables have RLS enabled and browser roles revoked; the frontend accesses them only through FastAPI.

## Module 5 validation

See `doc/MODULE_5_VALIDATION.md` for the complete automated, disposable-database, and manual UI
qualification sequence. Run the dependency-free boundary gate with:

```bash
python scripts/validate_module_5.py
```

## Explicitly not implemented yet

- Hunar Voice API calls
- Hunar outreach execution (Module 6)
- screening/call-result recovery
- screening answers dashboard
- authentication / RBAC

These belong to later modules and must consume the frozen Module 1–5 authorities rather than duplicating Job, Candidate, sourcing, match, shortlist, or outreach truth.


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

The qualified Module 2 baseline executed 87 backend tests with its dependencies and migrated disposable Postgres available. The current cumulative suite is larger; use the latest module validation document for the current gates.

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

## 9. Module 3 validation

Structural validation:

```bash
python scripts/validate_module_3.py
```

Backend regression and hosted/disposable Postgres qualification:

```powershell
cd apps\api
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
ruff check .
mypy app
$env:TEST_DATABASE_URL="YOUR_DISPOSABLE_HOSTED_SUPABASE_DATABASE_URL"
python -m pytest -q
```

With all optional/runtime dependencies and the migrated disposable database available, the current
Module 0–3 suite should execute 127 tests rather than environment-skipping Postgres/phone cases.

Frontend:

```bash
npm run web:lint
npm run web:typecheck
npm run web:test
npm run web:build
```

Manual Module 3 smoke:

1. Confirm DRAFT Jobs cannot start new sourcing.
2. Mark a Job READY and use **Find people**.
3. Verify persisted mapped/unmapped criteria and that search results do not create Candidates.
4. Enrich one selected result; repeated submit must return the same logical enrichment.
5. Run the worker and verify synchronous Candidate resolution plus asynchronous phone recovery.
6. Confirm `CONFLICT`, `NOT_FOUND`, `FAILED`, and `UNKNOWN` states fail closed.
7. Reopen the Job and verify historical runs remain readable while new sourcing is blocked.

See `doc/MODULE_3_VALIDATION.md` for hosted Supabase, webhook/poll, concurrency, and live-Apollo gates.


## 10. Module 4 validation

Structural validation:

```bash
python scripts/validate_module_4.py
```

Module 4 adds no Apollo endpoint or automatic enrichment. A new manual relationship is assessed after attachment commits; **Review match** assesses a new sourced relationship or changed preferred sourcing result after that update commits. Repeating the same attachment context returns existing truth without a hidden refresh or provider retry. Optional Gemini analysis remains inside the existing matching authority and runs only when explicit title evidence can improve role/seniority classification. Backend scoring and recruiter shortlist truth remain authoritative.

Run the cumulative backend/database and frontend gates documented in `doc/MODULE_4_VALIDATION.md`. The shared workflow is **Attach/Review match → automatic initial assessment → recruiter review**. The manual smoke must cover both Task-1 manual Candidate attachment and Task-2 resolved sourcing attachment, convergence to one relation, evidence-grounded matching, call-readiness separation, Job reapproval freshness, and recruiter decision reconfirmation.
