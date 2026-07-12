> **Prepend `prompts/_header.md`.** Branch from + PR against **`master`**. **Touch ONLY the files below.** **⚙ do NOT use `git stash`.** No migration. Foreground blocking only; run the FULL `uv run pytest` before reporting.

# FIX-C — Payment retry impossible: Lenco reference collides on UNIQUE (🟡 #5)

## Finding

`services/api/app/services/payments/initiate.py:94` (and `payments_card.py:498`) — `lenco_reference` is derived deterministically from a stable id (`order_id`/`checkout_group_id`) via `make_order_reference()` with no per-attempt salt, but `payments.lenco_reference` is `UNIQUE` (0006_money.sql:45). The payment state machine builds a retry flow, but a second `initiate` after a failed/expired attempt collides on the unique reference and errors.

## Required fix

- Add a **per-attempt component** to the Lenco reference so each initiate attempt gets a distinct, still-decodable reference (charset `[-._A-Za-z0-9]`, keep our `ord-*`/`pay-*` encoding intact). E.g. append an attempt counter or the `payment_id` so `reference` is unique per attempt while still round-trip-decodable back to our order/payment in the webhook.
- **Verify the webhook + reconciliation still resolve** the payment from the new reference (the handler must map `reference → payment` regardless of the salt — confirm the lookup keys on stored `lenco_reference`, not a re-derivation from order_id). Apply the same fix to the card path.
- Idempotency of a SINGLE attempt must be preserved (don't create N Lenco charges for one click); only a genuine RETRY (after failure/expiry, new attempt) gets a new reference.

## Files (ONLY)

- Modify `services/api/app/services/payments/initiate.py`, `services/api/app/services/payments/payments_card.py` (+ the reference encoder if it lives elsewhere in `payments/`)
- Add/extend `services/api/tests/test_payment_retry.py`
- **Do NOT touch** payments/state.py, reconcile.py (FIX-D owns it), db.ts, migrations.

## Tests (RUN)

Retry after a failed/expired attempt on the same order → a NEW payment attempt with a distinct reference succeeds (no unique collision); the webhook resolves the correct payment from the new reference; a same-attempt duplicate does NOT create a second charge. **Full `uv run pytest`** + ruff + mypy.

## Report

STATUS/FILES/DEVIATIONS (the per-attempt reference scheme + how the webhook still decodes it) /TESTS (paste retry-succeeds + webhook-resolves + full-pytest tail) /EXCERPTS the reference generation + the webhook lookup /QUESTIONS.
