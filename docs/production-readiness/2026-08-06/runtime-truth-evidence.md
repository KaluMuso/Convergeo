# Batch 0.5 — Runtime Truth Evidence Pack

**Date:** 2026-08-06  
**Repository SHA:** `fcf2b1918256bd3d8680741b17cf928cde8576c5` (`master`)  
**Auditor:** Cursor Cloud Agent (read-only)

---

## Migration truth

### Git tip (96 files)

Last sequential: `0095_rfq_threads.sql`  
Also: `0093_license_expiry_enforcement.sql`, `0094_vendor_storefront_collections_listing_analytics.sql`, `20260802153539_rls_policy_contract_remediation.sql`

**Note:** Triple `0093` prefix collision **remediated** on `master` via PR #583 (`223f776d`) — renumbered to `0093`/`0094`/`0095`.

### Production (`Vergeo5` — `dpadrlxukcjbewpqympu`)

| Field                             | Value                                                                                                                   |
| --------------------------------- | ----------------------------------------------------------------------------------------------------------------------- |
| Last applied (numeric)            | `0071_vendor_listing_compare_at`                                                                                        |
| Applied count                     | 71 version rows (some timestamp-keyed)                                                                                  |
| Missing vs Git                    | `0072`–`0095`, `20260802153539_*`, plus `0080`–`0092` band                                                              |
| Unexpected ordering               | `0051`–`0056` applied with timestamp versions out of numeric order; `0067`/`0068` stored without numeric prefix in name |
| Triple 0093 on prod               | **Never applied** (prod stopped at 0071 before collision landed)                                                        |
| `schema_migrations` deterministic | **Yes** on Supabase CLI; collision only when duplicate numeric prefix in Git                                            |

### Staging (`vergeo-sandbox` — `iyasmrmbcrvlfxpzescb`)

| Field              | Value                             |
| ------------------ | --------------------------------- |
| Last applied       | `0079_clip_cost_guard`            |
| Missing vs Git     | `0080`–`0095`, `20260802153539_*` |
| Clips/intake flags | Present, all `enabled=false`      |

---

## API live probes (production)

| Endpoint                    | HTTP | Payload (safe fields)                                                                                     |
| --------------------------- | ---- | --------------------------------------------------------------------------------------------------------- |
| `GET /healthz`              | 200  | `{"status":"ok"}`                                                                                         |
| `GET /fingerprint`          | 200  | `env=production`, `git_sha=e4a7bb79…`, `image_tag=e4a7bb79…`, `supabase_project_ref=dpadrlxukcjbewpqympu` |
| `GET /readyz?checks=search` | 200  | `search_rpc=ok`, `search_embedding=ok`                                                                    |

**Deploy vs master:** `e4a7bb79` is an ancestor of `fcf2b191` — **BEHIND_MASTER** (docs-only delta on tip).

---

## Frontend deployment identity

| App      | Endpoint                                   | Result                                                                |
| -------- | ------------------------------------------ | --------------------------------------------------------------------- |
| Customer | `GET https://vergeo5.com/en/health`        | 200 JSON — `buildId=fcf2b191…`, `env=production` → **MATCHES_MASTER** |
| Vendor   | `GET https://vendor.vergeo5.com/en/health` | HTML app shell (not JSON health) → **UNKNOWN**                        |
| Admin    | `GET https://admin.vergeo5.com/en/health`  | Cloudflare Access login redirect → **BLOCKED_EXTERNAL**               |

---

## Feature flags (DB — not env secrets)

### Production

| Flag                 | Enabled |
| -------------------- | ------- |
| `public_launch`      | false   |
| `paid_tiers`         | false   |
| `abandoned_cart`     | false   |
| `wallet`             | false   |
| `zamtel_collections` | false   |

(No `clips` / `waha_vendor_intake` rows — migrations not applied.)

### Staging

All flags above plus `clips`, `clips_comments`, `waha_vendor_intake` — all **false**.

### OCI env gates (BLOCKED_EXTERNAL)

`PAYMENTS_ENABLED`, `PAYMENTS_ALLOW_PRODUCTION`, `PAYOUTS_ENABLED`, `STAGING_ALLOW_PAYOUTS` — **not readable** from this session (no SSH/OCI env access). Treat as **UNKNOWN**; feature flags and zero money rows support safe-default posture.

---

## Money row counts (production)

| Table                 | Count                                             |
| --------------------- | ------------------------------------------------- |
| `ledger_transactions` | 0                                                 |
| `payments`            | (not queried; status doc + ledger=0 implies none) |
| `orders`              | (not queried; status doc cites 0)                 |

---

## n8n production inventory (MCP read-only, 9 workflows visible)

