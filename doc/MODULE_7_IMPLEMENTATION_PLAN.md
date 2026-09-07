# Module 7 implementation plan and ledger

This implementation follows the final cross-verified **Module 7 — Call Events, Screening Results &
Recovery — Low-Level Implementation Plan** supplied with the authoritative repository archive.

## Authoritative baseline

- Supplied repository: `hunar-hiring-assistant-main (2)(2).zip`
- Plan header reference: `(2)(3).zip` (not supplied)
- Evidence-backed resolution: implement and generate the patch against the supplied `(2)(2)` bytes;
  do not infer missing changes from the unavailable filename.
- Frozen upstream: Modules 0–6; backend `0.7.0`
- Module 7 target: backend `0.8.0`

## Frozen invariants

- Module 5 immutable outreach questions are the sole historical question authority.
- Module 6 remains the sole submission-certainty authority and is never mutated by Module 7.
- Signed Hunar `call_summary` is the normal terminal evidence path.
- Signature and timestamp validation operate on exact raw bytes before JSON parsing.
- Recovery performs one `GET /calls/{id}/` only for a known call ID and never searches or creates.
- Only `COMPLETED + HUMAN` can produce answers; retry evidence must prove zero redials.
- Result parsing is selected by the execution's stored agent-contract version.
- Provider answer values are permissively normalized for recruiter display; only configured
  numbered slots map to immutable Module 5 question identities.
- Terminal identity is immutable; only specified null enrichment and unavailable/invalid-to-available
  transitions are allowed.
- Webhook/GET timestamps that differ only because of sub-millisecond provider truncation represent
  the same terminal instant.
- Recording references remain backend-only; the public contract exposes a Boolean.

## Checkpoint ledger

| Checkpoint | Implemented contract |
| --- | --- |
| Baseline | Validators 0–6 and available backend tests; exact Module 5/6 producer/consumer audit |
| Provider/security | Lifecycle/human DTOs, summary/detail DTOs, normalized evidence, HMAC verification, rotating keys, GET-by-ID |
| Schema/domain | `voice_call_results`, `voice_screening_answers`, constraints, guards, RLS/revokes, ORM/DTO parity |
| Read seams | Historical Module 5 question context and immutable Module 6 result binding only |
| Finalizer | Shared identity/retry/human/version/mapping/classification/idempotency/enrichment path |
| Webhook | Signature-first raw request endpoint with commit-before-2xx |
| Recovery | Short read → closed transaction → one Hunar GET → shared finalizer |
| Frontend | Existing outreach execution panel extended with local polling and safe reconciliation |

## Provider assumptions requiring live qualification

- Hunar signs `timestamp + "." + raw_body` with Base64 HMAC-SHA256.
- Summary and call-detail responses use the fields represented by the strict local DTOs.
- Retry counters are present and equal to zero; scheduled retry time is absent/null.
- Detailed-call timezone may be absent, but must match the frozen execution when present.

No provider contradiction was hidden in implementation. Live credentials, a public HTTPS endpoint,
and controlled HUMAN/MACHINE calls remain separate release gates.
