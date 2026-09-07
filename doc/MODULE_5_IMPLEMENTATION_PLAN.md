# Module 5 — Outreach — Implementation Ledger

## Authoritative baseline

`hunar-hiring-assistant-main (2).zip`, archive commit marker
`ccbbb7e10de2e63d1348dd5c54b1fe1763328287`, with the final cross-verified
17-point Module 5 plan as the behavior contract. The plan's extra `(1)` filename suffix is
documentation drift only.

## Frozen invariants

- Manual and Apollo-origin Candidates converge before Module 5 at `job_candidates`.
- Module 5 persists only immutable request identity, decision binding, canonical phone snapshot,
  exact screening snapshot, deterministic screening hash, and creation time.
- Readiness is derived from current Module 1/2/4 truth.
- Question UUIDs are created only after exact-context lookup.
- Lock order remains JobCandidate, Job, Candidate.
- Module 5 performs no provider call, work-item operation, call lifecycle, or result persistence.

## Intentional implementation surface

- One migration and one SQLAlchemy model for `outreach_requests`.
- Public pure Job-domain duplicate-key helper used by Modules 1 and 5.
- Narrow Candidate contact and current-shortlist locking seams.
- Module 5 DTOs, repository, service, dependencies, router, tests, and validator.
- Typed TanStack Query API, preparation/list/detail pages, navigation, and reuse of
  `ScreeningQuestionEditor`.
- API/package version advanced from `0.5.0` to `0.6.0` under the existing convention.

## Evidence-backed plan correction

No architectural incompatibility was found. The only baseline conflict was the plan's archive
display name; the supplied archive was used as exact authority.
