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

The [`CI`](.github/workflows/ci.yml) workflow must be green before merging to `master`. In GitHub branch protection, mark these jobs as **required**:

| Job           | Purpose                                                              |
| ------------- | -------------------------------------------------------------------- |
| `js`          | Turbo-affected lint, typecheck, test, build                          |
| `python`      | API ruff, mypy, unit pytest                                          |
| `migrations`  | Fast Dockerless migration replay (`scripts/ci/migration-replay.sh`)  |
| `db`          | Supabase `db reset` + typegen drift on `packages/types/src/db.ts`    |
| `rls`         | RLS isolation matrix (`services/api/tests/rls`) against a live stack |
| `secret-scan` | gitleaks with [`.gitleaks.toml`](.gitleaks.toml)                     |

Also enable **“Do not allow bypassing the above settings”** so admins cannot merge past a red required check (the process fix for the 0009 migration escape). See [`docs/ops/ci.md`](docs/ops/ci.md) for setup details.

## Commit conventions

Conventional commits enforced via commitlint + lefthook. Example: `feat: add cart summary`.
