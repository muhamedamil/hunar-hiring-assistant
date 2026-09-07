# Module 6 — Hunar Voice AI Integration — Low-Level Implementation Plan

**Authoritative repository baseline:** `hunar-hiring-assistant-main (2)(1).zip`
**Current implemented state:** Modules 0–5 complete; Module 6 not yet implemented
**Current backend version:** `0.6.0` (through Module 5)
**Target backend version after Module 6:** `0.7.0`
**Provider contract:** Hunar Voice Agents External API v1
**Provider docs verified:** 2026-09-07
**Status:** FINAL / CROSS-VERIFIED / READY FOR IMPLEMENTATION

## Source-of-truth boundary

This plan was reconciled against both:

1. the actual latest repository implementation, especially Module 0 durable work semantics and
   `OutreachService.lock_dispatchable_outreach(...)`; and
2. Hunar's official external API documentation and OpenAPI schema:
   - `https://api.voice.hunar.ai/docs/external/`
   - `https://api.voice.hunar.ai/docs/external/openapi.json`

Repository truth and provider truth must remain separate. If either changes during implementation,
re-audit the affected contract before changing the design.

## Cross-verification corrections applied before freeze

The following corrections are already incorporated into this final plan:

- Module 6 does **not** create/update a Hunar agent per Candidate. Hunar agents are reusable,
  calls require an `agent_id`, and the external docs expose create/update but no activation API.
  Runtime uses pre-provisioned ACTIVE agents only.
- Agent contract preflight happens once before durable execution creation and again immediately
  before `POST /calls/`. The first prevents a bad deployment configuration from creating an
  unusable one-per-outreach execution; the second catches remote agent drift before the side effect.
- The earlier `dispatch_generation` idea is removed. Existing Module 0 active work-item dedupe plus
  execution row locking is sufficient for automatic and explicit safe retries.
- `UNKNOWN` may retain `provider_call_id` and/or `provider_initial_status` when those values were
  observed before the response became semantically uncertain. Only `SUBMITTED` requires them.
- Hunar's docs do not list HTTP `429` in the documented call status-code table. The existing shared
  transport still handles a received 429 defensively as an explicit rejection, but Module 6 does
  not treat 429 as a Hunar-documented guarantee.
- `request_id` is correlation only. Hunar documents no request-id idempotency guarantee and the
  calls list API has no `request_id` filter. It must never be used to justify replaying UNKNOWN work.
- Hunar provider automatic redial is explicitly disabled with `retry_config={0,0}` so the
  application, not an inherited organization default, controls whether another call is attempted.
- Module 6 may optionally include only a configured `call_summary_callback_url`. It implements no
  webhook handler. Module 7 owns signed webhook ingestion, terminal convergence, results and
  recovery.
- The English agent contract is versioned and immutable in code. Future languages require their own
  human-reviewed contract version, ACTIVE agent ID and live qualification; no runtime translation or
  language inference is allowed.

---

## 1. Objective

Implement the real outbound voice-screening execution boundary after Module 5.

The authoritative application flow is:

```text
Task 1 manual Candidate ──┐
                          │
Task 2 Apollo Candidate ──┤
                          ↓
                 Module 4 job_candidate
                 current shortlist decision
                          ↓
                 Module 5 outreach_request
             exact phone + exact questions
                          ↓
                      Module 6
                 Hunar call execution
                          ↓
                      Module 7
              events/results/recovery later
```

Task 1 and Task 2 have already converged before Module 6. Module 6 must never branch on Candidate
origin.

Module 6 answers exactly:

> Has this exact Module 5 outreach intent been durably submitted to Hunar, which configured agent
> contract was used, what provider call identity was returned, and is the submission outcome known,
> failed, or uncertain?

Module 6 owns:

- one durable voice-call execution per immutable Module 5 outreach request;
- the exact provider request payload frozen before the side effect;
- the configured Hunar agent/language/timezone used for that execution;
- durable queueing of the external side effect;
- provider submission certainty: `queued | submitted | failed | unknown`;
- the provider call ID and initial provider status when observed;
- safe retry classification for call submission.

Module 6 does **not** own ongoing call lifecycle, screening answers, recording/result truth, webhook
convergence, or call-result recovery. Those belong to Module 7.

---

## 2. Existing dependencies

### Module 0 — Application Foundation

Reuse without redesign:

- `ProviderHttpClient` with zero automatic HTTP retries;
- `ProviderAuthenticationError`, `ProviderPermanentError`, `ProviderTransientError`,
  `ProviderRateLimitError`, `ProviderTransportError`, `ProviderInvalidResponseError`;
- `work_items`, `WorkItemService`, `WorkerRunner`, `WorkHandlerRegistry`;
- `RetryableWorkError`, `PermanentWorkError`, `AmbiguousWorkError`;
- active work-item dedupe and `UNKNOWN` semantics;
- service-owned transactions and repository-no-commit convention;
- standard API errors, request IDs, logging/redaction and migration-only schema authority.

A Hunar call is a real external side effect, so Module 6 **must** use durable work items.

Do not change generic Module 0 UNKNOWN semantics.

### Module 1 — Job & Screening Definition

Use the exact immutable definition already bound by Module 5/Module 4:

```python
JobService.get_definition_version(job_id, definition_version)
```

Module 6 may use the approved Job snapshot only to construct compact role context.

Do **not** use Module 1 screening questions for the call. The call must use Module 5's frozen
recruiter-confirmed screening snapshot.

### Module 2 — Candidate Core

Use existing Candidate read functionality only to obtain the Candidate display name required by
Hunar's `callee_name` request field.

The phone number must come exclusively from `OutreachDispatchSnapshot.phone_e164`.

Do not add another contact authority or re-select the current phone independently.

### Module 3 — People Search & Contact Enrichment

No direct dependency.

Do not send Apollo IDs, sourcing origin, enrichment priority or provider evidence to Hunar.

### Module 4 — Candidate ↔ Job Matching & Shortlisting

No new direct decision authority.

Matching/shortlist eligibility is already revalidated through Module 5.

Do not inspect match score to decide whether a call may be created.

### Module 5 — Outreach

This is Module 6's mandatory upstream boundary:

```python
OutreachService.lock_dispatchable_outreach(
    outreach_request_id,
) -> OutreachDispatchSnapshot
```

The actual current DTO contains:

```text
outreach_request_id
job_candidate_id
job_id
candidate_id
decision_match_id
definition_version
phone_e164
screening_questions[]
```

`lock_dispatchable_outreach()` already revalidates current shortlist/match/Job/contact truth before
returning the frozen phone and screening context.

Module 6 must not re-read current Job screening defaults, choose another phone, or re-decide
shortlist eligibility.

---

## 3. Database changes

Add the next migration after current head `20260906213000_module_5_outreach.sql`.

Suggested filename:

```text
supabase/migrations/20260907113000_module_6_hunar_voice_execution.sql
```

Create exactly one new Module 6 business table:

```text
public.voice_call_executions
```

### Columns

```text
id uuid primary key

outreach_request_id uuid not null unique

status text not null
    queued
    submitted
    failed
    unknown

agent_id uuid not null
language text not null
timezone text not null
agent_contract_version text not null

provider_request_id varchar(64) not null unique
provider_call_id uuid null unique
provider_initial_status text null

provider_payload_snapshot jsonb not null

failure_code text null
submitted_at timestamptz null
created_at timestamptz not null default now()
updated_at timestamptz not null default now()
```

### Foreign key

```text
outreach_request_id
    -> public.outreach_requests(id)
```

One immutable outreach request may have at most one Module 6 execution row.

### Required checks

Persisted status:

```text
status in ('queued', 'submitted', 'failed', 'unknown')
```

Provider request ID:

```text
1..64 characters
only [A-Za-z0-9_.-]
```

When non-null, `provider_initial_status` must be one of Hunar's documented `CallStatus` values.

Language must be one of Hunar's documented enum values:

```text
ENGLISH
HINDI
TAMIL
TELUGU
KANNADA
MARATHI
MALAYALAM
GUJARATI
BENGALI
TURKISH
ARABIC
SPANISH
```

Timezone must use Hunar's currently documented supported values. Mirror the OpenAPI `Timezone` enum
in application code and DB qualification tests. Do not accept arbitrary IANA zones.

Submission invariants:

```text
status = submitted
    => provider_call_id is not null
       provider_initial_status is not null
       submitted_at is not null

status = queued
    => provider_call_id is null
       submitted_at is null

status = failed
    => provider_call_id is null
       submitted_at is null

status = unknown
    => provider_call_id may be null or non-null
       provider_initial_status may be null or non-null
       submitted_at remains null
```

`UNKNOWN` intentionally allows a provider call ID if the response exposed a valid call identity but
some other required response evidence was inconsistent or persistence later became uncertain.

### Input immutability

Add a trigger that rejects changes to execution input columns after insert:

```text
outreach_request_id
agent_id
language
timezone
agent_contract_version
provider_request_id
provider_payload_snapshot
```

The following operational fields may change through guarded service/repository transitions:

```text
status
provider_call_id
provider_initial_status
failure_code
submitted_at
updated_at
```

Enable RLS and revoke direct `anon` / `authenticated` table access, following existing migrations.

Do not add call-result, transcript, recording or webhook-event tables in Module 6.

---

## 4. Domain models

Create the Module 6 domain package:

```text
apps/api/app/voice_calls/
    __init__.py
    models.py
    schemas.py
    repository.py
    service.py
    workers.py
    errors.py
    dependencies.py
    router.py
    agent_contract.py
```

Complete the provider integration package:

```text
apps/api/app/integrations/hunar/
    __init__.py
    client.py
    schemas.py
    errors.py
```

### `VoiceCallExecutionStatus`

```python
class VoiceCallExecutionStatus(StrEnum):
    QUEUED = "queued"
    SUBMITTED = "submitted"
    FAILED = "failed"
    UNKNOWN = "unknown"
```

### Hunar enums

Mirror the documented provider enums explicitly:

- `HunarLanguage`
- `HunarTimezone`
- `HunarVoicePersona`
- `HunarAgentStatus`
- `HunarCallStatus`

Do not use untyped strings for provider contracts.

### Agent contract

Define immutable versioned behavior contracts in `agent_contract.py`.

Initial contract:

```text
contract_version = hunar_voice_screening_en_v1
language         = ENGLISH
voice_persona    = NEHA
persona_name     = Maya
required custom variables:
    job_role
    role_context
    screening_plan
```

Future versions must be added as new immutable contract definitions. Do not silently change the
meaning of `hunar_voice_screening_en_v1` after executions have referenced it.

### Provider DTOs

Define strict Pydantic DTOs for:

- Hunar agent detail response;
- call-create command;
- callback config;
- retry config;
- call-create response;
- safe optional call-ID salvage from malformed successful responses.

`custom_data` is `dict[str, str]`, matching the current OpenAPI schema.

### Public Module 6 DTOs

At minimum:

```text
VoiceScreeningOptionsResponse
VoiceCallExecutionCreateRequest
VoiceCallExecutionResponse
```

Public execution responses must not expose full phone or the raw provider payload snapshot.

---

## 5. Backend services

### `HunarVoiceProvider`

Implement only the runtime provider operations Module 6 needs:

```python
get_agent(agent_id: UUID) -> HunarAgentDetail
create_call(command: HunarCallCreateCommand) -> HunarCallCreateResponse
```

Do not expose runtime `create_agent()` / `update_agent()` methods in the production integration
adapter. Agent provisioning is an operational prerequisite, not per-Candidate application behavior.

Use `ProviderHttpClient` and `X-API-Key` authentication.

### `VoiceCallService`

Implement:

```python
get_options()
create_execution(outreach_request_id, *, language, timezone)
get_execution(execution_id)
get_execution_for_outreach(outreach_request_id)
retry_failed_execution(execution_id)
```

### Agent selection

Runtime supported languages are the intersection of:

1. a version-controlled implemented behavior contract; and
2. a configured Hunar ACTIVE-agent ID for that language.

Initial implementation exposes only `ENGLISH`.

Do not expose every language merely because Hunar supports it.

### Start execution flow

`create_execution()` must follow this order:

