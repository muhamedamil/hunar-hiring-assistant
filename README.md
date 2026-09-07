# Hunar Hiring Assistant

An AI-assisted recruiting system that turns a raw job description into a controlled hiring workflow: define the role, discover or add candidates, evaluate fit, prepare outreach, run a voice screening through Hunar, and return structured screening evidence to the recruiter.

The system is intentionally designed as more than a collection of API integrations. Its core concern is **state ownership**: every important business fact has one clear authority, external providers are treated as evidence or execution engines rather than sources of business truth, and irreversible actions are executed only from frozen historical context.

---

## Table of contents

- [What the system does](#what-the-system-does)
- [The design problem](#the-design-problem)
- [Design goals](#design-goals)
- [High-level architecture](#high-level-architecture)
- [How the system works](#how-the-system-works)
- [Domain model and state ownership](#domain-model-and-state-ownership)
- [Job definition and approval](#job-definition-and-approval)
- [Candidate identity](#candidate-identity)
- [People search and enrichment](#people-search-and-enrichment)
- [Candidate-to-job evaluation](#candidate-to-job-evaluation)
- [Outreach preparation](#outreach-preparation)
- [Voice-call execution](#voice-call-execution)
- [Call results and screening evidence](#call-results-and-screening-evidence)
- [Asynchronous work model](#asynchronous-work-model)
- [Provider integration boundaries](#provider-integration-boundaries)
- [Reliability and failure semantics](#reliability-and-failure-semantics)
- [Concurrency and historical consistency](#concurrency-and-historical-consistency)
- [Security and data exposure](#security-and-data-exposure)
- [Deployment architecture](#deployment-architecture)
- [Repository structure](#repository-structure)
- [Local development](#local-development)
- [Environment configuration](#environment-configuration)
- [Validation and testing](#validation-and-testing)
- [Current implementation status](#current-implementation-status)
- [Architectural summary](#architectural-summary)

---

# What the system does

The application supports two recruiter entry paths:

### Manual recruiting flow

A recruiter already knows the candidate and wants to screen them.

```text
Job description
      |
      v
Recruiter-approved role definition
      |
      v
Manual candidate
      |
      v
Candidate / Job evaluation
      |
      v
Recruiter shortlist
      |
      v
Prepared outreach
      |
      v
Hunar voice call
      |
      v
Structured screening evidence
```

### People-search flow

A recruiter starts from a job and wants the system to help discover suitable people.

```text
Job description
      |
      v
Recruiter-approved role definition
      |
      v
Apollo people search
      |
      v
Selected result + enrichment
      |
      v
Canonical candidate
      |
      v
Candidate / Job evaluation
      |
      v
Recruiter shortlist
      |
      v
Prepared outreach
      |
      v
Hunar voice call
      |
      v
Structured screening evidence
```

The important design decision is that these are **not two separate hiring systems**.

Once a sourced person has been resolved into a real Candidate, both paths use the same:

- Candidate model,
- Candidate-to-Job relationship,
- matching logic,
- shortlist decision,
- outreach preparation,
- voice execution,
- and result-processing flow.

This prevents provider-specific state from leaking into the rest of the hiring workflow.

---

# The design problem

A straightforward implementation could connect:

```text
Job form
 -> LLM
 -> people-search API
 -> voice API
 -> dashboard
```

That looks simple, but it creates difficult production questions.

For example:

- Which exact version of the job was used when a candidate was evaluated?
- Is an Apollo search result already considered a Candidate?
- If the recruiter changes the job after shortlisting someone, does the old decision silently change?
- If the Candidate's phone number changes after outreach is prepared, which number belongs to the historical call?
- If Hunar accepts a call but the HTTP response is lost, is it safe to retry?
- If a completed call returns `question_1_answer`, which exact screening question does that answer belong to?
- Should Gemini or Hunar be allowed to directly change recruiter-owned hiring decisions?
- If provider data changes later, should historical business records be rewritten?

The system is designed around answering those questions explicitly.

The central principle is:

> **External AI and provider systems can propose, enrich, execute, and report.  
> Application-owned domain state decides what becomes business truth.**

---

# Design goals

The system follows several engineering principles.

## One owner for every important fact

Important state should not be duplicated across multiple tables or providers.

Examples:

```text
Current editable job               -> Job
Approved historical job            -> immutable Job definition
Canonical person                    -> Candidate
Candidate's relationship to a job  -> Candidate / Job relation
Recruiter shortlist decision        -> shortlist state
Prepared call context               -> outreach snapshot
Provider submission certainty       -> call execution
Terminal call evidence              -> call result
Screening answers                   -> normalized result answers
```

Each concept has one clear owner.

---

## Separate current state from historical truth

Some information is expected to change:

- Candidate contact information,
- a draft Job,
- current shortlist state.

Other information must remain historically stable:

- the approved Job version used for an assessment,
- the phone number actually prepared for an outreach,
- the screening questions used for a call,
- the provider request sent for that execution,
- the final result attached to that execution.

The architecture treats these differently rather than using a single mutable record for both purposes.

---

## Freeze context before irreversible side effects

A provider call should never be constructed from whatever happens to be current at execution time.

Before dispatch, the system freezes the exact execution context.

```text
Current business state
        |
        | validate
        v
Immutable outreach snapshot
        |
        v
Immutable call execution
        |
        v
External side effect
```

This makes the system auditable and prevents later edits from changing historical meaning.

---

## Human decisions remain human-owned

Gemini may suggest requirements.

Apollo may suggest people.

The matching engine may calculate evidence-based fit.

Hunar may return screening answers.

But none of those providers are allowed to silently become the final hiring authority.

The recruiter owns:

- Job approval,
- shortlist decision,
- and later hiring interpretation.

---

## Fail closed when external certainty is missing

An uncertain provider write is not treated as a normal retryable failure.

The system distinguishes:

```text
definitely not sent
definitely rejected
definitely accepted
possibly accepted
```

That distinction prevents accidental duplicate calls or duplicate provider actions.

---

# High-level architecture

```text
┌───────────────────────────────────────────────────────────────┐
│                        Browser / Recruiter                    │
└───────────────────────────────┬───────────────────────────────┘
                                │
                                │ HTTPS
                                ▼
┌───────────────────────────────────────────────────────────────┐
│                    Next.js Web Application                    │
│             React + TypeScript + TanStack Query               │
└───────────────────────────────┬───────────────────────────────┘
                                │
                                │ JSON API
                                ▼
┌───────────────────────────────────────────────────────────────┐
│                         FastAPI API                           │
│                                                               │
│  Job logic       Candidate logic      Matching logic          │
│  Outreach logic  Voice execution      Result processing       │
│  Webhooks        Provider adapters    Validation               │
└───────────────────────────────┬───────────────────────────────┘
                                │
                                │ SQLAlchemy / psycopg
                                ▼
┌───────────────────────────────────────────────────────────────┐
│                    Supabase PostgreSQL                        │
│                                                               │
│  jobs                    candidates                           │
│  approved versions       provider identities                 │
│  sourcing evidence       candidate/job relationships         │
│  match history           outreach snapshots                  │
│  call executions         call results                        │
│  screening answers       durable work_items                  │
└──────────────────────┬────────────────────────────────────────┘
                       │
                       │ durable work claiming
                       ▼
┌───────────────────────────────────────────────────────────────┐
│                     Background Worker                         │
│                                                               │
│  Apollo enrichment / recovery                                 │
│  Hunar call dispatch                                          │
│  safe reconciliation                                          │
└───────────────┬───────────────────────────────┬───────────────┘
                │                               │
                ▼                               ▼
        ┌──────────────┐                 ┌──────────────┐
        │    Apollo    │                 │    Hunar     │
        └──────┬───────┘                 └──────┬───────┘
               │                                │
               │ callbacks                      │ signed call_summary
               └───────────────┬────────────────┘
                               ▼
                        FastAPI webhook layer
```

The API and background worker do **not** call each other directly.

They coordinate through the same PostgreSQL database.

That means:

```text
API
 |
 | creates durable work
 v
PostgreSQL work_items
 ^
 | claims work
 |
Worker
```

This gives the worker no need for its own public HTTP endpoint.

---

# How the system works

The system can be understood as a sequence of controlled state transitions.

```text
Unstructured role
      |
      v
Approved hiring definition
      |
      v
Candidate identity
      |
      v
Candidate / Job evidence
      |
      v
Recruiter decision
      |
      v
Frozen outreach intent
      |
      v
Provider call execution
      |
      v
Terminal provider evidence
      |
      v
Recruiter-readable screening result
```

Every transition changes the **meaning** of the data.

For example:

```text
search result
    != Candidate

Candidate
    != Candidate shortlisted for this Job

shortlisted Candidate
    != approved outreach

approved outreach
    != provider submission

provider submission
    != completed call

completed call
    != hiring decision
```

The architecture preserves those distinctions explicitly.

---

# Domain model and state ownership

The application does not use provider objects as its domain model.

Instead it maintains application-owned entities with clear responsibility.

## Job

Represents the recruiter's current editable working definition.

The Job is mutable while being edited.

Important state includes:

- status,
- revision,
- approved version pointer.

---

## Approved Job definition

Represents an immutable historical snapshot of a recruiter-approved Job.

A new approval creates a new version.

Existing versions are never rewritten.

```text
Job draft
   |
approve
   v
definition v1

reopen
   |
edit
   |
approve
   v
definition v2
```

`v1` continues to exist unchanged.

---

## Candidate

Represents one canonical person across the entire application.

A Candidate is independent of any specific Job.

A Candidate may have:

- name,
- email,
- phone,
- provider identities,
- mutable profile information.

Provider identities are stored separately so that:

```text
Apollo person ID
    != Candidate primary key
```

---

## Candidate / Job relationship

Represents one Candidate being considered for one Job.

This is where Job-specific state belongs.

Examples:

- match evidence,
- assessment history,
- shortlist status,
- call readiness.

This avoids polluting global Candidate identity with Job-specific decisions.

---

## Outreach snapshot

Represents the exact recruiter-confirmed context that is ready for execution.

It freezes:

- the Candidate / Job relationship,
- exact phone number,
- exact ordered screening questions,
- the relevant approved Job context.

This record is historical execution intent.

---

## Voice-call execution

Represents the application's attempt to submit one exact outreach intent to Hunar.

It owns:

- immutable execution inputs,
- provider request correlation,
- provider call identity when known,
- submission certainty.

It does **not** own final call completion.

---

## Call result

Represents trusted terminal provider evidence for a voice-call execution.

It owns:

- terminal provider/lifecycle status,
- human-vs-machine evidence,
- normalized conversation outcome,
- Candidate interest,
- timing,
- result availability,
- backend-only recording reference.

---

## Screening answers

Represent normalized answers to the exact questions frozen in outreach.

They are mapped back to immutable question UUIDs rather than relying on current Job state.

This is important because the Job may have changed after the call was created.

---

# Job definition and approval

A hiring workflow begins with an unstructured Job Description.

Gemini may optionally analyze it.

```text
Raw JD
   |
   +-----> Gemini
   |         |
   |         v
   |    structured proposal
   |         |
   +---------+
       |
       v
Recruiter editing
       |
       v
DRAFT Job
       |
       | approve
       v
Immutable definition vN
```

The AI response is never directly considered approved business state.

The recruiter may:

- accept suggestions,
- modify them,
- ignore them,
- add their own requirements,
- edit screening questions.

Only explicit approval creates the immutable definition used by downstream workflows.

If Gemini is unavailable, manual Job creation remains fully functional.

---

# Candidate identity

The application supports candidates from different sources without creating separate identity systems.

```text
Manual entry --------\
                      \
                       > canonical Candidate
                      /
Apollo enrichment ---/
```

The Candidate model is global.

A Job does not own the Candidate.

A provider does not own the Candidate.

Provider identifiers are attached as external identities.

This lets the system answer:

> Is this provider person already a Candidate we know?

without making provider search results authoritative by default.

### Identity safety

The system intentionally avoids automatically merging people based only on weak similarity such as:

- similar names,
- title,
- company,
- location.

Strong identifiers and explicit provider identity are used conservatively.

This protects against accidentally collapsing two real people into one Candidate.

---

# People search and enrichment

People search is split into two different operations:

```text
Search
   |
   v
Evidence

Enrichment
   |
   v
Identity/contact resolution
```

That separation is intentional.

## Search

Apollo search returns provider evidence that may help a recruiter identify potential candidates.

A search result is not automatically promoted into Candidate Core.

This prevents a broad search from polluting canonical Candidate data.

## Enrichment

A recruiter explicitly chooses a result worth enriching.

Only then does the system request additional provider information and attempt Candidate resolution.

Some enrichment work can complete asynchronously, so the background worker and provider callbacks are used where needed.

## Why search and enrichment are separated

Provider enrichment may:

- consume credits,
- reveal contact information,
- have uncertain network outcomes,
- require asynchronous recovery.

Those properties are different from simple search.

The system therefore does not hide them behind a single opaque “find candidate” operation.

---

# Candidate-to-job evaluation

Once a Candidate is attached to a Job, the application builds an evidence-grounded assessment.

```text
Approved Job definition
          +
Candidate evidence
          |
          v
assessment
          |
          v
recruiter review
          |
          v
shortlist decision
```

The system distinguishes:

```text
matching evidence
    != recruiter decision
```

The matching layer may evaluate:

- explicit Job requirements,
- available Candidate evidence,
- role/seniority signals,
- known or unknown evidence.

Missing evidence remains unknown rather than being silently converted into a negative or positive assumption.

Phone availability is not a fit signal.

It only affects whether a Candidate can progress to voice outreach.

---

# Outreach preparation

A shortlist decision alone is not enough to make a provider call.

Before execution, the recruiter prepares an immutable outreach context.

```text
Current shortlist
      |
      + current Candidate phone
      |
      + approved Job definition
      |
      + configured screening questions
      |
      v
immutable outreach snapshot
```

The snapshot is important because current application data can change.

For example:

```text
09:00 Candidate phone = +91 AAA
09:05 outreach prepared
09:10 Candidate phone edited = +91 BBB
09:15 call executes
```

The historical call must still know whether it was prepared for `AAA` or `BBB`.

It should not silently use whichever phone happens to be current at 09:15.

The same rule applies to screening questions.

---

# Voice-call execution

The background worker performs the actual Hunar call submission.

The execution path is deliberately split around the external HTTP request.

```text
Database
   |
   | validate execution
   | load frozen context
   v
close transaction
   |
   v
Hunar agent preflight
   |
   v
POST /calls
   |
   v
classify provider certainty
   |
   v
short persistence transaction
```

No database transaction is held open while waiting on Hunar.

## Submission states

```text
QUEUED
   |
   +------> SUBMITTED
   |
   +------> FAILED
   |
   +------> UNKNOWN
```

### `QUEUED`

The execution exists and is waiting for worker dispatch.

### `SUBMITTED`

Hunar positively acknowledged the call-create request and the provider identity was persisted.

This does **not** mean the call completed.

### `FAILED`

The system knows the call was not successfully submitted.

Only safe FAILED executions may be explicitly retried.

### `UNKNOWN`

The request may have reached Hunar, but the application cannot prove whether the side effect happened.

The system does not blindly replay UNKNOWN executions.

---

# Call results and screening evidence

Call completion is processed independently from call submission.

Hunar sends a signed terminal `call_summary` webhook to the FastAPI API.

```text
Hunar terminal event
        |
        v
raw request bytes
        |
        v
timestamp + HMAC verification
        |
        v
JSON parsing
        |
        v
execution identity validation
        |
        v
terminal evidence validation
        |
        v
human-answer gate
        |
        v
result normalization
        |
        v
screening answers
```

The signature is verified against the exact raw body before business JSON processing.

## Human-answer gate

A completed provider call is not automatically treated as a completed human screening.

```text
COMPLETED + HUMAN
        |
        v
screening evidence may be accepted

COMPLETED + MACHINE
        |
        v
no Candidate answers

COMPLETED + UNKNOWN
        |
        v
no Candidate answers

NOT_CONNECTED / FAILED / CANCELLED
        |
        v
no Candidate answers
```

This prevents voicemail or machine-answer scenarios from becoming Candidate responses.

---

# Mapping screening answers safely

Hunar returns numbered answer slots.

For example:

```text
question_1_answer
question_2_answer
...
question_10_answer
```

Those numbers are not treated as permanent question identity.

Instead:

```text
question_1_answer
        |
        v
outreach snapshot question #1
        |
        v
immutable question UUID
```

This matters because current Job questions may later be edited.

Historical screening evidence must always map to the exact question used during that call.

---

# Asynchronous work model

Long-running or externally uncertain operations are represented as durable database work.

The worker does not use an in-memory queue.

```text
FastAPI
   |
   | create domain state + work item
   v
PostgreSQL
   |
   | claim with concurrency protection
   v
Worker
   |
   v
Provider
```

Benefits:

- API restarts do not lose pending work.
- Worker restarts do not lose queue state.
- API and worker can run on separate hosting providers.
- work execution has explicit status and retry semantics.
- multiple workers can safely claim work without processing the same item simultaneously.

The database is therefore both:

- business-state authority,
- and durable work coordination authority.

This avoids introducing Redis/Celery when the application does not require them.

---

# Provider integration boundaries

Provider clients live behind dedicated integration boundaries.

The rest of the application should not depend directly on provider response structures.

---

## Gemini

Purpose:

- analyze raw Job Description,
- suggest structured requirements,
- suggest screening questions.

Gemini does not:

- approve the Job,
- mutate Candidate state,
- shortlist Candidates,
- trigger outreach,
- make hiring decisions.

---

## Apollo

Purpose:

- people search,
- enrichment,
- contact recovery.

Apollo search data is provider evidence.

Candidate Core remains application-owned.

---

## Hunar

Purpose:

- execute the voice call,
- report call lifecycle/result evidence.

Hunar does not own:

- Candidate identity,
- shortlist truth,
- screening question identity,
- application retry policy,
- hiring decisions.

The application uses pre-provisioned ACTIVE Hunar agents and does not dynamically create or mutate agents during Candidate execution.

---

# Reliability and failure semantics

A key engineering concern is avoiding incorrect retries.

## External writes are not assumed idempotent

A request identifier is not automatically treated as a provider idempotency key unless the provider contract explicitly guarantees it.

For Hunar, application `request_id` is used for correlation.

It does not justify blind replay.

---

## Provider failure classification

Conceptually:

```text
before provider side effect
        |
        + known failure
        |     |
        |     v
        | safe retry may be possible
        |
provider may have received request
        |
        + response definitely accepted
        |     |
        |     v
        | SUBMITTED
        |
        + response definitely rejected
        |     |
        |     v
        | FAILED
        |
        + acknowledgement uncertain
              |
              v
           UNKNOWN
```

That `UNKNOWN` state is intentional.

It protects the system from duplicate external actions.

---

## No provider HTTP inside database transactions

Provider latency should not control PostgreSQL lock duration.

This rule is used across asynchronous provider workflows.

---

## Recovery is read-only when side effects are uncertain

If the system already knows the exact provider call ID, recovery may perform a read-only provider lookup.

Recovery never creates a replacement call.

If the provider identity is unknown and the original write is ambiguous, the system fails closed rather than guessing.

---

# Concurrency and historical consistency

The application uses different techniques for mutable and immutable state.

## Mutable aggregates

Mutable records such as Jobs and Candidates use revision-based optimistic concurrency.

Example:

```text
Browser A loads revision 4
Browser B loads revision 4

Browser A saves
-> revision becomes 5

Browser B tries to save revision 4
-> conflict
```

This prevents silent lost updates.

---

## Immutable historical records

Approved definitions, match assessments, outreach execution context, and call execution inputs are preserved rather than updated in place.

That means downstream records can point to the exact historical evidence used at the time.

---

## Reopening a Job

Reopening an approved Job does not destroy historical truth.

```text
definition v1
    |
Job reopened
    |
edited
    |
definition v2
```

Anything historically bound to `v1` remains bound to `v1`.

New work should use the newly approved definition once the Job is READY again.

---

# Security and data exposure

The frontend communicates with application data through FastAPI.

It does not directly use Supabase business tables.

## Backend-only secrets

Never expose:

```text
DATABASE_URL
GEMINI_API_KEY
APOLLO_API_KEY
APOLLO_WEBHOOK_SIGNING_SECRET
HUNAR_API_KEY
HUNAR_WEBHOOK_API_KEYS_JSON
```

through `NEXT_PUBLIC_*`.

---

## Webhook verification

Provider callback authenticity is validated at the backend boundary.

For Hunar:

1. receive raw request body,
2. validate timestamp tolerance,
3. validate HMAC signature,
4. only then parse and process JSON.

---

## Sensitive recruiting data

Logs should not contain:

- provider authorization headers,
- Candidate phone numbers,
- Candidate email addresses,
- screening answers,
- raw result payloads,
- recording URLs,
- provider secrets.

Recording references remain backend-controlled rather than being directly exposed as raw provider URLs.

---

## Current access-control boundary

The current implementation does not yet contain complete application-level authentication/RBAC.

Therefore hosted qualification should use controlled/synthetic recruiting data or an external staging access boundary.

A public production deployment handling real Candidate data should add authenticated recruiter access before general exposure.

---

# Deployment architecture

The application is intentionally split by runtime responsibility.

```text
                   ┌─────────────────┐
                   │     Vercel      │
                   │    Next.js      │
                   └────────┬────────┘
                            │
                            ▼
                   ┌─────────────────┐
                   │     Render      │
                   │     FastAPI     │
                   └────────┬────────┘
                            │
                            ▼
                 ┌───────────────────────┐
                 │ Hosted Supabase      │
                 │ PostgreSQL           │
                 └──────────┬────────────┘
                            ▲
                            │
                   ┌────────┴────────┐
                   │    Railway      │
                   │ background      │
                   │ worker          │
                   └───────┬─────────┘
                           │
                  ┌────────┴────────┐
                  ▼                 ▼
               Apollo            Hunar
                  │                 │
                  └───────┬─────────┘
                          ▼
                     Render API
                     webhooks
```

### Vercel

Runs the browser-facing Next.js application.

It needs only public frontend configuration such as:

```env
NEXT_PUBLIC_API_BASE_URL=https://<api-host>/api/v1
```

---

### Render

Runs the public FastAPI service.

Responsibilities:

- browser API,
- Gemini synchronous analysis,
- Apollo callbacks,
- Hunar signed summary webhook,
- reads/writes application state.

---

### Railway

Runs the long-lived worker.

Responsibilities:

- durable work polling,
- Apollo provider work,
- Hunar call dispatch,
- recovery callbacks.

The worker does not need a public domain.

---

### Supabase

Runs PostgreSQL and is shared by FastAPI and the worker.

Both deployments must use the same database.

---

# Repository structure

```text
.
├── apps/
│   ├── api/
│   │   ├── app/
│   │   │   ├── core/
│   │   │   ├── jobs/
│   │   │   ├── candidates/
│   │   │   ├── sourcing/
│   │   │   ├── matching/
│   │   │   ├── outreach/
│   │   │   ├── voice_calls/
│   │   │   ├── call_results/
│   │   │   ├── work_items/
│   │   │   ├── worker/
│   │   │   └── integrations/
│   │   │       ├── gemini/
│   │   │       ├── apollo/
│   │   │       └── hunar/
│   │   └── tests/
│   │
│   └── web/
│       ├── app/
│       ├── components/
│       └── lib/
│
├── supabase/
│   ├── migrations/
│   ├── config.toml
│   └── seed.sql
│
├── scripts/
│   └── validation utilities
│
└── doc/
    ├── implementation plans
    ├── validation documents
    └── provider contracts / implementation ledgers
```

The top-level README explains the system.

Detailed implementation and qualification evidence remains in `doc/`.

---

# Local development

## Prerequisites

- Python 3.12+
- Node.js 20+
- npm 10+
- Supabase CLI
- Docker

Provider credentials are optional unless testing that integration.

---

## Start PostgreSQL / Supabase locally

From the repository root:

```bash
supabase start
supabase db reset
supabase status
```

Use the PostgreSQL connection shown by `supabase status`.

Example:

```text
postgresql+psycopg://postgres:postgres@127.0.0.1:54322/postgres
```

---

## Start the API

```bash
cd apps/api

python -m venv .venv
```

Windows:

```powershell
.\.venv\Scripts\Activate.ps1
```

macOS/Linux:

```bash
source .venv/bin/activate
```

Install development dependencies:

```bash
python -m pip install -e ".[dev]"
```

Copy environment configuration:

```bash
cp .env.example .env
```

At minimum:

```env
DATABASE_URL=postgresql+psycopg://postgres:postgres@127.0.0.1:54322/postgres
```

Run:

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Health:

```text
GET http://localhost:8000/api/v1/health/live
GET http://localhost:8000/api/v1/health/ready
```

---

## Start the worker

Open a second backend terminal:

```bash
cd apps/api
python -m app.worker.main
```

The worker is required for asynchronous provider workflows and voice dispatch.

Gemini Job analysis is synchronous and does not use the worker.

---

## Start the frontend

From the repository root:

```bash
npm install
cp apps/web/.env.local.example apps/web/.env.local
npm run web:dev
```

Configure:

```env
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000/api/v1
```

Open:

```text
http://localhost:3000
```

---

# Environment configuration

The repository's `.env.example` files remain the executable source of truth for configuration names.

The important groups are summarized below.

## Core backend

```env
APP_ENV=development
DATABASE_URL=
CORS_ORIGINS=http://localhost:3000
LOG_LEVEL=INFO

WORKER_POLL_INTERVAL_SECONDS=1
WORKER_LEASE_SECONDS=300
```

---

## Gemini

```env
GEMINI_API_KEY=
GEMINI_MODEL=gemini-3.7-flash
GEMINI_THINKING_LEVEL=low
GEMINI_READ_TIMEOUT_SECONDS=60
```

---

## Apollo

```env
APOLLO_API_KEY=
APOLLO_API_BASE_URL=https://api.apollo.io/api/v1
APOLLO_WEBHOOK_BASE_URL=https://your-public-api.example.com
APOLLO_WEBHOOK_SIGNING_SECRET=
APOLLO_SEARCH_READ_TIMEOUT_SECONDS=30
APOLLO_ENRICHMENT_READ_TIMEOUT_SECONDS=60
SOURCING_SEARCH_STALE_SECONDS=300
```

`APOLLO_WEBHOOK_BASE_URL` is the API origin, not the frontend origin.

---

## Hunar

```env
HUNAR_API_KEY=
HUNAR_API_BASE_URL=https://api.voice.hunar.ai/external/v1
HUNAR_SCREENING_AGENT_IDS_JSON={"ENGLISH":"<active-agent-uuid>"}
HUNAR_DEFAULT_LANGUAGE=ENGLISH
HUNAR_DEFAULT_TIMEZONE=Asia/Kolkata
HUNAR_READ_TIMEOUT_SECONDS=30

HUNAR_CALL_SUMMARY_CALLBACK_URL=https://your-public-api.example.com/api/v1/webhooks/hunar/call-summary
HUNAR_WEBHOOK_API_KEYS_JSON=[]
```

The Hunar callback value is the full callback endpoint.

---

# Validation and testing

The repository uses several layers of qualification rather than relying on one test suite.

## Static / structural validation

```bash
python scripts/validate_module_0.py
python scripts/validate_module_1.py
python scripts/validate_module_2.py
python scripts/validate_module_3.py
python scripts/validate_module_4.py
python scripts/validate_module_5.py
python scripts/validate_module_6.py
python scripts/validate_module_7.py
```

These scripts verify important implementation boundaries and module contracts.

---

## Backend quality

```bash
cd apps/api

ruff check .
mypy app
python -m pytest -q
```

---

## PostgreSQL qualification

For tests that exercise real database semantics, configure a **disposable migrated database**.

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

Database-specific qualification covers behavior that mocks cannot prove reliably, including:

- constraints,
- immutable triggers,
- concurrency,
- deduplication,
- work claiming,
- transaction behavior,
- historical version relationships.

---

## Frontend quality

From the repository root:

```bash
npm run web:lint
npm run web:typecheck
npm run web:test
npm run web:build
```

---

## Database rebuild

```bash
supabase db reset
```

A clean reset should recreate the full schema from migrations.

---

## Provider qualification

Live provider qualification should be run separately from deterministic unit/regression testing.

Typical sequence:

```text
Job approval
    |
Candidate
    |
matching / shortlist
    |
outreach
    |
worker dispatch
    |
real Hunar call
    |
signed terminal webhook
    |
screening result
```

Apollo qualification additionally exercises:

```text
search
  |
enrichment
  |
worker
  |
provider callback / recovery
  |
Candidate resolution
```

Detailed qualification procedures are maintained under `doc/`.

---

# Current implementation status

The hiring workflow through terminal screening-result recovery is implemented.

The current system includes:

- application foundation,
- recruiter-controlled Job definition,
- optional Gemini Job analysis,
- global Candidate identity,
- Apollo people search,
- explicit contact enrichment,
- Candidate / Job assessment,
- recruiter shortlist state,
- immutable outreach preparation,
- Hunar voice-call submission,
- safe provider uncertainty handling,
- signed Hunar terminal webhook ingestion,
- human-only screening-answer acceptance,
- exact historical question mapping,
- safe read-only result recovery,
- hosted API/worker/database/frontend topology.

The next planned product layer is the recruiter-facing dashboard and final end-to-end qualification experience.

That layer should **consume** existing business authorities rather than create new competing copies of Job, Candidate, matching, outreach, call, or result state.

---

# Architectural summary

The easiest way to understand the system is through what it deliberately refuses to collapse together.

```text
AI suggestion
    != approved Job

provider search result
    != Candidate

Candidate
    != Candidate-for-Job

matching evidence
    != recruiter decision

shortlist
    != execution approval

outreach preparation
    != provider submission

provider submission
    != call completion

call completion
    != human screening

human screening
    != hiring decision
```

Those boundaries are the design.

They make the system more predictable when:

- Jobs change,
- Candidate information changes,
- providers fail,
- HTTP responses become ambiguous,
- asynchronous work is retried,
- historical screening results arrive later,
- or multiple recruiter workflows converge on the same Candidate.

The result is a recruiting workflow where AI and external providers are useful without being allowed to silently redefine application truth.
