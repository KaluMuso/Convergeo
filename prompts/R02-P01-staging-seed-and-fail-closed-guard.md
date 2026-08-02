> **Prepend `prompts/_header.md` (PROJECT HEADER) above this prompt.** Composer sessions share no memory — the header is required context.

# R02-P01 — Staging synthetic seed passes + the schema guard fails closed `[CODE+OPS]`

## 1. Context
**Wave W1 (runtime truth).** Source: `docs/production-readiness/2026-08-01/vision-audit-rescore.md` §6.1 and §6.3.

Two defects block staging from producing trustworthy evidence:

1. **The staging schema guard reports OK when it verified nothing.** `scripts/ci/check-staging-schema.sh:36` reads:
   ```sh
   issues="$("${PSQL[@]}" -At -f "$SQL_FILE" | grep -E '^FAIL ' || true)"
   ```
   The `|| true` covers the **whole pipeline**, so a `psql` connection failure is swallowed exactly like "no FAIL rows found" and the script proceeds to print `OK:` and `exit 0`. Observed live in Deploy staging run **30695764799** (2026-08-01T10:31Z): the log carries `psql: error: … Network is unreachable` immediately followed by `OK: RLS enabled on public tables; exposed views use security_invoker (or none exposed)`.
2. **The runner cannot reach the staging database.** The same run failed at `scripts/seed_staging.py` with `Network is unreachable` against an IPv6 address (`2a05:d018:…`). GitHub-hosted runners have no IPv6 egress; Supabase's **direct** connection is IPv6-only, so the pooler (IPv4) URL is required.

A guard that passes without checking is worse than no guard, because it manufactures evidence — every downstream readiness claim that cites it is void.

**Type:** `[CODE+OPS]`.

## 2. Objective & scope
Make the staging schema guard **fail closed**, and make the synthetic seed reach the staging database.
**Non-goals:** changing what the guard checks; new seed data shapes; touching production.

## 3. Files (edit ONLY these)
- `scripts/ci/check-staging-schema.sh`
- `.github/workflows/deploy-staging.yml` (connection URL wiring only)
- `scripts/seed_staging.py` (only if its error path needs the same fail-closed treatment)
- `services/api/tests/test_staging_guards.py` **or** `scripts/ci/test-staging-guards.sh` — wherever the existing self-test lives

## 4. Implementation spec
- Capture `psql`'s exit status **separately** from the `grep`. Suggested shape:
  ```sh
  set -euo pipefail
  raw="$("${PSQL[@]}" -At -f "$SQL_FILE")" || die "cannot reach staging database (psql exited $?)"
  issues="$(printf '%s\n' "$raw" | grep -E '^FAIL ' || true)"
  ```
  `|| true` may only ever absorb **grep's** "no matches" (exit 1) — never a query or connection failure.
- Audit the rest of the file for the same pattern; any other `cmd | grep … || true` gets the same treatment.
- Use the **session/transaction pooler** (IPv4) host for `STAGING_SUPABASE_DB_URL` in CI. Do not print the URL; secret names only.
- The seed script already refuses correctly (`ERROR: Cannot reach staging database at guarded URL`) — keep that behaviour, do not weaken it.

## 5. Security / conventions
- No secret values in the repo, in logs, or in the PR. Names only.
- Do not disable TLS or add `sslmode=disable` to make a connection succeed.

## 10. Tests (RUN before reporting)
- **The regression test that matters:** run the guard with a deliberately unreachable `DB_URL` and assert it **exits non-zero and does not print `OK:`**. This test must fail against the current script and pass after the fix.
- Run the guard against `vergeo-sandbox` with a valid pooler URL → passes, having actually queried.
- `bash scripts/ci/test-staging-guards.sh` green.
- `python3 scripts/seed_staging.py --env staging --apply` reaches the database and applies the `stg-rv-*` synthetic set.

## 11. Acceptance criteria / DoD
- [ ] A connection failure makes the schema guard **fail**; a test proves it.
- [ ] No `psql`/`grep` pipeline in the file can still mask a query error.
- [ ] Deploy staging's `workflow_dispatch` path completes the "Supabase migrations + checks" job.
- [ ] Synthetic seed applies to `vergeo-sandbox`; row counts reported.
- [ ] No secret values anywhere in the diff or logs.

## 12. IMPLEMENTATION REPORT
**PEBBLE:** R02-P01 — Staging seed + fail-closed schema guard
**STATUS:** COMPLETE | PARTIAL | BLOCKED
**FILES:** … · **DEVIATIONS:** … · **TESTS:** paste the unreachable-DB run showing non-zero exit, plus the successful seed · **EXCERPTS:** the corrected pipeline · **QUESTIONS:** …