```text
1. Validate requested language/timezone against Module 6 enums and configuration.

2. Resolve the configured agent binding + immutable contract version.

3. Perform safe Hunar GET /agents/{id}/ preflight outside any DB transaction.

4. Validate the remote agent against the expected contract.
   If unavailable/not ACTIVE/drifted, create no execution row.

5. Open one DB transaction.

6. Call Module 5 lock_dispatchable_outreach(outreach_request_id).

7. Read Candidate display name from existing Candidate Core read functionality.

8. Read exact immutable Job definition using the snapshot's job_id + definition_version.

9. Deterministically build compact role_context.

10. Deterministically build ordered screening_plan from Module 5 screening questions.

11. Generate application execution UUID.

12. Build provider_request_id = "hha-" + execution_uuid.hex.

13. Build exact Hunar provider payload snapshot:
      agent_id
      callee_name
      mobile_number
      custom_data
      request_id
      timezone
      retry_config {0,0}
      optional callback_config only when configured

14. Insert voice_call_executions(status=queued).

15. Enqueue one work item in the same transaction.

16. Commit.
```

No provider HTTP call may occur inside the DB transaction.

### Concurrent/repeated creation

`UNIQUE(outreach_request_id)` is the final database authority.

The service/repository must use the repository's established nested-transaction uniqueness-race
pattern so concurrent `Start voice screening` actions return the same existing execution instead of
surfacing a raw integrity failure.

Do not enqueue a second active work item for the same execution.

### Deterministic role context

Build only from the exact immutable Job version fields that actually exist:

```text
Role title
Seniority when configured
Locations when configured
Minimum experience when configured
Employment type when configured
Work arrangement when configured
Required skills when configured
Preferred skills when configured
```

Use concise natural text.

Do not send or invent:

```text
salary
benefits
company facts not present in the Job model
match score
match reasons
Apollo evidence
Candidate source
```

### Deterministic screening plan

Use only Module 5 `screening_questions`, in exact frozen order.

For each question include compact metadata:

```text
Question N
Key
Answer type
Required yes/no
Options when applicable
Prompt
```

The metadata guides the voice agent but should not be spoken mechanically.

### Retry failed execution

`retry_failed_execution()` uses two short DB phases around one read-only provider preflight. Never
hold a database transaction or row lock across the Hunar GET.

```text
Phase A — short DB read
1. Read the execution and require status == failed.
2. Capture its immutable agent ID/contract version needed for preflight.
3. End the transaction.

Provider preflight — no DB transaction
4. GET the frozen Hunar agent and verify the exact frozen contract is currently ACTIVE.

Phase B — short DB mutation
5. Re-lock the execution and require it is still failed.
6. Revalidate the original Module 5 outreach through lock_dispatchable_outreach().
7. Reuse the exact immutable provider_payload_snapshot and provider_request_id.
8. Set execution back to queued, clear terminal failure fields and enqueue one active work item.
9. Commit.
```

Do not change the frozen agent ID, language, timezone, role context, phone, Candidate name or screening
context during retry.

`UNKNOWN` is never retryable through the normal endpoint.

### `VoiceCallWorkHandlers.handle_dispatch()`

The durable worker owns the actual side-effect boundary. Implement the handler in this exact topology:

```text
1. Short DB transaction:
   - load execution by work-item entity_id;
   - if execution is no longer queued, return idempotently;
   - call Module 5 lock_dispatchable_outreach() for the execution's outreach request;
   - if no longer dispatchable, mark execution failed with OUTREACH_NOT_DISPATCHABLE and stop;
   - copy the frozen execution inputs required for provider work;
   - end the transaction.

2. Read-only Hunar preflight outside DB transaction:
   - GET frozen agent_id;
   - validate ACTIVE + exact agent contract;
   - classify read-only transient failures as safely retryable;
   - contract/permanent configuration failures become FAILED.

3. Re-check no local state mutation is required before the side effect.
   The frozen payload is authoritative for this execution.

4. POST /calls/ outside every DB transaction using provider_payload_snapshot exactly.

5. Classify provider outcome:
   - known accepted + valid response -> continue;
   - known rejection -> FAILED;
   - known-not-sent retryable -> RetryableWorkError;
   - uncertain -> UNKNOWN / AmbiguousWorkError.

6. On valid acceptance, short DB transaction:
   - lock execution;
   - require it is still queued;
   - persist provider_call_id, provider_initial_status, submitted_at;
   - set status=submitted;
   - commit.

7. Return so WorkerRunner marks the work item succeeded.
```

A current upstream change can occur after the final DB revalidation and before/during the external
POST; PostgreSQL and Hunar cannot participate in one atomic transaction. Once the provider side
effect is accepted, preserve the frozen execution as historical truth rather than attempting an
undocumented cancellation.

---

## 6. Repository/database operations

Create `VoiceCallRepository` with persistence primitives only. It must never commit.

At minimum:

```python
insert_execution(...)
get_execution(...)
get_execution_for_update(...)
get_for_outreach(...)
mark_submitted(...)
mark_failed(...)
mark_unknown(...)
reset_failed_to_queued(...)
```

Every state mutation must be guarded by expected current execution status.

Examples:

```text
queued -> submitted
queued -> failed
queued -> unknown
failed -> queued   # explicit safe retry only
```

No repository may invoke Module 1–5 services or Hunar HTTP.

### Work item

Use:

```text
work_type   = hunar_voice_call_dispatch
entity_type = voice_call_execution
entity_id   = execution.id
dedupe_key  = hunar-voice-call:{execution.id}
max_attempts = 3
```

The same dedupe key may be reused after a terminal FAILED work item because Module 0 uniqueness is
only over active statuses. Active dedupe still prevents concurrent duplicate requeue.

No `dispatch_generation` column is needed.

---

## 7. API endpoints

Register a new Module 6 router in the FastAPI application factory.

### Options

```http
GET /api/v1/voice-screening/options
```

Return:

```text
configured/implemented languages
default language
Hunar-supported timezones
default timezone
automatic_redials = false
```

This endpoint performs no provider HTTP call.

### Start execution

```http
POST /api/v1/outreach-requests/{outreach_request_id}/voice-call-executions
```

