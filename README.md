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

## Commit conventions

Conventional commits enforced via commitlint + lefthook. Example: `feat: add cart summary`.
