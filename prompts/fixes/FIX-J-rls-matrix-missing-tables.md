> **Prepend `prompts/_header.md`.** Branch from + PR against **`master`**. **Touch ONLY the files below.** **⚙ do NOT use `git stash`.** **No migration** (tests only). Run the FULL `uv run pytest` before reporting.

# FIX-J — RLS test-matrix coverage gaps (🟢 hygiene / RC-07)

## Findings (from `docs/production-readiness/2026-07-21/code-reconciliation-since-audits.md` R-5 + 2026-07-19 vision-audit §5)

- Tables **policied but absent** from the RLS test registry `services/api/tests/rls/test_matrix.py`: `event_categories`, `product_relations`, `service_reviews` (plus legacy `embedding_jobs`, `reconciliation_reports`). `test_no_untested_tables` tolerates them only via allowlist/skip.

## Required fix

Add each table to the matrix with its **real** policy expectations (public-read / owner-write / admin-all / service-role-write) — verified against the actual `create policy` statements in `supabase/migrations/*`, not invented. Remove any now-unnecessary allowlist entries so the registry is the single source of truth.

## Files (ONLY)

- `services/api/tests/rls/test_matrix.py` (+ any small helper in `services/api/tests/rls/`)
- **Do NOT** change table policies, migrations, or db.ts — tests only.

## Tests (RUN)

`test_no_untested_tables` green with the five tables covered; the runtime RLS matrix exercises customer/vendor/admin isolation as policied. `uv run pytest -k rls` then the full suite.

## Report

STATUS/FILES/DEVIATIONS/TESTS/EXCERPTS (the added matrix rows + the policy lines they mirror)/QUESTIONS.