Request:

```json
{
  "language": "ENGLISH",
  "timezone": "Asia/Kolkata"
}
```

Response: `202 Accepted` with the created or already-existing execution projection.

The browser must never supply:

```text
agent_id
phone
callee_name
job_id
candidate_id
decision_match_id
definition_version
screening questions
role context
request_id
retry_config
callback URLs
```

### Get execution for outreach

```http
GET /api/v1/outreach-requests/{outreach_request_id}/voice-call-execution
```

### Get execution by ID

```http
GET /api/v1/voice-call-executions/{execution_id}
```

### Explicit retry

```http
POST /api/v1/voice-call-executions/{execution_id}/retry
```

Response: `202 Accepted`.

Only `failed` executions are eligible.

No endpoint may resend `unknown` executions.

Do not add call-result, webhook or recording endpoints in Module 6.

---

## 8. External provider contracts

### Authentication and base URL

Use Hunar's documented external endpoint:

```text
https://api.voice.hunar.ai/external/v1/
```

Authentication header:

```text
X-API-Key: <backend-only key>
```

### Backend settings

Extend existing `Settings` minimally:

```text
HUNAR_API_KEY
HUNAR_API_BASE_URL=https://api.voice.hunar.ai/external/v1
HUNAR_SCREENING_AGENT_IDS_JSON
HUNAR_DEFAULT_LANGUAGE=ENGLISH
HUNAR_DEFAULT_TIMEZONE=Asia/Kolkata
HUNAR_READ_TIMEOUT_SECONDS=30
HUNAR_CALL_SUMMARY_CALLBACK_URL optional
```

`HUNAR_SCREENING_AGENT_IDS_JSON` maps implemented language contract to pre-provisioned agent UUID,
for example:

```json
{
  "ENGLISH": "00000000-0000-0000-0000-000000000000"
}
```

Validate all Hunar URLs as HTTPS and normalize blanks to `None`, following current settings style.

No Hunar secret may enter `NEXT_PUBLIC_*`. Update `apps/api/.env.example` and README setup
documentation with placeholders only; never commit a real agent UUID/API key from a private account
unless the repository intentionally treats that UUID as non-secret deployment configuration.

### Agent provisioning model

Production runtime does not create/update/activate agents.

The initial English screening agent must be pre-provisioned and ACTIVE before Module 6 calls are
allowed. Hunar's external API documents create/update agent endpoints but does not document an
activation endpoint. Do not invent one.

Operational setup should create/update the reference behavior contract using Hunar-supported tooling,
then complete activation through Hunar's supported account process before setting the agent UUID in
application configuration.

### Exact English agent contract — `hunar_voice_screening_en_v1`

Reference agent configuration:

```text
Language:      ENGLISH
Voice persona: NEHA
Persona name:  Maya
```

The voice/persona choice is part of v1 and must be live-qualified for naturalness before release.
If changed, create a new contract version rather than silently changing v1.

#### Objective

```text
Conduct a short, respectful first-round recruiting screen. Confirm the correct person, check whether
now is a good time, collect accurate answers to the supplied screening questions, answer basic role
questions only from the supplied role context, and finish without making or implying a hiring
decision.
```

#### Introduction

```text
Hi, is this {callee_name}? I'm {persona_name}, an AI recruiting assistant. I'm calling about a
recruiting opportunity. Is now a good time for a short conversation?
```

This intentionally discloses that the caller is AI, confirms the intended person before revealing
the specific role, gives a clear purpose and asks permission before starting the screen. After the
Candidate confirms identity and availability, the agent states that the call concerns the
`{job_role}` role before asking the first screening question.

#### Agent prompt

```text
You are {persona_name}, a warm, professional AI recruiting assistant conducting a first-round voice
screening for the {job_role} role.

ROLE INFORMATION
{role_context}

SCREENING PLAN
{screening_plan}

CONVERSATION RULES

1. Be concise, calm and conversational. Do not sound like you are reading a form.
2. Confirm you are speaking with the intended candidate. If it is the wrong person, apologize
   briefly and end without revealing unnecessary recruiting information.
3. If the intended candidate confirms identity and says it is a convenient time, briefly explain
   that the call concerns the {job_role} role before beginning the screen. If it is not a good time,
   respect that immediately. Do not pressure the person to continue or promise a specific callback
   time.
4. Ask the supplied screening questions in their given order, one question at a time.
5. Do not invent, replace, score or add screening questions or hiring criteria.
6. If the candidate has already clearly answered a later supplied question naturally, do not force
   them to repeat the same information solely to follow the script.
7. You may ask one short clarification when an answer is genuinely ambiguous. A clarification must
   not introduce a new screening criterion.
8. For yes/no questions, accept natural equivalents. For choice questions, explain the supplied
   choices only when clarification is needed. For numeric questions, clarify units only when
   genuinely ambiguous.
9. Keep acknowledgements natural and brief. Vary them and avoid repeating the same phrase after
   every answer.
10. If the candidate asks about the role, answer only from ROLE INFORMATION. Never invent salary,
    benefits, company details, responsibilities, interview outcomes or hiring commitments that were
    not supplied.
11. If you do not know something, say so naturally and explain that the recruiting team can follow
    up. Never guess.
12. Never tell the candidate that they passed, failed, qualified, were shortlisted further or were
    rejected. Your role is information collection, not the hiring decision.
13. If the candidate says they are not interested or asks to stop, acknowledge it respectfully and
    end the conversation.
14. If the candidate is uncomfortable answering one supplied question, do not pressure them. Move
    on and preserve that no clear answer was obtained.
15. Do not ask for or infer protected personal characteristics unless they are part of an explicitly
    supplied recruiter question. Never invent sensitive questions yourself.
16. After the supplied screening plan is complete, thank the candidate briefly and end naturally.
    Do not promise a next step or timeline unless it was explicitly supplied in ROLE INFORMATION.
```

Module 6 executes recruiter-confirmed Module 5 questions; it does not add a new recruiter-question
content-policy authority. Separate compliance policy for recruiter-entered questions remains outside
this module.

#### Expected custom variables

The remote agent's `custom_variables` must equal:

```text
job_role
role_context
screening_plan
```

`callee_name` and `persona_name` are Hunar/system-level placeholders and are not sent as custom-data
keys.

#### Result schema

Use a fixed schema that can support Module 5's maximum of ten questions without allowing Hunar to
make a hiring decision:

```json
{
  "conversation_outcome": "",
  "candidate_interest": "",
  "question_1_answer": "",
  "question_2_answer": "",
  "question_3_answer": "",
  "question_4_answer": "",
  "question_5_answer": "",
  "question_6_answer": "",
  "question_7_answer": "",
  "question_8_answer": "",
  "question_9_answer": "",
  "question_10_answer": "",
  "notes": ""
}
```

Do not include provider-owned `qualified` or pass/fail decision fields.

#### Result prompt

```text
Extract factual screening information from this conversation only. Do not make a hiring
recommendation or infer whether the candidate passed, failed or is qualified.

Use the numbered questions in {screening_plan}.

conversation_outcome must be one of:
completed | partial | not_interested | wrong_person | not_available | disconnected | other

candidate_interest must be one of:
interested | not_interested | unclear

For question_1_answer through question_10_answer:
- map each slot to the correspondingly numbered screening question;
- preserve the candidate's actual meaning rather than rewriting it into a stronger claim;
- never infer an answer the candidate did not provide;
- use NO_CLEAR_ANSWER when the question was asked but no clear answer was obtained;
- use NOT_ASKED when a configured question was not asked;
- use NOT_APPLICABLE for slots beyond the number of configured questions.

notes must contain only short factual observations needed to understand the screening interaction.
Do not include a hiring recommendation.
```

Module 7 will later map `question_N_answer` back to the exact ordered Module 5 outreach-question UUIDs.

### Agent contract preflight

`GET /agents/{agent_id}/` is read-only and safe to retry.

Both the API creation path and worker immediately before call submission must verify:

```text
agent.id == configured agent UUID
agent.status == ACTIVE
agent.language == selected language
agent.voice_persona == contract voice persona
agent.persona_name == contract persona name
custom_variables == exact expected set
agent_prompt == canonical expected prompt
objective == canonical expected objective
introduction == canonical expected introduction
result_prompt == canonical expected result prompt
result_schema == canonical expected result schema
```

For text comparison normalize line endings and outer whitespace only. Do not weaken semantic drift
checks by loosely matching keywords.

`silence_response` and `conclusion` are returned in agent detail but are not writable fields in the
current external create/update request schema. Do not make Module 6 runtime depend on being able to
configure them. Evaluate their actual behavior during live qualification.

### Create call contract

Use:

```http
POST /calls/
```

Exact payload shape:

```json
{
  "agent_id": "<frozen configured UUID>",
  "callee_name": "<frozen Candidate display name>",
  "mobile_number": "<Module 5 E.164 phone>",
  "custom_data": {
    "job_role": "<exact role title>",
    "role_context": "<compact immutable role context>",
    "screening_plan": "<ordered Module 5 plan>"
  },
  "request_id": "hha-<execution_uuid_hex>",
  "timezone": "<selected supported timezone>",
  "retry_config": {
    "max_retry_count": 0,
    "retry_interval_hours": 0
  }
}
```

If `HUNAR_CALL_SUMMARY_CALLBACK_URL` is configured, add:

```json
{
  "callback_config": {
    "call_summary_callback_url": "https://..."
  }
}
```

Otherwise omit `callback_config` entirely. During Module 6-only qualification, leave this unset
unless a real Module 7-compatible HTTPS receiver already exists; do not point Hunar at a placeholder
or non-existent callback route.

Do not send `from_phone_number`; Hunar documents that omission lets the service select an available
organization number compatible with the destination.

Do not send `guardrails`; the organization default applies. The live production qualification must
confirm that the Hunar organization has appropriate calling guardrails configured. Always send the
recruiter-selected timezone so those guardrails are evaluated in the intended supported zone.

### Request ID

Generate:

```text
hha-{execution_uuid.hex}
```

This is valid under Hunar's 64-character format and is stored before dispatch.

Treat it only as tracking/correlation. It is not provider idempotency.

### Create-call response validation

The current OpenAPI create response requires:

```text
id
request_id
status
callee_name
mobile_number
timezone
```

Validate:

```text
id is UUID
request_id == frozen provider_request_id
callee_name == frozen payload value
mobile_number == frozen payload value
timezone == frozen payload value
status is a documented Hunar call status
```

If a successful response is malformed or inconsistent, the side effect may already exist.
Raise a Hunar-specific ambiguous-response error and salvage a valid provider call UUID from the raw
body when safely possible so Module 7 can later reconcile it.

Do not convert malformed success responses into safe retries.

---

## 9. State transitions

Persisted Module 6 execution state:

```text
ABSENT
   |
   | recruiter starts voice screening
   v
queued
   |
   +---- Hunar accepted + response persisted ----> submitted
   |
   +---- known rejection / safe retries exhausted -> failed
   |
   +---- external outcome uncertain -------------> unknown
```

Explicit safe retry:

```text
failed -> queued
```

Forbidden normal transition:

```text
unknown -> queued
```

`submitted` means only:

> Hunar accepted the call-create request and Module 6 durably stored its call identity.

It does **not** mean answered, completed, successfully screened, connected or qualified.

Hunar's attempt `status` / overall `lifecycle_status` belong to Module 7 after initial submission.
Module 6 stores only the initial status returned by create-call for audit.

Changes to Module 1/2/4/5 after the side-effect boundary do not retroactively rewrite a submitted
execution. Module 5 dispatchability is checked immediately before the side effect; there is no valid
cross-system transaction that can atomically lock PostgreSQL and Hunar.

---

## 10. Frontend components

Do not create a second Candidate/outreach workflow.

Extend the existing Module 5 outreach detail experience.

Suggested frontend surface:

```text
apps/web/lib/voice-calls/
    types.ts
    api.ts
    queries.ts

apps/web/components/voice-calls/
    voice-screening-start.tsx
    voice-call-execution-card.tsx
```

A separate global voice-call page/navigation entry is not required in Module 6.

