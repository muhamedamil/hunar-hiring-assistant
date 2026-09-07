# Hunar Hiring Assistant — Module 8 Implementation Plan

## Recruiter Dashboard, Screening Results Workspace, and Final End-to-End Qualification

**Authoritative baseline:** `hunar-hiring-assistant-main (3)(2).zip`

**Current baseline status:**
- Modules 0–7 implemented.
- Structural validators 0–7 pass.
- Current backend suite observed at the latest inspection: `302 passed / 49 skipped / 0 failed`.
- No dashboard package, dashboard table, dashboard API, or dashboard frontend exists yet.
- Module 8 must remain a **read/composition and recruiter-experience layer**, not a new business-truth layer.

**STEP 1 repository reconciliation (2026-09-07):**
- The `(3)(2)` upload supersedes the stale `(3)(1)` filename in the original handoff.
- Actual backend run on this baseline: `302 passed / 49 skipped / 0 failed`.
- `doc/MODULE_7_VALIDATION.md` still says 46 skipped; this is recorded documentation drift, not a Module 8 authority change.
- Current backend version remains `0.8.0`; current migration head remains `20260907170000_module_7_call_results.sql`.
- Exact frozen contracts, query joins, answer-absence semantics, index qualification, and file updates are recorded in `doc/MODULE_8_IMPLEMENTATION_LEDGER.md`.
- STEP 1 is documentation-only. No Module 8 backend, migration, worker, provider, or frontend production code is created in STEP 1.
- Final cross-verification corrections are frozen in this plan: `count_interested_screenings()` is explicit; one canonical screening-state SQL expression must be reused everywhere; recruiter KPI wording uses available screening results rather than completed calls; recent screenings are execution-based and deterministically ordered; `q` trim/validation is exact; screening-detail not-found vs historical-integrity failures are distinct; and the initial `/screenings` UI must not build a Job dropdown from a capped first-100 Jobs list.

---

# 0. Purpose

Module 8 closes the final recruiter-facing gap in the application.

The system already owns correct truth for:

```text
Job
Candidate
Candidate ↔ Job
Match assessment
Recruiter shortlist
Outreach
Voice-call execution
Call result
Screening answers
```

What is missing is a recruiter-facing place that answers:

```text
What is happening?
What needs attention?
Where are candidates in the workflow?
Which voice screenings are pending or failed?
Who completed screening?
Was the candidate interested?
What exact questions were asked?
What did the candidate answer?
```

Module 8 must therefore:

1. build a read-only cross-domain dashboard projection;
2. expose screening results in a recruiter-facing workspace;
3. complete final Task-1 and Task-2 end-to-end qualification.

Module 8 must **not** create duplicate business truth.

---

# 1. Core design rule

The dashboard is a projection of existing truth.

Correct:

```text
Existing authoritative domain state
            |
            v
Read-only dashboard projection
            |
            v
Recruiter dashboard / screening workspace
```

Incorrect:

```text
Existing authoritative domain state
            |
            v
New dashboard state table
            |
            v
Second source of truth
```

---

# 2. Frozen authority map

The implementation agent must preserve these owners exactly.

| Business fact | Authority | Module 8 behavior |
|---|---|---|
| Current Job | `jobs` | Read only |
| Approved historical Job | `job_definition_versions` | Use exact historical version when needed |
| Candidate identity | `candidates` | Read only |
| Provider identity | `candidate_external_identities` | Do not use as recruiter truth |
| Candidate-for-Job relation | `job_candidates` | Pipeline unit |
| Match assessment | `job_candidate_matches` | Do not recalculate |
| Recruiter shortlist | `job_candidates.shortlist_status` + decision binding | Do not duplicate |
| Outreach context | `outreach_requests` | Historical frozen execution context |
| Call submission | `voice_call_executions` | Preserve `queued/submitted/failed/unknown` |
| Terminal call truth | `voice_call_results` | Read only |
| Screening answers | `voice_screening_answers` | Read exact accepted answers |
| Historical question text | `outreach_requests.screening_questions_snapshot` | Sole question authority |
| Worker state | `work_items` | Operational only; never recruiter business truth |

---

# 3. Non-negotiable invariants

The implementation must satisfy all of the following.

```text
Dashboard MUST NOT own Candidate truth.

Dashboard MUST NOT own Job truth.

Dashboard MUST NOT create another pipeline-state table.

Dashboard MUST NOT copy shortlist truth.

Dashboard MUST NOT recalculate match scores.

Dashboard MUST NOT rewrite match freshness.

Dashboard MUST NOT infer submission state from terminal call result.

Dashboard MUST NOT infer hiring outcome from candidate_interest.

Dashboard MUST NOT treat MACHINE/UNKNOWN-human results as Candidate answers.

Dashboard MUST NOT remap answers against the current Job questions.

Dashboard MUST NOT branch behavior based on manual Candidate vs Apollo Candidate origin.

Dashboard MUST NOT expose raw provider payloads.

Dashboard MUST NOT expose raw recording URLs.

Dashboard MUST NOT use work_items as recruiter business truth.

Dashboard MUST NOT calculate authoritative totals from frontend lists capped at 100.

Dashboard GET endpoints MUST NOT call Gemini.

Dashboard GET endpoints MUST NOT call Apollo.

Dashboard GET endpoints MUST NOT call Hunar.

Dashboard GET endpoints MUST NOT enqueue work.

Dashboard MUST preserve Module 6 UNKNOWN even when Module 7 later proves a completed call.
```

---

# 4. Pipeline unit

A Candidate does not have one global hiring stage.

The correct workflow unit is:

