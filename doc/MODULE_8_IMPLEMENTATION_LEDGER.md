# Hunar Hiring Assistant — Module 8 Implementation Ledger

## STEP 1 status

**Status:** COMPLETE / FROZEN FOR STEP 2

This ledger freezes the Module 8 implementation boundary before any Module 8 production backend or
frontend code is written. It is based on the actual authoritative repository supplied for this run,
not on assumptions from an older handoff archive.

- Authoritative baseline: `hunar-hiring-assistant-main (3)(2).zip`
- Baseline SHA-256: `6ed957c8d3cf6327bd003844c5b0d4397b6eabbb5fc192441c7a3f2cd0e9950d`
- Supplied Module 8 handoff: `MODULE_8_AGENT_IMPLEMENTATION_PLAN(1).md`
- Handoff SHA-256: `769ce72099a921298e9d491c8bb34318f4b5b24a884ac9fda3134de7076f5d1a`
- STEP 1 baseline backend package version: `0.8.0`
- STEP 1 baseline FastAPI application version: `0.8.0`
- Migration head: `20260907170000_module_7_call_results.sql` (unchanged through STEP 2)
- STEP 1 source files checked by Module 0 validator: 243
- Module 8 implementation present before this step: no
- Dashboard tables present before this step: no
- Dashboard API package/routes present before this step: no
- Dashboard frontend/screensing routes present before this step: no

STEP 1 changes are documentation only:

- `doc/MODULE_8_IMPLEMENTATION_LEDGER.md`
- `doc/MODULE_8_IMPLEMENTATION_PLAN.md`

No backend version, migration, runtime code, worker, provider integration, or frontend UI is changed
in STEP 1.

---

## 1. Repository discrepancies discovered during STEP 1

### D1 — handoff baseline filename is stale

The supplied handoff names `hunar-hiring-assistant-main (3)(1).zip`. The user explicitly supplied
and designated `hunar-hiring-assistant-main (3)(2).zip` as authoritative. All Module 8 work must use
`(3)(2)`.

**Correction:** update the Module 8 plan baseline only. No upstream implementation changes.

### D2 — frozen Module 7 validation document has a stale skipped-test count

`doc/MODULE_7_VALIDATION.md` says `302 passed, 46 skipped`, while an actual baseline run in this STEP
1 environment reports `302 passed, 49 skipped`. The additional skips are environment-gated
`phonenumbers`/PostgreSQL cases; there are zero failures.

**Correction:** record the executable result here. Do not rewrite the frozen Module 7 validation
document as part of Module 8 STEP 1.

### D3 — historical screening join must be outreach-mediated

The handoff's conceptual cross-domain diagram can be read as if a voice execution directly selects a
match. The repository does not have such a direct foreign key. The exact immutable historical path is:

```text
voice_call_executions.outreach_request_id
    -> outreach_requests.id
    -> outreach_requests.decision_match_id
    -> job_candidate_matches.id
    -> (job_candidate_matches.job_id, job_candidate_matches.definition_version)
    -> job_definition_versions(job_id, version)
```

`outreach_requests.job_candidate_id` must also agree with the selected match's `job_candidate_id`.

**Correction:** freeze this exact join. Never infer historical Job context from current `jobs`.

### D4 — dashboard question display needs a distinct “no answer row exists” state

Module 7's authoritative answer states are only:

- `answered`
- `no_clear_answer`
- `not_asked`

For MACHINE, UNKNOWN-human, unavailable, invalid, or other non-accepted results, Module 7 correctly
persists **no Candidate answer rows**. Mapping absence to `not_asked` would fabricate business truth.

**Correction:** `DashboardQuestionAnswer.answer_state` is nullable. `null` means no authoritative
Module 7 answer row exists for that question. `not_asked` remains reserved for an actual immutable
Module 7 answer row whose state is `not_asked`.

### D5 — backend version bump also requires lockfile synchronization

`apps/api/pyproject.toml`, `apps/api/app/main.py`, and the local project entry in
`apps/api/uv.lock` all currently carry `0.8.0`.

**Correction:** when STEP 2 moves the backend to `0.9.0`, update all three consistently. Do not bump
the version during STEP 1.

### D6 — Module 8 index migration is conditional, not mandatory

The handoff proposes `20260907194500_module_8_recruiter_dashboard_read_indexes.sql`, but also says
speculative indexes must not be retained. Existing indexes already cover several joins.

**Correction:** create that migration only if representative PostgreSQL `EXPLAIN` proves at least one
new read index is useful. If no candidate is justified, Module 8 adds no migration and the migration
head remains Module 7.

### D7 — existing AppShell test is a known frontend consumer

STEP 3 will change recruiter navigation. `apps/web/tests/app-shell.test.tsx` already asserts AppShell
behavior and therefore is an existing consumer that must be updated in addition to new dashboard
tests.

