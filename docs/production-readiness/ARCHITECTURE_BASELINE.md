# Architecture Baseline — Batch 0 Ground Truth

**Audit date:** 2026-08-06  
**Commit:** `761733dd982a9400a0e0c7427046ecbaf0aac11c` (`master`)  
**Audit branch:** `cursor/batch0-architecture-baseline-9b44`

Evidence hierarchy: **code in Git** > dated ops docs > planning docs. Deployment/runtime claims marked separately.

---

## Repository Identity

| Field            | Value                                                            |
| ---------------- | ---------------------------------------------------------------- |
| Remote           | `https://github.com/KaluMuso/Convergeo`                          |
| Product brand    | Vergeo5 (`vergeo5.com`)                                          |
| Branch audited   | `master` @ `761733dd982a9400a0e0c7427046ecbaf0aac11c`            |
| Working tree     | Clean at audit start                                             |
| Monorepo manager | **pnpm 9.15.4** + **Turborepo 2.x**                              |
| Lockfiles        | `pnpm-lock.yaml`, `services/api/uv.lock`                         |
| Python           | 3.12 (`services/api/.python-version`)                            |
| Node             | `.nvmrc` pins 20; VM shim may report 22 (harmless per AGENTS.md) |

### Workspace layout

```
apps/customer     — Next.js 15 customer PWA (port 3000)
apps/vendor       — Next.js 15 vendor portal (port 3001)
apps/admin        — Next.js 15 admin ops (port 3002)
services/api      — FastAPI backend (port 8000)
packages/ui       — Design system + Tailwind preset
packages/types    — Shared TS types (Supabase-generated)
packages/config   — API client, env, CSP helpers
packages/i18n     — next-intl messages (5 locales)
packages/auth     — Supabase session middleware
packages/analytics, packages/observability — telemetry
supabase/         — 96 SQL migrations, seed, pgTAP tests, edge functions
infra/            — Docker Compose, Caddy, n8n workflows, deploy scripts
e2e/              — Playwright (nightly, not PR gate)
```

---

## Applications

| App      | Path                       | Framework                                                | Deploy target (evidence)                      | API dependency                       |
| -------- | -------------------------- | -------------------------------------------------------- | --------------------------------------------- | ------------------------------------ |
| Customer | `apps/customer`            | Next.js 15, React 19, Tailwind 4, next-intl, Serwist PWA | Vercel (`convergeo-customer`)                 | `NEXT_PUBLIC_API_BASE_URL` → FastAPI |
| Vendor   | `apps/vendor`              | Next.js 15, standalone output                            | OCI/Caddy (`vendor.vergeo5.com`)              | Same                                 |
| Admin    | `apps/admin`               | Next.js 15, standalone, CF Access JWT                    | OCI/Caddy (`admin.vergeo5.com`)               | Same                                 |
| API      | `services/api`             | FastAPI 0.139, Python 3.12                               | OCI Docker (`ghcr.io/kalumuso/convergeo-api`) | Supabase Postgres + Auth             |
| n8n      | `infra/docker-compose.yml` | n8n 1.82.1                                               | OCI (`n8n.vergeo5.com`)                       | Internal `/internal/*` ticks         |

**Build commands:** `pnpm build` (turbo, all apps); API image via `.github/workflows/api-image.yml`.  
**Test commands:** `pnpm test`, `pnpm lint`, `pnpm typecheck`; API: `uv run pytest`, `uv run ruff check`, `uv run mypy`.

---

## Frontend Architecture

- **Routing:** Locale-prefixed App Router (`/en`, `/bem`, `/nya`, `/fr`, `/zh`); `localePrefix: "always"`.
- **i18n:** `packages/i18n` — 19 namespaces; EN source-of-truth; bem/nya partial with EN deep-merge fallback.
- **HTTP:** `@vergeo/config` `createApiClient()` + per-app `lib/api-base-url.ts`.
- **Auth:** `@vergeo/auth` middleware — Supabase session, CSP nonce, login redirects.
- **PWA:** Customer only — Serwist SW (`sw.ts`), manifest, offline page.
- **Security:** CSP report-only; admin strictest; Cloudflare Access on admin in production.
- **Money display:** Shared `formatK()` from i18n (ngwee → ZMW display).