```text
Job
  |
  +-- JobCandidate
         |
         +-- match history
         +-- shortlist decision
         +-- outreach history
                |
                +-- voice execution
                       |
                       +-- terminal result
                              |
                              +-- screening answers
```

One Candidate may be in different states for different Jobs.

Example:

```text
Sarah
  ├─ Backend Engineer      -> shortlisted
  ├─ Engineering Manager   -> reviewing
  └─ Staff Engineer        -> not_selected
```

The dashboard must never collapse those into:

```text
Sarah = shortlisted
```

globally.

---

# 5. Module 8 implementation strategy

Implementation must happen in exactly three stages:

```text
STEP 1
Freeze implementation ledger and read contracts

        ↓

STEP 2
Build and prove backend dashboard projections

        ↓

STEP 3
Build recruiter UI and complete final E2E qualification
```

Do not begin Step 3 until Step 2 is qualified.

---

# STEP 1 — Freeze the Module 8 Implementation Ledger

## 1.1 Create the implementation ledger

Create:

```text
doc/MODULE_8_IMPLEMENTATION_LEDGER.md
```

The ledger must record:

```text
Authoritative baseline
Current backend version
Current migration head
Frozen upstream authorities
New Module 8 files
New endpoints
New schemas
Repository query contracts
Projection rules
Historical-context rules
Screening display-state rules
Expected database indexes
Frontend pages/components
Testing matrix
Provider isolation rules
Security constraints
Known non-goals
Implementation deviations
Qualification status
```

The ledger must be updated during implementation.

It is not optional documentation.

---

## 1.2 Create the final implementation plan document

Create:

```text
doc/MODULE_8_IMPLEMENTATION_PLAN.md
```

The content of this file should remain aligned with this handoff.

If repository evidence requires a bounded deviation:

1. record the evidence;
2. identify the exact invariant affected;
3. make the smallest correction;
4. update the ledger;
5. prove no upstream authority changed.

Do not redesign the system to make implementation easier.

---

## 1.3 New backend package

Create:

```text
apps/api/app/dashboard/
    __init__.py
    dependencies.py
    repository.py
    router.py
    schemas.py
    service.py
```

Do **not** create unless repository evidence proves a genuine requirement:

```text
models.py
workers.py
provider.py
webhooks.py
```

There is no new dashboard business entity.

Therefore no new ORM model should exist.

---

## 1.4 Required API endpoints

Create exactly these read endpoints:

```text
GET /api/v1/dashboard/overview

GET /api/v1/dashboard/screenings

GET /api/v1/dashboard/screenings/{execution_id}
```

Do not introduce dashboard mutation endpoints.

Forbidden:

```text
POST   /dashboard/...
PATCH  /dashboard/...
DELETE /dashboard/...
```

All mutation/actions remain owned by existing workflow APIs.

---

## 1.5 Required projection schemas

At minimum create typed schemas for:

```text
DashboardOverviewResponse

DashboardJobMetrics
DashboardCandidateMetrics
DashboardPipelineMetrics
DashboardScreeningMetrics

DashboardAttentionKind
DashboardAttentionItem

DashboardScreeningState
DashboardScreeningSummary
DashboardScreeningListResponse

DashboardQuestionAnswer
DashboardScreeningDetailResponse
```

Provider DTOs must never appear in dashboard public contracts.

Repository-evidence clarification: `DashboardQuestionAnswer.answer_state` must be nullable. `null`
means no authoritative Module 7 answer row exists. It must never be converted to `not_asked`, because
`not_asked` is itself an immutable Module 7 answer state. Reuse existing bounded upstream enums where
appropriate; do not expose Hunar request/response/webhook DTOs.

---

## 1.6 Dashboard screening state

Create a read-only display enum such as:

```text
queued
awaiting_result
dispatch_failed
submission_unknown
result_available
result_unavailable
result_invalid
```

This state must never be persisted.

Screening summary/detail must also return the unchanged Module 6 execution status separately as
`submission_status`, so result-first display projection never erases `UNKNOWN`.

Exact precedence:

```text
if voice_call_result exists:
    available   -> result_available
    unavailable -> result_unavailable
    invalid     -> result_invalid

else:
    execution queued    -> queued
    execution submitted -> awaiting_result
    execution failed    -> dispatch_failed
    execution unknown   -> submission_unknown
```

Important example:

```text
voice_call_execution.status = UNKNOWN
voice_call_result.state      = available
```

The dashboard may display:

```text
screening result available
```

while still returning:

```text
submission certainty = UNKNOWN
```

in detail.

It must never rewrite Module 6 state.

---

## 1.7 Historical context rules

For screening detail and screening list rows:

### Candidate identity

Current Candidate display name may be shown.

Do not claim it is a historical name snapshot unless the existing frozen execution contract contains one and the design intentionally uses it.

### Job title / approved definition

Use the historical Job definition associated with the exact match/outreach context.

Do not blindly use the current mutable Job title.

Expected trace:

```text
voice_call_executions.outreach_request_id
    -> outreach_requests.id
    -> outreach_requests.decision_match_id
    -> job_candidate_matches.id
    -> (job_candidate_matches.job_id, job_candidate_matches.definition_version)
    -> job_definition_versions(job_id, version)
```

The execution has no direct foreign key to a match. Preserve the outreach-mediated binding and also
require the selected match to belong to `outreach_requests.job_candidate_id`.

### Screening questions

Use:

```text
outreach_requests.screening_questions_snapshot
```

Map screening answers back to the exact historical question UUIDs.

Do not use current Job questions.

---

## 1.8 Database plan

Do not create:

```text
dashboard_state
candidate_pipeline_state
dashboard_metrics
screening_dashboard_cache
analytics_snapshot
```