**Correction:** include it in the planned frontend test changes.

---

## 2. Frozen upstream authority map

| Business fact | Existing authority | Repository evidence | Module 8 rule |
| --- | --- | --- | --- |
| Current Job | `public.jobs` | `20260905190000_module_1_job_definition.sql`; `app/jobs/service.py` | Read only for current-job metrics and current review attention |
| Historical approved Job | `public.job_definition_versions` | immutable trigger + `(job_id, version)` uniqueness; `JobService.get_definition_version()` | Exact historical title/version for screening contexts |
| Candidate identity | `public.candidates` | `20260905234000_module_2_candidate_core.sql`; `CandidateService.get_summaries_by_ids()` | Current display name only; no historical-name claim |
| Provider identity link | `public.candidate_external_identities` | immutable provider/person link | Not used by dashboard projection or UI branching |
| Candidate↔Job pipeline unit | `public.job_candidates` | unique `(job_id, candidate_id)`; Module 4 comment | All pipeline state remains JobCandidate-scoped |
| Match assessment/history | `public.job_candidate_matches` | historical rows bind immutable definition version | Never recalculate score, evidence, analysis mode, or freshness |
| Recruiter shortlist decision | `job_candidates.shortlist_status` + `decision_match_id` | DB state constraint + `MatchingService.update_shortlist()` | Read only; no dashboard shortlist state |
| Frozen outreach context | `public.outreach_requests` | immutable trigger; decision-match FK; frozen questions/phone | Historical execution context only |
| Historical screening question | `outreach_requests.screening_questions_snapshot[*].id/prompt` | `OutreachService.get_result_context()` | Sole question text/UUID authority for screening detail |
| Voice submission certainty | `public.voice_call_executions.status` | Module 6 migration/comment; `VoiceCallRepository` | Preserve `queued/submitted/failed/unknown` exactly |
| Voice frozen execution input | `voice_call_executions.provider_payload_snapshot` | immutable-input trigger | Never expose or use as dashboard display truth |
| Terminal call/screening result | `public.voice_call_results` | one result per execution; terminal identity guards | Read only; result state takes display precedence |
| Screening answers | `public.voice_screening_answers` | immutable rows keyed to outreach question UUID | Read only; never remap against current Job questions |
| Work orchestration | `public.work_items` | Module 0 queue migration | Operational only; never a recruiter business-state source |

### Authority proof

Module 8 requires **zero new business truth**. Every requested recruiter field can be read from the
existing owners above. Therefore Module 8 is permitted to add only read/composition contracts and
recruiter presentation.

---

## 3. Frozen Module 8 boundary

Module 8 owns:

1. read-efficient composition of existing authoritative state;
2. display-only screening-state projection;
3. recruiter-safe dashboard/screening DTOs;
4. recruiter dashboard and screening-result pages in STEP 3;
5. final Task 1 / Task 2 qualification.

Module 8 does **not** own:

- Candidate mutation or lifecycle;
- Job mutation/versioning;
- Candidate↔Job mutation;
- match scoring/freshness;
- shortlist decisions;
- outreach preparation/readiness;
- call submission/retry/reconciliation;
- terminal result normalization;
- answer normalization/mapping;
- provider calls/webhooks;
- work-item lifecycle;
- hiring outcomes.

No Module 8 `POST`, `PUT`, `PATCH`, or `DELETE` endpoint is allowed.

---

## 4. Exact file ledger

### STEP 1 — created now

```text
doc/MODULE_8_IMPLEMENTATION_LEDGER.md
doc/MODULE_8_IMPLEMENTATION_PLAN.md
```

### STEP 2 — planned backend files

```text
apps/api/app/dashboard/__init__.py
apps/api/app/dashboard/dependencies.py
apps/api/app/dashboard/repository.py
apps/api/app/dashboard/router.py
apps/api/app/dashboard/schemas.py
apps/api/app/dashboard/service.py

apps/api/tests/test_dashboard_service.py
apps/api/tests/test_dashboard_router.py
apps/api/tests/test_dashboard_database.py

scripts/validate_module_8.py
doc/MODULE_8_VALIDATION.md
```

### STEP 2 — planned updates to existing files

```text
apps/api/app/main.py
apps/api/pyproject.toml
apps/api/uv.lock
README.md
doc/MODULE_8_IMPLEMENTATION_LEDGER.md
doc/MODULE_8_IMPLEMENTATION_PLAN.md
```

### STEP 2 — conditional database file

Create only if PostgreSQL qualification proves one or more candidate indexes useful:

```text
supabase/migrations/20260907194500_module_8_recruiter_dashboard_read_indexes.sql
```

Do not create a migration merely to make Module 8 appear to have a database phase.

### STEP 3 — planned frontend files