---

## Backend Architecture

- **Framework:** FastAPI with auto-discovered routers (`app/main.py`).
- **Validation:** Pydantic v2 `StrictModel`; money as integer **ngwee** (`NgweeInt`).
- **Errors:** `AppError` + registered handlers; rate limits via SlowAPI + Upstash Redis (optional).
- **DB access:** Supabase Python client (service role server-side); direct psycopg via `app/services/db.py` for some paths.
- **Structure:** `app/routers/` (HTTP), `app/services/` (~30 domain packages), `app/schemas/`, `app/core/`.
- **Background:** No Celery; n8n cron → `/internal/*` endpoints with per-token auth.

---

## Database & Migrations

| Aspect            | Truth (Git)                                                                                           |
| ----------------- | ----------------------------------------------------------------------------------------------------- |
| Engine            | PostgreSQL via **Supabase** (cloud)                                                                   |
| Extensions        | `pgvector`, `pg_trgm`, FTS (`0001_extensions.sql`)                                                    |
| Migrations in Git | **96 files** (`0001`–`0092` + **3× `0093_*`** + `20260802153539_rls_policy_contract_remediation.sql`) |
| ORM               | None — SQL migrations + Supabase client / raw SQL                                                     |
| RLS               | Enabled + forced on core tables; money tables service-role write only                                 |
| Seed              | `supabase/seed.sql` (~150 products + categories); `[db.seed] enabled = false` in config.toml          |
| Local config      | `supabase/config.toml` — Postgres **15** in config (docs reference 16 for cloud)                      |

### Migration caveats (Git proves files exist; applied state UNKNOWN without live DB)

- **Triple `0093_*` prefix** — apply order alphabetical; disjoint objects today but fragile.
- **Historical drift** documented in `docs/production-readiness/2026-07-20/deploy-migration-truth.md` — production may lag Git tip (e.g. status doc cites prod at `0071` vs Git `0093+` as of 2026-08-01).
- **Custom access token hook** (`0051`) — SQL present; hook **disabled** in `config.toml`.

### Major table groups

Identity: `profiles`, `user_roles`, `vendors`, `kyc_records`, `business_buyers`  
Catalog: `categories`, `products`, `vendor_listings`, `listing_images`, `listing_location_stock`  
Commerce: `carts`, `cart_items`, `checkout_groups`, `orders`, `order_items`, `stock_reservations`  
Money: `ledger_accounts`, `ledger_transactions`, `ledger_postings`, `payments`, `payouts`, `refunds`, `invoices`  
Search: `search_documents`, `embedding_jobs`, `ask_cache`, `ask_usage`  
Events: `events`, `event_instances`, `ticket_types`, `tickets`  
Services/RFQ: `services`, `jobs`, `rfq_threads`, `enquiry_threads`  
Config: `feature_flags`, `commission_rates`, `delivery_zones`  
Clips/Intake: `video_clips`, intake tables (`0072`–`0079`)

---

## Authentication & Authorization

### Trust boundary

```
Browser → Next.js (session cookie, CSP) → FastAPI (Bearer JWT + role deps) → Postgres (RLS)
```

| Layer                       | Mechanism                                                            |
| --------------------------- | -------------------------------------------------------------------- |
| Customer/vendor/admin login | Supabase Auth — phone OTP, email, Google (`config.toml`)             |
| API auth                    | `Authorization: Bearer` → JWKS verify → `user_roles` from DB         |
| Admin API                   | `require_role("admin", "superadmin", "moderator")` + audit route     |
| Vendor scope                | `owner_user_id` match on `vendors`                                   |
| Guest cart                  | Signed cookie + `cart_guest_token()` GUC for anon RLS                |
| Internal jobs               | `X-Internal-Token` env-per-route                                     |
| Admin origin                | IP allowlist + optional Cloudflare Access JWT (admin app middleware) |

**Where enforced:** RLS for row visibility; API for mutations, state machines, and business rules; service-role for money writes.

