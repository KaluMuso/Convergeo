# Batch 1A.2 — Staging Schema Catch-Up Evidence

**Date:** 2026-08-06  
**Session:** Batch 1A.2 controlled staging schema catch-up  
**Repository SHA:** `ea80af3d92497f44ad416a59115e418eea8a8aa7` (`master`)  
**Working branch:** `cursor/batch1a2-staging-schema-catchup-0508`  
**Staging project:** `iyasmrmbcrvlfxpzescb` (`vergeo-sandbox`, eu-west-1)  
**Production project (untouched):** `dpadrlxukcjbewpqympu` (`Vergeo5`)

---

## Before

| Field                              | Value                                                                                                                    |
| ---------------------------------- | ------------------------------------------------------------------------------------------------------------------------ |
| Migration tip                      | `0079_clip_cost_guard` (79 rows)                                                                                         |
| Public table count                 | 89                                                                                                                       |
| Staging API SHA                    | `161b58a3e1973b79abd4fc8064611c50fa0268c8`                                                                               |
| Staging API `supabase_project_ref` | `iyasmrmbcrvlfxpzescb` ✓                                                                                                 |
| `/healthz`                         | 200 `{"status":"ok"}`                                                                                                    |
| `/readyz`                          | 200 (`search_embedding=degraded`)                                                                                        |
| `/readyz?checks=search`            | 200 (`search_rpc=ok`)                                                                                                    |
| Feature flags                      | All OFF (`public_launch`, `clips`, `waha_vendor_intake`, `paid_tiers`, `wallet`, `zamtel_collections`, `abandoned_cart`) |
| `vendor_locations`                 | 0                                                                                                                        |
| `vendor_listings`                  | 1                                                                                                                        |
| `cart_items`                       | 1                                                                                                                        |
| `orders`                           | 0                                                                                                                        |
| `ledger_transactions`              | 0                                                                                                                        |
| `payments`                         | 0                                                                                                                        |

---

## Dry Run

| Field                                 | Value                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                    |
| ------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `supabase db push --dry-run --linked` | **BLOCKED_EXTERNAL** — `SUPABASE_ACCESS_TOKEN` not available in agent VM; `supabase link` rejected with `LegacyPlatformAuthRequiredError`                                                                                                                                                                                                                                                                                                                                                                                                                |
| Equivalent derivation                 | Compared Git `supabase/migrations/*.sql` (sorted) against `supabase_migrations.schema_migrations` via Supabase MCP                                                                                                                                                                                                                                                                                                                                                                                                                                       |
| Pending count                         | **17** (exact match to Batch 1A.1 expected list)                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                         |
| Pending sequence                      | `0080_vendor_location_details` → `0081_listing_location_stock` → `0082_enquiry_threads` → `0083_vendor_follows` → `0084_vendor_licences` → `0085_product_classes` → `0086_cart_line_price_guard` → `0087_product_class_enum` → `0088_user_saves` → `0089_vendor_locations_geo_index` → `0090_stock_reservation_location` → `0091_admin_moderator_roles` → `0092_service_categories` → `0093_license_expiry_enforcement` → `0094_vendor_storefront_collections_listing_analytics` → `0095_rfq_threads` → `20260802153539_rls_policy_contract_remediation` |
| Divergence                            | **None** — no extra, missing, or reordered migrations                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                    |

---

## Apply

| Field              | Value                                                                                                                                                                                 |
| ------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Mechanism          | Supabase MCP `execute_sql` (authorized per programme: "legitimate Supabase CLI/MCP/environment access") with ledger `INSERT INTO supabase_migrations.schema_migrations` per file      |
| CLI `db push`      | Not used — token unavailable                                                                                                                                                          |
| Deviation          | Initial `0080`/`0081` attempted via MCP `apply_migration` (timestamp ledger keys `20260806185255`/`20260806185310`); corrected to `0080`/`0081` via ledger `UPDATE` before continuing |
| Result             | **All 17 migrations applied successfully**                                                                                                                                            |
| Failures           | None                                                                                                                                                                                  |
| Production touched | **No**                                                                                                                                                                                |

