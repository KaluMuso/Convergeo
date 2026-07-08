> **Prepend `prompts/_header.md` (PROJECT HEADER) above this prompt.** Branch from and PR against **`master`**. Wave 4 runs 6 pebbles in parallel. **⚠ SCHEMA-FREEZE WAVE.** You share `packages/types/src/db.ts` with M03-P05 + M03-P08 — see the db.ts rule.

# M03-P06 — Trust & ops schema

## 1. Context

**Wave 4 (parallel ×6).** Grounded against as-built `master`. Merged: `0002` identity (+`has_role()`, FORCE-RLS + `session_user` guard pattern), `0003` catalog, `0004` services/events, `0005` orders. **Exact names you FK into:** `public.orders(id, customer_id, vendor_id, status)`, `public.order_items(id, order_id, item_kind, …)`. The order status enum (from `0005`) includes `'delivered'`/`'completed'` — a review's verified-purchase gate keys off a delivered/completed order. Conventions (binding): one migration; tables+indexes+RLS+FORCE in-file; `bigint` ngwee; `updated_at` triggers; commented policies. Spec: `docs/plan/02-pebbles/M03-data-core.md` §M03-P06. **Note:** `notification_outbox` is the table M14 dispatches from.

## 2. Objective & scope

Migration `0007_trust_ops.sql`: reviews (verified-purchase by construction), disputes, returns, notification outbox, audit log, flags.
**Non-goals:** no review aggregation / Bayesian (M15-P02), no dispute/return business logic (M09), no notification dispatch (M14 — table only), no search projection (M03-P08).

## 3. Files (create/modify ONLY these)

- **Create:** `supabase/migrations/0007_trust_ops.sql` · `supabase/tests/0007_trust_ops.test.sql`
- **Modify:** `packages/types/src/db.ts` — **append** your tables (db.ts rule below).
  **Guardrail: nothing else. Do NOT touch `0006`/`0009` (siblings) or any app.**

## 4. Implementation spec

Tables (uuid pks, timestamps+trigger, RLS+FORCE, commented policies):

- **`reviews`** — **`order_item_id uuid NOT NULL references order_items(id)`** (verified-purchase by construction), `rating int not null check (rating between 1 and 5)`, `body text`, `photos text[]` (cloudinary ids), `vendor_reply text`, `vendor_reply_at timestamptz`, `status text check in ('published','flagged','removed') default 'published'`. **`unique(order_item_id)`** (one review per purchased item). A **CHECK/trigger** that the linked order_item's order is in a delivered/completed state at insert (verified-purchase gate) — implement via a `security definer` validation trigger (client can't bypass).
- **`disputes`** — `order_id FK orders`, `opener_user_id`, `evidence_paths text[]`, `vendor_response text`, `admin_decision text`, `status text check in ('open','vendor_responded','resolved_refund','resolved_release','rejected') default 'open'`.
- **`returns`** — `order_item_id FK order_items`, `lane int check in (1,2)`, `evidence_paths text[]`, `fee_breakdown jsonb`, `status text check in ('requested','approved','rejected','completed')`.
- **`notification_outbox`** — `dedupe_key text unique NOT NULL`, `channel text check in ('whatsapp','sms','email')`, `template text`, `payload jsonb`, `status text check in ('pending','sent','failed') default 'pending'`, `attempts int default 0`, `next_retry_at timestamptz`. Index (status, next_retry_at).
- **`audit_log`** — `actor uuid`, `action text`, `entity_type text`, `entity_id uuid`, `before jsonb`, `after jsonb`, `at timestamptz default now()`.
- **`flags`** — polymorphic `entity_type text`, `entity_id uuid`, `reason text`, `reporter_user_id uuid`, `status text check in ('open','actioned','dismissed') default 'open'`.
- **RLS (comment each):** `reviews` — **public select where status='published'**; author insert-once (only for own delivered order_item — enforced by the trigger + a WITH CHECK that the order_item belongs to `auth.uid()`'s order); author update limited to nothing sensitive (or none — edits later); vendor reply only on reviews of own listings; admin all. `disputes` — parties (order customer + order's vendor owner) select own; opener insert; admin all. `returns` — order_item's customer select/insert own; admin all; vendor of the listing reads own. **`notification_outbox` + `audit_log` — service-role only, zero client policies.** `flags` — reporter insert; admin all/select; no public read.

## 5–8. UI/UX · Responsiveness · Performance · SEO

N/A. EXPLAIN the published-reviews-by-listing and pending-outbox lookups; paste plans.

## 9. Security

**Review requires a delivered/completed order_item owned by the reviewer** — non-purchaser insert denied (trigger + RLS); one-review-per-item (unique); outbox/audit client-invisible; `dedupe_key` unique makes M14 exactly-once possible at DB level; flags not publicly readable.

## 10. Tests (RUN before reporting — pattern per `supabase/tests/0002/0005`)

Migrations `0001→0010` apply clean. **Unverified review insert denied** (order_item not owned / order not delivered); **double review on same order_item denied** (unique); verified path succeeds. Public reads only published reviews; author of non-delivered order_item blocked. `notification_outbox` dedupe_key unique enforced; client cannot read outbox/audit. Dispute parties see own, stranger denied. Regenerate `db.ts`; `pnpm --filter @vergeo/types typecheck`.

## 11. Acceptance criteria / DoD

- [ ] `db reset` clean through `0010` with `0007` in sequence.
- [ ] Verified-purchase review gate enforced (FK + delivered-state trigger + ownership); one-per-item unique (both tested).
- [ ] outbox/audit service-role-only; dedupe_key unique.
- [ ] EXPLAIN index use; db.ts appended + compiles.

## db.ts rule (shared with M03-P05 + M03-P08 this wave)

db.ts is hand-generated in-cloud. **Append ONLY your new tables to `public.Tables`; do NOT reorder/reformat siblings.** Report that CI's `db` job regenerates authoritatively and the later-merging schema PR combines table sets.

## 12. IMPLEMENTATION REPORT

When finished, output an **Implementation Report** in exactly this format:
**PEBBLE:** M03-P06 — Trust & ops schema
**STATUS:** COMPLETE | PARTIAL | BLOCKED
**FILES:** each path + one-line description
**DEVIATIONS:** (or "none")
**TESTS:** paste db reset + verified-purchase + one-per-item + outbox/audit RLS output
**EXCERPTS:** full SQL of the verified-purchase review trigger + the reviews/outbox/audit RLS policies (trust surfaces) — nothing else
**QUESTIONS:** (or "none")
