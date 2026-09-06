# Module 4 Validation

Module 4 is qualified only after the cumulative repository, database, frontend, and manual gates below pass against the exact Module 4 worktree.

## Automated backend gates

```bash
python scripts/validate_module_0.py
python scripts/validate_module_1.py
python scripts/validate_module_2.py
python scripts/validate_module_3.py
python scripts/validate_module_4.py
python -m compileall -q apps/api/app apps/api/tests

cd apps/api
python -m ruff check app tests
python -m mypy app
python -m pytest tests -q
```

Database-dependent tests must use a disposable migrated database through `TEST_DATABASE_URL`; never point them at production or normal application data.

## Database gates

Apply all migrations through `20260906190000_module_4_candidate_job_matching.sql`, then run the full backend suite with `TEST_DATABASE_URL` configured. Confirm:

- Module 4 tables exist and have RLS enabled.
- direct `anon` / `authenticated` table privileges remain revoked;
- one `(job_id,candidate_id)` relation is enforced under concurrency;
- active semantic analysis is unique per relation/analysis key;
- completed match rows reject UPDATE/DELETE;
- `match_score <= evidence_coverage` is database-enforced;
- current/decision match pointers cannot point to another relationship.

## Frontend gates

From repository root:

```bash
npm ci
npm run web:lint
npm run web:typecheck
npm run web:test
npm run web:build
```

## Manual shared-flow smoke

1. Create/READY a Job with title, alternate title, location, skills, seniority and screening questions.
2. Create a manual Candidate, open **Review candidates**, and click **Add to job**. Confirm it automatically performs the initial assessment, navigates directly to the relationship review, leaves unsupported skills/experience `Unknown`, and does not shortlist until the recruiter explicitly chooses **Shortlist**.
3. Run Module 3 People Search. Confirm pre-enrichment priority remains a Module 3 recommendation and does not show a Module 4 fit score.
4. Enrich one selected result only. When Candidate resolution completes, click **Review match** and confirm it selects that source, performs the required initial/current assessment, and opens the same Module 4 relationship review without another analysis click.
5. Verify manual-first then sourced converges to one relation if both resolve to the same Candidate.
6. Confirm professional evidence can improve role/seniority assessment but cannot manufacture skills or complete years of experience.
7. Confirm a Candidate with a canonical phone shows call-ready while the same match score remains unchanged if only phone/contact truth changes.
8. Reopen/reapprove the Job. Confirm historical match remains visible, current match becomes stale, and the prior shortlist decision requires explicit reconfirmation after reanalysis.
9. Repeat **Add to job** and **Review match** for unchanged contexts, including stale and previously failed/missing states. Confirm there is no silent refresh/provider retry; the detail page shows **Refresh match** for an existing current match or **Initial assessment unavailable** plus **Retry analysis** when no current match exists.
10. With Gemini unavailable or intentionally failed, confirm deterministic fallback remains visible, at most one provider call occurs for the new context, and no automatic provider retry occurs.

The shared workflow under test is: **Attach/Review match → automatic initial assessment → recruiter review**.

## Secret / PII audit

Confirm browser responses, source, and logs contain no Gemini/API keys and Module 4 does not duplicate Candidate email/phone values. Inspect the Gemini matching prompt to confirm Candidate names/contact values/protected attributes are excluded.

## Current assistant-environment checkpoint

At implementation time in the assistant environment:

- Modules 0–4 structural validators: PASS.
- Python compile: PASS.
- Ruff and strict mypy: PASS.
- Full backend suite: 157 passed, 24 environment-gated skips after adding the attachment workflow and concurrency tests.
- Module 4 real PostgreSQL tests are present but skipped because `TEST_DATABASE_URL`/PostgreSQL tooling is unavailable here.
- Frontend lint, typecheck, full Vitest suite (33 tests), and production Next build: PASS.