---

## Catalogue & Listings

| Stage                             | Status      | Evidence                                                       |
| --------------------------------- | ----------- | -------------------------------------------------------------- |
| Canonical products                | **PRESENT** | `products` table; admin moderation queue; `canonical_match.py` |
| Vendor listings                   | **PRESENT** | `vendor_listings`; vendor CRUD routers; CSV import             |
| Listing images                    | **PRESENT** | Cloudinary signed upload; max 8 images                         |
| Product classes / wholesale flags | **PRESENT** | `0085`–`0087`; B2B gating in `business/access.py`              |
| Comparison view                   | **PRESENT** | `comparison.py`, customer `/compare`                           |

---

## Inventory & Locations

| Stage              | Status      | Evidence                                               |
| ------------------ | ----------- | ------------------------------------------------------ |
| Vendor locations   | **PRESENT** | `vendor_locations`; geo index `0089`                   |
| Per-location stock | **PRESENT** | `listing_location_stock`, `0081`, `0090` reservations  |
| Stock reservations | **PRESENT** | `stock_reservations`; sweeper `internal_stock_sweeper` |

---

## Cart & Checkout

| Stage                | Status      | Evidence                                                                                      |
| -------------------- | ----------- | --------------------------------------------------------------------------------------------- |
| Cart (auth + guest)  | **PRESENT** | `cart.py`, `0012_carts.sql`                                                                   |
| Cart price integrity | **PARTIAL** | `0086` revokes client cart item writes; known read-path re-derivation gaps (G3 in status doc) |
| Checkout session     | **PRESENT** | `checkout.py` — multi-step session, fulfilment, delivery zones                                |
| Payment initiation   | **PRESENT** | `checkout_payment.py`, `payments_card.py`; gated by `PAYMENTS_ENABLED`                        |

---

## Orders & Fulfilment

| Stage               | Status      | Evidence                                       |
| ------------------- | ----------- | ---------------------------------------------- |
| Order creation      | **PRESENT** | `orders_create.py`; guarded status transitions |
| Order state machine | **PRESENT** | DB triggers + `app/services/orders/state.py`   |
| Pickup QR/PIN       | **PRESENT** | `0017`, `pickup_verify.py`                     |
| COD flow            | **PRESENT** | `cod.py`; ≤K500 cap in config                  |
| Delivery / dispatch | **PARTIAL** | Manual dispatch admin UX; no courier API       |
| Returns             | **PRESENT** | `returns.py`; lane 1/2 per D17                 |

---

## Payments

| Item                | Status           | Evidence                                  |
| ------------------- | ---------------- | ----------------------------------------- |
| Lenco MoMo push     | **CODE PRESENT** | `payments/lenco/`, `initiate.py`          |
| Lenco card widget   | **CODE PRESENT** | `payments_card.py`                        |
| Webhook ingestion   | **CODE PRESENT** | `webhooks_lenco.py`, `webhook_verify.py`  |
| Kill switches       | **CODE PRESENT** | `gate.py` — default OFF                   |
| Idempotency         | **CODE PRESENT** | `references.py`, `webhook_events`, `0015` |
| Production verified | **UNKNOWN**      | No real-money tests run in this audit     |

---

## Ledger / Escrow / Settlement / Payouts

| Item                | Status      | Evidence                                                              |
| ------------------- | ----------- | --------------------------------------------------------------------- |
| Double-entry ledger | **PRESENT** | `0006_money.sql`, `ledger/engine.py`                                  |
| Escrow release      | **PRESENT** | `escrow/release.py`, `internal_release_job.py`                        |
| Order money gates   | **PRESENT** | `0059`, `order_money_gate.py`                                         |
| Payout execution    | **PRESENT** | `payouts/execution.py`, `internal_payouts.py`; `PAYOUTS_ENABLED` gate |
| Reconciliation      | **PRESENT** | `reconcile.py`, `internal_reconciliation.py`, n8n workflow            |
| Refunds             | **PRESENT** | `refunds/execute.py`, clawback from vendor payable                    |
| Production verified | **UNKNOWN** | Status doc: 0 money rows on both DB projects (2026-08-01)             |

