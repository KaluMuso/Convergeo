> **Prepend `prompts/_header.md` (PROJECT HEADER) above this prompt.** Branch from and PR against **`master`**. Wave 3 runs 5 pebbles in parallel — **touch ONLY your files below**. You are the ONLY schema pebble this wave (no db.ts contention); M04-P01 owns `supabase/config.toml` + `supabase/functions/**` — do not touch those.

# M03-P04 — Orders spine & reservations schema

## 1. Context

**Wave 3 (parallel ×5).** Merged migrations: `0001` extensions · `0002` identity/vendors (+`has_role()`, FORCE-RLS + `session_user` guard-trigger patterns) · `0003` catalog (products, `vendor_listings`, `listing_images`) · `0004` services/events (**`tickets.order_item_id uuid` exists as a bare nullable column — YOU complete its FK**) · `0008` config (`delivery_zones`, `platform_config.cod_cap_ngwee`, `commission_rates`). Conventions: one migration per pebble, tables+indexes+RLS+FORCE in-file, `bigint` ngwee, `updated_at` triggers, commented policies. Spec: `docs/plan/02-pebbles/M03-data-core.md` §P04.

## 2. Objective & scope

Migration `0005_orders.sql`: addresses, checkout groups, orders, order items + per-kind detail tables, stock reservations, order-events audit — the transactional spine every money/fulfilment flow rides on.
**Non-goals:** no ledger/payments/payouts (`0006`/money schema, W4), no state-machine transition functions (M09, later — schema + guards only), no seeds beyond tests.

## 3. Files (create/modify ONLY these)

- **Create:** `supabase/migrations/0005_orders.sql` · `supabase/tests/0005_orders.test.sql`
- **Modify:** `packages/types/src/db.ts` — regenerate/extend (sole owner this wave).
  **Guardrail: nothing else.**

## 4. Implementation spec

Tables (uuid pks, timestamps + trigger, RLS + FORCE everywhere, commented policies):

- **`addresses`** — user_id FK auth.users, label, landmark text NOT NULL (Zambian addressing), lat/lng nullable, phone text.
- **`checkout_groups`** — customer_id FK, `idempotency_key text UNIQUE NOT NULL`, totals: `subtotal_ngwee/delivery_fee_ngwee/total_ngwee bigint NOT NULL check (>= 0)`, status `check in ('pending','completed','abandoned','expired')`.
- **`orders`** — checkout_group_id FK, vendor_id FK, customer_id FK, **status `check in ('placed','confirmed','processing','ready','shipped','delivered','completed','cancelled')` default 'placed'**, fulfilment `check in ('delivery','pickup')`, delivery_zone text nullable, address_id FK nullable, `delivery_fee_ngwee bigint check (>= 0)`, `cod boolean default false`, `commission_snapshot jsonb NOT NULL default '{}'` (rate at order time — never recomputed later). Indexes: (vendor_id, status), (customer_id, created_at desc), checkout_group_id.
- **`order_items`** — order_id FK, **`item_kind check in ('product','ticket','service_deposit','service_balance')`**, qty int check (>0), `unit_price_ngwee bigint NOT NULL check (>0)`, title_snapshot text.
- **Detail tables** — `order_item_products` (order_item_id pk/FK, listing_id FK vendor_listings, product_id FK nullable), `order_item_tickets` (order_item_id pk/FK, ticket_type_id FK, instance_id FK), `order_item_services` (order_item_id pk/FK, job_id FK nullable, quote_id FK nullable).
- **Complete the 0004 contract:** `alter table tickets add constraint tickets_order_item_id_fkey foreign key (order_item_id) references order_items(id);`
- **`stock_reservations`** — listing_id FK, checkout_group_id FK, qty int check (>0), `expires_at timestamptz NOT NULL` + **index on expires_at** (sweeper scans it). Unique(listing_id, checkout_group_id).
- **`order_events`** — order_id FK, actor uuid nullable, from_status/to_status text, note text, created_at. **Audit trigger on `orders`:** any status change inserts an order_events row automatically.
- **RLS:** addresses — owner CRUD own, admin all. checkout_groups — customer select own; **no client insert/update** (server-role creates them — comment why: totals/idempotency are server-computed). orders — customer select own; vendor select where vendor_id is theirs (owner_user_id join); **status column NOT updatable by ANY client role** — guard trigger (0002 `session_user` pattern) rejects client-side `UPDATE orders SET status`, service_role/admin pass; no client inserts. order_items + detail tables — visible to the parent order's customer + vendor; no client writes. stock_reservations — **no client policies at all** (server-only). order_events — parent-order parties select; trigger-written only.

## 5–8. UI/UX · Responsiveness · Performance · SEO

N/A. EXPLAIN two hot paths (vendor open-orders queue by (vendor_id,status); expiring reservations by expires_at) and paste plans.

## 9. Security

Client status flip impossible (the M09 state machine will be the only mutation path via server functions); totals/commission snapshots are server-written; reservation table invisible to clients; cross-customer/vendor isolation in the matrix.

## 10. Tests (RUN before reporting — pattern per `supabase/tests/0002/0003/0004` tests)

Migrations 0001→0008 apply clean in order. **Direct `UPDATE orders SET status` as customer AND as vendor → denied** (the must-pass). Customer A cannot see customer B's order; vendor sees only own-vendor orders; stranger sees no order_items. Client insert into checkout_groups/stock_reservations denied. Status change via service role writes an order_events audit row (assert before/after statuses). Duplicate idempotency_key rejected. tickets FK now enforced (insert ticket with bogus order_item_id fails). Regenerate `db.ts`; `pnpm --filter @vergeo/types typecheck`.

## 11. Acceptance criteria / DoD

- [ ] `db reset` clean; all 9 tables RLS+FORCE, commented.
- [ ] Client status UPDATE denied for every role (tested); audit trigger writes on every status change.
- [ ] tickets.order_item_id FK completed; reservation expiry index present; idempotency unique.
- [ ] EXPLAIN shows index use on both hot paths; db.ts regenerated + compiles.

## 12. IMPLEMENTATION REPORT

When finished, output an **Implementation Report** in exactly this format:
**PEBBLE:** M03-P04 — Orders spine & reservations schema
**STATUS:** COMPLETE | PARTIAL | BLOCKED
**FILES:** each path + one-line description
**DEVIATIONS:** (or "none")
**TESTS:** paste db reset + denial matrix + audit-trigger + EXPLAIN output
**EXCERPTS:** full SQL of the orders RLS policies + the status guard trigger + audit trigger (authz/integrity surfaces) — nothing else
**QUESTIONS:** (or "none")
