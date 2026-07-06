# M03 — Data Core (Schema, RLS, Types, Search Projection) — Pebbles

10 pebbles. Each schema pebble owns exactly ONE migration file (`supabase/migrations/NNNN_slug.sql`) with tables + indexes + **RLS policies for those tables** in the same file. All money columns `bigint` ngwee. `updated_at` triggers everywhere. After M03-P08 merges, migrations are **additive-only** (convention rule #6). FK targets must exist in an earlier-merged migration — waves in `03-waves.md` respect this.

---

### M03-P01 — Identity, vendors & KYC schema `M`
**Deps:** M01-P03 · **Files:** `supabase/migrations/0002_identity_vendors.sql`
`profiles` (1:1 auth.users; phone, display name, locale, notif prefs jsonb), `user_roles` (customer/vendor/admin — server-writable only), `vendors` (slug, status machine: draft→pending_kyc→active→suspended, kyc_tier 1|2|3, preferred_badge bool, caps snapshot), `vendor_locations` (lat/lng, landmark text, hours jsonb), `kyc_records` (tier, doc storage paths, momo_name_match result, status, reviewer notes). RLS: users see/edit own profile; vendor rows visible publicly only when `active`; kyc_records owner-read + admin-all; roles never client-writable.
**AC:** `db reset` clean; policy comments explain each rule; role escalation via PostgREST impossible.
**Tests:** (harness lands P09 — this pebble ships SQL assertions) policy smoke via `supabase test db` for owner/other/anon on each table.

### M03-P02 — Catalog schema `L`
**Deps:** P01 · **Files:** `supabase/migrations/0003_catalog.sql`
`categories` (tree: parent_id + materialized path, commission_key, vat_flag bool default false, prohibited bool), `products` (canonical: name, slug, spec jsonb, brand, category_id, status: pending_moderation→active→merged; `aliases text[]` incl. Bemba/Nyanja terms), `vendor_listings` (vendor_id, product_id nullable for quick-list, title override, `price_ngwee bigint`, condition enum, stock_mode enum(tracked|always_available), stock_qty, `wholesale bool`, `price_tiers jsonb` [{min_qty,price_ngwee}], `moq int`, `returnable bool` + `return_window_hours`, status), `listing_images` (cloudinary public_id, position ≤8 check). RLS: active listings public-read; vendors CRUD own; canonical products public-read, insert as pending only.
**AC:** ≤8-images enforced by constraint; price float impossible (bigint); category path queries indexed.
**Tests:** constraint tests (9th image rejected, negative price rejected); cross-vendor listing update denied.

### M03-P03 — Services & events schema `M`
**Deps:** P01 · **Files:** `supabase/migrations/0004_services_events.sql`
`services` (vendor-owned: category, description, service_area, from_price_ngwee nullable, portfolio images), `jobs` (RFQ: customer_id, category, description, preferred_date, budget_band, status: open→quoted→accepted→completed|cancelled), `job_quotes` (provider_id, amount_ngwee, message, status), `events` (organiser vendor_id, venue, lat/lng, images, status), `event_instances` (starts_at, capacity), `ticket_types` (kind: fixed|tier|free_rsvp, price_ngwee, qty_cap), `tickets` (instance, type, order_item link added in P04 via P05? — column added here as nullable uuid, FK added in 0005; status: issued→checked_in→transferred|void, qr_secret, pin_hash, checked_in_at). RLS: published events/services public; jobs visible to owner + matched providers; **quotes visible ONLY to quoting provider + job owner** (providers cannot see rivals).
**AC:** quote-privacy policy proven; capacity fields NOT NULL.
**Tests:** provider A cannot read provider B's quote on same job; anon cannot read draft events.

### M03-P04 — Orders spine & reservations schema `L`
**Deps:** P02, P03 · **Files:** `supabase/migrations/0005_orders.sql`
`addresses` (user, label, landmark, lat/lng, phone), `checkout_groups` (one customer submit → N vendor orders; totals ngwee, idempotency_key unique), `orders` (vendor_id, customer_id, status enum per M09 machine, fulfilment: delivery|pickup, delivery_zone, fees ngwee, cod bool, commission snapshot jsonb), `order_items` (`item_kind enum(product|ticket|service_deposit|service_balance)`, qty, unit_price_ngwee, detail refs), detail tables `order_item_products`, `order_item_tickets`, `order_item_services`; `stock_reservations` (listing_id, qty, checkout_group, expires_at); `order_events` audit table (actor, from→to, note). Tickets.order_item_id FK completed here. RLS: customer sees own orders; vendor sees own vendor orders; **status column not directly updatable by any client role** (transitions via server functions only).
**AC:** direct `UPDATE orders SET status` as customer/vendor denied; reservation expiry index present.
**Tests:** RLS denial matrix; audit row required trigger.

### M03-P05 — Money schema (ledger, payments, payouts, refunds, invoices) `L`
**Deps:** P04 · **Files:** `supabase/migrations/0006_money.sql`
`ledger_accounts` (platform_cash, escrow, commission_revenue, vendor_payable per vendor, cod_receivable…), `ledger_transactions` + `ledger_postings` (account, amount_ngwee signed; **trigger: postings per transaction must sum to 0**), `payments` (checkout_group, provider enum(lenco), rail enum(mtn|airtel|zamtel|card|cod), lenco_reference unique — charset `[-._A-Za-z0-9]`, status machine, raw payloads jsonb), `webhook_events` (provider, event_id unique — idempotency, signature_valid, processed_at), `payouts` (vendor, amount_ngwee, rail, lenco_reference, status, resolve_snapshot), `refunds` (order, lane 1|2, computed breakdown jsonb, status, executed-as-payout ref), `invoice_counters` (series, next_no — **gapless via SELECT…FOR UPDATE**), `invoices` (sequential no, order, snapshot jsonb, vat fields). RLS: ledger/webhooks service-role only; vendors read own payouts; customers read own payments/invoices.
**AC:** zero-sum trigger proven; duplicate webhook event_id rejected at DB level; ints everywhere.
**Tests:** SQL tests: unbalanced txn rejected; duplicate lenco_reference rejected; counter concurrency (two tx serialize).

### M03-P06 — Trust & ops schema `M`
**Deps:** P04 · **Files:** `supabase/migrations/0007_trust_ops.sql`
`reviews` (order_item-linked ⇒ verified-purchase by construction, 1–5 int, text, photos, vendor_reply, status: published→flagged→removed), `disputes` (order, opener, evidence paths, vendor_response, admin decision, status machine), `returns` (order_item, lane, evidence, fee breakdown jsonb, status), `notification_outbox` (dedupe_key unique, channel, template, payload jsonb, status: pending→sent→failed, attempts, next_retry_at), `audit_log` (actor, action, entity, before/after jsonb — admin mutations), `flags` (entity polymorphic ref, reason, reporter). RLS: reviews public-read, author-write-once; outbox/audit service-role only; dispute parties see own.
**AC:** review requires delivered order_item (FK+check); outbox dedupe_key unique.
**Tests:** unverified review insert denied; double review on same item denied.

### M03-P07 — Config tables & seeds `M`
**Deps:** P01 · **Files:** `supabase/migrations/0008_config.sql`
`commission_rates` (category_key → bps; seed D4: electronics 500, home 800, fashion/beauty 1000, services 1200, tickets 500, supplies 300, groceries 500, default 800; free events 0), `delivery_zones` (Lusaka bands + fees ngwee, free_delivery_threshold **20,000 ngwee = K200**), `platform_config` typed rows (cod_cap_ngwee=50000 ⚠F8, reservation_ttl_min, ai quotas: guest 3/free 25, ai_monthly_cap_usd 15, release windows 48h/7d), `feature_flags` (paid_tiers, abandoned_cart, wallet — off), `merch_slots` (slot key, variant key, payload jsonb, schedule from/to, position), `prohibited_categories` + `quotas` (T1 caps: 30 listings, first-5-orders ≤K500, payout velocity). RLS: public-read where needed (zones, commissions), **admin-role write only**, audit trigger.
**AC:** all D4/D12/D16/D23 numbers present as seeds (ngwee-correct); non-admin write denied.
**Tests:** seed-value assertions; RLS write denial; ngwee arithmetic sanity (K500 = 50,000 ngwee).

### M03-P08 — Search projection & pgvector `L`
**Deps:** P02, P03 · **Files:** `supabase/migrations/0009_search.sql`
`search_documents` (entity_kind product|listing|service|event|vendor, entity_id, title, body, category path, price_min/max ngwee, lat/lng, locale terms/aliases, `tsv tsvector` generated, `embedding vector(384)` nullable, boost_signals jsonb, is_public); sync **triggers** on all source tables (insert/update/delete/status changes); GIN(tsv), GIN trgm(title), HNSW(embedding) indexes; `search_rrf(query text, query_embedding vector, filters jsonb)` SQL function: FTS lane + trgm fuzzy lane + vector lane fused by Reciprocal Rank Fusion with boost for in-stock/verified/below-median; `synonyms` table (term→canonical, Bemba/Nyanja seed rows: chitenge/chitange etc.).
**AC:** trigger sync proven (update listing → document updated; unpublish → removed); EXPLAIN uses indexes on all three lanes.
**Tests:** sync trigger tests per entity kind; RRF returns fused order on fixture data; private entities never projected.

### M03-P09 — RLS test harness & seed framework `L`
**Deps:** P01–P08 · **Files:** `services/api/tests/rls/` (conftest with role-JWT factories: anon/customer/vendorA/vendorB/admin; per-table matrix tests), `scripts/seed.py`, `services/api/tests/fixtures/demo/`
Pytest harness executing PostgREST/SQL as each role; **full isolation matrix**: every table × {anon, customer, other-customer, vendor, other-vendor, admin} × {select, insert, update, delete}; seed framework: idempotent `scripts/seed.py --env local|staging` producing a browsable demo dataset (vendors incl. sandbox-flagged demo vendor, listings, events, services, orders in varied states).
**AC:** matrix has an explicit expectation for EVERY table (no unlisted tables — CI check diffs information_schema); cross-vendor denial proven; seed → home/PLP/PDP browsable.
**Tests:** the matrix itself + `test_no_untested_tables`.

### M03-P10 — Type generation, Pydantic base & catalog seed `L`
**Deps:** P01–P08 · **Files:** `packages/types/src/db.ts` (generated, committed), `packages/types/src/api/` (shared API DTO types), `services/api/app/schemas/base.py` (strict Pydantic base: `model_config = ConfigDict(strict=True)`, NgweeInt annotated type, reference codec `ord-*`/`pay-*`/`rfd-*` validators), `supabase/migrations/0010_seed_catalog.sql` (or `supabase/seed.sql`), `docs/plan/erd.md`
Category tree seed (8 departments → ~60–80 subcategories per D8/Bible) + **~150 canonical product stubs** (name, spec skeleton, category, aliases incl. Bemba/Nyanja) per D25; ERD doc (mermaid) of the whole schema.
**AC:** typegen drift check green; NgweeInt rejects floats at parse; founder can review seed as a readable SQL/fixture file; ERD covers every table.
**Tests:** Pydantic strict-mode tests (float money rejected, bad reference charset rejected); seed row counts + category tree integrity (no orphans).
