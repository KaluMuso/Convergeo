> **Prepend `prompts/_header.md`.** Branch from + PR against **`master`**. **Touch ONLY the files below.** **⚙ do NOT use `git stash`.** **Migration = `0032`.** Foreground blocking calls only; run the FULL `uv run pytest` before reporting.

# FIX-B — Refund double-execution → double payout & double escrow drain (🔴 #1)

## Finding (from `docs/plan/04-review-findings.md`)

`services/api/app/services/refunds/execute.py:238` — `execute_refund`'s only dedup is `_find_existing_refund(order_id)` (a plain SELECT, no `FOR UPDATE`/lock) then a plain insert. `refunds` has **no unique constraint on `order_id`** (0006_money.sql:113 is a non-unique index). Each call mints a fresh `refund_id`, so the ledger idempotency keys (`refund-{refund_id}-…`) differ per call and `post_transaction` can't collapse them. The caller idempotency_key (e.g. `dispute-{id}-refund`) is written to `breakdown` but **never passed to `post_transaction`**. Two concurrent/retried refunds → two refund rows, two REFUND/CLAWBACK ledger drains, two Lenco customer payouts. (The disputes/service.py:345 comment "all M08 calls are idempotency-keyed" is false.)

## Required fix

1. **DB backstop (migration `0032_refunds_order_unique.sql`, additive + reversible):** add a **partial UNIQUE index on `public.refunds(order_id)` WHERE status IN ('pending','processing','completed')** (an order can have at most one active/settled refund). Confirm no existing data violates it first. _(Unique index only — db.ts unaffected; do NOT edit db.ts.)_
2. **Pass the caller idempotency_key through to the ledger:** derive the ledger idempotency keys from the STABLE caller key (e.g. `{idempotency_key}-ledger` / `-clawback`) — NOT from a fresh per-call `refund_id` — so `post_transaction`'s `ON CONFLICT(idempotency_key)` collapses a retry to one posting. Same for the payout reference (`initiate_customer_refund_payout` must use a stable, idempotency-key-derived reference so a retry can't create a second Lenco payout).
3. **Serialize the guard:** perform the existing-refund check + insert atomically — either rely on the new unique index (catch the unique violation → return the existing refund idempotently) or take a row lock on the order. On a duplicate, return the already-created refund, do NOT post a second ledger tx or payout.
4. Money stays integer ngwee; refund amounts unchanged.

## Files (ONLY)

- Create `supabase/migrations/0032_refunds_order_unique.sql`
- Modify `services/api/app/services/refunds/execute.py` (+ `services/api/app/services/refunds/payout_port.py` if the payout reference needs the stable key)
- Optionally correct the false comment in `services/api/app/services/disputes/service.py` (only that comment line)
- Add/extend `services/api/tests/test_refund_execute.py`
- **Do NOT touch** db.ts, the ledger engine, other services, other migrations.

## Tests (RUN)

Real-Postgres: **two concurrent `execute_refund` for the same order** → exactly ONE refund row, ONE REFUND/CLAWBACK ledger transaction (escrow drained once), ONE payout. A sequential retry with the same idempotency_key → idempotent (returns the same refund, no second ledger/payout). **Full `uv run pytest`** + ruff + mypy. Migration replays clean.

## Report

STATUS/FILES/DEVIATIONS (the partial unique index; how the caller idempotency_key now flows to post_transaction + payout; the duplicate handling) /TESTS (paste two-concurrent-refund → one payout/one drain + retry-idempotent + full-pytest tail) /EXCERPTS the idempotency-key-derived ledger/payout keys + the duplicate guard /QUESTIONS.
