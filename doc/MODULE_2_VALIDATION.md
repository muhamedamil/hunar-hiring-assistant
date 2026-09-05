# Module 2 Validation Record

## Scope

Module 2 implements the global Candidate Core shared by manual Task-1 candidates and future
Task-2 provider-sourced people, on top of the qualified Module 0/1 repository.

## Frozen invariants

- Candidate identity is global and contains no Job relationship.
- email and phone are optional strong identifiers.
- email identity is case-insensitive; phone is canonical E.164 when present.
- provider/person identity lives in `candidate_external_identities`, not a single Candidate `source`.
- provider/person identity rows are immutable after insertion.
- same name/title/company/location never auto-merges Candidates.
- conflicting strong identities fail closed with zero automatic merge.
- external observations fill missing canonical fields only and never overwrite populated fields.
- identical provider replay is idempotent and does not increment revision.
- a bounded database race-reconciliation pass completes the original provider resolution instead of
  merely returning whichever Candidate won the uniqueness race.
- Candidate mutations use `expected_revision` plus a locked row.
- Candidate Core performs zero external HTTP calls and does not use the work-item worker.
- Candidate list projection exposes only `has_email` / `has_phone`, not contact values.
- SQLAlchemy hides bound parameters and structured logging redacts email/phone keys.

## Baseline repairs completed before Module 2

The latest user ZIP had qualification-document drift only. The implementation repairs:

- Module 0 validator migration filename;
- Module 1 validator plan path under `doc/`;
- README document layout;
- accidental text corruption in `doc/MODULE_1_VALIDATION.md`.

No Module 0/1 runtime state or workflow semantics were changed by these repairs.

## Validation completed in this environment

```text
python scripts/validate_module_0.py
PASS

python scripts/validate_module_1.py
PASS

python scripts/validate_module_2.py
PASS — 7 invariant groups

python -m compileall -q apps/api/app
PASS

python -m pytest -q
73 passed, 14 skipped
```

The environment-gated skips are:

- 1 valid-phone normalization test because the sandbox cannot download `phonenumbers`;
- 7 Module 2 real-PostgreSQL tests requiring `TEST_DATABASE_URL`;
- 3 Module 1 real-PostgreSQL tests requiring `TEST_DATABASE_URL`;
- 3 Module 0 real-PostgreSQL tests requiring `TEST_DATABASE_URL`.

The backend project now explicitly declares `phonenumbers` and `email-validator`; a normal local
`pip install -e ".[dev]"` installs them.

## Environment-limited local completion gates

From repository root:

```powershell
supabase start
supabase db reset
supabase status
```

Backend:

```powershell
cd apps\api
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
$env:TEST_DATABASE_URL="postgresql://postgres:postgres@127.0.0.1:54322/postgres"
ruff check .
mypy app
python -m pytest -q
```

Expected after dependencies + migrated local Supabase are available:

```text
87 passed
```

Frontend from repository root:

```powershell
npm install
npm run web:lint
npm run web:typecheck
npm run web:test
npm run web:build
```

The frontend test suite now includes explicit Candidate list, empty-state, list-error, detail-load,
and detail-error coverage in addition to Candidate create/edit/duplicate/revision-conflict tests.

## Manual UI qualification

1. Open `/candidates/new`.
2. Create `Sarah Ahmed` with no email/phone; creation must succeed at revision 0.
3. Create another same-name Candidate with no strong contact; it must create a distinct Candidate.
4. Create a Candidate with a valid email and international phone; detail should show canonical E.164.
5. Attempt another Candidate with the same email using different case; UI must show the duplicate
   error and **Open existing candidate** link.
6. Attempt phone without `+country-code`; client and backend must reject it without guessing region.
7. Open Candidate detail, edit profile, save, and confirm revision increments.
8. Open the same Candidate in two tabs; save Tab A, then save stale Tab B. Tab B must receive
   `CANDIDATE_REVISION_CONFLICT` instead of overwriting Tab A.
9. Confirm `/candidates` shows only contact availability, not raw email/phone.
10. Confirm Candidate UI has no match score, shortlist, people-provider search, or Hunar outreach.

## Database qualification

After `supabase db reset`, verify:

- `candidates` and `candidate_external_identities` exist;
- case-insensitive email uniqueness is enforced;
- E.164 phone uniqueness is enforced;
- `(provider, external_person_id)` uniqueness is enforced;
- provider identity rows reject direct `UPDATE` and `DELETE`;
- both Candidate tables have RLS enabled;
- `anon` and `authenticated` have no direct table access;
- concurrent same-email manual creates converge to one Candidate + one controlled duplicate result;
- concurrent same provider identity resolutions converge to one Candidate;
- concurrent distinct provider identities sharing one strong email converge to one Candidate and
  preserve both provider identity links;
- a provider/email identity conflict leaves no partial mutation.

## Release decision

Module 2 implementation is complete when repository-level validation remains green. Final
**QUALIFIED / FROZEN** status requires the local Supabase, full backend toolchain, frontend
lint/typecheck/tests/build, and manual Candidate UI smoke above.
