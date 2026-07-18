# Database Schema Inventory — Vergeo5 (live `dpadrlxukcjbewpqympu`)

**Audit date:** 2026-07-18 · **Source rank:** live DB (1) via read-only Supabase SQL / `list_tables`  
**Privacy:** aggregates + catalog metadata only; no PII/payment references dumped.

Status enums in Postgres are largely **CHECK-constrained `text`** (no `pg_enum` types found in `public`).

---

## 1. Global facts

| Fact                                     | Evidence                                                       | Status   |
| ---------------------------------------- | -------------------------------------------------------------- | -------- |
| RLS enabled on inventoried public tables | `list_tables` + `pg_class.relrowsecurity`                      | VERIFIED |
| FORCE RLS common                         | most tables `relforcerowsecurity=true`; exceptions noted below | VERIFIED |
| Views                                    | `analytics_event_stream`, `ask_usage_monthly`                  | VERIFIED |
| Money unit                               | `*_ngwee` `bigint` columns                                     | VERIFIED |
| Applied migrations                       | see `production-evidence.md`                                   | VERIFIED |

**FORCE RLS false (live):** `product_relations`, `ticket_type_instances`, `ticket_type_price_tiers` (PARTIAL — confirm intentional).

---

## 2. Inventory by domain

### Customer

| Table                  | Key fields                                                      | Ownership / status | Notes                         |
| ---------------------- | --------------------------------------------------------------- | ------------------ | ----------------------------- |
| `profiles`             | `id`, timestamps                                                | 1:1 auth user      | 3 rows                        |
| `addresses`            | `user_id`, timestamps                                           | customer-owned     | 0 rows                        |
| `carts` / `cart_items` | `user_id`/`guest`, `listing_id`, `status`, price snapshot ngwee | cart owner         | 3 / 2 rows                    |
| `business_buyers`      | `user_id`, `status` CHECK                                       | B2B eligibility    | 0 rows                        |
| `beta_invites`         | `code`, capacity/used                                           | launch gate        | 0 rows; `public_launch=false` |

### Vendor