---

## Vendor Architecture

- Onboarding/KYC: `kyc.py`, tiered caps, name match seam for Lenco.
- Listings, orders, payouts, analytics, events, services, clips, intake — dedicated vendor routers.
- Commercial tier, licences, storefront collections (`0070`, `0084`, `0093`).

---

## Admin Architecture

- Custom Next.js admin (not Supabase dashboard).
- Domains: KYC queue, orders/escrow, disputes, moderation, config/flags, merch, translations, clips, business buyers, search insights.
- `AdminAuditedRoute` for mutation audit trail.

---

## Search & Discovery

| Component                     | Status                                               |
| ----------------------------- | ---------------------------------------------------- |
| `/search` FTS + facets        | **IMPLEMENTED**                                      |
| `/search/suggest`             | **IMPLEMENTED**                                      |
| pgvector + RRF (`search_rrf`) | **IMPLEMENTED**                                      |
| Geo / nearby                  | **IMPLEMENTED**                                      |
| Ask Vergeo RAG (`/ask`)       | **IMPLEMENTED**                                      |
| Embedding cron                | **CODE/CONFIG PRESENT** — n8n `embeddings-cron.json` |
| Meilisearch                   | **NOT_PRESENT**                                      |
| Production search SLO         | **CANNOT_VERIFY**                                    |

---

## Automation / Workers / n8n

- **25 workflow JSON files** in `infra/n8n/`; registry in `docs/ops/n8n-workflows.md`.
- Categories: notifications, payment sweeper, reconciliation, escrow release, stock reservation, embeddings, backups, uptime alerts, WAHA intake sweeps.
- **Active in production: UNKNOWN** — status doc (2026-08-01): 7 active / 2 inactive; 15 never imported.
- No Celery/Redis queue workers in application code.

---

## Events

| Item                          | Status                                |
| ----------------------------- | ------------------------------------- |
| Event CRUD + ticketing schema | **PRESENT**                           |
| Dynamic QR + PIN scanner      | **PRESENT** (vendor scan PWA)         |
| Paid ticket checkout          | **PRESENT** (`internal_tickets.py`)   |
| Escrow timing per event type  | **PRESENT** (`event_release.py`)      |
| n8n ticket issue/release      | **CODE PRESENT** — activation UNKNOWN |

---

## B2B

| Item                              | Status                                                           |
| --------------------------------- | ---------------------------------------------------------------- |
| `business_buyers` verification    | **PRESENT**                                                      |
| Wholesale tiers + MOQ on listings | **PRESENT**                                                      |
| Wholesale-only 404 for consumers  | **PARTIAL** — API entry points fixed; cart read-path gaps remain |
| RFQ threads (`0093`)              | **PRESENT** (schema + routers)                                   |
| Credit terms / org accounts       | **ABSENT** (explicitly OUT of v1)                                |

---

## Social Commerce

| Item                            | Status                                                                                          |
| ------------------------------- | ----------------------------------------------------------------------------------------------- |
| Listing-anchored enquiries      | **PRESENT** (`0082`, `enquiries.py`)                                                            |
| Vendor follows                  | **PRESENT** (`0083`, `follows.py`)                                                              |
| User saves                      | **PRESENT** (`0088`)                                                                            |
| External share links            | **PRESENT** (customer routes)                                                                   |
| C2C DMs / public feeds / groups | **ABSENT** (D37 ban)                                                                            |
| Video clips (M17)               | **PRESENT** in Git — **deployment UNKNOWN** on prod (migrations `0072`–`0079` may be unapplied) |

---

## Infrastructure & Deployments