Do not create a materialized view unless real qualification later proves the read model cannot meet the intended scale without one.

Initial plan:

- repository-level SQL projections;
- optional read indexes only.

Conditional migration name, created only if representative PostgreSQL `EXPLAIN` proves at
least one new index useful:

```text
20260907194500_module_8_recruiter_dashboard_read_indexes.sql
```

If none of the candidate indexes is justified, Module 8 adds no migration and the migration head
remains the Module 7 head.

Candidate indexes:

```sql
create index ix_job_candidates_dashboard_status_updated
on public.job_candidates(shortlist_status, updated_at desc);

create index ix_outreach_requests_dashboard_relation_created
on public.outreach_requests(job_candidate_id, created_at desc);

create index ix_voice_call_executions_dashboard_status_updated
on public.voice_call_executions(status, updated_at desc);

create index ix_voice_call_results_dashboard_observed
on public.voice_call_results(observed_at desc);
```

Do not retain speculative indexes automatically.

Each index must be validated against the real query path with representative PostgreSQL qualification.

---

## 1.9 Frontend artifact ledger

Plan these files:

```text
apps/web/lib/dashboard/
    api.ts
    queries.ts
    types.ts

apps/web/components/dashboard/
    dashboard-overview.tsx
    dashboard-metrics.tsx
    attention-list.tsx
    recent-screenings.tsx
    screening-state-badge.tsx

apps/web/app/screenings/
    page.tsx

apps/web/app/screenings/[executionId]/
    page.tsx
```

Update:

```text
apps/web/app/page.tsx
apps/web/components/layout/app-shell.tsx
```

Final recruiter navigation:

```text
Dashboard
Jobs
Candidates
Outreach
Screenings
```

Do not show internal module numbers in normal recruiter UI.

---

## 1.10 Qualification artifacts

Create:

```text
scripts/validate_module_8.py

doc/MODULE_8_VALIDATION.md

apps/api/tests/test_dashboard_service.py
apps/api/tests/test_dashboard_router.py
apps/api/tests/test_dashboard_database.py

apps/web/tests/dashboard.test.tsx
apps/web/tests/screenings-dashboard.test.tsx
```

Update the existing navigation consumer as well:

```text
apps/web/tests/app-shell.test.tsx
```

Update:

```text
README.md
apps/api/pyproject.toml
apps/api/uv.lock
apps/api/app/main.py
```

The backend version is mirrored in the lockfile's local project entry; the `0.9.0` bump must keep
`pyproject.toml`, `uv.lock`, and FastAPI app metadata synchronized.

Target backend version:

```text
0.8.0 -> 0.9.0
```

---

## STEP 1 completion gate

**Repository status for authoritative `(3)(2)` baseline: COMPLETE.** The frozen answers live in
`doc/MODULE_8_IMPLEMENTATION_LEDGER.md`. STEP 2 is permitted only as backend read-projection work;
frontend/dashboard UI remains blocked until STEP 2 qualification passes.

Do not begin backend implementation until the ledger answers all of these:

```text
What owns each business fact?
What new files are required?
What new endpoints are required?
What public schemas are required?
What joins are required?
What is historical vs current display data?
How is screening state projected?
How are multiple outreaches handled?
How is UNKNOWN preserved?
How are human-only answers enforced?
What provider calls are forbidden?
What fields must never be exposed?
What indexes may be required?
What tests prove correctness?
```

If any answer is still ambiguous, resolve it from repository evidence before proceeding.

---

# STEP 2 — Build and Prove the Backend Dashboard Projection

This is the most important stage.

Do not build the frontend dashboard before this stage passes qualification.

---

## 2.1 DashboardRepository

Create:

```python
class DashboardRepository:
    ...
```

Its responsibility is read-efficient SQL composition only.

Expected operations:

```text
count_jobs_by_status()

count_candidates()

count_job_candidates_by_shortlist_status()

count_screening_states()

count_interested_screenings()

list_attention_candidates(...)

list_attention_executions(...)

list_recent_screenings(...)

list_screenings(filters, limit, offset)

count_screenings(filters)

get_screening_context(execution_id)

list_screening_answers(result_id)
```

The repository must define **one canonical reusable screening-state SQL/SQLAlchemy expression** implementing the frozen result-first state precedence. Conceptually:

```python
def dashboard_screening_state_expression(...):
    ...
```

The exact implementation may be a private helper or shared SQLAlchemy `case()` expression, but the logic must exist in one place and be reused by:

```text
count_screening_states()
list_attention_executions(...)
list_recent_screenings(...)
list_screenings(...)
count_screenings(...)
```

Do not hand-code separate state `CASE` logic independently in each query.

`count_interested_screenings()` remains a distinct repository operation because `interested` is a subset metric, not one of the mutually-exclusive screening states.

Repositories must not commit.

Service owns transaction boundaries.

No external HTTP is allowed.

---

## 2.2 DashboardService

Create:

```python
class DashboardService:
    ...
```

Responsibilities:

```text
compose authoritative counts
derive display-only screening state
compose Needs Attention items
compose recent screening summaries
compose paginated screening results
compose exact historical screening detail
```

It must not:

```text
refresh matching
recompute scores
change shortlist
prepare outreach
retry calls
reconcile provider state automatically
enqueue work
call providers
commit duplicate dashboard state
```

---

## 2.3 Overview endpoint

Implement:

```http
GET /api/v1/dashboard/overview
```

Response should include:

```text
generated_at

jobs
    total
    draft
    ready

candidates
    total

pipeline
    reviewing
    shortlisted
    not_selected

screenings
    total
    queued
    awaiting_result
    dispatch_failed
    submission_unknown
    result_available
    result_unavailable
    result_invalid
    interested

needs_attention[]

recent_screenings[]
```