| Table              | Key fields                                         | Ownership / status | Notes                 |
| ------------------ | -------------------------------------------------- | ------------------ | --------------------- |
| `vendors`          | `id`, `slug`, `status`, `archetype`                | vendor org         | 3 active demo vendors |
| `vendor_listings`  | `vendor_id`, `product_id`, `price_ngwee`, `status` | vendor-owned       | 134                   |
| `vendor_locations` | `vendor_id`                                        | vendor             | 0                     |
| `vendor_quotas`    | vendor limits                                      | config             | 3                     |
| `kyc_records`      | `vendor_id`, `status`                              | KYC lifecycle      | 0                     |
| `listing_images`   | `listing_id`, `cloudinary_public_id`, `position`   | media              | **134 demo/** IDs     |

### Catalogue

| Table                   | Key fields            | Notes                                              |
| ----------------------- | --------------------- | -------------------------------------------------- |
| `categories`            | tree/`slug`           | 74                                                 |
| `products`              | `status`, timestamps  | 150                                                |
| `product_relations`     | `product_id`          | present (migration 0052 under nonstandard version) |
| `prohibited_categories` | keywords/categories   | 7                                                  |
| `synonyms`              | locale variants       | 10                                                 |
| `search_documents`      | FTS/vector projection | 288                                                |
| `embedding_jobs`        | `status` queue        | 288                                                |
| `merch_slots`           | homepage merch        | 1                                                  |
| `event_categories`      | taxonomy              | 6                                                  |

**Missing vs repo tip:** `translation_overrides` (0053), service bookable column (0055), service-review extensions (0054) — MISSING on live.

### Orders

| Table                                                              | Key fields                                               | Ownership / status        |
| ------------------------------------------------------------------ | -------------------------------------------------------- | ------------------------- |
| `checkout_groups`                                                  | `customer_id`, `idempotency_key`, money totals, `status` | customer checkout fan-out |
| `orders`                                                           | `customer_id`, `vendor_id`, `status`                     | per-vendor order          |
| `order_items` (+ `order_item_products` / `_services` / `_tickets`) | line items                                               |                           |
| `order_events`                                                     | audit trail of order transitions                         |                           |
| `stock_reservations`                                               | `listing_id` holds                                       | service-role oriented     |
| `returns` / `disputes` / `reviews` / `review_aggregates`           | post-order trust                                         | all empty                 |

### Payments / money

| Table                                                         | Key fields                                         | Notes                             |
| ------------------------------------------------------------- | -------------------------------------------------- | --------------------------------- |
| `payments`                                                    | `amount_ngwee`, `status`, `lenco_reference` UNIQUE | **0 rows**                        |
| `ledger_accounts` / `ledger_transactions` / `ledger_postings` | double-entry; `idempotency_key`                    | **0 txns**; service-role oriented |
| `payouts` / `refunds`                                         | `amount_ngwee`, `status`                           | 0                                 |
| `webhook_events`                                              | inbound payment webhooks                           | 0                                 |
| `reconciliation_reports`                                      | daily Lenco-vs-ledger                              | 0                                 |
| `invoices` / `invoice_counters`                               | ZRA-ready sequencing                               | 0                                 |
| `commission_rates`                                            | bps                                                | 9                                 |
| `platform_config`                                             | keyed config                                       | 16                                |

### Delivery / pickup

| Table               | Key fields                                               | Notes                               |
| ------------------- | -------------------------------------------------------- | ----------------------------------- |
| `delivery_zones`    | fee ngwee                                                | 3                                   |
| Order pickup tokens | from migration `0017` (column-level; not re-listed here) | schema present via migrations ≤0050 |

### Admin / RBAC

| Table           | Key fields               | Notes                                              |
| --------------- | ------------------------ | -------------------------------------------------- |
| `user_roles`    | `user_id`, `role`        | 3 rows; RLS on, **0 policies** (service-role only) |
| `feature_flags` | `flag`, `enabled`        | 5 flags, all false                                 |
| `config_audit`  | config change audit      | 9                                                  |
| `audit_log`     | admin/mutation audit     | 0 rows; RLS on, **0 policies**                     |
| `flags`         | content moderation flags | 0                                                  |
| `beta_invites`  | invite codes             | 0                                                  |

### Notifications

| Table                 | Notes                                                            |
| --------------------- | ---------------------------------------------------------------- |
| `notification_outbox` | RLS on, **0 policies**; 0 rows; drained by n8n dispatch workflow |

### Analytics

| Table / view                                                            | Notes                     |
| ----------------------------------------------------------------------- | ------------------------- |
| `funnel_events`                                                         | 0 rows                    |
| `analytics_events`                                                      | 0 rows                    |
| `search_query_log`                                                      | 0 rows                    |
| `analytics_event_stream`                                                | VIEW over streams         |
| Ask: `ask_cache`, `ask_usage`, `ask_spend_monthly`, `ask_usage_monthly` | empty / quota scaffolding |

### Tickets / events / services

| Table                                                                                                                                                | Notes                                  |
| ---------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------- |
| `events`, `event_instances`, `ticket_types`, `ticket_type_instances`, `ticket_type_price_tiers`, `tickets`, `ticket_transfers`, `order_item_tickets` | schema present; **0** operational rows |
| `services`, `jobs`, `job_quotes`                                                                                                                     | 1 service row; jobs/quotes 0           |

### Integrations / system

| Table            | Notes                       |
| ---------------- | --------------------------- |
| `webhook_events` | payment ingress             |
| `rate_counters`  | OTP/auth limits; 0 policies |
| `embedding_jobs` | search backfill             |

---

## 3. Relationships (high level)

- Auth user → `profiles.id`
- `user_roles.user_id` → auth user
- `vendors` ← `vendor_listings.vendor_id` → optional `products`
- `checkout_groups.customer_id` → orders (`customer_id`,`vendor_id`) → `order_items`
- `payments.checkout_group_id` → checkout group; `lenco_reference` unique
- Ledger: `ledger_transactions` → `ledger_postings` → `ledger_accounts` (optional `vendor_id`)
- Events: `events` → `event_instances` / `ticket_types` → `tickets`
- Search projection: triggers maintain `search_documents` from catalogue entities

---

## 4. Indexes & constraints (sample)

Live indexes include ownership/status helpers such as:

- `orders_vendor_id_status_idx`, `orders_customer_id_created_at_idx`, `orders_checkout_group_vendor_key`
- `payments_lenco_reference_key`, `payments_status_idx`
- `ledger_transactions_idempotency_key_key`
- `notification_outbox_status_next_retry_at_idx`
- Cart uniqueness `cart_items_cart_id_listing_id_key`
- Money CHECKs on ngwee ≥ 0 style constraints across checkout/cart/payouts

Full index list truncated in probe (`LIMIT`); re-run safe query pack for complete dump if needed.

---

## 5. What this role could read

Audit used Supabase MCP SQL as a privileged project operator (service-level). That is **not** the anon/authenticated end-user view.

| Capability                                              | Result                                     |
| ------------------------------------------------------- | ------------------------------------------ |
| Read `information_schema` / `pg_catalog` / RLS metadata | yes                                        |
| Aggregate counts on public tables                       | yes                                        |
| Read feature flags / vendor slugs / demo image prefixes | yes                                        |
| Confirm absence of money/ticket rows                    | yes                                        |
| Export customer PII / payment refs                      | **forbidden by audit contract** (not done) |
| Write/DDL                                               | **not performed**                          |

End-user RLS capabilities: see `access-and-rls-inventory.md`.