```text
apps/web/lib/dashboard/api.ts
apps/web/lib/dashboard/queries.ts
apps/web/lib/dashboard/types.ts

apps/web/components/dashboard/dashboard-overview.tsx
apps/web/components/dashboard/dashboard-metrics.tsx
apps/web/components/dashboard/attention-list.tsx
apps/web/components/dashboard/recent-screenings.tsx
apps/web/components/dashboard/screening-state-badge.tsx

apps/web/app/screenings/page.tsx
apps/web/app/screenings/[executionId]/page.tsx

apps/web/tests/dashboard.test.tsx
apps/web/tests/screenings-dashboard.test.tsx
```

### STEP 3 — planned frontend updates

```text
apps/web/app/page.tsx
apps/web/components/layout/app-shell.tsx
apps/web/tests/app-shell.test.tsx
README.md
doc/MODULE_8_IMPLEMENTATION_LEDGER.md
doc/MODULE_8_VALIDATION.md
```

### Explicitly forbidden new Module 8 files unless a later evidence-backed plan change is approved

```text
apps/api/app/dashboard/models.py
apps/api/app/dashboard/workers.py
apps/api/app/dashboard/provider.py
apps/api/app/dashboard/webhooks.py
```

No dashboard ORM entity exists.

---

## 5. Exact public read endpoints

### `GET /api/v1/dashboard/overview`

No query parameters in the initial contract.

Returns authoritative database aggregates, bounded attention items, and bounded recent screenings.

### `GET /api/v1/dashboard/screenings`

Query contract:

```text
job_id: UUID | None
state: DashboardScreeningState | None
interest: CandidateInterest | None
q: str | None                   # 1..100 after trim when supplied
limit: int = 20                 # 1..100
offset: int = 0                 # >= 0
```

`q` searches only:

- current `candidates.full_name`;
- exact historical `job_definition_versions.title` for that execution.

It must not search phone, email, provider identifiers, payloads, or work-item data.

### `GET /api/v1/dashboard/screenings/{execution_id}`

Returns one safe screening context or the repository's normal not-found error contract. It performs
no provider recovery and no work-item enqueue.

---

## 6. Exact public schema ledger

Existing bounded enums should be reused where they already express authoritative values:

- `VoiceCallExecutionStatus`
- `HunarCallStatus`
- `HunarLifecycleStatus`
- `HunarAnsweredBy`
- `ScreeningResultState`
- `ScreeningAnswerState`
- `ConversationOutcome`
- `CandidateInterest`

No Hunar request/response/webhook DTO is part of a dashboard response.

### `DashboardAttentionKind`

```text
review_candidate
dispatch_failed
submission_unknown
result_invalid
result_unavailable
```

Display-only; never persisted.

### `DashboardScreeningState`

```text
queued
awaiting_result
dispatch_failed
submission_unknown
result_available
result_unavailable
result_invalid
```

Display-only; never persisted.

### `DashboardJobMetrics`

```text
total: int >= 0
draft: int >= 0
ready: int >= 0
```

### `DashboardCandidateMetrics`

```text
total: int >= 0
```

### `DashboardPipelineMetrics`

```text
reviewing: int >= 0
shortlisted: int >= 0
not_selected: int >= 0
```

### `DashboardScreeningMetrics`

```text
total: int >= 0
queued: int >= 0
awaiting_result: int >= 0
dispatch_failed: int >= 0
submission_unknown: int >= 0
result_available: int >= 0
result_unavailable: int >= 0
result_invalid: int >= 0
interested: int >= 0
```

`interested` is a subset of available results and is excluded from mutually-exclusive state-sum
invariants.

### `DashboardAttentionItem`

```text
kind: DashboardAttentionKind
candidate_id: UUID
candidate_name: str
job_id: UUID
job_candidate_id: UUID
job_title: str
execution_id: UUID | None
outreach_request_id: UUID | None
occurred_at: datetime
```

For `review_candidate`, `job_title` is current `jobs.title` because this is current workflow state.
For execution/result attention, `job_title` is the exact historical definition title bound through
the outreach decision match.

### `DashboardScreeningSummary`

```text
execution_id: UUID
outreach_request_id: UUID
job_candidate_id: UUID
candidate_id: UUID
candidate_name: str                 # current Candidate display identity
job_id: UUID
job_title: str                      # exact historical definition title
job_definition_version: int >= 1
screening_state: DashboardScreeningState
submission_status: VoiceCallExecutionStatus
conversation_outcome: ConversationOutcome | None
candidate_interest: CandidateInterest | None
duration_seconds: float | None
observed_at: datetime | None
sort_at: datetime
```

No phone, email, candidate source, provider request ID, provider call ID, raw payload, recording URL,
or work-item data.

### `DashboardScreeningListResponse`

```text
items: list[DashboardScreeningSummary]
total: int >= 0
limit: int
offset: int
```

`total` always comes from a database count using the same filters as the item query.