Important:

`interested` is a subset metric.

Do not include it in mutually exclusive screening-state arithmetic.

---

## 2.4 Screening list endpoint

Implement:

```http
GET /api/v1/dashboard/screenings
```

Supported filters:

```text
job_id?
state?
interest?
q?
limit=20
offset=0
```

Frozen STEP 1 query behavior:
- `q` searches only current Candidate full name and the exact historical Job-definition title;
- state filtering uses the same canonical result-first screening-state expression used in response projection and overview counts;
- list ordering is `coalesce(result.observed_at, execution.updated_at) desc, execution.id desc`;
- `total` uses the identical filter predicate in a database count query.

Exact `q` normalization/validation contract:

```text
q absent / null
    -> no search predicate

q supplied
    -> trim leading and trailing whitespace

trimmed length 1..100
    -> valid

trimmed empty or trimmed length > 100
    -> 422 validation error
```

A whitespace-only value such as `"   "` must never become a successful unbounded search.

Other constraints:

```text
limit  1..100
offset >= 0
```

`job_id` remains a valid backend filter for deep links and programmatic Job-scoped views. The initial Module 8 `/screenings` UI must **not** build a global Job dropdown from the existing capped Jobs list (for example `limit=100`). A future Job selector requires a proper paginated/searchable lookup contract and is outside the initial three-endpoint Module 8 boundary.

Response:

```text
items[]
total
limit
offset
```

`total` must come from authoritative database aggregation.

Do not calculate:

```text
total = items.length
```

---

## 2.5 Screening detail endpoint

Implement:

```http
GET /api/v1/dashboard/screenings/{execution_id}
```

Return safe recruiter context:

```text
execution_id
outreach_request_id

Candidate display identity

historical Job title
historical Job definition version

screening display state

submission certainty
provider terminal/lifecycle status
answered_by

conversation_outcome
candidate_interest
duration_seconds
observed_at
recording_available

notes

questions[]
    question_id
    position
    prompt
    answer_state
    answer_text
```

Do not return:

```text
phone number
raw recording URL
provider payload
provider auth
webhook signature
work-item payload/error internals
```

### Screening-detail error semantics

The endpoint must distinguish **identity absence** from **historical-integrity failure**.

```text
voice_call_execution does not exist
    -> return the existing stable execution-not-found application contract
    -> HTTP 404

voice_call_execution exists
but required immutable historical context is missing/inconsistent
    -> fail closed with an explicit application data-integrity / historical-context error
    -> do NOT convert this into a normal 404
    -> do NOT fall back to current jobs
    -> do NOT fall back to current screening questions
    -> do NOT select another outreach or another match
```

Examples of historical-integrity failure include:

```text
execution.outreach_request_id does not resolve
outreach.decision_match_id does not resolve
decision match belongs to a different job_candidate
(job_id, definition_version) does not resolve to the exact immutable Job definition
frozen outreach question identity is inconsistent with accepted answer identity
```

Prefer reuse of an existing stable application invariant/data-integrity error if the repository already has one. If a dedicated dashboard error type/file becomes necessary, record that evidence-backed deviation in the Module 8 ledger before creating it. This exception must not introduce a new business authority.

---

## 2.6 Cross-domain SQL composition

Screening projections should efficiently compose:

```text
voice_call_executions
        |
        +-- outreach_requests
                |
                +-- job_candidates
                |       |
                |       +-- candidates
                |
                +-- decision_match_id --> job_candidate_matches
                                        |
                                        +-- job_definition_versions

voice_call_executions
        |
        +-- voice_call_results
                |
                +-- voice_screening_answers   # detail only, separate ordered query
```

Do not join answer rows into screening list pagination. Load answers only for one detail result (or
aggregate them without row multiplication).

Avoid frontend N+1 composition.

Avoid calling multiple existing detail endpoints per screening row.

The backend should compose recruiter-safe read DTOs once.

---

## 2.7 Multiple outreach requests

Do not model:

```text
one JobCandidate = one call state
```

A JobCandidate may have historical outreach contexts.

Screening list rows are execution-based.

Each execution must retain the exact outreach context that created it.

---

## 2.8 Needs Attention projection

Do not create a persisted attention state.

Attention is derived.

Allowed categories should come only from existing authoritative state.

Initial categories are frozen for the first implementation as:

```text
review_candidate
dispatch_failed
submission_unknown
result_invalid
result_unavailable
```

`submission_unknown` and `dispatch_failed` attention apply only when no result row exists, matching
the **same canonical screening-state expression** used by overview counts, list projection, list filtering,
and recent screenings. An `UNKNOWN` execution with an available terminal result is not stale attention,
but detail must still show `submission_status = UNKNOWN`. `review_candidate` is exactly
`job_candidates.shortlist_status = reviewing`. Attention remains bounded to 20 rows.

Do not derive business meaning directly from `work_items`.

Examples:

```text
shortlist/review condition
        -> JobCandidate/Match truth

dispatch failed
        -> VoiceCallExecution FAILED

submission unknown
        -> VoiceCallExecution UNKNOWN

invalid result
        -> VoiceCallResult invalid
```

Keep the list bounded.

Overview is not a replacement for workflow-specific pages.

### Recent-screenings projection

`recent_screenings` means the **10 most recent voice-call executions**, not only terminal/completed results.

Use exactly the same row projection and screening-state expression as the screening list.

Frozen ordering:

```text
sort_at = coalesce(voice_call_results.observed_at, voice_call_executions.updated_at)

order by sort_at desc,
         voice_call_executions.id desc

limit 10
```

Therefore recent rows may legitimately include:

```text
queued
awaiting_result
dispatch_failed
submission_unknown
result_available
result_unavailable
result_invalid
```

Do not filter the recent list to completed calls only. This keeps the dashboard operational rather than historical-only.

---

## 2.9 Provider isolation proof

Add tests proving all dashboard GETs execute:

```text
0 Gemini calls
0 Apollo calls
0 Hunar calls
0 work-item creation
```

This must be a formal acceptance gate.

---

## 2.10 Historical correctness tests

Mandatory scenarios:

### Job edited after screening

```text
Job definition v1
    |
screening created/completed
    |
Job reopened
    |
questions/title changed
    |
definition v2
```

Old screening detail must still display:

```text
v1 historical context
v1 frozen questions
old answers
```

not v2.

### Candidate edited later

Current Candidate display identity may update.

Historical screening question/Job context must not change.

---

## 2.11 Human-answer safety tests

Test:

```text
COMPLETED + HUMAN
    -> accepted answers may display

COMPLETED + MACHINE
    -> no Candidate answers

COMPLETED + UNKNOWN
    -> no Candidate answers

For every case with no accepted answer rows, dashboard question display uses `answer_state = null`,
not the authoritative `not_asked` state.

NOT_CONNECTED
FAILED
CANCELLED
    -> no Candidate answers
```

Dashboard must consume Module 7 result truth.

Do not reimplement Module 7 normalization.

---

## 2.12 UNKNOWN/race tests

Mandatory:

```text
execution = UNKNOWN
result    = available
```

Expected:

```text
dashboard screening state = result_available

detail submission certainty = UNKNOWN
```

No mutation.

Also test:

```text
execution = QUEUED
result    = available
```

to cover terminal webhook race with submission persistence.

Result may control display projection, but execution truth remains unchanged.

---

## 2.13 Pagination/scale tests

Test beyond current frontend list limits.

At minimum qualify:

```text
>100 Jobs
>100 Candidates
>100 screening executions
```

Dashboard totals must remain authoritative.

Screening pagination must return:

```text
correct total
correct page
stable ordering
no duplicate rows
```

Also qualify:

```text
count_interested_screenings() is independent from the seven-state total
the seven mutually-exclusive screening states sum exactly to total
q is trimmed before filtering
whitespace-only q returns 422
q longer than 100 after trim returns 422
recent_screenings returns the 10 most recent executions, including unresolved executions
shared screening-state semantics are identical across overview, attention, recent, list and count
missing execution returns 404
broken historical context fails closed and never falls back to current Job/questions
```

---

## 2.14 Database/index qualification

Use disposable PostgreSQL.

Prove:

```text
one screening execution -> one dashboard list row
multiple answers do not duplicate list rows
multiple historical outreaches do not collapse
historical definition join is exact
pagination is deterministic
indexes exist only when useful
```

Use representative `EXPLAIN` checks for the final query shapes.

Remove speculative indexes if the query planner does not need them.

---

## 2.15 Backend quality gates

Run:

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

Backend:

```bash
cd apps/api

ruff check .
mypy app
python -m pytest -q
```

Database:

```bash
supabase db reset
```

If PostgreSQL tests require:

```text
TEST_DATABASE_URL
```

use only a disposable/local test database.

---

## STEP 2 completion gate

Do not start dashboard UI until all are true:

```text
Dashboard endpoints exist.

Dashboard endpoints make zero provider calls.

No dashboard business-state table exists.

Authoritative totals work beyond 100 rows.

Candidate pipeline is JobCandidate-scoped.

Historical Job context is correct.

Historical questions are correct.

UNKNOWN remains preserved.

Human-only answer safety is preserved.

Multiple outreach executions are handled correctly.

Screening list pagination is correct.

`count_interested_screenings()` is qualified as a subset metric.

One canonical screening-state expression is reused across counts, filtering, attention, recent rows and list projection.

`q` trim/validation semantics are qualified, including whitespace-only rejection.

Recent screenings are the 10 most recent executions under the frozen shared sort order.

Missing execution and broken historical-context failures are distinct and fail closed correctly.

No raw provider/recording secret data is exposed.

Backend validators/tests pass.
```

---

# STEP 3 — Build Recruiter UI and Complete Final E2E Qualification

Only begin after Step 2 passes.

---

## 3.1 Replace `/` with recruiter dashboard

The current root page should become an operational recruiter dashboard.

Recommended structure:

```text
Recruiting Overview

Jobs
Candidates
Shortlisted
Screening Results

Needs Attention

Recent Voice Screenings
```

Example:

```text
Recruiting Overview

Jobs            Candidates       Shortlisted      Screening Results
12              84               17               9 available


Needs Attention
----------------------------------------------------------------
Sarah Ahmed     Backend Engineer       Review candidate
Aisha Khan      Data Engineer          Call dispatch failed
Rahul Menon     Product Manager        Submission uncertain


Recent Voice Screenings
----------------------------------------------------------------
Candidate       Role                   Screening state      Interest
Sarah Ahmed     Backend Engineer       Result available     Interested
John Thomas     Data Engineer          Awaiting result      —
```

The screening KPI represents **available normalized screening results**, not all provider calls with lifecycle `COMPLETED`. A completed MACHINE/voicemail call is not a usable Candidate screening result.

Do not add charts simply because it is called a dashboard.

Start from recruiter decisions and operational visibility.

---

## 3.2 Dashboard metrics

Implement recruiter-safe KPI cards.

Initial metrics:

```text
Jobs
Candidates
Shortlisted
Screening Results — N available
```

The fourth KPI must be sourced from `screenings.result_available`. Do not label it `Completed Screenings`, because provider call completion does not imply an accepted HUMAN screening result.

