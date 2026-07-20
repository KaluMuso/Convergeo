# CI pipeline & branch protection

Vergeo5 gates every PR via [`.github/workflows/ci.yml`](../../.github/workflows/ci.yml) and
performance budgets via [`.github/workflows/perf.yml`](../../.github/workflows/perf.yml).
This document describes what each job protects and how to configure GitHub branch protection
so required checks cannot be admin-overridden (the process fix for the 0009 migration escape).

## Jobs (`ci.yml`)

| Job name                      | Workflow job id  | What it gates                                                                                                                                                                                                      | Blocking? |
| ----------------------------- | ---------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | --------- |
| JavaScript / TypeScript       | `js`             | Turbo-affected lint, typecheck, test, build across Next.js apps and packages                                                                                                                                       | yes       |
| Python API                    | `python`         | `ruff`, `mypy`, unit pytest (no live database)                                                                                                                                                                     | yes       |
| Migration replay (fast)       | `migrations`     | Dockerless Postgres 16 replay of `supabase/migrations/00*.sql` via [`scripts/ci/migration-replay.sh`](../../scripts/ci/migration-replay.sh) — catches immutability, ordering, and column-reference bugs in seconds | yes       |
| Database / typegen drift      | `db`             | Full Supabase stack `db reset --no-seed`, typegen, and `git diff` on `packages/types/src/db.ts`                                                                                                                    | yes       |
| RLS isolation matrix          | `rls`            | Live stack + `uv run pytest services/api/tests/rls` (M03-P09 suite)                                                                                                                                                | yes       |
| Secret scan (gitleaks)        | `secret-scan`    | Pinned gitleaks CLI (≥8.28) + [`.gitleaks.toml`](../../.gitleaks.toml); self-test plants a synthetic AWS key and asserts non-zero exit; n8n plaintext-secret static guard                                          | **yes**   |
| Dependency audit              | `deps-audit`     | `pnpm audit --audit-level=high` (with documented allowlist) + `pip-audit`                                                                                                                                          | yes       |
| Security gates                | `security-gates` | Authz matrix / OWASP-lite probes                                                                                                                                                                                   | yes       |
| i18n hardcoded strings (warn) | `i18n-lint`      | ESLint no-hardcoded-strings                                                                                                                                                                                        | no (warn) |

### Perf workflow (`perf.yml`)

| Check             | Blocking? | Notes                                                                                      |
| ----------------- | --------- | ------------------------------------------------------------------------------------------ |
| i18n completeness | yes       | Fast offline gate before stack boot                                                        |
| Bundle guard      | yes       | ≤150 KB gz first-load JS (CLAUDE.md #7)                                                    |
| Image lint        | yes       | Next/Image + format discipline                                                             |
| Lighthouse CI     | **yes**   | `lighthouserc.json` assertMatrix — a11y/SEO/best-practices + CI perf/LCP floors (see file) |

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
- `deps-audit`
- `security-gates`
- Performance workflow: `Bundle, image lint & Lighthouse` (`perf`)

`i18n-lint` remains informational (warn / continue-on-error) until the hardcoded-string debt is cleared.

### Do not allow bypassing

Enable **“Do not allow bypassing the above settings”** (and restrict who can push directly to `master`). Admin override of a red `db` or `migrations` check is what let the 0009 migration bugs merge; this setting is the founder action that closes that gap. It cannot be toggled from repository code.

## Local commands

```bash
# Secret scan (same binary pin as CI)
GITLEAKS_VERSION=8.28.0
curl -sSfL "https://github.com/gitleaks/gitleaks/releases/download/v${GITLEAKS_VERSION}/gitleaks_${GITLEAKS_VERSION}_linux_x64.tar.gz" \
  | sudo tar -xz -C /usr/local/bin gitleaks
bash scripts/ci/gitleaks-self-test.sh
bash scripts/ci/validate-n8n-no-plaintext-secrets.sh
gitleaks detect --source . --config .gitleaks.toml --verbose --redact

# Fast migration pre-flight (requires Postgres 16 + pgvector reachable via PG*)
bash scripts/ci/migration-replay.sh

# Full stack + typegen drift (same as db job)
export SEND_SMS_HOOK_SECRET='v1,whsec_Y2ktZHVtbXktc2VuZC1zbXMtaG9vay1zZWNyZXQtMDAw'
export SUPABASE_AUTH_EXTERNAL_GOOGLE_CLIENT_ID='ci-dummy-google-client-id'
export SUPABASE_AUTH_EXTERNAL_GOOGLE_SECRET='ci-dummy-google-secret'
export SUPABASE_AUTH_EXTERNAL_APPLE_SECRET='ci-dummy-apple-secret'
supabase db start && supabase db reset --no-seed && bash scripts/gen-types.sh
git diff --exit-code packages/types/src/db.ts

# RLS matrix
supabase db start && supabase db reset
export SUPABASE_DB_URL='postgresql://postgres:postgres@127.0.0.1:54322/postgres'
cd services/api && uv run pytest tests/rls -q
```

## Workflow validation

```bash
actionlint .github/workflows/*.yml
bash -n scripts/ci/migration-replay.sh
bash -n scripts/ci/gitleaks-self-test.sh
bash -n scripts/ci/validate-n8n-no-plaintext-secrets.sh
```

## Before / after (RC-06)

| Gate        | Before                                      | After                                      |
| ----------- | ------------------------------------------- | ------------------------------------------ |
| Secret scan | `continue-on-error: true` (could not fail)  | Blocking CLI + planted-secret self-test    |
| Lighthouse  | All assertions `warn` + `continue-on-error` | `error` assertMatrix (checkout SEO waived) |
| Docs        | Claimed secret-scan required while advisory | `ci.md` matches YAML                       |

## Rollback if an external scanner/runtime is unavailable

If **gitleaks GitHub releases** or **Chrome/LHCI** are down (tooling outage, not a score dip):

1. Revert only the affected step to a temporary `continue-on-error: true` with a dated comment linking the outage.
2. Do **not** broaden `.gitleaks.toml` allowlists or weaken Lighthouse floors to greenwash.
3. Re-enable blocking within one business day of the outage clearing.
