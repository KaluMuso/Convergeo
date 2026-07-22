> **Prepend `prompts/_header.md`.** Branch from + PR against **`master`**. **Touch ONLY the files below.** **Test-infra fix — NO product code changes.** Prove determinism before reporting.

# CR-F — Stabilize the flaky KYC CAS tests that block merges

## Finding

`services/api/tests/test_kyc_state.py::TestKycVendorCas` fails **intermittently** on the CI **"RLS isolation matrix"** job — all four tests (`test_concurrent_approve_exactly_one_wins`, `test_approve_happy_path_succeeds`, `test_illegal_transition_rejected_by_guard`, `test_concurrent_reject_exactly_one_wins`) failing with `app.errors.AppError: Vendor not found` raised from `_load_vendor` (`app/services/kyc/state_machine.py`). It **passed** on PR #469 and **failed** on PR #472 with identical code — i.e. flaky, and it intermittently blocks unrelated PRs from merging. It's also why two Cursor agents independently reached in and edited this file.

**Root-cause hypotheses (confirm before fixing):**
- The `db` fixture is **module-scoped** and only resets/seeds `if not schema_ready(conn)` — it may `DROP SCHEMA public CASCADE`, re-apply migrations, and `seed_matrix_fixtures`. If the RLS-matrix job runs multiple Postgres-backed test modules against the **same database** (serially or in parallel), another module resetting the schema mid-run wipes the seeded `VENDOR_OWNER_ID` profile and the freshly-inserted vendor row → `_load_vendor` finds nothing.
- `_seed_pending_kyc_vendor` INSERTs a vendor whose `owner_user_id` FKs `profiles(VENDOR_OWNER_ID)`; if that profile seed is absent for the run, the row can't be relied on.
- The existing `_PG_LOCK` serializes the fake client's SQL within a process but does nothing for cross-module DB isolation or a missing seed row.

## Required fix

- **Root-cause it first**, then make these tests deterministic. Likely combination:
  - Add a **pre-condition assertion** immediately after `_seed_pending_kyc_vendor` that the vendor row is actually readable via the wrapper — so the failure surfaces the true cause (missing seed / schema reset) instead of a late "Vendor not found".
  - Make the fixture **defensively ensure** the `VENDOR_OWNER_ID` profile + matrix fixtures exist before each test (re-seed if absent), and ensure inserts are committed (psql autocommit) and visible before the transition runs.
  - If the RLS-matrix job shares one DB across modules, **isolate this module** (own schema/search_path, or run it in its own DB step, or guard the schema-reset so it can't race) so a sibling module's reset can't wipe these rows. Adjust the CI job only if isolation genuinely requires it.
- Do **not** change `app/services/kyc/*` product code. The state machine is correct; the test harness is flaky.

## Files (ONLY)

- `services/api/tests/test_kyc_state.py`
- If the shared schema-reset/seed lives in a fixture module: `services/api/tests/conftest.py` and/or the matrix-fixture helper it imports (`seed_matrix_fixtures`) — **fixtures only**
- Only if DB isolation must change: the relevant `.github/workflows/*.yml` step that runs the "RLS isolation matrix" job (minimal change, documented)
- **Do NOT touch** product code, migrations, or other test files.

## Tests (RUN)

- Reproduce the flake, then prove the fix: run the CAS class **repeatedly** (e.g. `uv run pytest tests/test_kyc_state.py::TestKycVendorCas --count=20` via `pytest-repeat`, or a shell loop) → 0 failures. Run alongside another Postgres-backed module if the root cause is cross-module. Paste the repeat run + the pre-condition assertion in action.

## Report

STATUS / FILES / DEVIATIONS / TESTS (paste the repeat-run result + confirmed root cause) / EXCERPTS (the isolation/seed-guard change) / QUESTIONS.
