# Module 4 — Candidate ↔ Job Matching & Shortlisting

**Baseline:** `hunar-hiring-assistant-main (4).zip`
**Status:** implementation contract for the Module 4 qualified worktree

## 1. **Objective**

Create one shared Candidate↔Job authority for both assignment streams, evaluate available Candidate evidence against an immutable currently approved Job definition, and record the recruiter's actual shortlist decision. Module 4 separates evidence-backed fit from call readiness and never turns Apollo search order or contact availability into hiring fit.

## 2. **Existing dependencies**

Module 0 supplies transactions, errors, provider HTTP, logging, and frontend conventions. Module 1 supplies immutable approved Job versions through `lock_ready_definition_for_downstream_binding`. Module 2 supplies canonical Candidate identity plus a minimal title/location/phone-readiness snapshot. Module 3 supplies resolved sourcing provenance and optional normalized professional evidence. Raw search results remain Module 3 evidence and cannot enter Module 4 until Candidate Core resolution.

## 3. **Database changes**

Migration `20260906190000_module_4_candidate_job_matching.sql` adds exactly `job_candidates` and `job_candidate_matches`. `job_candidates` is unique on `(job_id,candidate_id)` and owns current shortlist state plus the preferred sourcing evidence reference. `job_candidate_matches` stores immutable completed match history bound to `(job_id,definition_version)`, exact input hashes, source provenance, scoring, evidence coverage, Gemini metadata, and failure metadata. RLS/revokes, score/coverage checks, active-analysis dedupe, same-relation current/decision FKs, and completed-match immutability are enforced in PostgreSQL.

## 4. **Domain models**

Relationship sources are `manual|sourcing`; recruiter states are `reviewing|shortlisted|not_selected`; criterion states are `supported|contradicted|unknown`. Match v1 consumes canonical Candidate title/location plus optional Module 3 title/location/employment-title evidence. When current Candidate Core title/location is populated, it remains authoritative over conflicting provider-current evidence; provider evidence supplies bounded historical/contextual support rather than replacing canonical current profile truth. Skills, complete years of experience, employment preference, and work arrangement remain `unknown` because the current evidence contract cannot prove them. Phone produces `ready|not_ready` call readiness only.

Backend score:

```text
match_score = supported configured weight / total configured weight
evidence_coverage = known configured weight / total configured weight
```

The backend owns the numeric score. Gemini never returns one.

## 5. **Backend services**

`MatchingService` owns manual/sourced convergence, shared relationship reads, match evaluation, freshness, history, and recruiter decisions. After its relationship transaction commits, manual attachment calls the existing evaluator only for a newly created relation. After its relationship/source transaction commits, sourced attachment calls that evaluator only for a new relation or changed `preferred_sourcing_result_id`. Repeated identical contexts return existing truth, including stale or missing truth after an earlier failed attempt; only the explicit refresh/retry action re-evaluates them. `scoring.py` remains the single pure deterministic evidence implementation. `CandidateMatchProvider` isolates optional semantic classification. Candidate Core adds read/lock matching snapshot seams only. Module 3 adds a read-only resolved-source seam that succeeds even when richer professional evidence is absent.

## 6. **Repository/database operations**

Repositories never commit. Relationship creation locks the READY Job and canonical Candidate, then relies on `UNIQUE(job_id,candidate_id)` as final concurrency authority; existing sourced relations are row-locked while preferred evidence is selected. The relationship/source transaction commits before `evaluate_match()` begins. Match input is then captured inside its own short transaction, external Gemini HTTP runs after that commit, and finalization re-locks/re-hashes current Job/Candidate/source evidence before promoting the result. A late result whose input changed remains historical and cannot become current truth. No transaction spans Gemini HTTP.

## 7. **API endpoints**

```text
POST  /api/v1/jobs/{job_id}/job-candidates
POST  /api/v1/sourcing-results/{result_id}/job-candidate
GET   /api/v1/jobs/{job_id}/job-candidates
GET   /api/v1/job-candidates/{job_candidate_id}
POST  /api/v1/job-candidates/{job_candidate_id}/match
GET   /api/v1/job-candidates/{job_candidate_id}/matches
PATCH /api/v1/job-candidates/{job_candidate_id}/shortlist
```

Manual and sourced routes converge on the same relationship and return its detail after any required initial/current evaluation. Sourced attachment derives Job/Candidate/provenance server-side.

## 8. **External provider contracts**

Module 4 adds zero Apollo calls. The dedicated Gemini adapter reuses the repository's existing `/v1beta/interactions` contract and settings. Gemini receives approved title/alternate/seniority plus explicit Candidate title evidence and the already-normalized employment-history start/current markers available from Module 3, and returns structured role/seniority verdicts with evidence IDs. It may not infer skills, years of experience, employer prestige, protected traits, a numeric score, or a shortlist decision. No automatic provider retry exists.

