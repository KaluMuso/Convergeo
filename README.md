# Vergeo5

Mobile-first, multi-vendor commerce-powered discovery platform for Zambia.

## Prerequisites

- Node.js 20 (see `.nvmrc` / `.node-version`)
- [pnpm](https://pnpm.io/) 9 (`corepack enable`)

## Quick start

```bash
pnpm i
pnpm dev
```

## Workspace layout

```
apps/customer   apps/vendor   apps/admin        # Next.js 15 apps
services/api                                     # FastAPI backend
packages/ui     packages/types  packages/config  packages/i18n
supabase/migrations  supabase/seed  supabase/tests
infra/          .github/workflows/
```

## Commands

| Command                | Description                      |
| ---------------------- | -------------------------------- |
| `pnpm dev`             | Start all dev servers (turbo)    |
| `pnpm build`           | Build all packages               |
| `pnpm lint`            | Lint all packages                |
| `pnpm typecheck`       | Type-check all packages          |
| `pnpm test`            | Run all tests                    |
| `make dev`             | Same as `pnpm dev`               |
| `make verify-scaffold` | Run scaffold verification script |

Copy `.env.example` to `.env.local` (or service-specific env files) and fill in values locally — never commit secrets.

## Required CI checks

The [`CI`](.github/workflows/ci.yml) and [`Performance budgets`](.github/workflows/perf.yml) workflows must be green before merging to `master`. In GitHub branch protection, mark these jobs as **required**:

| Job                   | Purpose                                                                    |
| --------------------- | -------------------------------------------------------------------------- |
| `js`                  | Turbo-affected lint, typecheck, test, build                                |
| `python`              | API ruff, mypy, unit pytest                                                |
| `ask-evals`           | Deterministic Ask Vergeo grounding evals                                   |
| `staging-guards`      | Staging separation, seed, and config syntax guards                         |
| `secret-scan`         | Blocking gitleaks + n8n plaintext-secret scan                              |
| `deps-audit`          | Blocking pnpm/pip audit, with documented accepted advisory allowlist       |
| `security-gates`      | Headers manifest + route x role authz matrix                               |
| `migrations`          | Fast Dockerless migration replay (`scripts/ci/migration-replay.sh`)        |
| `db`                  | Supabase `db reset` + typegen drift on `packages/types/src/db.ts`          |
| `rls`                 | Blocking curated DB-backed integration set; demo seed + broad RLS advisory |
| `money-db-triggers`   | Release/accounting/reconcile trigger integration                           |
| `cod-container-smoke` | Real API container COD smoke, heavy steps path-filtered                    |
| `perf`                | Bundle guard, image lint, and blocking Lighthouse CI                       |

`i18n-lint` is intentionally warning-only in `ci.yml`. Also enable **“Do not allow bypassing the above settings”** so admins cannot merge past a red required check (the process fix for the 0009 migration escape). See [`docs/ops/ci.md`](docs/ops/ci.md) for setup details.

## Commit conventions

Conventional commits enforced via commitlint + lefthook. Example: `feat: add cart summary`.
