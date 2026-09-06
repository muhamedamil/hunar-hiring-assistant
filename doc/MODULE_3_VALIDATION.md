# Module 3 Validation Record

## Scope

Module 3 implements READY-Job-bound Apollo People Search, provider evidence, deliberate contact
enrichment, asynchronous phone recovery, and canonical Candidate resolution on top of qualified
Modules 0–2.

## Frozen invariants

- every new sourcing run atomically binds to a currently READY immutable Job definition version;
- historical sourcing runs retain their original definition version after Job reopen/reapproval;
- Apollo search results are sourcing evidence and never directly create Candidate rows;
- exact supported filters are mapped while unsupported Job requirements remain explicit diagnostics;
- application search limit is 10/25/50 with a hard maximum of 50;
- over-limit provider pages are rejected by the adapter/service and DB checks result count bounds;
- stale `SEARCHING` retry advances a persisted search generation so older in-flight executions
  cannot overwrite the newer retry's run state;
- enrichment is one logical operation per result and occurs only after recruiter action;
- contact mutation goes only through `CandidateService.resolve_external_candidate`;
- uncertain credit-consuming provider execution becomes `UNKNOWN` and is not automatically replayed;
- safe enrichment retry exhaustion converges queue and domain state to `FAILED`;
- phone webhook and zero-credit polling share one idempotent finalization authority;
- Apollo search phone-availability strings (`Yes`/`Maybe`/`No`) are normalized explicitly;
- an enriched person ID cannot differ from the selected search-result provider person ID;
- a single-person phone result must contain exactly one person;
- poll observer/configuration failures leave `AWAITING_PHONE` open for the signed webhook;
- only Apollo's semantic terminal request-ID result may terminally fail an awaiting-phone enrichment;
- invalid provider phone values may be skipped, but phone-normalization runtime failures stay visible;
- Module 0 stale-work UNKNOWN is projected into Module 3 without weakening generic queue semantics;
- sourcing tables do not store email/phone truth;
- no matching, shortlist, or Hunar/outreach lifecycle belongs to Module 3.

## Validation completed in this environment

Current sandbox checkpoint after the final conformance corrections:

```text
Module 0 structural validator   PASS
Module 1 structural validator   PASS
Module 2 structural validator   PASS
Module 3 structural validator   PASS
Backend pytest                  105 passed / 22 environment-gated skips
Total backend tests             127
```

At the final implementation checkpoint, run:

```text
python scripts/validate_module_0.py
python scripts/validate_module_1.py
python scripts/validate_module_2.py
python scripts/validate_module_3.py

python -m compileall -q apps/api/app apps/api/tests
cd apps/api
python -m pytest -q
```

The sandbox cannot execute real PostgreSQL tests without `TEST_DATABASE_URL`, phone-normalization
cases without the installed `phonenumbers` package, or the complete frontend/ruff/mypy toolchain
when its dependencies are absent. Those remain local gates rather than being treated as passing.

## Hosted Supabase qualification

Use a disposable/test hosted Supabase database that already has Modules 0–2 migrations, then push
`20260906113000_module_3_people_sourcing.sql` and set `TEST_DATABASE_URL` to that database only if
it is safe for destructive qualification data.

Verify:

- all three Module 3 tables exist with RLS enabled and browser roles revoked;
- `(job_id, definition_version)` references a real immutable Job snapshot;
- `result_count > result_limit` is rejected;
- duplicate run/person and duplicate enrichment/result identities are rejected;
- negative/full signed-64-bit Apollo request IDs persist correctly;
- READY/reopen locking permits only one valid ordering;
- stale UNKNOWN credit work projects enrichment to UNKNOWN;
- stale UNKNOWN read-only poll work creates a safe recovery poll generation.

## Backend local gates

```powershell
cd apps\api
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
ruff check .
mypy app
$env:TEST_DATABASE_URL="YOUR_DISPOSABLE_HOSTED_SUPABASE_DATABASE_URL"
python -m pytest -q
```

## Frontend local gates

```powershell
npm install
npm run web:lint
npm run web:typecheck
npm run web:test
npm run web:build
```

## Manual UI qualification

1. Open a DRAFT Job and verify new people search is unavailable while historical runs remain visible.
2. Mark the Job READY and click **Find people**.
3. Start a small bounded search (prefer 5 only for a live-provider smoke via direct test tooling;
   normal UI choices are 10/25/50).
4. Confirm the run displays its approved Job version and exact persisted mapped/unmapped criteria.
5. Confirm raw Apollo results show sourcing evidence only and no Candidate row is created merely by
   search.
6. Select one result and click **Enrich contact** once. Repeated clicks must not create another
   logical enrichment.
7. Confirm synchronous enrichment resolves/links a Candidate and phone state becomes
   `AWAITING_PHONE` when a recoverable request ID exists.
8. Deliver the signed webhook or allow polling recovery; confirm terminal `COMPLETED` and Candidate
   contact normalization when a valid phone exists.
9. Confirm `CONFLICT`, `NOT_FOUND`, `FAILED`, and `UNKNOWN` states are visible and do not create a
   second credit-consuming action.
10. Reopen the Job. Historical run remains readable; a new search is blocked until the Job is READY
    again.

## Bounded live Apollo smoke

Use synthetic assessment data and a small result set. People Search must not create Candidate rows.
Enrich only one selected result because enrichment may consume credits. The public callback base
must be HTTPS and reachable by Apollo when phone reveal is tested.

## Release decision

Module 3 implementation is complete only after structural validation, backend regression,
PostgreSQL qualification, frontend lint/typecheck/tests/build, and the bounded manual/live smoke are
green. Only then mark Module 3 **COMPLETE / QUALIFIED / FROZEN**.
