> **Prepend `prompts/_header.md` (PROJECT HEADER) above this prompt.** Composer sessions share no memory — the header is required context.

# M03-P01 — Identity, vendors & KYC schema

## 1. Context
**Wave 1 batch B (parallel with M03-P07 — separate migration files, no shared files). Dispatch only after M01-P08 (Supabase pipeline) is merged** — you need `supabase/` + `0001_extensions.sql` + `scripts/gen-types.sh` in place. Spec source: `docs/plan/02-pebbles/M03-data-core.md` §P01. Conventions (binding): one migration file per pebble; tables + indexes + **RLS in the same file**; money `bigint` ngwee; `updated_at` triggers everywhere.

## 2. Objective & scope
Migration `0002_identity_vendors.sql`: profiles, roles, vendors, vendor locations, KYC records — with complete RLS. This is the FK root for the entire schema.
**Non-goals:** no catalog/orders/config tables (other pebbles' migrations), no seed data beyond what RLS tests need, no auth flows (M04), no RLS test harness (M03-P09 — ship SQL assertions inline for now).

## 3. Files (create/modify ONLY these)
- **Create:** `supabase/migrations/0002_identity_vendors.sql` · `supabase/tests/0002_identity_vendors.test.sql` (policy smoke via `supabase test db` / pgTAP if configured, else a psql assertion script)
- **Modify:** `packages/types/src/db.ts` — regenerate via `scripts/gen-types.sh` and commit (the CI drift check requires it)
**Guardrail: nothing else. Do NOT touch `0008_config.sql` (M03-P07's file, running in parallel).**

## 4. Implementation spec
Tables (all with `id uuid pk default gen_random_uuid()` unless keyed otherwise, `created_at/updated_at` + trigger):
- **`profiles`** — 1:1 `auth.users` (pk = `id uuid references auth.users`), phone, display_name, locale (default `'en'`), notif_prefs jsonb, dpa_consent_at timestamptz, soft-delete `deleted_at`.
- **`user_roles`** — user_id FK, role `text check (role in ('customer','vendor','admin'))`, unique(user_id, role). **Server-writable only** (no client policy grants insert/update/delete).
- **`vendors`** — owner user_id FK, slug unique, display fields, **status machine** `text check (status in ('draft','pending_kyc','active','suspended'))` default 'draft', kyc_tier `int check (kyc_tier in (1,2,3))`, preferred_badge bool default false, caps_snapshot jsonb.
- **`vendor_locations`** — vendor FK, lat/lng double precision, landmark text, hours jsonb.
- **`kyc_records`** — vendor FK, tier, doc_storage_paths text[] (private-bucket paths), momo_name_match jsonb, status `check in ('pending','approved','rejected')`, reviewer_notes text.
- **Shared helper (contract other pebbles use — exact signature):**
  ```sql
  create or replace function public.has_role(required_role text) returns boolean
  language sql stable security definer set search_path = public
  as $$ select exists(select 1 from user_roles where user_id = auth.uid() and role = required_role) $$;
  ```
- **RLS (enable on EVERY table):** profiles — owner select/update own row (not `deleted_at`, not id), admin all; user_roles — **no client-role policies at all** (service-role only); vendors — public `select` only where `status='active'`, owner select/update own (status column changes via server functions later — do not grant status update to owner; use a column-restricted policy or trigger guard), admin all; vendor_locations — follow vendor visibility; kyc_records — owner-read own, admin all, **no public access**.
- Policy comments in SQL explaining each rule. Indexes: vendors(slug), vendors(status), user_roles(user_id), kyc_records(vendor_id, status).

## 5–8. UI/UX · Responsiveness · Performance · SEO
N/A. EXPLAIN not required yet (no hot queries) — indexes above suffice.

## 9. Security
- **Role escalation via PostgREST must be impossible:** no policy path lets an authenticated user insert into `user_roles` or update `vendors.status`/`kyc_tier`. Prove it in tests.
- `has_role` is `security definer` with pinned `search_path` (prevents search-path hijack).
- KYC doc paths point at private storage; the table itself is never publicly readable.

## 10. Tests (RUN before reporting)
- `supabase db reset` clean (0001 + 0002 apply).
- Policy smoke per table: owner / other-authed / anon for select/insert/update — matrix asserting the RLS spec above (esp.: anon cannot read draft vendors; other user cannot read my kyc_records; authed user **cannot** insert user_roles; owner cannot update own `vendors.status`).
- `has_role('admin')` returns true only for the seeded admin test user.
- `scripts/gen-types.sh` run; `pnpm --filter @vergeo/types typecheck`; `git diff --exit-code` clean after committing regenerated types.

## 11. Acceptance criteria / DoD
- [ ] `db reset` clean; all 5 tables with RLS enabled + commented policies.
- [ ] Role escalation impossible (tested); vendor status not owner-updatable (tested).
- [ ] `has_role()` helper exact-signature, security-definer, search-path-pinned.
- [ ] Regenerated `db.ts` committed; CI drift check green.
- [ ] Only the two supabase files + regenerated types touched.

## 12. IMPLEMENTATION REPORT
When finished, output an **Implementation Report** in exactly this format:
**PEBBLE:** M03-P01 — Identity, vendors & KYC schema
**STATUS:** COMPLETE | PARTIAL | BLOCKED
**FILES:** each path + one-line description of the change
**DEVIATIONS:** any departure from spec, and why (or "none")
**TESTS:** paste db reset + policy-matrix + typegen output
**EXCERPTS:** full SQL of the RLS policies + `has_role()` (authz surfaces) — nothing else
**QUESTIONS:** uncertainties needing a reviewer decision (or "none")
