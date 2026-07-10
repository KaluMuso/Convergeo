> **Prepend `prompts/_header.md` (PROJECT HEADER) above this prompt.** Branch from and PR against **`master`**. Wave 12 runs 9 pebbles in parallel — **touch ONLY your files below**. **⚠ SCHEMA FROZEN** — `payouts` table + `vendor_quotas.payout_velocity` exist. Stay dep-free. **Run the FULL `uv run pytest` before reporting.**

# M08-P09 — Payouts

## 1. Context

**Wave 12 (parallel ×9).** Grounded against as-built `master`:

- **`payouts` (0006):** `(id, vendor_id, amount_ngwee, rail in (mtn|airtel|zamtel|card|cod), lenco_reference text UNIQUE [charset], status in (pending|processing|paid|failed))`. **`lenco_reference` (a `pay-*` code via M08-P01 `references.py`) is the idempotent key — a retry re-uses it (never double-pays).** Ledger: **`payout_executed` template (M08-P05)** debits `vendor_payable(vendor)`, credits `platform_cash`; **eligible balance = the vendor's `vendor_payable` credit balance** (released by M08-P08). Every payout = one ledger transaction.
- **Lenco client merged (M08-P02):** payouts via `LencoStrategy.initiate_momo_payout` / `initiate_bank_payout`; **pre-payout `/resolve` name-match** (`resolve_account`) vs the KYC momo name (`kyc_records`) — **mismatch → payout HELD + vendor notified (never auto-sent)**. Amounts via `payments.money` decimal converters (no float).
- **Velocity caps:** `vendor_quotas.payout_velocity` (jsonb: max per day / max amount per day) by `kyc_tier` — enforce. `app/services/` implicit namespace — create `payouts/` with own `__init__.py`. Router auto-discovers (never edit `main.py`); service-role via `app.deps.get_supabase_client` (import-guard; local `Protocol`).
  Spec: `docs/plan/02-pebbles/M08-payments-escrow.md` §M08-P09. **Live E2E needs F9b — mock/fixture-tested here.**

## 2. Objective & scope

Payout execution: eligibility from released `vendor_payable` balance, **pre-payout `/resolve` name-match** (mismatch → held + notify), execution via M08-P02 (MoMo + bank rails), **KYC-tier velocity caps**, batching, retry/backoff (status re-query before re-send), failure → dead-letter to admin queue; every payout a ledger transaction with an **idempotent `pay-*` reference**.
**Non-goals:** no release rules (M08-P08 — consume its eligibility), no refunds (M08-P10 — sibling), no schema.

## 3. Files (create/modify ONLY these)

- **Create:** `services/api/app/services/payouts/__init__.py` · `payouts/*.py` (eligibility, resolve-check, execution, batching, retry) · `services/api/app/routers/internal_payouts.py` (internal-token-guarded) · `services/api/tests/test_payouts.py`
  **Guardrail: nothing else. Do NOT touch `app/services/ledger/*`/`payments/*` (M08-P05/P02 — call), `escrow/*` (M08-P08), `0006`/`0008`, `main.py`, schema.**

## 4. Implementation spec

- **Eligibility:** a vendor's payable = their `vendor_payable` credit balance (released). **A payout NEVER exceeds released balance** (compute under a lock / atomic check — race-safe). **Velocity caps** from `vendor_quotas.payout_velocity` by tier (max payouts/day, max amount/day) — a payout that breaches → deferred/held.
- **Pre-payout name-match:** call M08-P02 `resolve_account` for the vendor's momo/bank; **compare to the KYC momo name** — **mismatch → payout HELD (status stays pending/held) + vendor notified; NEVER auto-send** on mismatch.
- **Execution:** create the `payouts` row with a fresh `pay-*` `lenco_reference` (idempotent); call M08-P02 `initiate_momo_payout`/`initiate_bank_payout` (amount decimal-major via `payments.money`); post the `payout_executed` ledger template. **Retry with backoff → but re-query status BEFORE re-sending** (a timed-out payout may have succeeded — never double-pay; the unique `lenco_reference` is the guard). Repeated failure → **dead-letter to an admin queue** (structured + status=failed). Bank vs MoMo expectations (instant vs 24–36h) recorded.

## 5–9. UI/UX · Responsiveness · Performance · SEO · Security

Backend only; payout ≤ released balance (race-tested); mismatch blocks; idempotent `pay-*` reference (no double-pay); velocity caps enforced; `Decimal`/int money; secrets env-only. **F9b for live.**

## 10. Tests (RUN before reporting — full `uv run pytest` + ruff + mypy)

`test_payouts.py`: **balance race** (two concurrent payout attempts on the same released balance → total never exceeds it); **resolve-mismatch** (name mismatch → held + not sent); **retry-after-timeout** (status re-query before re-send → no double-pay); **velocity-cap boundary** (at cap ok, +1 deferred). **Full `uv run pytest` + ruff + mypy.**

## 11. Acceptance criteria / DoD

- [ ] Payout never exceeds vendor released balance (race-tested); name mismatch blocks (never auto-sent); retries never double-pay (idempotent `pay-*` ref).
- [ ] Velocity caps enforced at the boundary; every payout a ledger transaction; failures dead-lettered. **F9b flagged for live E2E.**

## 12. IMPLEMENTATION REPORT

**PEBBLE:** M08-P09 — Payouts
**STATUS/FILES/DEVIATIONS/TESTS** (paste balance-race + resolve-mismatch + retry-no-double-pay + velocity-cap + full-pytest tail) **/EXCERPTS** the balance-check + retry-status-requery — nothing else **/QUESTIONS** (flag F9b)
