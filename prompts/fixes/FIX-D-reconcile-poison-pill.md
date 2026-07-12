> **Prepend `prompts/_header.md`.** Branch from + PR against **`master`**. **Touch ONLY the files below.** **⚙ do NOT use `git stash`.** No migration. Foreground blocking only; run the FULL `uv run pytest` before reporting.

# FIX-D — Reconciliation poller poison pill: one illegal transition aborts the whole tick (🟡 #6)

## Finding

`services/api/app/services/payments/reconcile.py:379` — `apply_payment_status` → `transition_payment` raises `PaymentTransitionError` when the `(from_status, event)` pair is absent from `TRANSITION_TABLE`. The poller fetches `INITIATED` payments (in `NON_TERMINAL_POLL_STATUSES`) but there is NO transition out of `INITIATED` for `pay_offline`/`success`/`failed` (only `ussd_pushed`/`cancelled`). A single such payment raises and **aborts the entire reconciliation tick**, so every later payment in the batch is skipped.

## Required fix

- **Isolate per-payment failures:** wrap each payment's reconciliation in a try/except inside the loop so an illegal/unexpected transition (or any error on one payment) is caught, logged, and the tick CONTINUES with the rest of the batch. One bad payment must never freeze reconciliation.
- **Handle the INITIATED-terminal-event gap sanely:** when a Lenco status implies a transition that the state machine has no edge for from the current status, do NOT crash — log it as a reconciliation anomaly (and, if appropriate, surface it for admin/alert) and skip that payment. Prefer fixing the legitimate path if `INITIATED + success/failed` is a real state Lenco can report (add the guarded edge in `payments/state.py` ONLY if it's genuinely a valid transition — otherwise just skip-and-log). Keep transitions guarded + audited; no raw status UPDATE.

## Files (ONLY)

- Modify `services/api/app/services/payments/reconcile.py` (+ `services/api/app/services/payments/state.py` ONLY if adding a genuinely-valid guarded transition edge)
- Add/extend `services/api/tests/test_reconcile.py`
- **Do NOT touch** initiate.py / payments_card.py (FIX-C owns them), db.ts, migrations.

## Tests (RUN)

A batch containing one payment that would trigger an illegal transition + several healthy ones → the healthy ones are reconciled, the bad one is logged/skipped, the tick does NOT abort (assert all healthy payments were processed). **Full `uv run pytest`** + ruff + mypy.

## Report

STATUS/FILES/DEVIATIONS (per-payment isolation; how the INITIATED gap is handled — skip-log vs new guarded edge) /TESTS (paste the mixed-batch result showing healthy ones still processed + full-pytest tail) /EXCERPTS the per-payment try/except loop /QUESTIONS.