### `DashboardQuestionAnswer`

```text
question_id: UUID                   # outreach question UUID
position: int                       # 1..10
prompt: str                         # exact frozen outreach prompt
answer_state: ScreeningAnswerState | None
answer_text: str | None
```

Semantics:

- `answered` -> authoritative Module 7 answer text may display;
- `no_clear_answer` -> answer text is null;
- `not_asked` -> answer text is null;
- `null` -> no accepted Module 7 Candidate answer row exists; do not relabel it as `not_asked`.

### `DashboardScreeningDetailResponse`

```text
execution_id: UUID
outreach_request_id: UUID
job_candidate_id: UUID
candidate_id: UUID
candidate_name: str
job_id: UUID
job_title: str
job_definition_version: int >= 1
screening_state: DashboardScreeningState
submission_status: VoiceCallExecutionStatus
provider_status: HunarCallStatus | None
lifecycle_status: HunarLifecycleStatus | None
answered_by: HunarAnsweredBy | None
conversation_outcome: ConversationOutcome | None
candidate_interest: CandidateInterest | None
duration_seconds: float | None
observed_at: datetime | None
recording_available: bool
notes: str | None
questions: list[DashboardQuestionAnswer]
```

The detail response intentionally omits phone/email, raw recording URL, provider payload, provider
request ID, provider call ID, webhook/signature data, work-item payload/error internals, and Candidate
origin.

### `DashboardOverviewResponse`

```text
generated_at: datetime
jobs: DashboardJobMetrics
candidates: DashboardCandidateMetrics
pipeline: DashboardPipelineMetrics
screenings: DashboardScreeningMetrics
needs_attention: list[DashboardAttentionItem]
recent_screenings: list[DashboardScreeningSummary]
```

Initial bounds:

- `needs_attention`: at most 20 rows;
- `recent_screenings`: at most 10 rows.

---

## 7. Repository query contracts

`DashboardRepository` is read-only SQL composition. It never commits and never invokes a service or
external provider.

Frozen operations:

```text
count_jobs_by_status()
count_candidates()
count_job_candidates_by_shortlist_status()
count_screening_states()
count_interested_screenings()
list_attention_candidates(limit)
list_attention_executions(limit)
list_recent_screenings(limit)
list_screenings(job_id, state, interest, q, limit, offset)
count_screenings(job_id, state, interest, q)
get_screening_context(execution_id)
list_screening_answers(result_id)
```

The service owns the read transaction boundary and DTO composition. Repositories never commit.

### No frontend N+1 composition

The web application must not call Job, Candidate, Match, Outreach, Voice Execution, and Result detail
endpoints separately per row. Dashboard list rows are composed in the backend once.

---

## 8. Exact screening joins

### Screening list / recent-screening base join

```sql
from public.voice_call_executions e
join public.outreach_requests o
  on o.id = e.outreach_request_id
join public.job_candidates jc
  on jc.id = o.job_candidate_id
join public.candidates c
  on c.id = jc.candidate_id
join public.job_candidate_matches m
  on m.id = o.decision_match_id
 and m.job_candidate_id = o.job_candidate_id
join public.job_definition_versions jdv
  on jdv.job_id = m.job_id
 and jdv.version = m.definition_version
left join public.voice_call_results r
  on r.voice_call_execution_id = e.id
```

No `jobs` join is used to obtain historical screening title/version.

### Screening detail

Use the same single-row context join. Read exact frozen question JSON from:

```text
o.screening_questions_snapshot
```

If a result exists, load its answer rows separately by:

```text
voice_screening_answers.voice_call_result_id = voice_call_results.id
order by voice_screening_answers.position asc
```

A separate answer query is intentional: joining answer rows into list/context SQL would multiply one
execution into many rows and create pagination/count risk.

### Overview independent authorities

```text
Job totals       -> jobs
Candidate total  -> candidates
Pipeline totals  -> job_candidates
Screening totals -> voice_call_executions LEFT JOIN voice_call_results
```

No overview metric is calculated from capped existing list APIs.

---

## 9. Historical-context rules

### Candidate display

Dashboard shows the current canonical Candidate display name from `candidates.full_name`.

It does not claim that name is the historical name at call time. Candidate edits may therefore alter
the displayed name while historical Job/question meaning remains fixed.

### Historical Job

For every execution-based screening row/detail:

```text
execution
 -> outreach request
 -> exact decision match
 -> match.definition_version
 -> immutable job_definition_versions snapshot
```

Never use `jobs.title` for execution historical context.

### Historical screening questions

Use only `outreach_requests.screening_questions_snapshot`.

Each snapshot question already has its own server-owned outreach UUID. Match answers by exact
`voice_screening_answers.outreach_question_id`, and verify position consistency. Never use current
`jobs.screening_questions` or `job_definition_versions.screening_questions` to remap answer IDs.