Do not calculate these from frontend cached list lengths.

Use `/dashboard/overview`.

---

## 3.3 Needs Attention UI

Display a bounded list.

Each item must route to the owning workflow.

Examples:

```text
Review candidate
    -> JobCandidate / match page

Call dispatch failed
    -> Outreach detail

Submission uncertain
    -> Outreach / execution detail

Invalid result
    -> Screening detail
```

Dashboard does not own the action.

It only points the recruiter to the correct authority.

---

## 3.4 Recent Voice Screenings UI

Display the **10 most recent voice-call executions** returned by `/dashboard/overview`.

Columns/fields:

```text
Candidate
Role
Screening state
Outcome
Interest
Activity time
```

The list is not terminal-result-only. It may include queued, awaiting-result, failed, unknown, available, unavailable, or invalid screening projections.

`Activity time` is the backend-provided `sort_at`:

```text
coalesce(result.observed_at, execution.updated_at)
```

Do not reconstruct ordering in the frontend.

Each row routes to:

```text
/screenings/{executionId}
```

---

## 3.5 Screening results workspace

Create:

```text
/screenings
```

Columns:

```text
Candidate
Role
Screening state
Call outcome
Interest
Duration
Observed
```

Initial UI filters:

```text
Screening state
Interest
Search
```

The backend continues to support `job_id` for deep links/programmatic Job-scoped filtering, but Module 8 v1 must not render a global Job selector sourced from the existing first-100 Jobs list.

If a future Job selector is added, it must use a proper paginated/searchable lookup contract rather than assuming a capped Job response is complete.

Use server pagination.

Do not load all records and filter client-side.

---

## 3.6 Screening detail page

Create:

```text
/screenings/{executionId}
```

Recommended layout:

```text
Candidate
Role
Historical Job version


Call
------------------------------------------------
Submission certainty
Lifecycle
Answered by
Duration
Recording available


Screening
------------------------------------------------
Conversation outcome
Candidate interest
Notes


Questions & Answers
------------------------------------------------
1. <exact frozen question>
   <answer>

2. <exact frozen question>
   No clear answer

3. <exact frozen question>
   Not asked
```

---

## 3.7 Answer rendering rules

### Answered

Show answer text.

### `no_clear_answer`

Show:

```text
No clear answer
```

### `not_asked`

Show:

```text
Not asked
```

### Result unavailable

Do not fabricate question answers.

### MACHINE / human not confirmed

Explain that no human screening answers are available.

### Invalid result

Show a controlled message such as:

```text
Screening result could not be safely normalized.
```

Do not display malformed raw provider output.

---

## 3.8 Product language cleanup

Remove recruiter-facing development language such as:

```text
Module 1
Module 2
Module 3
Module 4
Module 5
Module 6
Module 7
future Module...
```

Use product terminology:

```text
Dashboard
Jobs
Candidates
People Search
Matching
Outreach
Voice Screening
Screening Results
Needs Attention
```

Internal module numbering remains allowed in:

```text
docs
validators
developer comments
implementation ledgers
```

---

## 3.9 Frontend polling

Dashboard overview may poll the local API while visible.

Suggested starting cadence:

```text
~10 seconds
```

Screening list may poll only while unresolved rows exist:

```text
queued
awaiting_result
submission_unknown
```

Do not call Hunar directly.

Do not create frontend provider polling.

---

## 3.10 Frontend tests

Test:

```text
dashboard empty state
metric rendering
Screening Results KPI uses result_available, not generic completed-call count
attention list
Recent Voice Screenings includes unresolved executions and respects backend sort_at
screening state filter
interest filter
search filter
no capped first-100 Jobs dropdown
programmatic/deep-link job_id filtering remains supported by API client contract
server pagination
screening detail
404 for missing execution
controlled historical-integrity error display
historical question text
answered state
no clear answer
not asked
no authoritative answer row
machine/no-human result
invalid result
UNKNOWN submission + available result
no unsafe retry action
navigation
no module-number recruiter copy
```

Run:

```bash
npm run web:lint
npm run web:typecheck
npm run web:test
npm run web:build
```

---

# 6. Final end-to-end qualification

Module 8 is not complete until both original hiring assignment paths are proven through the dashboard.

---

## 6.1 Task 1 — Manual Candidate E2E

Run:

```text
Raw JD
    |
optional Gemini analysis
    |
recruiter edits/approves Job
    |
manual Candidate
    |
Candidate / Job relationship
    |
match assessment
    |
recruiter shortlist
    |
outreach preparation
    |
voice-call execution
    |
Railway worker
    |
Hunar
    |
signed call_summary
    |
terminal result
    |
screening answers
    |
Dashboard
    |
Screening detail
```

Acceptance:

```text
Candidate visible
historical Job correct
call state correct
interest correct
exact questions visible
exact answers visible
```

---

## 6.2 Task 2 — Apollo Candidate E2E

Run:

```text
Raw JD
    |
approved Job
    |
Apollo search
    |
selected enrichment
    |
Candidate resolution
    |
same Candidate / Job authority
    |
same matching
    |
same shortlist
    |
same outreach
    |
same voice execution
    |
same Hunar result flow
    |
same Dashboard
```

Acceptance:

The dashboard must not expose or depend on Candidate origin.

There must be no downstream:

```text
manual Candidate dashboard
vs
Apollo Candidate dashboard
```

---

## 6.3 Historical mutation E2E

After a successful call:

```text
reopen Job
change role/question configuration
approve new version
```

Verify old screening still displays:

```text
historical role/version
historical frozen questions
historical answers
```

not the new Job definition.

---

## 6.4 MACHINE / voicemail E2E

Run at least one controlled negative call.

Expected:

```text
terminal call evidence exists

but

Candidate screening answers do not exist/display
```

The dashboard may show:

```text
Call completed
Human screening not confirmed
```

but must never invent answers.

---

## 6.5 Submission uncertainty E2E

Where practical, verify an `UNKNOWN` execution path or deterministic test fixture.

Expected:

```text
submission certainty remains UNKNOWN
```

even if terminal evidence later exists.

---

# 7. Hosted topology qualification

Final hosted topology:

```text
                    Vercel
                 Next.js Web
                      |
                      v
                  Render API
                      |
                      v
              Supabase PostgreSQL
                      ^
                      |
                Railway Worker
                  |        |
                  v        v
               Apollo    Hunar
                  |        |
                  +---+----+
                      |
                      v
               Render webhooks
                      |
                      v
                  Supabase
                      |
                      v
                  Dashboard
```

Prove:

```text
frontend -> API works
API -> DB works
worker -> DB works
worker -> Apollo works
worker -> Hunar works
Apollo callback -> Render works
Hunar callback -> Render works
terminal result -> DB works
dashboard -> DB projection works
```

---

# 8. Security constraints

Module 8 must never expose:

```text
DATABASE_URL
GEMINI_API_KEY
APOLLO_API_KEY
APOLLO_WEBHOOK_SIGNING_SECRET
HUNAR_API_KEY
HUNAR_WEBHOOK_API_KEYS_JSON

raw provider request/response payloads
webhook signatures
provider authorization headers
work-item payload internals
raw recording URL
```

Recruiter-safe fields may include:

```text
Candidate display name
Job role
screening state
call outcome
candidate interest
duration
notes
historical screening questions
normalized answers
recording_available boolean
```

---

# 9. Authentication / RBAC boundary

The current application does not contain a full recruiter authentication/RBAC/multi-tenant model.

Module 8 must not fake one.

Do not add:

```text
recruiter_id
tenant_id
organization_id
```

only inside the dashboard.

Authentication and multi-tenancy would require a system-wide authority design affecting:

```text
Jobs
Candidates
Sourcing
Matching
Outreach
Voice execution
Results
Dashboard
```

Therefore they remain outside Module 8 unless separately designed.

Current hosted qualification should use controlled/synthetic data or external staging protection.

---

# 10. Explicitly out of scope

Do not implement:

```text
authentication / RBAC
multi-tenancy
organization accounts

new Candidate state machine
new hiring-result state
automatic acceptance/rejection

AI recruiter recommendations
new match scoring

Apollo calls from dashboard
Hunar polling from dashboard
new call creation from dashboard
new redial logic

recording playback/download
transcription
LLM transcript analysis

provider payload explorer
worker operations dashboard

analytics warehouse
materialized BI layer
decorative chart suite

new sourcing logic

persisted dashboard stage
persisted screening-reviewed state
```

If a future requirement introduces new recruiter-owned truth such as:

```text
screening reviewed
decision made
next interview scheduled
```

that must receive its own explicit domain design.

Do not infer or hide it inside Module 8 projection code.

---

# 11. Blast-radius audit before freeze

Before producing the final Module 8 patch, inspect all changed contracts.

For every new dashboard read contract verify its producers and consumers.

Required blast-radius questions:

```text
Did any existing authority change?

Did any write path change?

Did any provider call move into dashboard code?

Did any current Job value replace required historical Job truth?

Did current screening questions replace frozen outreach questions?

Did UNKNOWN submission certainty get normalized away?

Did MACHINE/UNKNOWN-human result become Candidate answers?

Did Candidate origin become a downstream branch?

Did work_items leak into recruiter business state?

Did dashboard counts rely on capped list endpoints?

Did new SQL joins duplicate screening rows?

Did new indexes alter migration/RLS/security behavior?

Did frontend expose phone/email/raw recording/provider payload?

Did Module 8 create a second match/shortlist/outreach/result authority?
```

All must resolve cleanly.

---

# 12. Validation matrix

Run all structural validators:

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

Backend:

```bash
cd apps/api

ruff check .
mypy app
python -m pytest -q
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

Disposable PostgreSQL qualification:

```text
TEST_DATABASE_URL=<disposable migrated PostgreSQL URL>
```

Live provider qualification:

```text
Apollo live search/enrichment
Hunar live call
Hunar signed call_summary
dashboard result display
```

---

# 13. Final completion criteria

Module 8 is complete only when all are true:

```text
/ is a real recruiter dashboard.

Dashboard totals are authoritative.

Dashboard totals remain correct above 100 rows.

Candidate pipeline is JobCandidate-scoped.

One Candidate may appear independently across multiple Jobs.

Screening list is paginated and filterable.

Initial screening UI does not depend on a capped first-100 Jobs dropdown.

Backend `job_id` filtering remains available for deep links/programmatic Job-scoped views.

Recruiter can open screening detail.

Missing execution returns the stable 404 contract.

Broken immutable historical context fails closed without current-state fallback.

Historical Job version is correct.

Historical screening questions are correct.

Normalized answers are correct.

Only HUMAN-qualified results show Candidate answers.

UNKNOWN submission truth remains preserved.

One canonical screening-state projection is reused across overview, filtering, attention, recent screenings and list/count queries.

`interested` remains a separate subset metric.

Recent Voice Screenings means the 10 most recent executions under the frozen `sort_at` ordering.

Dashboard search trims `q`, rejects whitespace-only input, and enforces 1..100 characters after trimming.

Dashboard GETs perform zero provider calls.

Dashboard creates zero work items.

Dashboard owns zero new business-state tables.

No raw recording URL is exposed.

No raw provider payload is exposed.

No module-number development language remains in recruiter UI.

