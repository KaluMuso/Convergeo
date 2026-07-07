> **Prepend `prompts/_header.md` (PROJECT HEADER) above this prompt.** Branch from and PR against **`master`**. Wave 2 runs 7 pebbles in parallel — **touch ONLY your files below**. Do NOT touch `0003_catalog.sql` (M03-P02's file, running in parallel).

# M03-P03 — Services & events schema

## 1. Context

**Wave 2 (parallel ×7).** On `master`: Supabase pipeline (PG 15 local config, `0001_extensions.sql`, typegen + CI db job), `0002_identity_vendors.sql` (vendors + **`public.has_role(text)`** — use, never redefine), `0008_config.sql`. Conventions (binding): one migration per pebble, tables + indexes + RLS + `FORCE ROW LEVEL SECURITY` in one file, money `bigint` ngwee, `updated_at` triggers, policy comments, guard-trigger pattern from 0002 (`session_user`). Spec: `docs/plan/02-pebbles/M03-data-core.md` §P03.

## 2. Objective & scope

Migration `0004_services_events.sql`: services, RFQ jobs + quotes, events, instances, ticket types, tickets — the services-RFQ and ticketing data core. **Quote privacy is the headline security property.**
**Non-goals:** no catalog tables (M03-P02 owns `0003_catalog.sql`), no orders spine (`0005`, W3 — see the tickets FK note below), no QR/PIN logic (M10), no seeds beyond tests.

## 3. Files (create/modify ONLY these)

- **Create:** `supabase/migrations/0004_services_events.sql` · `supabase/tests/0004_services_events.test.sql`
- **Modify:** `packages/types/src/db.ts` — regenerate/extend. ⚠ **M03-P02 also touches db.ts in parallel: whichever PR merges second regenerates on top of the first (note in report).**
  **Guardrail: nothing else.**

## 4. Implementation spec

Tables (uuid pks, timestamps + trigger, RLS + FORCE everywhere):

- **`services`** — vendor_id FK, category text/key, title, description, service_area text, `from_price_ngwee bigint nullable check (> 0)`, portfolio_images jsonb/text[], status `check in ('draft','active','paused')`.
- **`jobs`** (RFQ) — customer_id FK auth.users, category, description, preferred_date date nullable, budget_band `check in` sensible bands or `{min,max}_ngwee bigint`, status `check in ('open','quoted','accepted','completed','cancelled')` default 'open'.
- **`job_quotes`** — job_id FK, provider_vendor_id FK vendors, `amount_ngwee bigint not null check (> 0)`, message text, status `check in ('submitted','accepted','declined','expired')`, unique(job_id, provider_vendor_id), expires_at.
- **`events`** — organiser vendor_id FK, title, slug unique, description, venue text, lat/lng, images, status `check in ('draft','published','cancelled','completed')`.
- **`event_instances`** — event_id FK, `starts_at timestamptz NOT NULL`, `capacity int NOT NULL check (capacity >= 0)`.
- **`ticket_types`** — event_id FK, kind `check in ('fixed','tier','free_rsvp')`, name, `price_ngwee bigint not null check (price_ngwee >= 0)` (0 allowed ONLY when kind='free_rsvp' — CHECK constraint), `qty_cap int nullable check (> 0)`.
- **`tickets`** — instance_id FK, ticket_type_id FK, holder_user_id FK auth.users, **`order_item_id uuid NULL` — column only, NO foreign key** (the orders spine `0005` lands in W3 and completes the FK; comment this contract explicitly), status `check in ('issued','checked_in','transferred','void')` default 'issued', `qr_secret text`, `pin_hash text`, checked_in_at timestamptz. Indexes: (instance_id, status), holder_user_id.
- **RLS (comment every policy):** services — public select active; vendor CRUD own; admin all. jobs — owner (customer) full CRUD own; **matched providers select** (v1 matching contract: vendors with `status='active'` may select `open` jobs — comment that category-matching narrows this at the API layer in M11); admin all. **job_quotes — the crown jewel: a quote is selectable ONLY by (a) the quoting provider's owner, (b) the job's customer, (c) admin. Providers must NOT see rival quotes on the same job.** Insert: active vendors on open jobs, own vendor id pinned via WITH CHECK. events/instances/ticket_types — public select where event `status='published'`; organiser CRUD own; admin all. tickets — **select ONLY holder, the event's organiser (owner of organiser vendor), admin**; no client insert/update (issuance is server-side via service role; status transitions guarded — trigger blocks client status flips like 0002's pattern).
- `qr_secret`/`pin_hash` are sensitive: never readable by anyone but holder/organiser/admin (falls out of the tickets policy — assert it explicitly in tests).

## 5–8. UI/UX · Responsiveness · Performance · SEO

N/A. EXPLAIN the hot path (published events with next instance by starts_at) and paste the plan.

## 9. Security

Quote privacy proven; ticket secrets unreadable by third parties; free-RSVP price-0 constraint (paid kinds can't be 0); client cannot mint or check-in tickets; capacity NOT NULL (oversell guard logic lands with purchase flow, the schema must not allow null capacity).

## 10. Tests (RUN before reporting — pattern per `supabase/tests/0002_*.test.sql`)

Migrations 0001+0002+0004+0008 apply clean. **Provider A cannot read provider B's quote on the same job** (the must-pass). Job customer sees all quotes on own job; stranger sees none. Anon cannot read draft events; published visible. Ticket visible to holder + organiser only; third authenticated user denied; client ticket insert denied; client status flip denied. price_ngwee=0 rejected for kind='fixed', accepted for 'free_rsvp'. Regenerate `db.ts`; `pnpm --filter @vergeo/types typecheck`.

## 11. Acceptance criteria / DoD

- [ ] `db reset` clean with 0004 in sequence; all seven tables RLS+FORCE, commented.
- [ ] Quote-privacy matrix passes; ticket secrets holder/organiser-only.
- [ ] `tickets.order_item_id` is a bare nullable uuid with the 0005-completes-FK contract commented.
- [ ] Free-RSVP zero-price constraint correct both directions; db.ts regenerated + compiles.

## 12. IMPLEMENTATION REPORT

When finished, output an **Implementation Report** in exactly this format:
**PEBBLE:** M03-P03 — Services & events schema
**STATUS:** COMPLETE | PARTIAL | BLOCKED
**FILES:** each path + one-line description
**DEVIATIONS:** (or "none")
**TESTS:** paste db reset + quote-privacy/ticket matrix output
**EXCERPTS:** full SQL of the job_quotes and tickets RLS policies (the privacy surfaces) — nothing else
**QUESTIONS:** (or "none")
