# Module 3 — People Search & Contact Enrichment Implementation Plan

## 1. Objective

Module 3 owns Job-bound people sourcing and deliberate contact enrichment for Task 2.
It consumes one immutable approved Job definition, retains provider search evidence, enriches only
recruiter-selected evidence, and resolves enriched people through Module 2 Candidate Core.

The authority boundary is:

```text
Module 1 approved Job vN
        -> Module 3 search/enrichment truth
        -> Module 2 canonical Candidate identity/contact
        -> future Module 4 Candidate↔Job matching/shortlist truth
```

A provider search hit is never canonical Candidate truth and Apollo ordering is never a match score.

## 2. Existing dependencies

Module 3 reuses Module 0 database transactions, stable errors, `ProviderHttpClient`, `work_items`,
worker lease/UNKNOWN semantics, request IDs, and redacted logging. Repositories never commit and
external HTTP never executes inside a database transaction.

Module 3 consumes Module 1 only through an additive READY-lock binding seam and consumes Module 2
only through `CandidateService.resolve_external_candidate(ExternalCandidateObservation)`.

## 3. Database changes

One Supabase migration introduces exactly three workflow tables:

- `sourcing_runs`: one immutable Job-version-bound search execution/history record whose lifecycle
  fields mutate from `searching` to `completed|failed`;
- `sourcing_results`: normalized provider search evidence, never contact truth;
- `sourcing_enrichments`: one logical credit-aware enrichment per sourcing result.

Every run stores `job_id`, `definition_version`, provider-neutral criteria, exact provider query,
mapping version, result limit/count, provider total matches, attempts, and terminal failure metadata.
The composite FK targets `job_definition_versions(job_id, version)`.

The app search cap is 50 and truth is enforced twice: the Apollo adapter rejects a response larger
than requested and PostgreSQL checks `result_count <= result_limit`.

`provider_request_id` is PostgreSQL `BIGINT` because Apollo request IDs occupy the full signed
64-bit range and may be negative. All Module 3 tables enable RLS and revoke browser roles.

## 4. Domain models

Provider-neutral contracts include:

- `SourcingSearchCriteria` — frozen Job-derived intent plus explicitly unmapped requirements;
- `ProviderSearchQuery` — exact Apollo query persisted for historical replay;
- `ProviderSearchHit/Page` — contact-free sourcing evidence;
- `ProviderEnrichedPerson` — validated synchronous enriched person profile;
- `ProviderPhoneResult` — validated asynchronous phone result;
- `ProviderPollResult` — pending/completed/terminal poll semantics.

Public responses contain sourcing status and Candidate IDs only. Email and phone values are never
returned from sourcing responses; Candidate Core remains their authority.

## 5. Backend services

`SourcingService` owns search creation/retry/history and enrichment enqueue semantics.
`SourcingWebhookService` owns the single idempotent webhook/poll finalization authority.
`SourcingWorkHandlers` owns credit-aware enrichment execution and read-only poll recovery.

Starting a search atomically locks the Job, verifies `READY`, captures its approved version,
creates the run, commits, and only then calls Apollo.

## 6. Repository/database operations

`SourcingRepository` performs CRUD/locking for runs, results, and enrichments but never commits and
contains no Apollo or Candidate business decisions.

A successful search page is persisted atomically. Duplicate provider people and over-limit pages
fail before partial evidence is committed. `UNIQUE(sourcing_result_id)` ensures a recruiter cannot
create two logical enrichment operations for the same search evidence.

## 7. API endpoints

Public application endpoints are:

```text
POST /api/v1/jobs/{job_id}/sourcing-runs
GET  /api/v1/jobs/{job_id}/sourcing-runs
GET  /api/v1/sourcing-runs/{run_id}
POST /api/v1/sourcing-runs/{run_id}/retry
POST /api/v1/sourcing-results/{result_id}/enrich
GET  /api/v1/sourcing-enrichments/{enrichment_id}
POST /api/v1/webhooks/apollo/people-enrichment/{enrichment_id}/{signature}
```

New search is blocked for DRAFT Jobs. Historical runs remain readable after reopen.

## 8. External provider contract — Apollo

Apollo is isolated under `app/integrations/apollo`. Search uses People Search with explicit title,
personal-location, and exact supported seniority filters. `include_similar_titles=false`, page is 1,
and `per_page` is restricted by application input to 10, 25, or 50.

Required/preferred skills, minimum experience, unsupported seniorities, employment type, and work
arrangement remain visible as unmapped requirements rather than being silently translated into
provider filters with different semantics.

Search is contact-free. Contact enrichment uses the Apollo person ID returned by search, requests
asynchronous phone reveal, and validates the signed 64-bit recovery request ID.

## 9. State transitions

Search:

```text
SEARCHING -> COMPLETED
          -> FAILED
```

Zero results are `COMPLETED`, not failure. A retry uses the exact persisted provider query and Job
version; it never re-reads the latest mutable Job.

Enrichment:

```text
PENDING -> AWAITING_PHONE -> COMPLETED
        -> NOT_FOUND
        -> FAILED
        -> UNKNOWN
        -> CONFLICT
```

Candidate identity conflict never auto-merges. Existing enrichment state is idempotently returned
on repeated recruiter submission.

## 10. Frontend components

READY Job pages expose **Find people**. `/jobs/{jobId}/sourcing` shows current eligibility and
historical runs. `/sourcing/{runId}` shows the persisted criteria actually used, explicit unmapped
requirements, provider search evidence, and deliberate enrichment action.