### Multiple outreaches

`job_candidates` is not a call-state record. One JobCandidate may have multiple immutable historical
outreach requests across changed recruiter-confirmed contexts. `voice_call_executions` is unique per
outreach request, so screening list identity is always `voice_call_executions.id`.

Do not collapse multiple historical executions to one JobCandidate row.

### Candidate origin

`job_candidates.created_source` exists as `manual|sourcing`, but Module 8 does not expose or branch on
it. Manual and Apollo-resolved Candidates flow through the same Candidate/JobCandidate projection.

---

## 10. Projection rules

### Screening-state precedence

```text
if voice_call_result exists:
    available   -> result_available
    unavailable -> result_unavailable
    invalid     -> result_invalid
else:
    queued      -> queued
    submitted   -> awaiting_result
    failed      -> dispatch_failed
    unknown     -> submission_unknown
```

This is display-only and never written to the database.

Example that must remain legal:

```text
voice_call_executions.status = unknown
voice_call_results.screening_result_state = available

screening_state   = result_available
submission_status = unknown
```

The dashboard does not rewrite Module 6 UNKNOWN.

### Screening metrics

- `total` = count of `voice_call_executions`.
- The seven display states are mutually exclusive and must sum to `total`.
- `interested` = count where result state is `available` and `candidate_interest='interested'`.
- `interested` is not added into the seven-state sum.

### Pipeline metrics

Count `job_candidates` by its authoritative `shortlist_status`. A Candidate with relations to several
Jobs contributes independently to each JobCandidate status.

### Needs Attention rules

Initial categories are frozen as follows:

1. `submission_unknown`
   - projected screening state is `submission_unknown` (therefore no result row exists);
   - source: `voice_call_executions.status='unknown'`.
2. `dispatch_failed`
   - projected screening state is `dispatch_failed`;
   - source: `voice_call_executions.status='failed'`.
3. `result_invalid`
   - result exists with `screening_result_state='invalid'`.
4. `result_unavailable`
   - result exists with `screening_result_state='unavailable'`.
5. `review_candidate`
   - `job_candidates.shortlist_status='reviewing'`.

Result precedence means an UNKNOWN execution that later has an available result is **not** listed as
`submission_unknown` attention, but detail still exposes `submission_status=unknown`.

Attention is not persisted. Do not use `work_items`.

Priority/order:

```text
submission_unknown
then dispatch_failed
then result_invalid
then result_unavailable
then review_candidate
```

Within each kind, newest `occurred_at` first, then stable UUID tie-break. Merge and cap at 20.

### Screening list filters

- `job_id`: exact Job identity on the JobCandidate/match context.
- `state`: derived with the same result-first precedence as response projection.
- `interest`: exact persisted `voice_call_results.candidate_interest`.
- `q`: case-insensitive substring over current Candidate full name OR historical definition title.

### Screening list ordering

Stable initial ordering:

```text
sort_at = coalesce(voice_call_results.observed_at, voice_call_executions.updated_at)
order by sort_at desc, voice_call_executions.id desc
```

`DashboardScreeningSummary.sort_at` is returned so frontend behavior can remain deterministic without
reconstructing ordering semantics.

### Human-answer safety

Even if malformed database data somehow contains answer rows, dashboard detail may expose answer
states/text only when:

```text
voice_call_results.screening_result_state = 'available'
and voice_call_results.lifecycle_status = 'COMPLETED'
and voice_call_results.answered_by = 'HUMAN'
```

Otherwise every frozen question is returned with `answer_state=null`, `answer_text=null` and no
Candidate answer is inferred.

Module 8 does not re-run Module 7 normalization.

### Recording safety

```text
recording_available = (voice_call_results.recording_url is not null)
```

Never return `recording_url`.

---

## 11. Database/index ledger

### Existing indexes/constraints that already support Module 8

- `ix_jobs_status_updated(status, updated_at desc)`
- `ix_candidates_updated(updated_at desc)`
- `ix_job_candidates_job_status_updated(job_id, shortlist_status, updated_at desc)`
- `ix_job_candidates_candidate(candidate_id)`
- `ix_candidate_matches_relation_created(job_candidate_id, created_at desc)`
- `uq_outreach_requests_exact_context(...)` with leading `job_candidate_id`
- `uq_voice_call_executions_outreach(outreach_request_id)`
- `uq_voice_call_results_execution(voice_call_execution_id)`
- `uq_voice_screening_answers_position(voice_call_result_id, position)`
- `uq_job_definition_versions(job_id, version)`

### Candidate indexes to qualify, not automatically retain

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

Qualification rule:

- use representative migrated PostgreSQL data;
- run `EXPLAIN (ANALYZE, BUFFERS)` or an equivalent representative plan check on final query shapes;
- retain only indexes that materially improve a real Module 8 query path;
- verify no RLS/ownership/security behavior changes;
- no trigram/search extension or materialized view in initial Module 8.