Task 1 reaches the dashboard end-to-end.

Task 2 reaches the same dashboard end-to-end.

Historical Job mutation does not rewrite old screening meaning.

Negative MACHINE/voicemail case is safe.

Modules 0–7 regressions remain green.

Backend quality gates pass.

Frontend quality gates pass.

Database reset passes.

Hosted Vercel/Render/Railway/Supabase topology is verified.
```

---

# 14. Agent execution rules

The implementation agent must follow these rules.

## Before coding

1. inspect the latest repository;
2. verify migration head;
3. verify current backend version;
4. run validators 0–7;
5. create/update Module 8 implementation ledger;
6. confirm no newer implementation already exists.

## During implementation

After each major checkpoint:

```text
update ledger
run focused tests
run structural validator
check git diff
check authority drift
```

Do not defer drift auditing until the end.

## Code quality

Production Python must use:

```text
clear module docstrings
clear public class/function/method docstrings
PEP 8 conventions
Ruff compliance
strict typing
mypy compliance
bounded responsibilities
repository/service separation
```

Repositories never commit.

Services own transaction boundaries.

No external HTTP inside DB transactions.

Frontend remains strict TypeScript.

## Before final patch

1. run all validators 0–8;
2. run full backend suite;
3. run frontend lint/typecheck/test/build;
4. run clean Supabase migration reset;
5. run disposable PostgreSQL qualification;
6. run provider-isolation tests;
7. run historical-version tests;
8. run blast-radius audit;
9. scan for secrets/PII exposure;
10. apply the generated patch to a clean copy of the authoritative baseline;
11. rerun qualification on the clean patch-applied tree;
12. byte-compare all changed files against the implementation tree.

Only after those gates pass should a final patch artifact be produced.

---

# 15. Final architecture after Module 8

```text
Job Definition
      |
      v
Candidate Identity
      |
      v
Candidate / Job Evaluation
      |
      v
Recruiter Shortlist
      |
      v
Frozen Outreach
      |
      v
Voice-call Submission
      |
      v
Terminal Screening Result
      |
      v
Recruiter Dashboard
```

The key rule remains:

```text
Dashboard = projection of truth
Dashboard != owner of truth
```

---

# 16. Final implementation sequence summary

## STEP 1

```text
Freeze Module 8 ledger
Freeze read contracts
Freeze historical/projection rules
```

## STEP 2

```text
Build dashboard repository/service/schemas/router
Build overview + screening list + screening detail
Use one canonical screening-state query expression
Keep interested counting separate from state counting
Freeze recent screenings as latest 10 executions
Freeze q trim/validation and job_id deep-link semantics
Prove missing-execution vs historical-integrity error behavior
Prove historical correctness
Prove scale/pagination
Prove provider isolation
Prove no authority drift
```

## STEP 3

```text
Build recruiter dashboard
Build screening workspace
Build screening detail
Clean recruiter-facing language
Run full local qualification
Run Task-1 E2E
Run Task-2 E2E
Run hosted Vercel/Render/Railway/Supabase qualification
Run final blast-radius audit
Produce final patch only after all gates pass
```

---

# 17. Final cross-verification corrections — frozen

The following corrections are part of the implementation contract and must not be dropped during STEP 2 or STEP 3:

```text
1. DashboardRepository explicitly includes count_interested_screenings().

2. One canonical result-first screening-state SQL/SQLAlchemy expression is reused by:
   - screening-state counts;
   - screening list projection;
   - screening list filtering;
   - screening count filtering;
   - Needs Attention execution projection;
   - Recent Voice Screenings.

3. Dashboard KPI wording is:
   Screening Results — N available
   not Completed Screenings.

4. recent_screenings means the 10 most recent voice-call executions,
   ordered by:
   coalesce(result.observed_at, execution.updated_at) desc,
   execution.id desc.

5. q is trimmed before validation/filtering.
   Null/absent means no filter.
   Trimmed empty or >100 characters returns 422.

6. Screening detail distinguishes:
   - missing execution -> stable 404;
   - broken immutable historical context -> explicit fail-closed integrity error.
   No fallback to current Job/questions is permitted.

7. job_id remains a backend filter for deep links/programmatic views.
   Module 8 v1 does not build a global Job dropdown from a capped first-100 Jobs list.
```

These are contract clarifications only. They do not change any Modules 0–7 business authority.

---

# Final decision

```text
Module 8 implementation boundary:
Recruiter read/composition layer + screening-results experience + final E2E qualification

New business truth:
NONE

New business-state tables:
NONE

New provider integration:
NONE

New worker:
NONE

New dashboard read APIs:
YES

New recruiter dashboard:
YES

New screening-results workspace:
YES

Final Task-1/Task-2 qualification:
YES
```

This plan is intentionally designed so Module 8 completes the product without weakening or duplicating the authority model already established by the existing system.

---

# STEP 2 repository-evidence correction — global version validator ownership

During STEP 2 qualification, the frozen `0.8.0 -> 0.9.0` backend version bump exposed one stale
structural check in `scripts/validate_module_6.py`: Module 6 asserted that the **global application
version** must remain exactly `0.8.0`.

Repository evidence shows that the application release version is not Module 6 business truth and
must advance as later modules are implemented. The smallest safe correction is therefore:

- keep all Module 6 behavioral/router/provider/worker assertions unchanged;
- remove only Module 6's exact ownership of global `pyproject.toml` / FastAPI version `0.8.0`;
- let Module 8's validator assert the new synchronized `0.9.0` release across `pyproject.toml`,
  `uv.lock`, and FastAPI metadata.

No Module 6 production source, endpoint, schema, provider contract, work-item behavior, or authority is
changed by this correction.
