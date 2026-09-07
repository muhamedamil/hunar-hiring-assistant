# Module 5 — Outreach — Validation

## Automated gates

Run from the repository root:

```bash
python scripts/validate_module_0.py
python scripts/validate_module_1.py
python scripts/validate_module_2.py
python scripts/validate_module_3.py
python scripts/validate_module_4.py
python scripts/validate_module_5.py

cd apps/api
uv sync --all-extras --frozen
uv run python -m compileall -q app tests
uv run ruff check app tests
uv run mypy app
uv run pytest -q

cd ../..
npm ci
npm run web:lint
npm run web:typecheck
npm run web:test
NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8000 npm run web:build
git diff --check
```

## Disposable PostgreSQL/Supabase gate

Reset or migrate a disposable database through
`20260906213000_module_5_outreach.sql`, then run:

```bash
cd apps/api
TEST_DATABASE_URL=postgresql://postgres:postgres@127.0.0.1:54322/postgres \
  uv run pytest -q tests/test_outreach_postgres.py
```

These tests verify RLS/revokes, constraints, immutable UPDATE/DELETE behavior, and concurrent
identical confirmation. They are skipped, not passed, when `TEST_DATABASE_URL` is absent.

## Manual UI E2E

1. Create one manual Candidate and one Apollo-resolved Candidate with canonical phones.
2. Attach each to a READY Job, complete/refresh matching, and shortlist the current match.
3. Confirm both show the same **Prepare voice outreach** action and same preparation page.
4. Verify Candidate, role, approved version, masked phone, and exact Job questions.
5. Edit, add, remove, reorder, then reset questions; verify Job defaults remain unchanged.
6. Confirm twice and verify both confirmations resolve to one request.
7. Change question order/options and reconfirm from a fresh preparation; verify a distinct request.
8. Change the phone while preparation is open; verify confirmation returns
   `OUTREACH_PREPARATION_STALE`.
9. Change phone after confirmation; verify history remains and reads `STALE`.
10. Change email only while keeping phone/match inputs stable; verify readiness remains
    `READY_FOR_EXECUTION`.
11. Reopen/reapprove the Job or refresh/reconfirm a new match; verify historical outreach remains
    immutable and becomes `STALE`.
12. Verify list/detail pages never display a full phone and no call is placed.
