# Architecture Inventory — Vergeo5 / Convergeo

**Audit date:** 2026-07-18 · **Evidence rank:** repository (3) + live probes where noted · **Mode:** READ-ONLY

---

## 1. Monorepo layout

| Path                  | Purpose                                                                                                                                               |
| --------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------- |
| `apps/customer`       | Next.js 15 customer marketplace (SSR/ISR, SEO, PWA/serwist). Locale-prefixed. Port 3000. Vercel project `convergeo-customer`.                         |
| `apps/vendor`         | Next.js vendor portal (listings, KYC, orders, organiser/scanner). Port 3001. Vercel `convergeo-vendor`.                                               |
| `apps/admin`          | Next.js admin console (KYC, disputes, merch, flags, dashboard). Port 3002. Vercel `convergeo-admin` + Cloudflare Access.                              |
| `services/api`        | FastAPI Python 3.12 backend (commerce, payments/escrow, search/Ask, notifications, internal cron ticks). GHCR image `ghcr.io/kalumuso/convergeo-api`. |
| `packages/ui`         | Design tokens + shared UI/SEO components.                                                                                                             |
| `packages/types`      | Generated Supabase types (`packages/types/src/db.ts`).                                                                                                |
| `packages/config`     | Shared Zod env loaders, eslint/prettier.                                                                                                              |
| `packages/i18n`       | next-intl messages (EN/Bemba/Nyanja/FR +).                                                                                                            |
| `packages/auth`       | Supabase SSR/browser clients, middleware, role helpers.                                                                                               |
| `packages/analytics`  | Consent-aware GA4 mirror.                                                                                                                             |
| `infra/`              | Docker Compose (api/Caddy/n8n), Caddyfile, redeploy/rollback, Cloudflare/Vercel docs, n8n JSON.                                                       |
| `supabase/migrations` | Ordered SQL `0001`–`0055`.                                                                                                                            |
| `supabase/functions`  | Edge functions (e.g. `send-sms-otp`).                                                                                                                 |
| `e2e/`                | Standalone Playwright (outside workspace).                                                                                                            |
| `load/`               | k6 + ledger invariant checks.                                                                                                                         |
| `scripts/`            | CI, typegen, DR restore, security probes.                                                                                                             |
| `docs/`               | Plan, ops, designs, research distillations.                                                                                                           |
| `.github/workflows/`  | `ci.yml`, `perf.yml`, `e2e.yml`, `api-image.yml`, `deploy-staging.yml` (stub).                                                                        |

Workspace: pnpm + Turborepo (`pnpm-workspace.yaml`, `turbo.json`).

---

## 2. Integrations (paths only)

| Integration              | Evidence paths                                                                                                    |
| ------------------------ | ----------------------------------------------------------------------------------------------------------------- |
| Supabase Auth / Postgres | `supabase/config.toml`, `packages/auth/*`, `services/api/app/core/auth.py`, `services/api/app/supabase_client.py` |
| Lenco payments           | `services/api/app/services/payments/lenco/*`, routers `webhooks_lenco`, `checkout_payment`, `payments_card`       |
| Cloudinary               | `services/api/app/media/cloudinary_signing.py`, `NEXT_PUBLIC_CLOUDINARY_CLOUD_NAME`                               |
| WhatsApp Cloud API       | `services/api/app/services/notifications/adapters/whatsapp.py`, `webhooks_whatsapp.py`                            |
| Africa’s Talking SMS     | `adapters/sms.py`, `supabase/functions/send-sms-otp/`                                                             |
| Resend email             | `adapters/email.py`, `apps/customer/app/api/contact/route.ts`                                                     |
| OpenRouter / Ask Vergeo  | `services/api/app/services/ask/*`, `embeddings/*`                                                                 |
| Sentry                   | `services/api/app/core/sentry.py`, `apps/*/sentry.client.config.ts`                                               |
| n8n                      | `infra/docker-compose.yml`, `infra/n8n/*.json`, `docs/ops/n8n-workflows.md`                                       |
| Cloudflare               | `infra/cloudflare-dns.md`, `apps/admin/lib/cf-access.ts`, `infra/Caddyfile`                                       |

---

## 3. Environment variable names only

### Shared / API (`services/api/app/settings.py`, `infra/.env.example`, root `.env.example`)

`SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, `SUPABASE_ANON_KEY`, `SUPABASE_DB_URL`, `ENV`, `LOG_LEVEL`, `CORS_ORIGINS`, `API_IMAGE_TAG`, `LENCO_API_TOKEN`, `LENCO_ENV`, `LENCO_SANDBOX_BASE_URL`, `LENCO_ACCOUNT_ID`, `LENCO_ENABLE_ZAMTEL_COLLECTIONS`, `WHATSAPP_TOKEN`, `WHATSAPP_ACCESS_TOKEN`, `WHATSAPP_PHONE_NUMBER_ID`, `WHATSAPP_APP_SECRET`, `WHATSAPP_WEBHOOK_VERIFY_TOKEN`, `WHATSAPP_API_VERSION`, `AT_API_KEY`, `AT_USERNAME`, `AT_SENDER_ID`, `RESEND_API_KEY`, `RESEND_FROM_EMAIL`, `CLOUDINARY_URL`, `OPENROUTER_API_KEY`, `SENTRY_DSN`, `SENTRY_ENVIRONMENT`, `SENTRY_RELEASE`, `SENTRY_TRACES_SAMPLE_RATE`, `PUBLIC_SITE_URL`, `FOUNDER_WHATSAPP_E164`, `MERCH_PREVIEW_TOKEN`, `INTERNAL_RECONCILIATION_TOKEN`, `INTERNAL_PAYMENT_SWEEPER_TOKEN`, `INTERNAL_N8N_TOKEN`, `INTERNAL_DISPATCH_TOKEN`, `INTERNAL_DIGEST_TOKEN`, `INTERNAL_EMBEDDINGS_TOKEN`, `INTERNAL_EVENT_RELEASE_TOKEN`, `INTERNAL_FUNNEL_TOKEN`, `INTERNAL_ORDER_JOBS_TOKEN`, `INTERNAL_PAYOUTS_TOKEN`, `INTERNAL_RELEASE_JOB_TOKEN`, `INTERNAL_REVIEW_AGGREGATE_TOKEN`, `INTERNAL_STOCK_SWEEPER_TOKEN`, `INTERNAL_TICKETS_ISSUE_TOKEN`, …

### Host / Caddy / n8n

`API_DOMAIN`, `VENDOR_DOMAIN`, `ADMIN_DOMAIN`, `N8N_DOMAIN`, `VENDOR_UPSTREAM`, `ADMIN_UPSTREAM`, `ADMIN_ALLOWED_IPS`, `ADMIN_REQUIRE_CF_ACCESS`, `ACME_EMAIL`, `N8N_HOST`, `N8N_PROTOCOL`, `N8N_ENCRYPTION_KEY`, `N8N_BASIC_AUTH_ACTIVE`, `N8N_BASIC_AUTH_USER`, `N8N_BASIC_AUTH_PASSWORD`, `WEBHOOK_URL`, `API_ENV_FILE`, `API_BIND`

### Next.js apps

`NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_ANON_KEY`, `NEXT_PUBLIC_API_BASE_URL`, `NEXT_PUBLIC_CLOUDINARY_CLOUD_NAME`, `NEXT_PUBLIC_LENCO_PUBLIC_KEY`, `NEXT_PUBLIC_VENDOR_APP_URL`, `NEXT_PUBLIC_SUPPORT_WHATSAPP`, `NEXT_PUBLIC_GA4_MEASUREMENT_ID`, `NEXT_PUBLIC_SITE_URL`, `NEXT_PUBLIC_SENTRY_DSN`, `NEXT_PUBLIC_SENTRY_ENVIRONMENT`, `NEXT_PUBLIC_SENTRY_RELEASE`, `NEXT_PUBLIC_ADMIN_BYPASS`, `CF_ACCESS_TEAM_DOMAIN`, `CF_ACCESS_AUD`, `RESEND_API_KEY`, `CONTACT_INBOX`, `CONTACT_FROM`

### Supabase Auth / CI secret _names_

`SEND_SMS_HOOK_SECRET`, `SUPABASE_AUTH_EXTERNAL_GOOGLE_CLIENT_ID`, `SUPABASE_AUTH_EXTERNAL_GOOGLE_SECRET`, `SUPABASE_ACCESS_TOKEN`, `SUPABASE_DB_PASSWORD`, `SUPABASE_PROJECT_ID`, E2E/`LENCO_SANDBOX_*`, `VERCEL_TOKEN`, `VERCEL_ORG_ID`, `VERCEL_PROJECT_ID`, `OCI_*` (deploy stub)

---

## 4. Database clients & auth flow

| Client                      | Path                                                    |
| --------------------------- | ------------------------------------------------------- |
| Service-role (bypasses RLS) | `services/api/app/supabase_client.py`                   |
| User-scoped Supabase        | `services/api/app/core/supabase.py`                     |
| Direct Postgres (psycopg)   | `services/api/app/services/db.py` via `SUPABASE_DB_URL` |
| Browser / RSC               | `packages/auth/src/{browser-client,server-client}.ts`   |

**Auth entry points:** customer `(auth)/{login,otp,signup}`; middleware `packages/auth/src/middleware.ts` + per-app `middleware.ts`; JWT verify `services/api/app/core/auth.py`; SMS OTP edge `supabase/functions/send-sms-otp`; role hook migration `0051_custom_access_token_role_hook.sql` (dormant until dashboard enable — see production-evidence).

---

## 5. RBAC enforcement points

| Layer                       | Where                                                                     |
| --------------------------- | ------------------------------------------------------------------------- |
| Postgres RLS + `has_role()` | Migrations (esp. `0002`); tests `services/api/tests/rls/*`                |
| API `require_role` / JWT    | `services/api/app/core/auth.py`                                           |
| Admin routers + audit       | `admin_base.py`, `admin_audit.py`, `admin_*.py`                           |
| Vendor scope                | `require_vendor_owner` / `require_vendor_scope`                           |
| Edge gates                  | `packages/auth` middleware; admin CF Access `apps/admin/lib/cf-access.ts` |
| Caddy IP allowlist          | `infra/Caddyfile` + `ADMIN_ALLOWED_IPS`                                   |
| Internal cron               | `X-Internal-Token` on `internal_*.py`                                     |
| Authz matrix                | `services/api/tests/test_authz_matrix.py`                                 |

Roles: `customer` \| `vendor` \| `admin` (`user_roles`). Authoritative mutation authz = API + RLS, not JWT claims alone.

---

## 6. Migrations

- Location: `supabase/migrations/NNNN_slug.sql` (repo count **55**: `0001`–`0055`).
- Local: `supabase db reset|diff|push` (`docs/ops/supabase-workflow.md`).
- CI: `scripts/ci/migration-replay.sh` + full `db` / `rls` jobs in `.github/workflows/ci.yml`.
- Live applied set: see `production-evidence.md` (**drift** vs repo).

---

## 7. Test / build / lint / CI / deploy / rollback

| Surface   | Commands / artifacts                                                                                                                 |
| --------- | ------------------------------------------------------------------------------------------------------------------------------------ |
| JS/TS     | `pnpm i`, `pnpm lint\|typecheck\|test\|build\|dev`                                                                                   |
| API       | `uv run ruff check .`, `uv run mypy app tests scripts`, `uv run pytest`                                                              |
| DB        | `supabase db reset\|push`; `bash scripts/gen-types.sh`                                                                               |
| E2E       | `e2e/` + `.github/workflows/e2e.yml` (nightly; not per-PR required)                                                                  |
| Load      | `load/k6/*`, `load/invariant-check.py`                                                                                               |
| CI        | `ci.yml` jobs: `js`, `python`, `ask-evals`, `secret-scan`, `deps-audit`, `security-gates`, `i18n-lint`, `migrations`, `db`, `rls`, … |
| Perf      | `perf.yml` (Lighthouse `continue-on-error: true`)                                                                                    |
| API image | `api-image.yml` → GHCR `{latest,sha}`                                                                                                |
| Deploy    | Customer/vendor/admin: Vercel git-connected; API: `infra/redeploy-api.sh` / compose behind Caddy; `deploy-staging.yml` is a **stub** |
| Rollback  | `infra/ROLLBACK.md`, `docs/ops/runbook-disaster-recovery.md`                                                                         |

**Non-blocking CI (repo):** `secret-scan` (`continue-on-error: true`), `i18n-lint`, Lighthouse advisory, portions of `db`/`rls` heavy steps per workflow comments — see critical-risk-register.
