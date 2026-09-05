# Hunar Hiring Assistant — Module 0 Foundation

This repository contains **Module 0 — Application Foundation** for the Hunar AI hiring-assistant assessment.

Module 0 intentionally contains **no hiring business logic**. It establishes the shared infrastructure used by later modules:

- Next.js + React + TypeScript + shadcn/ui-compatible frontend foundation
- FastAPI backend
- Supabase PostgreSQL accessed through SQLAlchemy 2.x + psycopg 3
- Supabase SQL migrations as the only schema-migration authority
- durable PostgreSQL-backed `work_items` queue
- conservative worker failure semantics (`UNKNOWN` for ambiguous/crashed side effects)
- stable API error envelope (including framework 404/405 errors) and request IDs
- explicit provider HTTP failure classification without generic automatic retries
- structured logging with sensitive-field redaction
- health/readiness endpoints

## Architecture

```text
Next.js
   |
   | HTTPS
   v
FastAPI
   |
SQLAlchemy + psycopg
   |
Supabase PostgreSQL
   |
work_items
   |
Python worker
```

### Core invariants

1. **Supabase Postgres owns durable application state.**
2. **Supabase SQL migrations own schema.** SQLAlchemy never calls `create_all()`.
3. **Services own transaction boundaries; repositories never commit.**
4. **External HTTP calls must not run inside open DB transactions.**
5. **Only the integration that understands a side effect may decide whether it is safe to retry.**
6. **Expired `RUNNING` work becomes `UNKNOWN`, never automatically `PENDING`.**
7. **A dedupe key prevents duplicate active internal work; it does not imply provider-side exactly-once behavior.**

## Repository layout

```text
apps/
  api/
    app/
      core/
      work_items/
      worker/
      jobs/             # placeholder for Module 1+
      candidates/       # placeholder for Module 2+
      sourcing/         # placeholder for Module 3+
      matching/         # placeholder for Module 4+
      outreach/         # placeholder for Module 5+
      integrations/
        hunar/          # placeholder for Module 6
    tests/
    pyproject.toml
    .env.example
  web/
    app/
    components/
    lib/
    tests/
supabase/
  migrations/
  seed.sql
```

## 1. Prerequisites

- Python 3.12+
- Node.js 20+
- npm 10+
- Supabase CLI
- Docker (for local Supabase)

## 2. Start local Supabase

From the repository root:

```bash
supabase start
supabase db reset
supabase status
```

`supabase db reset` rebuilds the local database from `supabase/migrations/` and then runs `supabase/seed.sql`.

Copy the local Postgres URL shown by `supabase status`. For SQLAlchemy + psycopg, use the `postgresql+psycopg://` scheme.

Example local value:

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

Copy environment file:

```bash
cp .env.example .env
```

Set `DATABASE_URL` to the local Supabase Postgres URL.

Run API:

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Run worker in another terminal:

```bash
cd apps/api
python -m app.worker.main
```

Health endpoints:

```text
GET http://localhost:8000/api/v1/health/live
GET http://localhost:8000/api/v1/health/ready
```

## 4. Frontend setup

From repository root:

```bash
npm install
cp apps/web/.env.local.example apps/web/.env.local
npm run web:dev
```

Open:

```text
http://localhost:3000
```

## 5. Module 0 validation

Backend:

```bash
cd apps/api
ruff check .
mypy app
pytest -q
```

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

Before pushing migrations to hosted Supabase:

```bash
supabase link --project-ref <your-project-ref>
supabase db push --dry-run
supabase db push
```

## 6. Hosted Supabase connection

For a persistent FastAPI/worker deployment, use the hosted Supabase Postgres connection string appropriate for a long-lived backend (direct connection when supported by the deployment network, or Supavisor session mode). Keep it only in backend deployment secrets as `DATABASE_URL`.

Do not put database credentials in the Next.js environment.

## 7. Secrets

Backend `.env` contains secrets and is ignored by Git.

Frontend only receives:

```text
NEXT_PUBLIC_API_BASE_URL
```

Module 0 uses a direct PostgreSQL connection from the Python backend, so the only Supabase runtime credential it needs is `DATABASE_URL`. It does **not** use Supabase Data API/Auth/Storage/Realtime, therefore no Supabase publishable/secret API key is required (and neither are the legacy `anon` / `service_role` keys). If a later module introduces one of those Supabase APIs, that module will add the minimum key it actually consumes.

Database integration tests deliberately use a separate shell variable named `TEST_DATABASE_URL`; they do not silently fall back to the normal application database.

## 8. What Module 0 intentionally does not include

- Jobs/candidates database tables
- Apollo/PDL/Proxycurl/Coresignal integration
- Hunar Voice AI integration
- JD parsing
- candidate matching
- outreach business logic
- webhooks
- authentication/RBAC
- Redis/Celery/Kafka
- WebSockets
- Supabase Auth/Storage/Realtime/Edge Functions

Those belong to later modules only when required.