### READY outreach with no execution

Show:

```text
Voice screening
────────────────────────

Candidate:
Aisha Khan

Role:
Senior Backend Engineer

Screening questions:
5

Language:
English

Timezone:
Asia/Kolkata

Automatic redials:
Off

[Start voice screening]
```

Only configured + implemented languages appear.

The recruiter must not re-enter:

```text
phone
Candidate
Job
role context
screening questions
agent ID
```

### Execution UI states

`queued`:

```text
Preparing voice call…
```

`submitted`:

```text
Call submitted to Hunar

The provider accepted the call. Live status and screening results will be handled by the next call-
result module.
```

`failed`:

```text
Call could not be submitted

<safe user-facing failure explanation>

[Retry dispatch]
```

`unknown`:

```text
Call submission outcome is uncertain.

Do not retry automatically. A call may already have been created at the provider.
```

No normal Retry button for UNKNOWN.

Do not surface raw provider payloads, full phone numbers or API keys.

---

## 11. Exceptional cases

Handle explicitly and fail closed.

### Before durable execution creation

```text
Hunar API key absent
requested language not implemented
requested language not configured
unsupported timezone
configured agent missing
agent DRAFT/ARCHIVED
agent contract mismatch
agent preflight transiently unavailable
outreach already stale/not dispatchable
```

A remote-agent preflight failure creates **no execution row**.

### Before worker side effect

Revalidate:

```text
execution still queued
Module 5 outreach still dispatchable
configured/frozen agent still ACTIVE and contract-compatible
```

If the outreach is stale before POST:

```text
execution -> failed
failure_code = OUTREACH_NOT_DISPATCHABLE
no Hunar POST
```

### Hunar documented call rejections

Treat received documented rejection statuses as known failure:

```text
400 telephony/business validation
401 authentication
402 subscription/minutes exhausted
404 agent/resource/active version missing
422 request/custom-data validation
```

Map them to stable Module 6 failure codes without exposing full provider error bodies.

### Defensive shared-transport rejection

If a real HTTP `429` is received, the existing shared transport classifies it as rate limited.
Because a 429 response is an explicit rejection, it may use the known-safe retry path. This is a
defensive shared-transport behavior, not a Hunar-documented status guarantee.

### Ambiguous outcomes

Treat as `UNKNOWN`:

```text
read timeout after POST
write timeout after POST
remote protocol failure after POST
other transport error marked operation_may_have_completed=true
Hunar HTTP 500/502/503/504 after POST
invalid JSON after successful/accepted POST
successful HTTP response missing/inconsistent required call identity
DB/persistence failure after provider acceptance may have occurred
worker lease expiry while call creation may have occurred
unclassified exception after side-effect boundary
```

Do not resend automatically.

If a valid provider call UUID was already observed, retain it on the UNKNOWN execution when possible.

### Safe known-not-sent outcomes

Provider connect failure classified `operation_may_have_completed=false` is safe for internal retry.

Read-only agent preflight GET failures are also safe for internal retry because they perform no
provider side effect.

### Provider automatic redial

Always send:

```json
{
  "max_retry_count": 0,
  "retry_interval_hours": 0
}
```

Do not inherit organization redial defaults.

---

## 12. Retry / idempotency rules

### Logical execution idempotency

One Module 5 outreach request owns at most one Module 6 execution:

```text
UNIQUE(outreach_request_id)
```

Repeated or concurrent Start actions return the same execution and do not create another active work
item.

### Provider request correlation

`provider_request_id` is deterministic for the execution and reused across safe dispatch retries.

It is **not** treated as provider idempotency.

### Automatic worker retries

Automatic retries are permitted only when repeating the POST is known safe.

For a retryable failure:

```text
if item.attempt_count < item.max_attempts:
    execution remains queued
    raise RetryableWorkError

if item.attempt_count >= item.max_attempts:
    mark execution failed
    raise PermanentWorkError
```

Do not let the generic runner mark the queue item FAILED while leaving domain execution incorrectly
QUEUED.

### Ambiguous submission

Before raising `AmbiguousWorkError`, the handler should attempt to mark the domain execution UNKNOWN
and retain any safely observed provider call ID/status.

If that domain write itself fails, Module 0 will still mark the work item UNKNOWN. Domain
reconciliation must later converge the execution to UNKNOWN.

### UNKNOWN reconciliation

Add Module 6 domain reconciliation for:

```text
work_items.status = unknown
work_type = hunar_voice_call_dispatch
entity_type = voice_call_execution
```

Rules:

```text
execution submitted -> leave submitted
execution unknown   -> no change
execution failed    -> no change
execution queued    -> mark unknown using queue failure code
```

The current worker has one `after_stale_recovery` callback. Do not redesign `WorkerRunner` merely to
support Module 6. Update the worker composition root to invoke both:

```text
SourcingWorkHandlers.reconcile_unknown_work()
VoiceCallWorkHandlers.reconcile_unknown_work()
```

through one small composite callback.

### Explicit recruiter retry

Only `failed` may be explicitly retried.

Retry must:

- revalidate Module 5 dispatchability;
- revalidate the frozen Hunar agent contract;
- reuse the exact provider payload snapshot;
- reuse the exact request ID;
- create one new active work item with the same dedupe key.

Never automatically or normally retry UNKNOWN.

### Why UNKNOWN cannot auto-recover by request ID

Hunar documents `request_id` as a tracking identifier. The current list-calls API filters only by
campaign, agent and status, not request ID. Therefore there is no documented safe automatic lookup
that proves whether an UNKNOWN create-call request produced a call.

Module 7 may recover an UNKNOWN execution when a known call ID/webhook/provider evidence proves the
outcome, but Module 6 must not guess.

---

## 13. Security considerations

### Secrets

`HUNAR_API_KEY` is backend-only.

Never expose it through:

```text
NEXT_PUBLIC_*
frontend source
API responses
logs
work-item payloads
```

### PII

The provider payload contains Candidate name and phone and must remain backend/database-only.

Do not log raw:

```text
mobile_number
provider_payload_snapshot
full custom_data
screening answers/results
```

The existing logging redactor already redacts keys containing `phone`; add tests to ensure Module 6
logging never emits a full payload under non-sensitive wrapper keys.

