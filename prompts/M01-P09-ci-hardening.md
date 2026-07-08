> **Prepend `prompts/_header.md` (PROJECT HEADER) above this prompt.** Branch from and PR against **`master`**. Wave 5 runs 6 pebbles in parallel — **touch ONLY your files below**. **You are the SOLE owner of `.github/workflows/**` and `scripts/ci/**` this wave.**

# M01-P09 — CI hardening (migration validator + RLS gate + drift enforcement)

## 1. Context

**Wave 5 (parallel ×6).** This pebble closes the process gap that let two `0009` migration bugs ship (a generated column that wasn't immutable + a bad `search_rrf` column ref). Grounded against as-built `master`:

- **CI already exists** (`.github/workflows/ci.yml`): jobs `js`, `python`, `secret-scan` (gitleaks-action), `deps-audit`, `i18n-lint` (warn), and **`db`** (`supabase db start` → `db reset --no-seed` → `scripts/gen-types.sh` → `git diff --exit-code packages/types/src/db.ts`). `deploy-staging.yml` is a dispatch stub.
- **The `db` job was fixed this session** — it now sets dummy CI-only auth secrets (`SEND_SMS_HOOK_SECRET` in valid `v1,whsec_` form, `SUPABASE_AUTH_EXTERNAL_GOOGLE_*`, `SUPABASE_AUTH_EXTERNAL_APPLE_SECRET`) in its `env:` because `config.toml` enables the `send_sms` hook + Google OAuth via `env()` substitution and the stack cannot start without them. **PRESERVE this fix.** (Root cause of the 0009 escape: this job was red and PRs were merged via admin-override.)
- **Interface edge with M03-P09 (same wave):** M03-P09 ships an RLS isolation matrix as `uv run pytest services/api/tests/rls`, which needs a **live DB**. The `python` job has no database. **You wire the RLS suite into a DB-integrated job** (extend `db`, or add an `rls` job that boots the stack) and run it against the stack DB. M03-P09 owns the tests; you own the CI wiring. If M03-P09 hasn't merged when you open your PR, add the job pointing at `services/api/tests/rls` and note it will go green once M03-P09 lands.
- `.gitleaks.toml` referenced by the M01-P06 spec **does not exist** (gitleaks-action runs with defaults) — add a tuned allowlist config so docs/fixtures don't false-positive. `README.md` has no "Required CI checks" section yet.
  Spec basis: `docs/plan/02-pebbles/M01-foundations.md` §P06 (CI pipeline) — this hardens/completes it.

## 2. Objective & scope

Make CI actually block bad migrations and RLS regressions, and make the required-checks non-bypassable by policy.
**Non-goals:** no perf/Lighthouse budgets (M16-P01, W10), no real deploy (deploy-staging stays a stub), no E2E, no app/schema code.

## 3. Files (create/modify ONLY these)

- **Modify:** `.github/workflows/ci.yml` (preserve the db-job secret fix; add the RLS gate + the fast pre-flight replay below; ensure `db` + `rls` are in the required set) · `README.md` (**add a "Required CI checks" section** listing the job names to mark Required in branch protection, and a one-line note that admin-override of required checks is forbidden — this is the 0009-class fix)
- **Create:** `scripts/ci/migration-replay.sh` (fast, **Dockerless** pre-flight: spin a plain Postgres 16 service, install `pg_trgm`/`pgcrypto`/`vector`, apply a minimal Supabase shim [roles `anon`/`authenticated`/`service_role`/`supabase_admin`, `auth` schema + `auth.users`/`auth.uid()`/`auth.jwt()`], then apply `supabase/migrations/00*.sql` in order with `ON_ERROR_STOP=1` — fails on the first non-applying migration) · `.gitleaks.toml` (tuned allowlist) · `docs/ops/ci.md` (what each job gates + branch-protection setup)
  **Guardrail: nothing else. Do NOT edit `scripts/gen-types.sh`, migrations, `config.toml`, or app code.**

## 4. Implementation spec

- **Fast migration pre-flight (`migration-replay.sh` + a `migrations` job):** runs on a `postgres:16` service (or `services:` container), no Supabase CLI/Docker-in-Docker. This catches immutability/ordering/column bugs (exactly the `0009` class) in ~seconds, **before** the slower stack-based `db` job. The shim mirrors what Supabase provides. Job fails if any migration errors. (This is the guard that would have caught `0009` even when the full stack job is flaky.)
- **Keep the `db` job** as the authoritative `db reset` + typegen-drift gate (with the preserved secret env). Order: `migrations` (fast) → `db` (full).
- **RLS gate:** run `uv run pytest services/api/tests/rls` against a booted stack (reuse the `db` job's stack or a dedicated `rls` job with the same secret env + `supabase db start`/`reset` + seed). Set the DB URL via env for the tests.
- **Required-checks + policy:** in `README.md` + `docs/ops/ci.md`, list the jobs that MUST be green to merge (`js`, `python`, `db`, `migrations`, `rls`, `secret-scan`) and instruct enabling **branch protection with “Do not allow bypassing the above settings”** so a red required check can’t be admin-overridden (the failure mode that shipped 0009). _(You cannot toggle the GitHub setting from code — document it as the founder action.)_
- **`.gitleaks.toml`:** allowlist docs/fixtures/`.env.example` name-only patterns; must NOT allowlist real secret shapes.
- Least-privilege `permissions:`, `--frozen-lockfile`, `concurrency` cancel — keep as-is.

## 5–9. UI/UX · Responsiveness · Performance · SEO · Security

N/A except: workflows stay least-privilege; no secret values (dummy CI values only, already justified in the db job); gitleaks config doesn't weaken scanning.

## 10. Tests (RUN / verify before reporting)

- `actionlint .github/workflows/*.yml` (or YAML parse if unavailable) — paste output.
- Run `bash scripts/ci/migration-replay.sh` locally against `supabase/migrations/` — show it **applies 0001→0011 clean** (and, as a demonstration, that reverting a migration to a known-bad form makes it fail — then restore).
- `bash -n` the script; confirm the RLS command M03-P09 documents matches your job’s invocation.
- Confirm the `db` job still carries the auth-secret env (don’t regress the fix).

## 11. Acceptance criteria / DoD

- [ ] Fast Dockerless `migrations` pre-flight applies `0001→0011` and fails on any non-applying migration (0009-class caught).
- [ ] `db` job’s auth-secret env preserved; typegen drift still gated.
- [ ] RLS suite wired into a DB-integrated job (green once M03-P09 lands).
- [ ] Required-checks documented + branch-protection/no-bypass instruction (the anti-admin-override fix); `.gitleaks.toml` tuned.

## 12. IMPLEMENTATION REPORT

When finished, output an **Implementation Report** in exactly this format:
**PEBBLE:** M01-P09 — CI hardening
**STATUS:** COMPLETE | PARTIAL | BLOCKED
**FILES:** each path + one-line description
**DEVIATIONS:** (or "none")
**TESTS:** paste actionlint + the migration-replay run (clean 0001→0011 + the demonstrated fail-then-restore)
**EXCERPTS:** the `migrations` + `rls` job YAML + the shim head of `migration-replay.sh` — nothing else
**QUESTIONS:** (or "none")