---

## 12. Provider isolation and security rules

Every dashboard GET must prove:

```text
0 Gemini calls
0 Apollo calls
0 Hunar calls
0 work-item creation
0 provider reconciliation
0 upstream mutations
```

Dashboard repository/service must not import provider clients or worker handlers.

Never expose:

- Candidate phone;
- Candidate email;
- outreach full phone snapshot;
- voice provider payload snapshot;
- raw recording URL;
- provider auth/API keys;
- provider request IDs;
- webhook signatures;
- work-item payload/errors;
- raw provider result/body;
- external Candidate provider identity.

The repository has no full recruiter auth/RBAC/multi-tenancy authority. Module 8 must not invent one.

---

## 13. Frontend artifact contract — planned only, no STEP 1 UI work

Recruiter navigation after STEP 3:

```text
Dashboard
Jobs
Candidates
Outreach
Screenings
```

No internal module numbers in normal recruiter UI.

Dashboard root `/` will consume only `GET /api/v1/dashboard/overview` for metrics/attention/recent
screenings. It must not calculate global totals from local list lengths.

`/screenings` uses server filters/pagination against `GET /api/v1/dashboard/screenings`.

`/screenings/[executionId]` uses only the dashboard detail GET for recruiter-safe screening context.

Frontend may poll local dashboard APIs according to the final plan; it never polls Hunar directly.

No frontend/dashboard implementation begins until STEP 2 backend qualification passes.

---

## 14. Test and qualification matrix

### STEP 1 gates

- Inspect authoritative `(3)(2)` repository: PASS
- Confirm backend version `0.8.0`: PASS
- Confirm migration head `20260907170000_module_7_call_results.sql`: PASS
- Confirm no existing Module 8/dashboard implementation: PASS
- Validate frozen authorities Modules 1–7 from code/migrations: PASS
- Module 0 validator: PASS
- Module 1 validator: PASS
- Module 2 validator: PASS
- Module 3 validator: PASS
- Module 4 validator: PASS
- Module 5 validator: PASS
- Module 6 validator: PASS
- Module 7 validator: PASS
- Full backend pytest baseline: `302 passed, 49 skipped, 0 failed`: PASS for available environment
- Documentation-only blast-radius check: pending final STEP 1 file diff, then freeze

### STEP 2 backend tests to implement

`apps/api/tests/test_dashboard_service.py` must cover:

- exact screening-state precedence for all execution/result states;
- UNKNOWN + available result preserves `submission_status=unknown`;
- QUEUED + available result race preserves queued execution truth while display is result available;
- current Candidate name + historical Job title/version;
- current Job mutation cannot rewrite historical screening role;
- frozen outreach question prompts map by exact outreach UUID;
- MACHINE/UNKNOWN-human/non-completed results expose zero Candidate answer truth;
- `not_asked` remains distinct from missing answer row;
- multiple JobCandidate relations for one Candidate remain independent;
- multiple historical outreaches/executions remain independent;
- attention projection rules and precedence;
- interested is a subset metric, not state arithmetic;
- zero external/provider/work-item side effects.

`apps/api/tests/test_dashboard_router.py` must cover:

- overview response contract;
- screening list filters;
- `q` validation and trim;
- limit/offset validation;
- authoritative `total` independent of page size;
- detail found/not-found behavior;
- no unsafe fields in serialized responses;
- no mutation routes under `/api/v1/dashboard`.

`apps/api/tests/test_dashboard_database.py` must cover using disposable migrated PostgreSQL:

- >100 Jobs authoritative totals;
- >100 Candidates authoritative totals;
- >100 executions authoritative totals/pagination;
- one execution = one list row;
- multiple answer rows do not duplicate list rows;
- historical outreaches do not collapse;
- exact historical definition join;
- deterministic sort/tie-break;
- count query uses identical filters to item query;
- answer UUID/position mapping;
- read-index existence only if justified;
- representative query plan qualification.

`scripts/validate_module_8.py` must structurally prove at minimum:

- dashboard has no ORM model/table;
- only the three allowed GET routes exist;
- dashboard code imports no Gemini/Apollo/Hunar client or worker handler;
- no `work_items` query in dashboard package;
- no current Job question source in screening-detail mapping;
- no raw recording/payload/phone/email field in public dashboard schemas;
- version synchronization when STEP 2 bumps to `0.9.0`;
- required tests/docs are present.

### STEP 3 frontend tests to implement/update

- `apps/web/tests/dashboard.test.tsx`
- `apps/web/tests/screenings-dashboard.test.tsx`
- update `apps/web/tests/app-shell.test.tsx`

Coverage:

