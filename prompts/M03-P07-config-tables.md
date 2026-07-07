> **Prepend `prompts/_header.md` (PROJECT HEADER) above this prompt.** Composer sessions share no memory — the header is required context.

# M03-P07 — Config tables & seeds

## 1. Context
**Wave 1 batch B (parallel with M03-P01 — separate migration files, no shared files). Dispatch only after M01-P08 (Supabase pipeline) is merged.** Spec source: `docs/plan/02-pebbles/M03-data-core.md` §P07; seed values from `docs/plan/00-decisions.md` D4/D12/D16/D23. Conventions: one migration per pebble, RLS in-file, money `bigint` ngwee, `updated_at` triggers.
**Cross-pebble contract:** M03-P01 (running in parallel, migration `0002`) defines `public.has_role(required_role text) returns boolean`. Your migration is `0008` — it applies after 0002 at reset time, so **use `has_role('admin')` in your RLS policies without redefining it**. Do not FK any 0002 table (this pebble is FK-free by design).

## 2. Objective & scope
Migration `0008_config.sql`: every admin-tunable number the platform reads at runtime — commissions, delivery zones, platform config, feature flags, merch slots, prohibited categories, vendor quotas — seeded with the locked decision values, admin-write-only RLS, config audit trail.
**Non-goals:** no admin UI (M13-P07), no FK to identity/catalog tables, no schema for entities (other pebbles).

## 3. Files (create/modify ONLY these)
- **Create:** `supabase/migrations/0008_config.sql` · `supabase/tests/0008_config.test.sql`
- **Modify:** `packages/types/src/db.ts` — regenerate + commit. ⚠ **Both batch-B pebbles regenerate this file; whichever PR merges second must regenerate on top of the first (note it in your report).**
**Guardrail: nothing else. Do NOT touch `0002_identity_vendors.sql` (M03-P01's file).**

## 4. Implementation spec
Tables (all `created_at/updated_at` + trigger, RLS enabled):
- **`commission_rates`** — category_key text pk, rate_bps int. **Seeds (D4, basis points):** electronics 500 · home 800 · fashion_beauty 1000 · services 1200 · event_tickets 500 · supplies 300 · groceries 500 · default 800 · free_events 0.
- **`delivery_zones`** — zone key, label, fee_ngwee bigint, active bool. Seeds: Lusaka bands (sensible A/B/C placeholder fees, admin-editable) + `free_delivery_threshold_ngwee = 20000` (K200) as a platform_config row, not per-zone.
- **`platform_config`** — key text pk, value jsonb, description text. Seeds: `cod_cap_ngwee: 50000` (K500 ⚠F8 — comment the flag), `reservation_ttl_min: 15`, `ai_guest_quota: 3`, `ai_free_monthly_quota: 25`, `ai_monthly_cap_usd: 15`, `release_after_delivered_hours: 48`, `release_after_shipped_days: 7`.
- **`feature_flags`** — flag text pk, enabled bool default false, description. Seeds (all OFF): `paid_tiers`, `abandoned_cart`, `wallet`, `zamtel_collections` (⚠F9a).
- **`merch_slots`** — slot_key, variant_key, payload jsonb, schedule_from/to timestamptz, position int, active bool. Seed one `hero` row (editorial-light variant placeholder) so the home renderer has data.
- **`prohibited_categories`** — key text pk, reason text. Seeds per D8 fence: salaula, used_phones, fresh_produce, alcohol, pharma, live_animals, heavy_building_materials.
- **`vendor_quotas`** — tier int pk, max_listings int, first_orders_cap_ngwee bigint, first_orders_count int, payout_velocity jsonb. Seeds: tier 1 → 30 listings, 50000 ngwee cap on first 5 orders; tiers 2/3 → null caps.
- **`config_audit`** — table + trigger on ALL tables above: actor (auth.uid()), table_name, row_key, before jsonb, after jsonb, at timestamptz. Every write audited.
- **RLS:** public/anon `select` on commission_rates, delivery_zones, feature_flags, merch_slots (customer app reads these), platform_config select for authenticated (or a public view exposing only safe keys — your call, justify in report); **all writes `has_role('admin')` only**; config_audit — admin-read, no client writes (trigger-written).

## 5–8. UI/UX · Responsiveness · Performance · SEO
N/A.

## 9. Security
- Non-admin writes denied on every table (tested). Audit rows written by trigger, not trusted client input.
- No secrets in seeds. Ngwee sanity: every K value seeded ×100 correctly (K500 = 50 000 ngwee).

## 10. Tests (RUN before reporting)
- `supabase db reset` clean (0001 + 0002 + 0008 apply in order).
- Seed-value assertions: every D4 rate, `cod_cap_ngwee = 50000`, threshold `20000`, AI quotas 3/25/15, all flags false.
- RLS: anon can read commission_rates; authed non-admin **cannot** update any config table; admin (seeded via 0002's user_roles under service role) can.
- Audit: an admin update writes a config_audit row with before/after.
- Typegen regenerated; `pnpm --filter @vergeo/types typecheck`.

## 11. Acceptance criteria / DoD
- [ ] All D4/D12/D16/D23 numbers present, ngwee-correct (tested).
- [ ] Non-admin write denied on every table; audit trigger proves before/after.
- [ ] FK-free of all other migrations; uses `has_role()` contract, doesn't redefine it.
- [ ] `db reset` clean alongside 0002; regenerated types committed.

## 12. IMPLEMENTATION REPORT
When finished, output an **Implementation Report** in exactly this format:
**PEBBLE:** M03-P07 — Config tables & seeds
**STATUS:** COMPLETE | PARTIAL | BLOCKED
**FILES:** each path + one-line description of the change
**DEVIATIONS:** any departure from spec, and why (or "none")
**TESTS:** paste db reset + seed assertions + RLS denial + audit output
**EXCERPTS:** full SQL of the RLS policies + audit trigger (authz/money-config surfaces) — nothing else
**QUESTIONS:** uncertainties needing a reviewer decision (or "none")