| Workflow (live name)         | Git analogue                                                 | Status                |
| ---------------------------- | ------------------------------------------------------------ | --------------------- |
| payment reconciliation crons | `reconciliation.json` + `payment-sweeper.json`               | **ACTIVE**            |
| reservation sweeper          | `reservation-sweeper.json`                                   | **ACTIVE**            |
| notification dispatch        | `notification-dispatch.json`                                 | **ACTIVE**            |
| embeddings cron              | `embeddings-cron.json`                                       | **ACTIVE**            |
| operational nudges           | `kyc-nudge`, `low-stock`, `review-request`, `payout-failure` | **ACTIVE**            |
| admin digest                 | `admin-digest.json`                                          | **ACTIVE**            |
| analytics retention          | `analytics-retention.json`                                   | **ACTIVE**            |
| Database Backup              | `backup.json`                                                | **IMPORTED_INACTIVE** |
| shared error alert           | `money-workflow-error-alert.json`                            | **IMPORTED_INACTIVE** |

**IN_GIT_ONLY (not in MCP list):** `release-job`, `order-jobs`, `event-release`, `tickets-issue`, `tickets-release`, `daily-summary`, `funnel-abandon`, `abandoned-cart`, `export-purge`, `uptime-alert`, `waha-intake-*`, others — **UNKNOWN** import state (16 of 25 JSON files not confirmed active).

---

## RLS CI (RG-6) — current `master`

| Question                         | Answer                                                   |
| -------------------------------- | -------------------------------------------------------- |
| Role under test                  | `vergeo_rls_tester` (NOSUPERUSER, NOBYPASSRLS)           |
| Subject to RLS?                  | Yes — `assert_tester_is_rls_bound()` fails closed        |
| FORCE RLS                        | Required in migrations; tested per-table in `tests/rls/` |
| Impersonation                    | anon, authenticated customer/vendor/admin personas       |
| Cross-tenant read/write          | Matrix tests per table                                   |
| `continue-on-error` on RLS step? | **No** (only on demo seed step)                          |
| Workflow pass if RLS fails?      | **No** — blocking step                                   |
| PR #583 CI                       | RLS matrix **passed**                                    |

**Classification:** **RLS CI TRUSTWORTHY** (on current `master`; was FALSE-GREEN RISK before Aug 2026 fix).

---

## 0093 collision assessment (current Git)

| File                                                       | Purpose                                        |
| ---------------------------------------------------------- | ---------------------------------------------- |
| `0093_license_expiry_enforcement.sql`                      | Vendor licence expiry + `suspended_compliance` |
| `0094_vendor_storefront_collections_listing_analytics.sql` | Storefront collections + listing analytics     |
| `0095_rfq_threads.sql`                                     | B2B RFQ threads                                |

**Dependencies:** Disjoint objects; no cross-migration FK assumptions.  
**Historical risk (pre-583):** **REQUIRES_REMEDIATION** — `schema_migrations_pkey` collision.  
**Current Git:** **SAFE** (unique prefixes).  
**Production:** Not yet at 0093+ — apply order untested live.

---

## B2B cart read-path trace

| Step                       | Re-validates wholesale? | Evidence                                              |
| -------------------------- | ----------------------- | ----------------------------------------------------- |
| `POST /cart/items`         | Yes (add time)          | `fetch_listing()` D36 404 for wholesale-only          |
| `GET /cart`                | **No**                  | `_build_cart_response` uses stored `unit_price_ngwee` |
| `fetch_listings_for_items` | **No**                  | No `business_eligible` filter on read                 |
| `POST /checkout/session`   | **Yes**                 | `_rederive_line_prices` → 409 `checkout.cart_changed` |

**Classification:** **PARTIAL** — checkout blocks money path; cart read can show stale lines after eligibility change.

---

## Money drill prerequisite matrix

| Prerequisite                        | Status                                           |
| ----------------------------------- | ------------------------------------------------ |
| Sandbox Lenco config in code        | READY                                            |
| Webhook endpoint + signature verify | READY (code)                                     |
| Idempotency storage                 | READY (`webhook_events`, payment refs)           |
| Ledger / escrow schema              | READY (Git; prod DB at 0071)                     |
| Payment kill switch                 | READY (`PAYMENTS_ENABLED` gate in code)          |
| Payout kill switch                  | READY (`PAYOUTS_ENABLED` gate)                   |
| Reconciliation mechanism            | PARTIAL (code + n8n active; unproven with money) |
| Sandbox credentials (F9b)           | BLOCKED_EXTERNAL                                 |
| Synthetic vendor/order fixtures     | PARTIAL (demo seed + RLS fixtures)               |
| Production migration parity         | BLOCKED (prod 24+ migrations behind Git)         |

**Drill execution:** NOT RUN (per Batch 0.5 scope).