- empty state;
- authoritative metric rendering;
- attention categories/routes;
- recent screening rows;
- screening filters and server pagination;
- historical title/version and frozen questions;
- answered / no clear answer / not asked / no-answer-row distinction;
- MACHINE/UNKNOWN-human safe display;
- invalid result safe display;
- UNKNOWN submission + available result;
- no unsafe retry/reconcile action in dashboard;
- recruiter navigation/product language;
- no internal module-number copy.

### Regression gates after implementation

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

cd apps/api
ruff check .
mypy app
python -m pytest -q

# where available
supabase db reset
TEST_DATABASE_URL=<disposable migrated PostgreSQL URL> python -m pytest -q

cd ../..
npm run web:lint
npm run web:typecheck
npm run web:test
npm run web:build
```

---

## 15. Frozen non-goals

Do not implement in Module 8:

- authentication/RBAC/multi-tenancy/org accounts;
- recruiter/tenant/org columns local to dashboard;
- Candidate pipeline state machine;
- global Candidate stage;
- hiring result/accept/reject decision state;
- automatic acceptance/rejection;
- AI recruiter recommendations;
- new/changed matching score or match freshness;
- current-Job remapping of historical screening context;
- current-Job remapping of screening questions;
- Candidate-source-specific dashboard behavior;
- Apollo calls from dashboard;
- Hunar calls/polling/reconciliation from dashboard;
- Gemini calls from dashboard;
- voice-call creation or redial from dashboard;
- worker operations dashboard;
- provider payload explorer;
- recording playback/download;
- transcription or LLM transcript analysis;
- analytics warehouse/materialized BI layer;
- persisted attention state;
- persisted dashboard state;
- persisted screening-reviewed state;
- decorative chart suite.

Any future recruiter-owned fact such as `screening_reviewed`, `decision_made`, or
`next_interview_scheduled` requires a separate domain design rather than being hidden in projection
code.

---

## 16. Modules 0–7 invariant cross-check

### Module 0 — work queue

- Dashboard does not read `work_items` as business truth.
- Dashboard GETs create no work.
- No worker or queue behavior changes.

**Result:** preserved.

### Module 1 — Job definition

- Current Job metrics read `jobs` only.
- Historical screening title/version uses immutable `job_definition_versions` selected through the
  exact decision match.
- Current Job questions never remap historical screening answers.

**Result:** preserved.

### Module 2 — Candidate Core

- Current canonical Candidate name is display identity.
- No duplicate dashboard Candidate table/profile.
- Email/phone/provider identity are not exposed by dashboard.

**Result:** preserved.

### Module 3 — sourcing/enrichment

- Dashboard does not query or call Apollo for Candidate origin behavior.
- `created_source` is ignored as a downstream branch.
- Sourcing evidence remains upstream matching provenance only.

**Result:** preserved.

### Module 4 — Candidate↔Job matching/shortlist

- `job_candidates` remains the pipeline unit.
- Match rows are never recomputed by dashboard.
- `shortlist_status`/`decision_match_id` remain sole shortlist truth.
- One Candidate may appear differently across Jobs.

**Result:** preserved.

### Module 5 — Outreach

- Historical execution context is `outreach_requests`.
- Frozen question snapshot is sole screening-question display/mapping authority.
- Dashboard never exposes frozen full phone.
- Multiple historical outreach contexts are not collapsed.

**Result:** preserved.

### Module 6 — voice execution

- Execution status remains independent submission certainty.
- UNKNOWN is never rewritten by a result.
- Dashboard provides no retry/replay/redial action.
- Provider payload/request correlation remains backend-only.

**Result:** preserved.

### Module 7 — call result/answers

- Result state controls result-first display projection without mutating Module 6.
- Only accepted HUMAN/available answers display as Candidate answers.
- MACHINE/UNKNOWN-human cannot become Candidate answers.
- Exact outreach question UUIDs remain answer keys.
- Raw recording URL remains backend-only.

**Result:** preserved.

---

## 17. STEP 1 decision

All required STEP 1 questions are resolved from repository evidence:

- business-fact owners: resolved;
- new files: frozen;
- endpoints: frozen;
- public schemas: frozen;
- joins: frozen;
- historical/current display rules: frozen;
- screening projection: frozen;
- multiple outreach handling: frozen;
- UNKNOWN preservation: frozen;
- human-only answer safety: frozen;
- provider isolation: frozen;
- unsafe fields: frozen;
- index candidates: frozen as conditional;
- test matrix: frozen;
- non-goals: frozen.

**STEP 2 decision: GO.**

Reason: the planned Module 8 boundary is a read/composition layer over existing owners. No planned
contract requires a second Candidate, Job, pipeline, shortlist, match, outreach, execution, result,
answer, or worker authority. STEP 2 may begin with backend projection implementation only; frontend
work remains blocked until STEP 2 qualification passes.

---

## 18. STEP 2 qualification-patch update

**Implementation status:** backend read projection implemented; local/external qualification remains required before STEP 3.

Implemented exactly the frozen backend boundary:

- `apps/api/app/dashboard/` contains only `__init__.py`, `dependencies.py`, `repository.py`,
  `router.py`, `schemas.py`, and `service.py`;
- exactly three dashboard GET endpoints are wired;
- one shared `dashboard_screening_state_expression()` owns result-first display semantics;
- `count_interested_screenings()` remains independent from the seven mutually-exclusive states;
- screening list/count/recent/attention all use the same state projection and historical join;
- screening detail uses `outreach_requests.screening_questions_snapshot` and exact Module 7 answer UUIDs;
- `answer_state=null` remains distinct from authoritative `not_asked`;
- Module 6 `unknown` remains exposed independently as `submission_status` even when a Module 7 result
  drives display state;
- no dashboard model/table, worker, provider integration, webhook, mutation endpoint, or frontend UI
  was added;
- no Module 8 migration was added because no representative PostgreSQL `EXPLAIN` evidence has yet
  justified a new read index.

### Evidence-backed deviation: Module 6 structural validator version ownership

After the global backend version moved from `0.8.0` to the frozen Module 8 target `0.9.0`,
`scripts/validate_module_6.py` failed only because it asserted the whole application's version was
exactly `0.8.0`. Module 6 does not own the global release version.

The validator was therefore narrowed to continue asserting Module 6 router/behavior wiring without
asserting a frozen global application version. No Module 6 production source, schema, endpoint,
worker, provider contract, or business authority changed.

### Qualification state

The qualification patch includes:

- focused service tests;
- router/validation/privacy tests;
- PostgreSQL compilation tests;
- disposable PostgreSQL scale/history/pagination/race tests gated by `TEST_DATABASE_URL`;
- representative `EXPLAIN (ANALYZE, BUFFERS)` output in the disposable PostgreSQL test;
- `scripts/validate_module_8.py` structural authority/security validation.

STEP 3 remains blocked until the full STEP 2 gate is executed successfully in an environment with
Ruff, mypy, and disposable migrated PostgreSQL available.


---

## 19. STEP 2 patch cross-verification update

This qualification patch was re-audited against the authoritative `(3)(2)` archive and the frozen
STEP 2 contract before regeneration. Contract-source hashes used for this audit:

```text
authoritative baseline ZIP
6ed957c8d3cf6327bd003844c5b0d4397b6eabbb5fc192441c7a3f2cd0e9950d

