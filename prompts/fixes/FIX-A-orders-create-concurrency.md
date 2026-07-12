> **Prepend `prompts/_header.md`.** Branch from + PR against **`master`**. **Touch ONLY the files below.** **⚙ do NOT use `git stash`.** **Migration = `0031`.** Foreground blocking calls only; run the FULL `uv run pytest` before reporting.

# FIX-A — Concurrent checkout creates duplicate orders + order-create oversell (🔴 #2 + 🟡 #4)

## Findings (from `docs/plan/04-review-findings.md`)

- **#2 CRITICAL** `services/api/app/services/orders/create.py:512` — `create_orders_atomic` guards idempotency/status via PostgREST reads BEFORE the transaction; the in-tx `SELECT … FOR UPDATE` on `checkout_groups` has NO `status='pending'` recheck; `orders` has NO unique constraint on `(checkout_group_id, vendor_id)`; order ids are fresh uuid4 per call. Two concurrent submits → two full order sets for one checkout_group/payment.
- **#4 MAJOR** same file, ~:584 — stock/hold validity checked only by a pre-transaction PostgREST read; several more round-trips run before the tx; the tx consumes the hold with a bare `DELETE FROM stock_reservations WHERE checkout_group_id=…` with no re-verification that the hold still exists/covers the qty → oversell against stock a sweeper reclaimed.

## Required fix

1. **DB backstop (migration `0031_orders_checkout_group_unique.sql`, additive + reversible):** add a **UNIQUE index on `public.orders(checkout_group_id, vendor_id)`**. This makes a duplicate order set a hard DB error, not a silent double. (First confirm no existing seed/data violates it; the migration replay + rls seed must still pass.) _(Unique index only — no column/function change, so `packages/types/src/db.ts` is unaffected; do NOT edit db.ts.)_
2. **In-transaction status recheck:** inside the `FOR UPDATE`-locked section, re-select `checkout_groups.status` and abort (idempotent no-op / already-completed response) if it is not `pending`. The lock + recheck is the real serialization; the unique index is the backstop.
3. **In-transaction stock re-verification (#4):** consume each hold with a conditional statement that fails if the hold no longer exists or no longer covers the ordered qty (e.g. `DELETE … WHERE checkout_group_id=… AND listing_id=… AND qty>=… RETURNING`, assert a row came back; or re-check `stock` in the same tx). If a hold is gone/insufficient, abort the whole tx (no partial order, no oversell).
4. Keep everything in the single `run_sql_script` transaction (one psql BEGIN…COMMIT). Money stays integer ngwee.

## Files (ONLY)

- Create `supabase/migrations/0031_orders_checkout_group_unique.sql`
- Modify `services/api/app/services/orders/create.py`
- Add/extend `services/api/tests/test_order_create_concurrency.py` (or the existing order-create test file)
- **Do NOT touch** db.ts, other routers/services, other migrations.

## Tests (RUN)

Real-Postgres concurrency test: fire **two concurrent `create_orders_atomic`** for the same session/idempotency_key → exactly ONE order set persists (the second is a no-op or unique-violation-handled idempotent response), never two. Oversell test: a hold expiring/removed between pre-check and tx → the order is rejected, stock never goes negative. Double-submit returns the same order set (idempotent). **Full `uv run pytest`** + `ruff` + `mypy`. Migration replays clean.

## Report

STATUS/FILES/DEVIATIONS (the unique index; the in-tx status recheck; the conditional hold consumption) /TESTS (paste the two-concurrent-submit result showing exactly one order set + the oversell rejection + full-pytest tail) /EXCERPTS the locked recheck + conditional stock consumption /QUESTIONS.