The UI never labels Apollo order as fit, match score, or shortlist state. Actual contact PII is
viewed through Candidate detail only.

## 11. Exceptional cases

The implementation explicitly handles:

- DRAFT Job at new-search time;
- Job reopen racing with new downstream binding;
- zero search results;
- malformed, duplicate, or over-limit provider pages;
- provider authentication, rate limit, transient, transport, and schema errors;
- duplicate enrichment clicks;
- person-not-found enrichment;
- Candidate strong-identity conflict;
- asynchronous webhook duplication;
- webhook/poll race;
- missing/expired/unknown poll request ID;
- missing provider or webhook configuration;
- worker crash/expired lease during enrichment or polling.

## 12. Retry/idempotency

People Search is read-only/zero-credit and may make at most two attempts for safe transient
conditions. Short `Retry-After` may be honored synchronously; long rate limits become an explicit
failed run with retry metadata.

Enrichment can consume credits. Known-not-sent connect failures and provider 429 responses may use
the bounded work-item budget. Ambiguous timeout/5xx/invalid accepted responses become `UNKNOWN` and
are never automatically replayed. If the safe work budget is exhausted, both queue and domain state
converge to `FAILED`.

Polling is read-only. Apollo `result_pending` schedules a retry using the provider delay.
Webhook and polling share one finalizer and repeated callbacks are idempotent.

When Module 0 recovers a crashed RUNNING work item to `UNKNOWN`, an optional post-recovery hook
projects certainty into Module 3: credit-consuming enrichment becomes domain `UNKNOWN`; an unknown
read-only poll may enqueue one new recovery generation keyed by the UNKNOWN item ID.

## 13. Security/privacy

Apollo API key and callback-signing secret are backend-only. Callback URLs use HMAC-SHA256 over the
enrichment ID and constant-time verification. The configured callback base must use HTTPS.

Module 3 does not store raw provider payloads or duplicate contact PII. Logs use IDs/status/error
codes rather than provider payloads, emails, or phone values.

## 14. Tests

Required proof covers deterministic mapping, search result bounds, atomic READY binding, immutable
historical version binding, safe search retries, no-Candidate-from-search, enrichment dedupe,
provider adapter validation, signed 64-bit request IDs, Candidate Core resolution, fill-only
regression, uncertain enrichment `UNKNOWN`, bounded safe retry exhaustion, HMAC validation,
webhook idempotency, phone selection, polling semantics, queue/domain UNKNOWN reconciliation,
PostgreSQL constraints/RLS/concurrency, API reachability, frontend states, and Module 0/1/2
regression.

## 15. Acceptance criteria

Module 3 is acceptable only when:

- new sourcing is atomically bound to a currently READY approved Job version;
- raw search hits never create Candidates;
- exact provider mapping and unmapped requirements are persisted;
- result counts cannot exceed the requested limit in adapter, service, or DB truth;
- enrichment requires explicit recruiter action and is one logical operation per result;
- uncertain credit-consuming outcomes become `UNKNOWN` with no automatic replay;
- worker lease recovery cannot leave Module 3 indefinitely `PENDING`;
- webhook and poll converge through one idempotent finalizer;
- Candidate identity/contact mutation occurs only through Candidate Core;
- no matching, shortlist, or Hunar state appears in this module;
- Modules 0, 1, and 2 remain green.

## 16. Explicitly out of scope

Module 3 does not implement `job_candidates`, AI matching/ranking, shortlisting, applicant status,
Hunar/voice calls, screening answers, outreach lifecycle, bulk provider crawling, multi-provider
fallback, Apollo waterfall enrichment, automatic Candidate merge, or a raw-provider data warehouse.

## 17. Dependency impact on Module 4

Module 4 may consume the approved Job definition plus canonical Candidate IDs resolved by Module 3.
It owns the Candidate↔Job relationship, definition-version binding for matching, match score/reasons,
and shortlist workflow. It must not reinterpret Apollo result position as hiring truth and must not
re-run provider enrichment already owned by Module 3.

## Implementation corrections frozen after conformance audit

The implementation audit added bounded corrections without changing module ownership:

1. provider result limits are enforced at Apollo adapter, service defense, and PostgreSQL levels;
2. Module 0 stale-work `UNKNOWN` is reconciled into Module 3 according to operation certainty, so
   credit-consuming enrichment fails closed while read-only polling remains safely recoverable;
3. Apollo's current `has_direct_phone` string signals are normalized explicitly (`Yes`, `Maybe`,
   `No`) rather than treated as booleans only;
4. synchronous enrichment must return the selected Apollo person ID when it supplies an ID, and a
   single-person phone result must contain exactly one person before Candidate truth can change;
5. polling is a recovery observer, not the authoritative phone-delivery event: observer/configuration
   failures leave the enrichment `AWAITING_PHONE`, while only Apollo's semantic terminal request-ID
   result may terminally fail it;
6. invalid provider phone values are ignored, but a missing/broken phone-normalization runtime is not
   converted into false `COMPLETED` business truth;
7. failed persisted search runs expose their run ID to the UI so the recruiter can reach the exact
   historical run and its retry path rather than losing recovery reachability;
8. stale `SEARCHING` recovery uses a persisted `search_generation` token. A manual stale-search
   retry advances the generation, and late success/failure from an older in-flight read-only search
   is ignored so execution topology cannot overwrite newer authoritative run state.
