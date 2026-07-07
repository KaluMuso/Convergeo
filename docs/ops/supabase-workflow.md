# Supabase workflow (Vergeo5)

Local-dev and CI reference for the Supabase CLI pipeline introduced in M01-P08. Domain tables and RLS land in M03 pebbles — this repo only ships `0001_extensions.sql` until then.

## Prerequisites

- [Supabase CLI](https://supabase.com/docs/guides/cli) on your PATH (or `npx supabase`)
- Docker Engine running (local stack uses containers)

## Local stack

```bash
# Start Postgres + Supabase services (first run pulls images)
supabase start

# Apply all migrations from scratch (drops data; seeds disabled in config)
supabase db reset --no-seed

# Stop when done
supabase stop
```

Verify extensions after reset:

```bash
docker exec supabase_db_vergeo5 psql -U postgres -c \
  "select extname from pg_extension where extname in ('pgcrypto','pg_trgm','vector') order by extname;"
```

## Migrations

| Rule                     | Detail                                                                                                |
| ------------------------ | ----------------------------------------------------------------------------------------------------- |
| **Naming**               | One file per pebble: `NNNN_slug.sql` (e.g. `0002_identity_vendors.sql`)                               |
| **Pre-assigned numbers** | 0002 identity/vendors · 0003 catalog · 0004 services/events · 0005 orders · 0008 config · 0009 search |
| **Additive-only**        | After M03-P08 merges, never edit shipped migrations — add a new numbered file                         |
| **Contents (M01)**       | `0001_extensions.sql` only: `pgcrypto`, `pg_trgm`, `vector`                                           |

Create a new migration from schema drift:

```bash
supabase db diff -f NNNN_slug
# Review the generated file under supabase/migrations/, then commit
```

## Type generation

Committed types in `packages/types/src/db.ts` are the source of truth. Regenerate after any migration change:

```bash
# Local stack must be running (supabase start / db reset)
bash scripts/gen-types.sh
# or
pnpm --filter @vergeo/types gen:types
```

**Staging / remote project** (requires Supabase login + project ref):

```bash
SUPABASE_PROJECT_ID=<project-ref> bash scripts/gen-types.sh
# equivalent: supabase gen types typescript --project-id <project-ref> > packages/types/src/db.ts
```

CI runs `supabase db reset`, regenerates types, and fails if `packages/types/src/db.ts` drifts (`git diff --exit-code`).

## Push to staging / production

```bash
# Link once per machine (interactive)
supabase link --project-ref <project-ref>

# Apply pending migrations to the linked remote database
supabase db push
```

For non-interactive CI deploys, set:

- `SUPABASE_ACCESS_TOKEN`
- `SUPABASE_DB_PASSWORD`
- `SUPABASE_PROJECT_ID` (or use `supabase link` in a prior step)

## Environment variables (names only)

| Variable                    | Used by                  | Notes                                                        |
| --------------------------- | ------------------------ | ------------------------------------------------------------ |
| `SUPABASE_URL`              | API, Next.js server      | Project API URL                                              |
| `SUPABASE_ANON_KEY`         | Browser / customer app   | **Only** browser-safe Supabase key                           |
| `SUPABASE_SERVICE_ROLE_KEY` | FastAPI (`services/api`) | **Server-side only** — bypasses RLS; never expose to clients |
| `SUPABASE_ACCESS_TOKEN`     | CLI in CI                | Personal access token for `db push` / remote typegen         |
| `SUPABASE_DB_PASSWORD`      | CLI in CI                | Remote Postgres password                                     |
| `SUPABASE_PROJECT_ID`       | `scripts/gen-types.sh`   | Remote project ref for staging typegen                       |

Never commit project refs, tokens, or keys — placeholders and env names only in the repo.

## Quick checklist (fresh session)

1. `supabase start` (or `supabase db reset --no-seed`)
2. Confirm extensions query returns `pgcrypto`, `pg_trgm`, `vector`
3. After migration edits: `bash scripts/gen-types.sh` and commit `packages/types/src/db.ts`
4. `pnpm --filter @vergeo/types typecheck`
