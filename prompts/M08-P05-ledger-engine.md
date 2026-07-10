> **Prepend `prompts/_header.md` (PROJECT HEADER) above this prompt.** Branch from and PR against **`master`**. Wave 10 runs 8 pebbles in parallel — **touch ONLY your files below**. **⚠ SCHEMA: you are the SOLE migration + `db.ts` editor this wave** (one additive migration below). Stay dep-free. **Run the FULL `uv run pytest` (import guard) before reporting.**

# M08-P05 — Escrow ledger engine

## 1. Context

**Wave 10 (parallel ×8).** Grounded against as-built `master`:

- **Double-entry tables exist (0006):** `ledger_transactions(id, kind, checkout_group_id, order_id, payment_id, payout_id, refund_id, created_at)` + `ledger_postings(transaction_id, account_id, amount_ngwee, …)` with **signed ngwee (debit +, credit −)** and a trigger `enforce_ledger_transaction_balance()` that **rejects any transaction whose postings don't sum to 0**. `ledger_accounts` (platform + per-vendor) exists. **Reuse these — build the engine ON them.**
- **`ledger_transactions` has NO idempotency column** → you add **ONE additive migration `0015_ledger_idempotency.sql`**: `alter table public.ledger_transactions add column idempotency_key text; create unique index … on (idempotency_key) where idempotency_key is not null;` (reversible; partial-unique so legacy rows are fine). **You are the sole migration + `db.ts` editor this wave** — regenerate the `ledger_transactions` entry in `packages/types/src/db.ts` by hand (CI `db` job validates the drift).
- `app/services/` is an implicit namespace package — create `app/services/ledger/` with its **own `__init__.py`**; **NO `app/services/__init__.py`**. Money = **`Decimal`/int ngwee only** (float = review-blocking); reuse `app.services.payments.money` (M08-P01, merged) for any decimal work + `app.schemas.base` ngwee types. This pebble adds **no router** (engine + templates only; callers are M07-P06/webhooks/M13-P06).
  Spec: `docs/plan/02-pebbles/M08-payments-escrow.md` §M08-P05. Signing convention in `0006`: debits positive, credits negative, Σ per transaction = 0.

## 2. Objective & scope

A double-entry ledger engine where **posting templates are the ONLY write path** (no ad-hoc postings): `post_transaction(idempotency_key, template, ...)` + the template set (charge_received, escrow_hold, commission_capture, release_to_vendor, payout_executed, refund_lane1/lane2, cod_collected, clawback), each documenting its debit/credit legs; **idempotent per business-event key**; balances derivable.
**Non-goals:** no Lenco client (M08-P02), no order creation (M07-P06), no webhook wiring (M08-P03/M11), no HTTP router.

## 3. Files (create/modify ONLY these)

- **Create:** `services/api/app/services/ledger/__init__.py` · `ledger/engine.py` (`post_transaction` API — the only writer; enforces balance + idempotency) · `ledger/templates.py` (the posting templates, each with documented legs) · `services/api/tests/test_ledger.py` (incl. **hypothesis property tests**) · `supabase/migrations/0015_ledger_idempotency.sql`
- **Modify:** `packages/types/src/db.ts` (add `idempotency_key` to `ledger_transactions` Row/Insert/Update — sole db.ts editor this wave)
  **Guardrail: nothing else. Do NOT touch `0006`, `main.py`, `app/services/__init__.py`, `app/services/payments/*` (import from it), other tables.**

## 4. Implementation spec

- **`engine.py`:** `post_transaction(*, idempotency_key, template, **event_args)` — builds the transaction + balanced postings from the template, writes via service-role in **one transaction**; **same `idempotency_key` posts once** (unique index → on conflict return the existing transaction, no double-post). The DB `enforce_ledger_transaction_balance` trigger is the backstop; the engine should also assert Σ=0 before writing. **Templates are the only public write path** — no ad-hoc posting API is exposed.
- **`templates.py`:** each template (charge_received, escrow_hold, commission_capture, release_to_vendor, payout_executed, refund_lane1, refund_lane2, cod_collected, clawback) is a pure function of its money args → a list of `(account, signed_ngwee)` legs that **sum to 0**, with a docstring naming each debit/credit leg. Commission uses bps→ngwee integer math (no float). Account resolution (platform vs per-vendor) is explicit.

## 5–9. UI/UX · Responsiveness · Performance · SEO · Security

Backend only; templates = sole write path; idempotent per event key; `Decimal`/int only (no float); balances indexed/derivable; no secrets.

## 10. Tests (RUN before reporting — full `uv run pytest` + ruff + mypy)

`test_ledger.py`: **hypothesis property test — Σ postings = 0 for EVERY generated transaction across random amounts × every template**; **template goldens** (exact legs per money event); **idempotent re-post** (same key → one transaction, second call no-ops to the same id); balance derivation. If the property test needs live PG it may skip in CI (note it) but MUST pass on your Postgres run. **Full `uv run pytest` (import guard) + ruff + mypy.** Confirm `0015` replays clean in migration order and `db.ts` matches.

## 11. Acceptance criteria / DoD

- [ ] Property test: Σ postings = 0 for every generated transaction; templates are the only write path; commission bps→ngwee integer-exact.
- [ ] Same event key posts once (idempotency unique index); `0015` additive + reversible; `db.ts` matches gen-types; full API suite + repo green.

## 12. IMPLEMENTATION REPORT

**PEBBLE:** M08-P05 — Escrow ledger engine
**STATUS/FILES/DEVIATIONS** (confirm `0015` additive + db.ts hand-update) **/TESTS** (paste the Σ=0 property test + idempotent re-post + a template golden + full-pytest tail) **/EXCERPTS** `post_transaction` idempotency + one balanced template — nothing else **/QUESTIONS**
