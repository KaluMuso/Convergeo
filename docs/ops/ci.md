# CI pipeline & branch protection

Vergeo5 gates every PR via [`.github/workflows/ci.yml`](../../.github/workflows/ci.yml). This document describes what each job protects and how to configure GitHub branch protection so required checks cannot be admin-overridden (the process fix for the 0009 migration escape).

## Jobs

| Job name                   | Workflow job id       | What it gates                                                                                                                                                                                                                        |
| -------------------------- | --------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| JavaScript / TypeScript    | `js`                  | Turbo-affected lint, typecheck, test, build across Next.js apps and packages                                                                                                                                                         |
| Python API                 | `python`              | `ruff`, `mypy`, unit pytest (no live database)                                                                                                                                                                                       |
| Ask Vergeo grounding evals | `ask-evals`           | RAG grounding eval set — zero fabricated listings (M06-P05)                                                                                                                                                                          |
| Staging guards             | `staging-guards`      | Asserts staging/prod safety invariants in config before deploy                                                                                                                                                                       |
| Security gates             | `security-gates`      | `scripts/ci/check-headers.mjs` + `tests/test_authz_matrix.py` (headers/CSP + route×role authz)                                                                                                                                       |
| Migration replay (fast)    | `migrations`          | Dockerless Postgres 16 replay of `supabase/migrations/00*.sql` via [`scripts/ci/migration-replay.sh`](../../scripts/ci/migration-replay.sh) — catches immutability, ordering, duplicate-prefix, and column-reference bugs in seconds |
| Database / typegen drift   | `db`                  | Full Supabase stack `db reset --no-seed`, typegen, and `git diff` on `packages/types/src/db.ts`                                                                                                                                      |
| RLS isolation matrix       | `rls`                 | Live stack + `uv run pytest services/api/tests/rls` (M03-P09 suite) + curated DB-backed integration tests                                                                                                                            |
| Money DB triggers          | `money-db-triggers`   | Release / release-accounting / reconcile DB-trigger tests, each against a freshly-reset schema                                                                                                                                       |
| COD container smoke        | `cod-container-smoke` | Boots the built API image and smoke-checks the COD path                                                                                                                                                                              |
| Secret scan (gitleaks)     | `secret-scan`         | Repository secret scan with [`.gitleaks.toml`](../../.gitleaks.toml) allowlists for docs/fixtures only — **blocking** (fails CI on any finding)                                                                                      |
| Dependency audit           | `deps-audit`          | `pnpm audit` + `pip-audit`, **fail-on-high** (blocking since M15-P05; one justified allowlist for `tmp`/`@lhci/cli`)                                                                                                                 |
| Performance budgets        | `perf` (perf.yml)     | Bundle guard (≤150KB gz, blocking) + image lint (blocking) + i18n completeness sweep (blocking) + Lighthouse (advisory, see `docs/ops/performance-budgets.md`)                                                                       |

### Job ordering

1. **`migrations`** — fast pre-flight; fails on the first migration that does not apply.
2. **`db`** — depends on `migrations`; authoritative stack reset + committed type drift check.
3. **`rls`** — parallel with `db`; boots its own stack, resets with seed, runs the RLS matrix.

The `db` job requires dummy auth-hook/OAuth env vars (see workflow comments) because `supabase/config.toml` enables `send_sms` and Google OAuth via `env()` substitution.

## Required checks (branch protection)

Mark these jobs as **required** on `master` in GitHub → Settings → Branches → Branch protection rules:

- `js`
- `python`
- `migrations`
- `db`
- `rls`
- `secret-scan` (now blocking — `continue-on-error` removed)
- `deps-audit` (now blocking — fail-on-high)
- `security-gates`
- `money-db-triggers`

The performance-budgets job (`perf.yml`) is blocking on bundle/image/i18n and advisory on Lighthouse; require it once a stable measurement target exists. `i18n-lint` (the ESLint variant) remains informational; the blocking i18n completeness sweep runs inside `perf`.

### Do not allow bypassing

Enable **“Do not allow bypassing the above settings”** (and restrict who can push directly to `master`). Admin override of a red `db` or `migrations` check is what let the 0009 migration bugs merge; this setting is the founder action that closes that gap. It cannot be toggled from repository code.

## Local commands

```bash
# Fast migration pre-flight (requires Postgres 16 + pgvector reachable via PG*)
bash scripts/ci/migration-replay.sh

# Full stack + typegen drift (same as db job)
export SEND_SMS_HOOK_SECRET='v1,whsec_Y2ktZHVtbXktc2VuZC1zbXMtaG9vay1zZWNyZXQtMDAw'
export SUPABASE_AUTH_EXTERNAL_GOOGLE_CLIENT_ID='ci-dummy-google-client-id'
export SUPABASE_AUTH_EXTERNAL_GOOGLE_SECRET='ci-dummy-google-secret'
export SUPABASE_AUTH_EXTERNAL_APPLE_SECRET='ci-dummy-apple-secret'
supabase db start && supabase db reset --no-seed && bash scripts/gen-types.sh
git diff --exit-code packages/types/src/db.ts

# RLS matrix (after M03-P09 lands)
supabase db start && supabase db reset
export SUPABASE_DB_URL='postgresql://postgres:postgres@127.0.0.1:54322/postgres'
cd services/api && uv run pytest tests/rls -q
```

## Workflow validation

```bash
actionlint .github/workflows/*.yml
bash -n scripts/ci/migration-replay.sh
```