| Layer             | Code state                  | Deployment evidence                       | Live state                                      |
| ----------------- | --------------------------- | ----------------------------------------- | ----------------------------------------------- |
| Customer app      | In Git                      | Vercel project `convergeo-customer`       | Dated docs: READY at master tip — **re-verify** |
| Vendor/admin apps | In Git                      | Vercel + OCI standalone                   | Dated docs: READY — **re-verify**               |
| API container     | Dockerfile + GHCR workflow  | `deploy-production.yml` (manual SSH)      | `/healthz` **UNKNOWN** this session             |
| Supabase          | 96 migrations in Git        | `supabase db push` in CI/staging workflow | Prod migration tip **UNKNOWN** (may lag Git)    |
| n8n               | Compose + 25 JSON workflows | OCI compose                               | Partial import per status doc                   |
| Staging plane     | `infra/staging/`            | `deploy-staging.yml` on `staging` branch  | Sandbox project cited in status doc             |

**Domains (documented):** `vergeo5.com`, `vendor.vergeo5.com`, `admin.vergeo5.com`, `api.vergeo5.com`, `n8n.vergeo5.com`.

---

## Observability

| Item                   | Status                                                                          |
| ---------------------- | ------------------------------------------------------------------------------- |
| Structured logging     | **CONFIGURED** (`configure_logging` in API)                                     |
| Sentry API + Next apps | **CONFIGURED** (DSN env-gated; projects may be missing in Sentry org)           |
| Health endpoints       | **IMPLEMENTED** (`/healthz`, `/readyz`, `/fingerprint`; app `/{locale}/health`) |
| UptimeRobot            | **DOCUMENTED** (`infra/uptimerobot.md`) — active monitors UNKNOWN               |
| Metrics/traces         | **PARTIAL** — Sentry traces sample rate only                                    |
| Audit logs             | **PRESENT** — admin audit, order_events, config_audit                           |

---

## Backup & Recovery

| Item                    | Status                                                                                    |
| ----------------------- | ----------------------------------------------------------------------------------------- |
| Supabase backups / PITR | **CONFIGURED** (Supabase cloud) — **RECOVERY_UNPROVEN**                                   |
| n8n backup workflow     | **CODE PRESENT** — inactive per status doc                                                |
| GitHub restore drill    | **CONFIGURED** (`.github/workflows/restore-drill.yml`) — CI self-contained, not prod dump |
| Runbooks                | **PRESENT** (`docs/production-readiness/ROLLOUT_RUNBOOK.md`, dated drills)                |

---

## Test Baseline

Commands executed in Batch 0 audit (2026-08-06):

| Command                               | Result                            | Scope                                                          |
| ------------------------------------- | --------------------------------- | -------------------------------------------------------------- |
| `pnpm lint`                           | **PASS**                          | All turbo lint tasks                                           |
| `pnpm typecheck`                      | **PASS**                          | All workspaces                                                 |
| `pnpm test`                           | **PASS**                          | 527+ customer vitest; vendor/admin passWithNoTests             |
| `uv run ruff check .`                 | **PASS**                          | API                                                            |
| `uv run mypy app tests scripts`       | **PASS**                          | 539 source files                                               |
| `uv run pytest` (full)                | **NOT COMPLETED** in audit window | 7005 collected (parametrized); RLS tests require live Postgres |
| `uv run pytest --ignore=tests/rls -x` | **48 passed, 1 ERROR**            | Stopped at RLS clip test (needs DB)                            |

CI (`.github/workflows/ci.yml`) additionally runs: migrations replay, RLS matrix, money DB triggers, COD container smoke, ask evals, gitleaks, bundle/Lighthouse on PRs.

---

## Known Unknowns

1. **Production Supabase migration tip** vs Git `0093+` / timestamp migration.
2. **API live health** at `api.vergeo5.com` — no egress probe this session.
3. **n8n workflow import/activation** state on production host.
4. **Payment/payout env flags** on production (`PAYMENTS_ENABLED`, `PAYOUTS_ENABLED`).
5. **Sentry project provisioning** and DSN deployment on all surfaces.
6. **RLS CI matrix validity** — RG-6: matrix may run as superuser (status doc 2026-08-02).
7. **Full Canonical Requirements Registry** — not present in repository; see MASTER_REQUIREMENTS.md.
8. **Real-money sandbox drill** — blocked on F9b credentials per status doc.

---

_Batch 0 complete. No application code changed. See DECISIONS.md, AUDIT_LEDGER.md, BLOCKERS.md for programme continuation._
