> **Prepend `prompts/_header.md`.** Branch from + PR against **`master`**. **Touch ONLY the files below.** This is a **verification/ops pebble** against **Lenco sandbox** — it must NOT touch production credentials or live rails, and must NOT weaken the `payments_enabled()` gate. Secrets only via env (never repo). Foreground blocking only.

# CR-D — Lenco sandbox money-drill (proves the payment rail end-to-end)

## Finding

The Lenco integration (`services/api/app/services/payments/lenco/*`, `checkout_payment.py`, `payments_card.py`, `webhooks_lenco.py`) is **code-complete but never proven against a real Lenco rail** — it is gated behind `payments_enabled()` / F9b (needs Lenco sandbox+prod creds). Launch gate requires an E2E money drill vs Lenco sandbox (per `docs/plan/launch-checklist.md §3`). Until this runs, "payments work" is an assumption.

## Required fix (drill harness + runbook, not product code)

- Write a **scripted, idempotent money-drill** runnable against **Lenco sandbox** with env-supplied sandbox credentials (`LENCO_ENV=sandbox`) that exercises, end-to-end, asserting ledger balance at each step:
  1. MoMo collection (USSD push) happy path → escrow HOLD posting created, `payment` row `succeeded`, one `CHARGE_RECEIVED` per checkout group (idempotency key honored).
  2. Webhook replay (Lenco retries 30min×24h) → **no double-posting** (dedupe via `webhook_events`).
  3. Escrow release → payout batch → refund-as-payout path (`refunds/payout_port.py`) → ledger nets to zero, no orphaned payout.
  4. Card widget flow (`payments_card.py`) reaches a terminal state without a false-success (mirror `e2e/specs/checkout-false-success.spec.ts` invariant).
- Emit a **pass/fail report artifact** (ledger imbalance = FAIL) suitable for attaching to the launch checklist.
- Add a runbook: how to obtain sandbox creds, run the drill, read the report, and what "PASS" means for gates S1–S6.

## Files (ONLY)

- Add `scripts/drills/lenco_sandbox_money_drill.py` (or `.mjs`) + `scripts/drills/README.md`
- Add `docs/ops/lenco/sandbox-money-drill.md` (runbook + gate mapping)
- Optionally extend `e2e/fixtures/lenco*` **only** if the drill reuses fixtures (no behavior change)
- **Do NOT touch** `services/payments/*` product code, `payments_enabled()`, migrations, or any router. If the drill reveals a product bug, STOP and report it as a QUESTION — do not fix it in this pebble.

## Tests (RUN)

- Dry-run the drill against sandbox (or a recorded sandbox cassette if creds are unavailable in CI) and paste the ledger-balance assertions per step + the final report. `uv run ruff check` on the script.

## Report

STATUS / FILES / DEVIATIONS / TESTS (paste the per-step ledger assertions + PASS/FAIL report; if creds unavailable, say so explicitly and provide the cassette/dry-run) / EXCERPTS (the webhook-replay no-double-post assertion) / QUESTIONS (any product bug found — do not fix here).
