# Environments — Vergeo5

Secret **names only** — never commit values. See `infra/.env.example` for OCI runtime names.

## Matrix

| Concern        | Local                                         | Staging                                                                                        | Production                                         |
| -------------- | --------------------------------------------- | ---------------------------------------------------------------------------------------------- | -------------------------------------------------- |
| Customer app   | `pnpm dev --filter customer` (localhost:3000) | Vercel Preview on branch `staging` (`convergeo-customer`)                                      | Vercel Production (`vergeo5.com`)                  |
| Vendor app     | localhost:3001                                | Vercel Preview on branch `staging` (`convergeo-vendor`); optional `vendor.staging.vergeo5.com` | Vercel Production (`vendor.vergeo5.com`)           |
| Admin app      | localhost:3002                                | Vercel Preview on branch `staging` (`convergeo-admin`); optional `admin.staging.vergeo5.com`   | Vercel Production (`admin.vergeo5.com`, allowlist) |
| API            | localhost:8000 / compose                      | `api.staging.vergeo5.com` (OCI container `vergeo5-api-staging`)                                | `api.vergeo5.com`                                  |
| Postgres/Auth  | Supabase local or dev project                 | Separate Supabase staging project (ref ≠ `dpadrlxukcjbewpqympu`)                               | Supabase production project                        |
| n8n            | optional compose profile                      | `n8n.staging.vergeo5.com` (inactive workflows until verified)                                  | `n8n.vergeo5.com`                                  |
| Budget posture | $0                                            | OCI Always Free + Supabase free + Vercel hobby                                                 | ≤ $50/mo all-in (D6)                               |

Staging plane templates: `infra/staging/`. Runbook:
`docs/production-readiness/2026-07-18/staging/staging-plane-runbook.md`.

## Where secrets live

| Secret / config                                    | OCI `infra/.env` | Vercel (customer)               | GitHub Actions | Notes                                                                                                                                                                                                                               |
| -------------------------------------------------- | ---------------- | ------------------------------- | -------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `SUPABASE_URL`                                     | ✓ (api)          | `NEXT_PUBLIC_*` mirror          | —              | Public URL (REST endpoint)                                                                                                                                                                                                          |
| `SUPABASE_DB_URL`                                  | ✓ (api)          | ✗                               | —              | **Load-bearing.** Session-pooler DSN (5432, not 6543) for server-side SQL: ledger/escrow, `/internal/*` ticks, search RRF. Blank ⇒ silent fallback to local `127.0.0.1:54322` ⇒ every direct-DB call 500s + search `degraded=true`. |
| `NEXT_PUBLIC_API_BASE_URL`                         | —                | ✓ (customer/vendor/admin)       | —              | Browser API origin (`https://api.vergeo5.com`). Distinct from the server-only `API_BASE_URL`; blank ⇒ client calls (cart, wishlist) hit `localhost:8000`.                                                                           |
| `SUPABASE_ANON_KEY`                                | ✓ (api)          | `NEXT_PUBLIC_*`                 | —              | Client-safe                                                                                                                                                                                                                         |
| `SUPABASE_SERVICE_ROLE_KEY`                        | ✓ (api only)     | ✗                               | —              | **Never** in customer/vendor bundles                                                                                                                                                                                                |
| `LENCO_API_TOKEN`                                  | ✓ (api)          | ✗                               | —              | Server-only                                                                                                                                                                                                                         |
| `OPENROUTER_API_KEY`                               | ✓ (api)          | ✗                               | —              | Server-only                                                                                                                                                                                                                         |
| `WHATSAPP_TOKEN` / `AT_API_KEY` / `RESEND_API_KEY` | ✓ (api)          | ✗                               | —              | Outbox workers                                                                                                                                                                                                                      |
| `CLOUDINARY_URL`                                   | ✓ (api)          | optional public cloud name only | —              | Prefer unsigned upload presets                                                                                                                                                                                                      |
| `N8N_*`                                            | ✓                | ✗                               | —              | n8n container only                                                                                                                                                                                                                  |
| `VERCEL_TOKEN` / `VERCEL_ORG_ID` / project ids     | ✗                | —                               | ✓ (`staging`)  | Preview deploy / inspect (STG-01)                                                                                                                                                                                                   |
| `STAGING_*` / `SUPABASE_ACCESS_TOKEN`              | ✗                | —                               | ✓ (`staging`)  | See staging-secret-register.md                                                                                                                                                                                                      |
| `OCI_*` / `STAGING_OCI_SSH_*`                      | ✗                | —                               | ✓ (`staging`)  | Staging VM deploy                                                                                                                                                                                                                   |

## Conventions

1. Root `.env.example` lists platform-wide names; `infra/.env.example` lists OCI compose runtime names.
2. Copy `infra/.env.example` → `infra/.env` on the VM — file mode `600`, owned by deploy user.
3. Rotations: update OCI `.env`, `docker compose up -d`, and Vercel env separately; never log values.
4. Service-role and payment keys exist **only** in the API container environment on OCI.