## 9. **State transitions**

Stable relation: absent → reviewing → shortlisted/not_selected, with recruiter-controlled movement back through reviewing. All shortlist-state mutations require the Job to be currently READY; DRAFT keeps historical state read-only. Match attempts are `analyzing -> completed|failed`. A match is current only when the Job is READY, its definition version matches the current approved version, the fit-evidence hash is unchanged, and matcher policy is current. A recruiter decision is current only when `decision_match_id == current_match_id` and that match is fresh.

## 10. **Frontend components**

`/jobs/{jobId}/candidates` is the shared Task-1/Task-2 review workspace. Manual Candidates use existing Candidate Core search; successful **Add to job** performs the required initial assessment and navigates directly to `/job-candidates/{id}`. Resolved sourcing results expose one explicit **Review match** action that selects the sourced evidence, performs any required assessment, and navigates to the same detail route. Detail uses **Refresh match** when current truth exists; if an earlier initial assessment genuinely left no current match, it shows **Initial assessment unavailable** and **Retry analysis**. It also shows match score, evidence coverage, supported/contradicted/unknown criteria, call readiness, semantic fallback warnings, explicit recruiter decisions, and immutable history. Phone is only a review-order tie-break after fit quality.

## 11. **Exceptional cases**

Handle DRAFT Jobs, reapproval during analysis, Candidate title/location edits during analysis, contact-only edits, sourced Candidates with no professional evidence, old sourcing v1 evidence matched against current READY v2, manual-first/sourced-first convergence, invalid source provenance, Gemini auth/rate-limit/timeout/schema failures, duplicate refresh/retry clicks, stale analyses, stale recruiter revisions, stale matches, and stale decisions.

## 12. **Retry / idempotency rules**

Relation creation is idempotent through the Job/Candidate unique key. A new relation gets one automatic initial evaluation; a changed preferred source gets one evaluation for that new context. The same manual relation or same preferred source never silently refreshes a stale/missing match or retries a failed attempt. Exact completed match input is cached and reused. One active semantic analysis exists per relation/analysis key; concurrent collisions map to `MATCH_ANALYSIS_IN_PROGRESS`. Gemini is never automatically retried. Semantic failure completes truthful deterministic fallback and a later explicit recruiter refresh can retry; a genuinely missing current assessment exposes **Retry analysis**. Shortlist writes use row locks plus `expected_revision`.

## 13. **Security considerations**

Do not send Gemini Candidate name, email, phone, profile URL, company prestige, or protected attributes. Do not score provider order/contact availability. Public Module 4 projections expose only contact readiness, not contact values. Raw Apollo/Gemini payloads are not persisted. RLS and browser-role revokes apply to Module 4 tables. Authentication/RBAC remains outside current assessment scope.

## 14. **Tests**

Qualification includes pure scoring, Gemini schema/prompt/failure tests, automatic Task-1 and Task-2 initial assessment, repeat-context no-rematch behavior, both convergence orders, sourced evidence absent/present, stale/missing no-silent-retry behavior, deterministic provider fallback, historical Job-version provenance, contact-only vs fit-evidence freshness, late-result safety, exact-input Gemini caching, active-analysis deduplication, recruiter decision freshness, direct frontend review navigation and recovery labels, API routes, and disposable PostgreSQL constraints/RLS/immutability/concurrency. Modules 0–3 validators/regression remain mandatory.

## 15. **Acceptance criteria**

One Job/Candidate relation serves both streams; only resolved Candidates enter Module 4; Attach/Review match produces the required automatic initial assessment before recruiter review; repeated identical contexts do not silently refresh or retry; all new work binds current READY Job truth; old sourcing provenance remains historical; unsupported evidence stays unknown; Gemini is evidence classification only; backend scoring is deterministic; phone never changes fit; recruiter owns shortlist truth; late/stale work cannot overwrite current truth; old decisions require reconfirmation after rematch; no Apollo call is added; all automated/database/frontend/regression gates pass.

## 16. **What is explicitly out of scope**

Module 3 search prioritization/enrichment, additional Apollo endpoints, résumé/CV ingestion, verified skill extraction, complete experience reconstruction, inferred skills/experience, company-prestige scoring, automatic shortlist/rejection, outreach, Hunar calls, call events/results/recovery, authentication/RBAC, Candidate merge, vector/RAG/agent frameworks.

## 17. **Dependency impact on next module**

Module 5 receives one stable `job_candidate_id` with canonical Candidate/Job IDs, immutable current match, recruiter shortlist state, and the exact match on which the decision was made. Safe downstream eligibility is `shortlisted` + current decision match + fresh current match. Module 5 must separately own contact snapshot/outreach lifecycle and must not reinterpret match score as permission to contact.
