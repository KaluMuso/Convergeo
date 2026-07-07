> **Prepend `prompts/_header.md` (PROJECT HEADER) above this prompt.** Branch from and PR against **`master`**. Wave 2 runs 7 pebbles in parallel — **touch ONLY your files below**. Do NOT touch `0004_services_events.sql` (M03-P03's file, running in parallel).

# M03-P02 — Catalog schema

## 1. Context

**Wave 2 (parallel ×7).** On `master`: Supabase pipeline (`supabase/config.toml` PG 15, `0001_extensions.sql`, `scripts/gen-types.sh`, CI `db` job with typegen drift check), `0002_identity_vendors.sql` (vendors + **`public.has_role(text)`** helper — use it, never redefine), `0008_config.sql` (`commission_rates` with `category_key`, `prohibited_categories`). Conventions (binding): one migration per pebble, **tables + indexes + RLS + `FORCE ROW LEVEL SECURITY` in the same file**, money `bigint` ngwee, `updated_at` triggers, policy comments. Spec: `docs/plan/02-pebbles/M03-data-core.md` §P02.

## 2. Objective & scope

Migration `0003_catalog.sql`: category tree, canonical products, vendor listings (incl. supplies fields), listing images — the discovery/commerce data core.
**Non-goals:** no services/events/jobs (M03-P03's `0004`), no orders (`0005`, W3), no search projection (`0009`, W4), no seed data beyond what tests need.

## 3. Files (create/modify ONLY these)

- **Create:** `supabase/migrations/0003_catalog.sql` · `supabase/tests/0003_catalog.test.sql`
- **Modify:** `packages/types/src/db.ts` — regenerate/extend for the new tables. ⚠ **M03-P03 also touches db.ts in parallel: whichever PR merges second regenerates on top of the first (note in report).**
  **Guardrail: nothing else.**

## 4. Implementation spec

Tables (uuid pks `gen_random_uuid()`, `created_at/updated_at` + trigger, RLS + FORCE on every table):

- **`categories`** — parent_id self-FK nullable, name, slug unique, **materialized path** (text, e.g. `electronics/phones`), `commission_key text` (matches `commission_rates.category_key` values — no FK across pebbles needed, but comment the contract), `vat_flag boolean default false`, `prohibited boolean default false`, position int. Index on path (text_pattern_ops or btree) + parent_id.
- **`products`** (canonical) — name, slug unique, brand, `spec jsonb default '{}'`, category_id FK, **`aliases text[]`** (Bemba/Nyanja search terms), status `check (status in ('pending_moderation','active','merged'))` default 'pending_moderation', merged_into_id self-FK nullable.
- **`vendor_listings`** — vendor_id FK `vendors`, product_id FK `products` **nullable** (quick-list), title_override text nullable, `price_ngwee bigint not null check (price_ngwee > 0)`, condition `check in ('new','refurbished')`, stock_mode `check in ('tracked','always_available')`, `stock_qty int check (stock_qty >= 0)`, `wholesale boolean default false`, `price_tiers jsonb` (shape `[{min_qty int, price_ngwee bigint}]` — validate via CHECK using jsonb_typeof or a validation trigger), `moq int check (moq >= 1) default 1`, `returnable boolean default false`, `return_window_hours int`, status `check in ('draft','active','paused','removed')` default 'draft'. Indexes: vendor_id, product_id, (status, wholesale).
- **`listing_images`** — listing_id FK, `cloudinary_public_id text`, `position int check (position between 1 and 8)`, **unique(listing_id, position)** + a trigger or constraint guaranteeing **≤8 rows per listing** (count-check trigger — comment why). This is the ⚙ contract M12-P03/P05 code against in W7.
- **RLS:** categories — public select, `has_role('admin')` writes. products — public select where `status='active'`; authenticated **insert only as `pending_moderation`** (WITH CHECK pins status); no client update/delete (admin-all policy only; moderation flows come later). vendor_listings — public select where `status='active'` AND parent vendor active (EXISTS on vendors); vendor CRUD own (owner check via vendors.owner_user_id, mirroring 0002's pattern); admin all. listing_images — follow parent listing's visibility/ownership.
- Owner must NOT be able to flip a listing to bypass moderation-sensitive fields — status transitions stay ('draft'↔'active'↔'paused' allowed for owner; 'removed' admin-only) — enforce via trigger guard like 0002's `session_user` pattern.

## 5–8. UI/UX · Responsiveness · Performance · SEO

N/A. EXPLAIN-check the two hot lookups (active listings by product_id; category by path prefix) and paste plans.

## 9. Security

Price float impossible (bigint); negative price/stock rejected; cross-vendor listing mutation denied; canonical insert cannot self-approve; `price_tiers` shape validated server-side (malformed jsonb rejected).

## 10. Tests (RUN before reporting — pgTAP or psql asserts, pattern per `supabase/tests/0002_*.test.sql`)

Migrations 0001+0002+0003+0008 apply clean in filename order. Constraint tests: **9th image rejected**, duplicate position rejected, negative price rejected, price_tiers with wrong shape rejected, moq<1 rejected. RLS matrix: anon reads only active products/listings; vendor A cannot update vendor B's listing; authenticated product insert forced to pending_moderation (explicit 'active' insert rejected); owner cannot set listing status='removed'. Regenerate `db.ts`; `pnpm --filter @vergeo/types typecheck`.

## 11. Acceptance criteria / DoD

- [ ] `db reset` clean with 0003 in sequence; all four tables RLS+FORCE with commented policies.
- [ ] ≤8 images + position uniqueness enforced by constraint/trigger (tested).
- [ ] Moderation status pinning + owner status-transition guard tested.
- [ ] EXPLAIN shows index use on the two hot lookups; db.ts regenerated + compiles.

## 12. IMPLEMENTATION REPORT

When finished, output an **Implementation Report** in exactly this format:
**PEBBLE:** M03-P02 — Catalog schema
**STATUS:** COMPLETE | PARTIAL | BLOCKED
**FILES:** each path + one-line description
**DEVIATIONS:** (or "none")
**TESTS:** paste db reset + constraint/RLS matrix + EXPLAIN output
**EXCERPTS:** full SQL of the RLS policies + the ≤8-images and status-guard triggers (authz/integrity surfaces) — nothing else
**QUESTIONS:** (or "none")