Public Module 6 APIs must not return full phone or raw provider payload.

### Data minimization

Send Hunar only what the voice interaction requires:

```text
Candidate name
Module 5 frozen phone
role context
Module 5 frozen screening plan
```

Do not send:

```text
email
Apollo identifiers
sourcing origin
match score
match reasons
private provider evidence
```

### Agent behavior safety

The agent must never make or communicate a hiring decision.

It may clarify supplied questions but may not invent criteria, salary, benefits, company facts or
next-step promises.

### Webhooks

Module 6 does not implement webhook endpoints or signature verification.

If an optional summary callback URL is configured, it must be HTTPS. Module 7 must later implement
Hunar's documented timestamped HMAC-SHA256 verification and idempotent duplicate-event handling.

---

## 14. Tests

Add:

```text
scripts/validate_module_6.py
doc/MODULE_6_IMPLEMENTATION_PLAN.md
doc/MODULE_6_VALIDATION.md
doc/MODULE_6_HUNAR_AGENT_CONTRACT.md
```

Update cumulative README/module status and backend metadata from `0.6.0` to `0.7.0` following the
existing version convention.

### Baseline regression

Before and after implementation run:

```text
validate_module_0.py
validate_module_1.py
validate_module_2.py
validate_module_3.py
validate_module_4.py
validate_module_5.py
validate_module_6.py
```

### Agent-contract unit tests

Prove exact v1 values for:

```text
language
voice persona
persona name
objective
introduction
agent prompt
result prompt
result schema
required custom-variable set
contract version
```

Test remote drift rejection for every contract field.

Test text canonicalization permits only line-ending/outer-whitespace normalization, not semantic
changes.

### Provider adapter tests

Mock exact:

```text
GET /agents/{id}/
POST /calls/
X-API-Key
custom_data string values
request_id format
E.164 phone
selected timezone
retry_config = 0/0
optional summary callback only when configured
from_phone_number omitted
guardrails omitted
```

Verify create-call response parsing and exact echo validation.

Test malformed 200 response with salvageable call UUID -> ambiguous response with retained UUID.

### Provider failure classification

Preflight GET:

```text
API create-path preflight:
    connect/transport/transient/invalid JSON -> no execution row; surface retryable service error
    401/404/permanent -> configuration failure; no execution row
    contract mismatch -> fail closed; no execution row

Worker preflight:
    connect/transport/transient/invalid JSON -> RetryableWorkError
    401/404/permanent -> domain FAILED
    contract mismatch -> domain FAILED
```

Call POST:

```text
connect failure known not sent -> retryable
received defensive 429 -> retryable rejection
400 -> failed
401 -> failed
402 -> failed
404 -> failed
422 -> failed
500/502/503/504 -> unknown
read timeout -> unknown
write timeout -> unknown
remote protocol failure -> unknown
invalid JSON after POST -> unknown
malformed successful response -> unknown
```

### Service/idempotency tests

Prove:

```text
Task 1 outreach -> one execution
Task 2 outreach -> same Module 6 path
no Candidate-origin branching

repeated Start -> same execution
concurrent Start -> one execution
one active work item

submitted -> cannot start another execution
unknown -> cannot retry
failed -> explicit retry allowed only after revalidation
```

### Upstream authority tests

Before worker POST:

```text
outreach still current -> allowed
phone changed -> fail before provider
shortlist changed -> fail before provider
Job reopened/new match required -> fail before provider
```

Changes after successful provider submission preserve historical execution and do not rewrite it.

### Payload snapshot tests

Verify provider payload uses:

```text
phone from Module 5 snapshot
questions from Module 5 snapshot
exact immutable Job version role context
Candidate current display name at execution creation
```

Verify retry reuses byte-equivalent canonical payload content and the same request ID.

### Work queue tests

Prove:

```text
work_type registration
active dedupe
max_attempts
retry scheduling
safe retry exhaustion -> domain failed
ambiguous handler -> domain/work item unknown
stale RUNNING -> work item unknown -> domain unknown reconciliation
submitted execution not downgraded by reconciliation
```

Verify worker composition preserves Module 3 unknown reconciliation while adding Module 6.

### PostgreSQL tests

Use disposable `TEST_DATABASE_URL` and prove:

```text
migration rebuild
one execution per outreach
provider request ID unique
provider call ID unique when non-null
status checks
submitted invariants
UNKNOWN may retain provider call ID
input immutability trigger
allowed operational field transitions
RLS/revokes
concurrent execution creation
```

### Frontend tests

Prove:

```text
READY_FOR_EXECUTION outreach shows Start voice screening
STALE outreach does not
only configured language shown
supported timezone selection
automatic redials displayed Off
no phone/question re-entry
queued UI
submitted UI
failed Retry UI
unknown no-Retry UI
```

### Natural conversation live smoke matrix

Using a controlled test number, qualify the actual ACTIVE Hunar agent for:

1. normal candidate who answers all questions;
2. candidate says it is a bad time;
3. wrong person answers;
4. candidate says not interested;
5. candidate interrupts the agent;
6. candidate naturally answers a later question early;
7. ambiguous answer requiring one short clarification;
8. candidate refuses one question;
9. candidate asks about salary/benefits not present in role context;
10. candidate asks whether they passed;
11. candidate goes silent;
12. candidate asks the AI to stop.

Verify the conversation feels concise and natural rather than form-reading.

### Live provider qualification

Before Module 6 freeze:

```text
GET configured agent
verify ACTIVE
verify exact contract fields/custom variables
verify voice/persona naturalness
make one controlled call
verify exact request_id
verify retry_config=0/0
verify call ID returned
verify introduction disclosure/permission
verify ordered screening behavior
verify no invented role facts
verify no pass/fail statement
verify result schema shape
GET resulting call by provider_call_id
verify provider call exists and initial correlation is correct
```

If live behavior requires changing the prompt/persona, update the contract version and plan before
freezing the implementation; do not silently change v1.

### Full quality gates

Run every available:

```text
Python compile
Ruff
strict mypy
full backend pytest
disposable PostgreSQL/Supabase migration tests
frontend lint
frontend typecheck
Vitest
Next production build
secret/PII scan
git diff --check
fresh patch-apply validation
```

Unavailable environment/provider gates must be reported as unavailable, never as passed.

---

## 15. Acceptance criteria

Module 6 is complete only when all of the following are true:

1. Task 1 and Task 2 use exactly the same Module 6 execution path.
2. Module 6 starts only from `OutreachService.lock_dispatchable_outreach()` truth.
3. Phone comes exclusively from the Module 5 frozen snapshot.
4. Screening questions come exclusively from Module 5's exact frozen ordered snapshot.
5. Role context comes from the exact immutable bound Job version.
6. Candidate origin, match score and Apollo evidence never reach Hunar.
7. Runtime never creates or updates an agent per Candidate.
8. A call can be created only with a configured implemented-language agent contract.
9. Remote agent must be ACTIVE.
10. Remote agent contract drift fails closed before the call side effect.
11. English v1 prompt/objective/introduction/result contract is versioned and reconstructable.
12. The agent transparently identifies itself as an AI recruiting assistant.
13. The agent asks permission before beginning the screen.
14. Screening is conversational, one supplied question at a time.
15. The agent may clarify but may not invent criteria.
16. The agent never claims pass/fail/qualification/rejection.
17. Unknown role facts are not invented.
18. English is the only initial implemented language.
19. Additional languages require their own human-reviewed contract, configured ACTIVE agent and live
    qualification.
20. Recruiter does not re-enter phone, role or questions at call execution.
21. One outreach request produces at most one Module 6 execution row.
22. Repeated/concurrent Start actions do not duplicate execution or active work.
23. Hunar `request_id` is treated as correlation only.
24. Safe known-not-sent failures may retry internally.
25. Retry exhaustion converges both queue and domain execution to FAILED.
26. Ambiguous side-effect outcomes become UNKNOWN.
27. UNKNOWN never automatically or normally replays.
28. UNKNOWN may retain a safely observed provider call ID for future recovery.
29. Hunar automatic redial is explicitly disabled with `0/0`.
30. `submitted` means provider acceptance only, not call completion.
31. Module 6 persists no final screening answers/results/recordings.
32. Module 6 implements no webhook handler.
33. Public API/UI never expose full phone, provider payload or API key.
34. Module 3 worker behavior and UNKNOWN reconciliation remain unchanged and green.
35. Controlled live Hunar qualification passes before Module 6 freeze.
36. All Module 0–6 automated/database/frontend/regression gates pass in their required environments.

---

## 16. What is explicitly out of scope

Module 6 does not implement:

```text
Apollo sourcing or enrichment
Candidate matching/scoring
shortlist mutation
outreach question editing

per-Candidate agent creation
runtime agent mutation
agent activation automation

bulk calls
campaign creation

automatic language detection
runtime translation
mid-call language switching

provider lifecycle/status convergence after create response
Hunar webhook endpoints
webhook signature verification
screening answer persistence
result persistence
recording persistence
transcript processing
call-result recovery

provider automatic redial/retry scheduling
application-level automatic Candidate re-calling

recruiter dashboard analytics
```

The external Hunar API exposes bulk calls and call history, but they are not required for this Module
6 assessment boundary.

---

## 17. Dependency impact on next module

Module 7 — Call Events, Screening Results & Recovery — receives one durable Module 6 execution
identity:

```text
voice_call_execution_id
outreach_request_id
provider = hunar
provider_call_id when known
provider_request_id
agent_id
agent_contract_version
language
timezone
```

Through the outreach relationship it can recover the exact immutable Module 5 screening questions and
question UUIDs that the voice agent was supposed to ask.

Hunar's documented webhook payloads include:

```text
event_type
call_id
agent_id
request_id
```

The `call_summary` event fires once when the lifecycle reaches a terminal state and includes terminal
status plus recording/result information. Module 7 should use that as the primary terminal event for
future calls when summary callbacks are enabled.

Module 7—not Module 6—will own:

```text
signed Hunar webhook ingestion
X-Hunar-Timestamp / X-Hunar-Signature validation
duplicate webhook idempotency
attempt/lifecycle status convergence
screening result normalization
question_N -> Module 5 question UUID mapping
recording/result references
NOT_CONNECTED/FAILED/CANCELLED terminal handling
recovery of known provider call IDs
reconciliation of UNKNOWN Module 6 executions when evidence proves an outcome
```

The final authority chain remains:

```text
Module 1  approved Job/version/default-screening truth
    ↓
Module 2  canonical Candidate/contact truth
    ↓
Module 3  sourcing/enrichment truth
    ↓
Module 4  Candidate↔Job match + recruiter shortlist truth
    ↓
Module 5  exact immutable outreach execution context
    ↓
Module 6  Hunar call-submission execution truth
    ↓
Module 7  call events/results/recovery truth
```

---

# Implementation checkpoint order

Implementation should follow the existing agent-driven SDLC rather than coding all layers at once:

```text
1. Re-run baseline Module 0–5 qualification.
2. Add provider enums/contracts + exact English agent contract tests.
3. Add migration/model and PostgreSQL qualification.
4. Add Hunar read-only agent adapter + contract preflight.
5. Add Module 6 repository/service creation path.
6. Add durable work handler + worker composition/reconciliation.
7. Add call POST adapter and complete failure-certainty classification.
8. Add API routes and typed frontend integration.
9. Add focused Module 6 tests.
10. Run full Modules 0–6 regression suite.
11. Perform controlled live Hunar qualification.
12. Correct any provider/repository drift discovered by live evidence.
13. Perform final producer/consumer + blast-radius audit.
14. Only then generate the final patch.
```

At each checkpoint verify:

```text
no duplicate truth owner
no Task-1/Task-2 branching
no provider HTTP inside DB transaction
no unsafe UNKNOWN replay
no Module 7 result ownership leaking backward
no current Job questions replacing Module 5 frozen questions
no current Candidate phone replacing Module 5 frozen phone
no runtime per-Candidate agent mutation
```

Passing tests is necessary but not sufficient if these authority boundaries drift.

Baseline filename corrected by explicit user instruction in this implementation session.