### Applied migrations (chronological)

1. `0080_vendor_location_details` ✓
2. `0081_listing_location_stock` ✓
3. `0082_enquiry_threads` ✓
4. `0083_vendor_follows` ✓
5. `0084_vendor_licences` ✓
6. `0085_product_classes` ✓
7. `0086_cart_line_price_guard` ✓
8. `0087_product_class_enum` ✓
9. `0088_user_saves` ✓
10. `0089_vendor_locations_geo_index` ✓
11. `0090_stock_reservation_location` ✓
12. `0091_admin_moderator_roles` ✓
13. `0092_service_categories` ✓
14. `0093_license_expiry_enforcement` ✓
15. `0094_vendor_storefront_collections_listing_analytics` ✓
16. `0095_rfq_threads` ✓
17. `20260802153539_rls_policy_contract_remediation` ✓

---

## After

| Field                    | Value                                                       |
| ------------------------ | ----------------------------------------------------------- |
| Migration tip            | `20260802153539_rls_policy_contract_remediation`            |
| Numeric band complete    | `0080`–`0095` all present in ledger                         |
| Ledger classification    | **STAGING_SCHEMA_AT_GIT_TIP**                               |
| Staging API SHA          | `161b58a3` (unchanged — no API deploy per scope)            |
| `/healthz`               | 200                                                         |
| `/readyz`                | 200                                                         |
| `/readyz?checks=search`  | 200 (`search_rpc=ok`, `search_embedding=degraded`)          |
| Feature flags            | All remain OFF (no `payments`/`payouts` rows — fail-closed) |
| `orders`                 | 0                                                           |
| `ledger_transactions`    | 0                                                           |
| `payments`               | 0                                                           |
| `vendor_locations`       | 0                                                           |
| `listing_location_stock` | 0 (no tracked listings with primary location)               |
| `vendor_licences`        | 0                                                           |

### Schema validation (spot checks)

| Artifact                                                                                       | Status             |
| ---------------------------------------------------------------------------------------------- | ------------------ |
| `enquiry_threads`, `enquiry_messages`                                                          | PRESENT            |
| `vendor_follows`, `vendor_licences`, `user_saves`                                              | PRESENT            |
| `rfq_threads`, `rfq_messages`                                                                  | PRESENT            |
| `service_categories`, `listing_location_stock`                                                 | PRESENT            |
| `vendor_storefront_collections`, `listing_analytics`                                           | PRESENT            |
| `vendor_locations.label/is_primary/status` columns                                             | PRESENT            |
| `vendor_listings.product_class/sale_unit/fulfilment_mode/defect_notes`                         | PRESENT            |
| `vendor_locations_lat_lng_idx` (0089)                                                          | PRESENT            |
| `cart_items_pickup_location_id_fkey` (0090)                                                    | PRESENT            |
| `cart_items` client INSERT/UPDATE grants                                                       | **REVOKED** (0086) |
| `guard_review_reply_columns` (TS remediation)                                                  | PRESENT            |
| Key functions (`vendor_licence_is_valid`, `listing_line_total_ngwee`, `vendor_follower_count`) | PRESENT            |
| RLS enabled+forced on `enquiry_threads`, `rfq_threads`, `cart_items`, etc.                     | VERIFIED           |

### RLS verification

| Check                           | Method                                                               | Result                                                                        |
| ------------------------------- | -------------------------------------------------------------------- | ----------------------------------------------------------------------------- |
| CAN-ORD-002 grant revoke        | `information_schema.role_table_grants` on staging                    | **PASS** — `anon`/`authenticated` have SELECT/DELETE only; no INSERT/UPDATE   |
| RLS FORCE on new tables         | `pg_class.relforcerowsecurity`                                       | **PASS**                                                                      |
| Policy coverage on new tables   | `pg_policies` count                                                  | 13 policies on sampled tables                                                 |
| Full `pytest tests/rls` harness | `uv run pytest tests/rls/test_cart_items_client_write_revocation.py` | **NOT RUN** — no `psql`/local Postgres in VM; no `SUPABASE_DB_URL` to staging |

