# CI pipeline & branch protection

Vergeo5 gates every PR via [`.github/workflows/ci.yml`](../../.github/workflows/ci.yml). This document describes what each job protects and how to configure GitHub branch protection so required checks cannot be admin-overridden (the process fix for the 0009 migration escape).

## Jobs

| Job name                      | Workflow job id | What it gates                                                                                                                                                                                                      |
| ----------------------------- | --------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| JavaScript / TypeScript       | `js`            | Turbo-affected lint, typecheck, test, build across Next.js apps and packages                                                                                                                                       |
| Python API                    | `python`        | `ruff`, `mypy`, unit pytest (no live database)                                                                                                                                                                     |
| Migration replay (fast)       | `migrations`    | Dockerless Postgres 16 replay of `supabase/migrations/00*.sql` via [`scripts/ci/migration-replay.sh`](../../scripts/ci/migration-replay.sh) — catches immutability, ordering, and column-reference bugs in seconds |
| Database / typegen drift      | `db`            | Full Supabase stack `db reset --no-seed`, typegen, and `git diff` on `packages/types/src/db.ts`                                                                                                                    |
| RLS isolation matrix          | `rls`           | Live stack + `uv run pytest services/api/tests/rls` (M03-P09 suite)                                                                                                                                                |
| Secret scan (gitleaks)        | `secret-scan`   | Repository secret scan with [`.gitleaks.toml`](../../.gitleaks.toml) allowlists for docs/fixtures only                                                                                                             |
| Dependency audit              | `deps-audit`    | `pnpm audit` + `pip-audit` (warn-only until M15-P05)                                                                                                                                                               |
| i18n hardcoded strings (warn) | `i18n-lint`     | ESLint no-hardcoded-strings (non-blocking)                                                                                                                                                                         |

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
- `secret-scan`

`deps-audit` and `i18n-lint` are informational (warn / continue-on-error) and should **not** be required until their fail-on-high behavior lands.

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