MODULE_8_IMPLEMENTATION_PLAN_FINAL(2).md
749cf3ccda3e5f182b1867aedc30702eed4db5e4a93a1d7ebf9d6dce7849944e

STEP 1 frozen MODULE_8_IMPLEMENTATION_LEDGER.md
45076c36d5fc6c76ad4cbf4a09548fba7ad994439cfa7931dfad166e04e9f6dc
```

Cross-verification found **no upstream business-authority drift and no need to redesign the Module 8
read projection**. The production dashboard package remains within the frozen repository/service
boundary. Corrections made during this audit are qualification/shape corrections only:

- fixed application import ordering so the new dashboard router wiring conforms to the frozen Ruff
  import-order gate;
- expanded disposable PostgreSQL qualification to prove two historical outreaches for one
  JobCandidate remain two execution rows;
- added multiple Module 7 answer rows so list pagination proves answers cannot multiply execution
  rows;
- upgraded the historical mutation scenario to a real immutable Job definition v1 -> v2 transition
  with changed current title/questions while the old screening remains bound to v1 and frozen outreach
  questions;
- explicitly qualifies both QUEUED+available-result and UNKNOWN+available-result races without
  rewriting Module 6 submission truth;
- proves UNKNOWN+available is not retained as stale submission attention;
- proves `recent_screenings` is exactly the latest 10 execution rows under frozen `sort_at` ordering
  and can contain unresolved executions;
- recursively scans all three dashboard response shapes for forbidden phone/email/provider/work-item
  fields rather than checking detail top-level keys only;
- strengthens `validate_module_8.py` to enforce exact three-GET shape, canonical state reuse, search
  columns, historical join integrity, answer-row isolation from list projection, and absence of direct
  network/provider/worker dependencies.

No Module 8 migration, frontend artifact, provider integration, worker, business-state table, or
Modules 0–7 production change was introduced by this cross-verification. The only pre-existing
Module 0–7 file modified by STEP 2 remains `scripts/validate_module_6.py`, solely to remove stale
ownership of the global application release version; its production Module 6 invariants are unchanged.

Current STEP 2 code version is `0.9.0`; migration head remains
`20260907170000_module_7_call_results.sql`. STEP 3 remains blocked pending real Ruff, mypy, and
disposable PostgreSQL/EXPLAIN qualification on the final patch-applied tree.