### Backfill validation

| Migration                     | Expected                   | Observed                                |
| ----------------------------- | -------------------------- | --------------------------------------- |
| 0080 vendor locations primary | Backfill on existing rows  | N/A — 0 `vendor_locations` rows         |
| 0081 listing location stock   | Backfill tracked listings  | 0 rows — vendor has no primary location |
| 0093 licence body             | Backfill if licences exist | 0 `vendor_licences` rows                |

No constraint failures. No unexpected data loss (`cart_items` still 1, `vendor_listings` still 1).

### Current API + new DB compatibility (old API, new schema)

| Endpoint                        | HTTP | Notes                                        |
| ------------------------------- | ---- | -------------------------------------------- |
| `GET /healthz`                  | 200  | Unchanged                                    |
| `GET /readyz?checks=search`     | 200  | `search_rpc=ok`                              |
| `GET /search?q=test`            | 200  | Results returned                             |
| `GET /catalog/listings?limit=1` | 200  | Listing data returned                        |
| `GET /products/{id}`            | 200  | Product lookup OK                            |
| `GET /cart`                     | 200  | Cart read OK                                 |
| `POST /checkout/session`        | 401  | Auth required (expected; no money initiated) |
| `GET /enquiries`                | 404  | Router absent on deployed API SHA            |

**Classification:** **PARTIAL COMPAT** — core browse/search/cart read paths healthy; enquiries/RFQ routes absent on API (pre-existing; not a regression from schema apply).

### n8n health

| Workflow                     | Status | Post-schema execution probe             |
| ---------------------------- | ------ | --------------------------------------- |
| Reservation sweeper          | ACTIVE | UNKNOWN (recent execution fetch failed) |
| Notification dispatch        | ACTIVE | UNKNOWN                                 |
| Embeddings cron              | ACTIVE | UNKNOWN                                 |
| Payment reconciliation crons | ACTIVE | UNKNOWN                                 |

Workflows remain ACTIVE; no schema-dependent failures observed. No financial workflows triggered.

### Feature gate state

All intentionally gated capabilities remain **OFF**. Schema existence did not activate features.

### Enquiries triangle state

| Layer          | State                                                                                     |
| -------------- | ----------------------------------------------------------------------------------------- |
| DB capability  | **PRESENT** (`enquiry_threads`, `enquiry_messages`)                                       |
| API capability | **ABSENT** (`enquiries.py` not in deployed SHA `161b58a3`; `GET /enquiries` → 404)        |
| Customer CTA   | **HIDDEN** (fail-closed probe in `apps/customer/lib/enquiries-capability.ts`; 404 → hide) |

### Financial safety

| Table                 | Before | After | Delta |
| --------------------- | ------ | ----- | ----- |
| `orders`              | 0      | 0     | 0     |
| `ledger_transactions` | 0      | 0     | 0     |
| `payments`            | 0      | 0     | 0     |

No payment rows, ledger transactions, escrow releases, or payouts created by migration apply.

---

## Deviations

1. **Apply mechanism:** MCP `execute_sql` + ledger INSERT used instead of `supabase db push --linked` (CLI token unavailable).
2. **Ledger correction:** Two initial `apply_migration` calls recorded timestamp versions; corrected to `0080`/`0081` before continuing.
3. **RLS pytest:** Full repository RLS harness not executed against staging (no DB URL credentials in VM).

---

## GO / NO-GO

**GO — STAGING SCHEMA CURRENT**

Staging database schema is at Git tip (`0095` + `20260802153539`). All 17 pending migrations applied. Feature flags fail-closed. Financial tables unchanged. Core API smoke (search, catalog, cart read) passes against new schema with deployed API `161b58a3`.

---

## Recommended next action

**A.** Deploy `master` (≥ `ea80af3d`) API image to **staging only** and run API compatibility regression (enquiries, RFQ, cart write paths, branch stock). Do not touch production.
