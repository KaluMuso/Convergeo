# Production Evidence — Vergeo5 / Convergeo

**Audit timestamp (UTC):** 2026-07-18 ~12:48–13:00  
**Repo HEAD inspected:** `8cc1fa07745f48d8326897d68c4b5eb4f68a7d27` (merge PR #271)  
**Mode:** READ-ONLY · No secrets printed

Evidence labels per `document-audit-contract.md`.

---

## 1. Live URLs & health

| Surface           | URL                                                | Probe            | Result                                                       | Status   |
| ----------------- | -------------------------------------------------- | ---------------- | ------------------------------------------------------------ | -------- |
| Customer (www)    | `https://www.vergeo5.com`                          | `GET /en/health` | `200` `{"status":"ok","app":"customer"}`                     | VERIFIED |
| Customer apex     | `https://vergeo5.com/en`                           | HEAD             | `308` → `https://www.vergeo5.com/en` (Cloudflare + Vercel)   | VERIFIED |
| Customer HTML     | `https://www.vergeo5.com/en`                       | headers          | `server: cloudflare`, `x-vercel-id`, CSP present             | VERIFIED |
| API               | `https://api.vergeo5.com`                          | `GET /healthz`   | `200` `{"status":"ok"}`; `via: 1.1 Caddy`; `server: uvicorn` | VERIFIED |
| API ready         | `https://api.vergeo5.com/readyz`                   | GET              | `200` `{"status":"ok"}`                                      | VERIFIED |
| API OpenAPI       | `https://api.vergeo5.com/openapi.json`             | GET              | title `Vergeo5 API`, version `0.1.0` (not a git SHA)         | PARTIAL  |
| Catalog           | `https://api.vergeo5.com/catalog/listings?limit=1` | GET              | `total: 134` (demo catalogue live)                           | VERIFIED |
| Vendor custom     | `https://vendor.vergeo5.com`                       | `/en/health`     | `307` → login (auth gate); Vercel headers                    | VERIFIED |
| Vendor vercel.app | `https://convergeo-vendor.vercel.app`              | same             | login redirect                                               | VERIFIED |
| Admin custom      | `https://admin.vergeo5.com`                        | `/en/health`     | `302` Cloudflare Access challenge                            | VERIFIED |
| Admin vercel.app  | `https://convergeo-admin.vercel.app`               | `/en/health`     | `403` `Forbidden — Cloudflare Access required`               | VERIFIED |

---

## 2. Vercel deployment / commit evidence

Team: `Vergeo Projects` (`team_I2OEqmMjTwN2k5g7ACbQW705`).

| Project                                                   | Domains                                          | Latest production target (READY)   | Commit SHA                                           | Status   |
| --------------------------------------------------------- | ------------------------------------------------ | ---------------------------------- | ---------------------------------------------------- | -------- |
| `convergeo-customer` (`prj_lK6jnhAfVmhtaDZdMsIUF7LswgTP`) | `vergeo5.com`, `www.vergeo5.com`, `*.vercel.app` | `dpl_66qkpsXVaXm7MbgT8UwZsfzhfdzW` | `8cc1fa07745f48d8326897d68c4b5eb4f68a7d27` (PR #271) | VERIFIED |
| `convergeo-vendor` (`prj_QiX9rpStSpNeEXd3UZDFFp7H2dXf`)   | `vendor.vergeo5.com`, `*.vercel.app`             | `dpl_GG7SwEKzxUfrj9kBTE2EyEV7JC9s` | `8cc1fa0…` (PR #271)                                 | VERIFIED |
| `convergeo-admin` (`prj_Bpf852KXDuG1NZUomri0OsMBt1YS`)    | `admin.vergeo5.com`, `*.vercel.app`              | `dpl_8wWRXjo8Auu2yX2yxa5SG4uCTGGk` | `8cc1fa0…` (PR #271)                                 | VERIFIED |

**Frontend drift vs repo HEAD:** production Vercel apps match inspected `master` tip `8cc1fa0` — **no frontend commit drift** at audit time (VERIFIED).

---

## 3. API / container version

| Claim                                 | Evidence                                                                                                                             | Status                                           |
| ------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------ | ------------------------------------------------ |
| API reachable behind Caddy            | `/healthz` headers `via: 1.1 Caddy`                                                                                                  | VERIFIED                                         |
| Exact deployed git SHA / image digest | OpenAPI only reports `0.1.0`; GHCR manifest requires auth (`UNAUTHORIZED`); no SSH to API host; no `SENTRY_RELEASE` header on health | **NOT_AUDITABLE**                                |
| Intended deploy mechanism             | `infra/docker-compose.yml` image `ghcr.io/kalumuso/convergeo-api:${API_IMAGE_TAG:-latest}`; `infra/redeploy-api.sh`                  | PARTIAL (config only)                            |
| Host notes from status docs           | Status claims Hetzner CX23 + system Caddy (OCI micro abandoned for API)                                                              | PARTIAL (docs/status; not re-SSH’d this session) |

**CONFLICT risk:** Frontend at `8cc1fa0` vs API image tag unknown — treat API commit as **NOT_AUDITABLE** until host/`API_IMAGE_TAG`/GHCR digest is read with least privilege.

---

## 4. Database (Supabase) evidence

| Field                               | Value                                                                   | Status   |
| ----------------------------------- | ----------------------------------------------------------------------- | -------- |
| Project                             | `Vergeo5` / `dpadrlxukcjbewpqympu`                                      | VERIFIED |
| Region                              | `eu-north-1`                                                            | VERIFIED |
| Status                              | `ACTIVE_HEALTHY`                                                        | VERIFIED |
| Postgres engine (platform metadata) | 17.x channel                                                            | VERIFIED |
| Applied migrations                  | `0001`–`0050` + timestamped `20260717100303` (`0052_product_relations`) | VERIFIED |
| Repo migrations                     | `0001`–`0055` (55 files)                                                | VERIFIED |

### Migration drift (repo vs applied)

| Migration                            | In repo        | Applied on live         | Object check                               | Status                     |
| ------------------------------------ | -------------- | ----------------------- | ------------------------------------------ | -------------------------- |
| `0051_custom_access_token_role_hook` | yes            | **no**                  | `custom_access_token*` function **absent** | CONFLICT / MISSING on live |
| `0052_product_relations`             | yes (`0052_…`) | yes as `20260717100303` | `product_relations` **exists**             | CONFLICT (version key)     |
| `0053_translation_overrides`         | yes            | **no**                  | `translation_overrides` **absent**         | MISSING on live            |
| `0054_service_reviews`               | yes            | **no**                  | (not applied)                              | MISSING on live            |
| `0055_service_bookable`              | yes            | **no**                  | `services.bookable` **absent**             | MISSING on live            |

**Verdict:** Live DB ≠ repository migration tip. Do not assume staging/prod schema matches `master`.

---

## 5. Catalogue / seed reality (aggregates only)

| Metric                                                   | Value                                                                                                     | Status   |
| -------------------------------------------------------- | --------------------------------------------------------------------------------------------------------- | -------- |
| Vendors                                                  | 3 (`cairo-road-fashions`, `kabwata-market`, `lusaka-electronics`) all `active`                            | VERIFIED |
| Vendor listings                                          | 134                                                                                                       | VERIFIED |
| Products                                                 | 150                                                                                                       | VERIFIED |
| Categories                                               | 74 (table inventory)                                                                                      | VERIFIED |
| Listing images with `cloudinary_public_id LIKE 'demo/%'` | **134**                                                                                                   | VERIFIED |
| Orders / payments / ledger_transactions / tickets        | **0**                                                                                                     | VERIFIED |
| Profiles / user_roles                                    | 3 / 3                                                                                                     | VERIFIED |
| Feature flags                                            | `paid_tiers`, `abandoned_cart`, `wallet`, `zamtel_collections`, `public_launch` — all **`enabled=false`** | VERIFIED |
| Public catalog API `total`                               | 134                                                                                                       | VERIFIED |

Live marketplace is a **demo/seed catalogue** with zero money ops rows.

---

## 6. n8n automation evidence

MCP `search_workflows` against live n8n instance returned **exactly 2** workflows, both **active**:

| Workflow id        | Name                                   | Active | Covers                                                                            |
| ------------------ | -------------------------------------- | ------ | --------------------------------------------------------------------------------- |
| `sevKtX1AmimQCWsG` | Vergeo5 — notification dispatch        | true   | `POST /internal/dispatch/tick`                                                    |
| `C1MpTNjrfLACMG3f` | Vergeo5 — payment reconciliation crons | true   | webhook-drain (1m), recon poll (30m), payment sweeper (10m), daily report (02:00) |

Registry in repo (`docs/ops/n8n-workflows.md` + `infra/n8n/*.json`) lists many more (escrow release, tickets-issue, order-jobs, backups doc, digests, etc.) that are **not present** as live workflows.

| Expected (repo registry)                                        | Live                                                          | Status                                  |
| --------------------------------------------------------------- | ------------------------------------------------------------- | --------------------------------------- |
| `release-job.json` / escrow auto-release                        | absent                                                        | MISSING                                 |
| `tickets-issue.json` / ticket issuance tick                     | absent                                                        | MISSING                                 |
| `order-jobs.json` auto-confirm                                  | absent                                                        | MISSING                                 |
| `event-release.json`                                            | absent                                                        | MISSING                                 |
| DB backup workflow                                              | only `backup-schedule.md` contract; no workflow in n8n search | MISSING / NOT_AUDITABLE (OCI dump host) |
| `admin-digest.json`, nudges, embeddings, reservation-sweeper, … | absent from live list                                         | MISSING                                 |

---

## 7. Observability evidence

| Signal                                                | Evidence                                                                                                | Status                  |
| ----------------------------------------------------- | ------------------------------------------------------------------------------------------------------- | ----------------------- |
| Sentry org accessible to audit principal              | `convergeo-w2`                                                                                          | VERIFIED                |
| Sentry projects for Vergeo5/customer/vendor/admin/API | **None** (only `zedapply-staging`, `zedcv-*`)                                                           | MISSING                 |
| Code has Sentry no-op without DSN                     | `docs/ops/observability.md` + init sites                                                                | PARTIAL                 |
| UptimeRobot live monitors                             | Not queried this session                                                                                | NOT_AUDITABLE           |
| Admin dashboard analytics data                        | `analytics_events` / `funnel_events` row counts **0**; dashboard UI exists and calls `/admin/dashboard` | PARTIAL (empty streams) |

---

## 8. Seller CTA live behavior

| Check                                                                     | Result                                                              | Status                                               |
| ------------------------------------------------------------------------- | ------------------------------------------------------------------- | ---------------------------------------------------- |
| `https://www.vergeo5.com/en/sell` contains `localhost:3001`               | **false**                                                           | VERIFIED (localhost fallback not emitted)            |
| Sell CTAs                                                                 | Disabled buttons; copy: “Vendor signup is temporarily unavailable…” | VERIFIED                                             |
| Implies `NEXT_PUBLIC_VENDOR_APP_URL` unset/invalid in customer prod build | Fail-closed path in `vendor-app.ts`                                 | PARTIAL (env value not read; behavior matches unset) |

---

## 9. Repository vs deployed reality (summary)

| Layer                        | Repo / docs           | Live                                                         | Label                    |
| ---------------------------- | --------------------- | ------------------------------------------------------------ | ------------------------ |
| Customer/vendor/admin commit | `8cc1fa0`             | Vercel production `8cc1fa0`                                  | VERIFIED match           |
| API commit/image             | unknown tip           | healthy, SHA unknown                                         | NOT_AUDITABLE            |
| Migrations                   | through `0055`        | through `0050` + odd `0052` version; missing `0051/53/54/55` | CONFLICT                 |
| n8n registry                 | ~18 workflow files    | 2 active workflows                                           | CONFLICT / MISSING       |
| Catalogue                    | seed scripts          | 134 demo listings + demo images                              | VERIFIED demo            |
| Money path usage             | code complete in repo | 0 payments / 0 ledger rows                                   | PARTIAL (unused in prod) |
