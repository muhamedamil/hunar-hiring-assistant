# Module 2 — Candidate Core Implementation Plan

## Implementation objective

Module 2 establishes one provider-neutral, global Candidate identity authority shared by both
assessment streams:

```text
Task 1 manual candidate ─┐
                         ├─> Candidate Core
Task 2 sourced candidate ┘
```

Candidate Core answers **who this person is in this application**. It does not own Job matching,
shortlisting, provider search/enrichment, outreach, or screening state.

## Frozen state authorities

- `candidates` owns one mutable current Candidate profile.
- `candidate_external_identities` owns immutable provider/person identity links.
- `revision` protects Candidate profile/identity mutations from stale writes.
- `email` and `phone_e164` are optional strong identifiers.
- `(provider, external_person_id)` is a strong external identifier.
- full name, title, company, and location are never sufficient for automatic identity merging.
- there is no Candidate business-status state machine in Module 2.
- there is no `job_id` on Candidate Core.

## Shared Task-1 / Task-2 contract

Task 1 can create Candidates manually through the public Candidate API. Task 2 will later translate
provider results into `ExternalCandidateObservation` and call
`CandidateService.resolve_external_candidate(...)`. Both paths converge on the same Candidate rows.

A valid Candidate may contain only a name. Email and phone are intentionally optional because
people-search providers can surface a person before contact enrichment completes.

## Identity resolution rules

Strong identity signals are:

1. `(provider, external_person_id)`;
2. case-insensitive canonical email;
3. canonical E.164 phone.

Resolution gathers all available strong signals before mutating state:

- zero matches -> create Candidate, then attach external identity when present;
- exactly one distinct Candidate -> resolve to that Candidate;
- all signals resolve to the same Candidate -> resolve idempotently;
- signals resolve to different Candidates -> fail closed with `CANDIDATE_IDENTITY_CONFLICT` and
  perform no mutation.

Manual create never silently merges. If email/phone already belongs to another Candidate it returns
`CANDIDATE_ALREADY_EXISTS` with only the existing Candidate ID.

## Canonical profile update policy

External observations may fill only currently-null canonical fields. They never overwrite populated
canonical profile values. This rule is deliberately source-agnostic, so no field-provenance subsystem
is needed in Module 2. Provider raw evidence belongs to the future sourcing/enrichment module.

An identical external observation must be idempotent and must not increment Candidate revision.
Attaching a new external identity or filling at least one missing canonical field increments revision.

## Contact normalization

- email is validated with Pydantic `EmailStr` / `email-validator`;
- email uniqueness is case-insensitive in PostgreSQL;
- phone input must include an explicit international country code;
- phone is normalized with `phonenumbers` to E.164 before persistence;
- the application never guesses a default phone region.

## Persistence design

### `candidates`

Current mutable truth:

- `id`
- `full_name`
- `current_title`
- `current_company`
- `location`
- `email`
- `phone_e164`
- `revision`
- `created_at`
- `updated_at`

Database constraints/indexes enforce:

- valid nonblank bounded profile strings;
- case-insensitive unique email when non-null;
- globally unique E.164 phone when non-null;
- non-negative revision.

### `candidate_external_identities`

Provider identity links:

- `id`
- `candidate_id`
- `provider`
- `external_person_id`
- `profile_url`
- `created_at`

`(provider, external_person_id)` is globally unique. No public mutation endpoint is exposed for this
table in Module 2. PostgreSQL also rejects `UPDATE` and `DELETE` on these rows so provider identity
links remain immutable even outside the application service path.

Both tables use the existing Supabase RLS/revoke pattern and remain inaccessible to browser
`anon`/`authenticated` roles.

## Transaction ownership

Module 0 rules remain unchanged:

- repositories never commit;
- services own transaction boundaries;
- mutable Candidate updates use `SELECT ... FOR UPDATE`;
- expected revision is checked while the row is locked;
- database uniqueness remains authoritative for concurrent identity races.

A known unique-constraint race in external Candidate resolution may perform one bounded database-only
re-resolution after rollback. That pass must complete the original logical operation: re-check all
strong identities, lock the resolved Candidate, fill still-missing canonical fields, and attach the
requested provider identity when it is not already present. This is not a generic retry and does not
repeat an external side effect.

## Public API

