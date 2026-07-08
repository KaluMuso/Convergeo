> **Prepend `prompts/_header.md` (PROJECT HEADER) above this prompt.** Branch from and PR against **`master`**. Wave 4 runs 6 pebbles in parallel. **⚠ SCHEMA-FREEZE WAVE — after Wave 4 merges, migrations are additive-only.** You share `packages/types/src/db.ts` with two sibling schema pebbles (M03-P06, M03-P08) — see the db.ts rule below.

# M03-P05 — Money schema (ledger, payments, payouts, refunds, invoices)

## 1. Context

**Wave 4 (parallel ×6).** Grounded against as-built `master`. Merged migrations: `0001` ext · `0002` identity/vendors (+`has_role()`, FORCE-RLS + `session_user` guard-trigger pattern) · `0003` catalog · `0004` services/events · `0005` orders · `0008` config · `0010` profile-bootstrap. **Exact orders-spine names you FK into:** `public.checkout_groups(id, customer_id, idempotency_key, subtotal_ngwee, delivery_fee_ngwee, total_ngwee, status)`, `public.orders(id, checkout_group_id, vendor_id, customer_id, status, cod, commission_snapshot, …)`, `public.order_items(id, order_id, item_kind, unit_price_ngwee, qty)`. Conventions (binding): one migration per pebble; tables+indexes+RLS+`FORCE ROW LEVEL SECURITY` in-file; money `bigint` ngwee; `updated_at` triggers; commented policies. Lenco constraints (`docs/ops/lenco/lenco-api-distilled.md`): `reference` charset `[-._A-Za-z0-9]`; webhook idempotency mandatory; amounts decimal-major at boundary, integer ngwee internally. Spec: `docs/plan/02-pebbles/M03-data-core.md` §M03-P05.

## 2. Objective & scope

Migration `0006_money.sql`: double-entry escrow ledger, payments, webhook idempotency, payouts, refunds, gapless invoices — the financial spine.
**Non-goals:** no Lenco client / API code (M08, services/api), no state-machine transition functions (M08/M09 — schema + zero-sum guard only), no seeds beyond tests.

## 3. Files (create/modify ONLY these)

- **Create:** `supabase/migrations/0006_money.sql` · `supabase/tests/0006_money.test.sql`
- **Modify:** `packages/types/src/db.ts` — **append** your tables (see db.ts rule).
  **Guardrail: nothing else. Do NOT touch `0007`/`0009` (siblings) or any app.**

## 4. Implementation spec

Tables (uuid pks, `created_at/updated_at`+trigger where mutable, RLS+FORCE, commented policies), money `bigint` ngwee:

- **`ledger_accounts`** — `kind text check in ('platform_cash','escrow','commission_revenue','vendor_payable','cod_receivable','fees')`, `vendor_id uuid null references vendors(id)` (for per-vendor payable/cod), unique(kind, vendor_id) with a partial unique for null vendor.
- **`ledger_transactions`** — id, `kind text` (payment_captured, escrow_release, payout, refund, commission, cod_settle…), ref columns (checkout_group_id / order_id / payment_id / payout_id / refund_id — nullable), created_at.
- **`ledger_postings`** — `transaction_id FK`, `account_id FK`, `amount_ngwee bigint NOT NULL` (signed: debit +, credit −, your convention — document it). **Zero-sum trigger**: an AFTER trigger (deferred constraint trigger or statement-level) raising unless `sum(amount_ngwee)` per transaction = 0. Index (transaction_id), (account_id).
- **`payments`** — `checkout_group_id FK checkout_groups`, `provider text check in ('lenco')`, `rail text check in ('mtn','airtel','zamtel','card','cod')`, `lenco_reference text unique` with `CHECK (lenco_reference ~ '^[-._A-Za-z0-9]+$')`, `amount_ngwee bigint`, `status text check in ('initiated','pending','success','failed','expired')`, `raw jsonb`. Index (checkout_group_id), (status).
- **`webhook_events`** — `provider text`, `event_id text`, **`unique(provider, event_id)`** (DB-level idempotency), `signature_valid bool`, `processed_at timestamptz`, `raw jsonb`.
- **`payouts`** — `vendor_id FK`, `amount_ngwee bigint`, `rail text`, `lenco_reference text` (charset check), `status text check in ('pending','processing','paid','failed')`, `resolve_snapshot jsonb` (name-match result).
- **`refunds`** — `order_id FK orders`, `lane int check in (1,2)`, `breakdown jsonb` (computed: item/outbound/return/restock), `amount_ngwee bigint`, `status text`, `payout_ref uuid null references payouts(id)` (refunds execute as payouts — no Lenco refunds API).
- **`invoice_counters`** — `series text primary key`, `next_no bigint not null default 1`. **Gapless allocation via `SELECT … FOR UPDATE`** (document the function `public.next_invoice_no(series)` that locks the row, returns+increments — serialized).
- **`invoices`** — `no bigint` (from counter), `series text`, unique(series, no), `order_id FK`, `snapshot jsonb`, `vat_flag bool default false`, `vat_ngwee bigint default 0`.
- **RLS (comment each):** `ledger_accounts/ledger_transactions/ledger_postings/webhook_events/invoice_counters` — **service-role only, zero client policies** (all money mechanics are server-side). `payments` — customer reads own (via checkout_groups.customer_id join); `payouts` — vendor reads own (vendors.owner_user_id join); `refunds` — order's customer reads own; `invoices` — order's customer reads own. Admin-all on all. No client writes anywhere.

## 5–8. UI/UX · Responsiveness · Performance · SEO

N/A. EXPLAIN the payments-by-checkout-group and payouts-by-vendor lookups; paste plans.

## 9. Security

Zero-sum enforced at DB (a bug can't create money); `lenco_reference` charset-constrained; webhook `(provider,event_id)` unique = replay-proof at DB level; invoice numbers gapless under concurrency; all ledger tables client-invisible; float impossible (bigint).

## 10. Tests (RUN before reporting — pattern per `supabase/tests/0002/0005`)

Migrations `0001→0010` apply clean in filename order (paste tail). **Unbalanced transaction rejected** (postings sum ≠ 0 → error); balanced accepted. **Duplicate `(provider,event_id)` webhook rejected**; duplicate `lenco_reference` rejected; bad-charset reference rejected. **Invoice counter concurrency**: two concurrent `next_invoice_no` calls serialize to consecutive numbers (no gap, no dup) — use two transactions/`FOR UPDATE`. RLS: client cannot read ledger/webhooks; customer reads own payment/invoice; vendor reads own payout; cross-party denied. Regenerate `db.ts`; `pnpm --filter @vergeo/types typecheck`.

## 11. Acceptance criteria / DoD

- [ ] `db reset` clean through `0010` with `0006` in sequence.
- [ ] Zero-sum trigger proven; webhook + lenco_reference uniqueness at DB level; gapless invoice counter under concurrency.
- [ ] Ledger/webhook tables service-role-only; party-scoped reads on payments/payouts/refunds/invoices.
- [ ] EXPLAIN index use; db.ts appended + compiles.

## db.ts rule (shared with M03-P06 + M03-P08 this wave)

db.ts is hand-generated in-cloud (no Docker). **Append ONLY your new tables into the `public.Tables` object; do NOT reorder or reformat sibling entries.** Note in your report that CI's `db` job regenerates authoritatively and that whichever of the three schema PRs merges later resolves the db.ts overlap by combining table sets.

## 12. IMPLEMENTATION REPORT

When finished, output an **Implementation Report** in exactly this format:
**PEBBLE:** M03-P05 — Money schema
**STATUS:** COMPLETE | PARTIAL | BLOCKED
**FILES:** each path + one-line description
**DEVIATIONS:** (or "none")
**TESTS:** paste db reset + zero-sum + webhook/reference uniqueness + invoice-concurrency + RLS output
**EXCERPTS:** full SQL of the zero-sum trigger + `next_invoice_no()` + the ledger/webhook RLS (money-integrity surfaces) — nothing else
**QUESTIONS:** (or "none")