```text
POST  /api/v1/candidates
GET   /api/v1/candidates
GET   /api/v1/candidates/{candidate_id}
PATCH /api/v1/candidates/{candidate_id}
```

Candidate list responses intentionally expose only `has_email` / `has_phone`, not contact values.
Full contact details appear only on Candidate detail.

PATCH uses complete profile replacement plus `expected_revision`; it is not a deep JSON merge.

## Internal downstream API

`CandidateService.resolve_external_candidate(observation)` is the provider-neutral seam that future
Module 3 uses. Module 2 itself performs zero external HTTP requests and does not use `work_items`.

## Frontend scope

- `/candidates` — list/empty/error states and Add Candidate action;
- `/candidates/new` — manual Candidate creation;
- `/candidates/[candidateId]` — Candidate detail and revision-safe editing;
- AppShell navigation gains `Candidates` beside `Jobs`.

The frontend remains typed React state + TanStack Query with backend-authoritative validation. No new
form framework is introduced.

## PII hardening

Module 2 is the first PII-bearing module. The implementation must:

- create the SQLAlchemy engine with `hide_parameters=True`;
- redact structured-log keys containing `email` or `phone`;
- avoid logging Candidate request/profile payloads;
- return Candidate IDs, never conflicting contact values, in identity error details;
- keep DB/provider secrets backend-only;
- use synthetic Candidate data for unauthenticated public assessment demonstrations.

## Agentic-driven SDLC sequence

1. **Baseline evidence gate** — inspect latest repository, run current structural/backend tests, and
   repair only confirmed Module 0/1 qualification-document drift.
2. **Contract freeze** — commit this plan before Candidate business code.
3. **Schema/domain implementation** — migration, SQLAlchemy mappings, Pydantic contracts,
   normalization, domain errors.
4. **Persistence/service implementation** — repository primitives, transaction ownership, strong
   identity resolution, optimistic concurrency, fill-only provider semantics.
5. **API integration** — request-scoped service dependency and four bounded Candidate endpoints.
6. **Frontend workflow** — Candidate list/create/detail/edit with contact-minimized list projection.
7. **Qualification tests** — schemas/normalization, service identity equivalence classes, HTTP
   contracts, PostgreSQL uniqueness/concurrency/RLS, PII hardening, frontend behavior.
8. **Regression/blast-radius audit** — Module 0/1 state/retry/provider boundaries remain unchanged.
9. **Clean-artifact qualification** — structural validator + backend suite + available frontend
   checks on a fresh archive extraction before handoff.

## Coding-quality requirements

Every new Python source file must:

- start with a concise module docstring describing its responsibility;
- use PEP 8 naming and the repository's 100-character line limit;
- type all public functions/methods and meaningful private helpers;
- give public classes and non-obvious public functions concise docstrings;
- keep repository persistence, service business rules, router HTTP wiring, and schemas separate;
- avoid broad exception handling where a typed/domain error is possible;
- avoid hidden commits, hidden retries, and provider-specific vocabulary inside Candidate Core.

## Tests required before freeze

- normalization/schema unit tests;
- manual create/update/dedupe tests;
- every strong-identity resolution equivalence class;
- fill-only/idempotent external observation tests;
- Candidate API tests using standard Module 0 error envelopes;
- real PostgreSQL tests for email/phone/provider uniqueness, concurrent resolution, rollback safety,
  RLS/revokes, and PII hardening;
- frontend create/list/detail/edit/conflict/error tests;
- all existing Module 0 and Module 1 tests remain green;
- `ruff`, `mypy`, frontend lint/typecheck/tests/build, and `supabase db reset` pass locally.

## Explicitly out of scope

- Job ↔ Candidate relationship;
- match scoring / shortlisting;
- Apollo/PDL/Proxycurl/Coresignal clients;
- contact enrichment and provider webhooks;
- work-item orchestration for enrichment;
- Hunar / voice outreach / screening results;
- automatic Candidate merge framework;
- Candidate profile version history;
- multi-email / multi-phone contact subsystem;
- authentication/RBAC.

## Downstream guarantees

Module 3 may source/enrich people but must resolve them through Candidate Core instead of creating a
parallel Candidate store. Module 4 will own `job_candidates` and the Job/Candidate relationship.
Future outreach must snapshot the actual contact value used for historical truth instead of relying
forever on the mutable Candidate profile.
