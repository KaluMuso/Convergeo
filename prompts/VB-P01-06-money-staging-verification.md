> **Prepend `prompts/_header.md` (PROJECT HEADER) above this prompt.** Composer sessions share no memory — the header is required context.

# VB-P01…P06 — Money & escrow staging-verification evidence pack `[OPS]`

## 1. Context
**Wave 2.** Source: `docs/production-readiness/2026-07-19/vision-audit/03-waves-and-phases.md` (VM-B); `01-audit-findings.md` §5; MR-B01/B01b/B03; `release-gates.md` S1–S3, G3. **Depends on Wave 1 (VA-P02 migrations applied, VA-P03 API pinned) + Lenco sandbox credentials + Wave-0 B-1 (isolated stack: staging plane or throwaway DB branch).**
**Why one pebble, not six:** the drills are a **single sequenced flow** on one sandbox order — you cannot prove release (VB-P04) or refund (VB-P05) before a paid order exists (VB-P01). Output 3 lists VB-P02…P06 all `Deps: VB-P01`; they run as one runbook, not parallel agents. VB-P07 (false-success E2E, `[CODE]`) is the separate parallel-safe pebble.
**Build state (verified):** money handling is CODE_COMPLETE and correct — `settle_prepaid_collection`→`CHARGE_RECEIVED` (#274), `compute_release_amounts`/`capture_order_commission` (#288/#294), `enforce_ledger_transaction_balance` deferred zero-sum trigger, `webhook_verify` HMAC-on-raw-body + `webhook_events` unique/`23505` dedupe, `refunds/payout_port.py` `rfd-*` stable-key payout. **The gap is 0 live rows / never STAGING_VERIFIED**, not the code.
**Type:** `[OPS]` — Cursor writes the runbook + evidence docs + invariant queries; the **founder** runs sandbox checkouts with Lenco sandbox creds and pastes **redacted** ledger/SQL proof. **No production money, ever, in this pebble.**

## 2. Objective & scope
Produce STAGING_VERIFIED evidence that the prepaid→escrow→release→refund→reconciliation money path is correct and idempotent, against the **Lenco sandbox** on an **isolated stack**.
**Non-goals:** enabling production prepaid collection or `public_launch`; live payouts (F9b); Zamtel collections (stays off); any application code (that path is done).

## 3. Files (create ONLY these)
- `…/vision-audit/evidence/money-momo.md` (VB-P01), `money-card.md` (VB-P02), `webhook-idempotency.md` (VB-P03), `release-accounting.md` (VB-P04), `refund-matrix.md` (VB-P05), `recon-alert.md` (VB-P06)
- `scripts/db/ledger-invariants.sql` (read-only: per-transaction zero-sum + escrow-balance + orphan-leg checks)
**Guardrail: modify ONLY these files; run `load/invariant-check.py` but do NOT edit it.**

## 4. Implementation spec (sequenced runbook)
Run on the isolated stack with `LENCO_ENV=sandbox`, `payments_enabled()`→true only there, `zamtel_collections=false`.
- **VB-P01 — MoMo → ledger:** complete a MoMo prepaid checkout (MTN/Airtel sandbox). Assert `payments` row → success, and `ledger_transactions`/`ledger_postings` post `CHARGE_RECEIVED` (charge −gross + escrow-hold legs) summing to **zero** (`ledger-invariants.sql`). Record redacted `payment_id`/`ledger_txn_ids` + Lenco sandbox dashboard match.
- **VB-P02 — Card → ledger:** same via the Lenco hosted **card** widget (`payments_card`); same invariants.
- **VB-P03 — Webhook replay idempotency:** re-POST the same Lenco webhook (same `event:data.id`); assert a **single** ledger txn (dedupe via `webhook_events` unique / `23505`); a bad signature → 401 (not 500).
- **VB-P04 — Release accounting:** run the escrow release tick; assert `COMMISSION_CAPTURE` posts **before** `RELEASE_TO_VENDOR`, escrow nets to **0** over charge+capture+release, and a double-tick captures **once** (keyed `release-{order_id}-commission-*`). Free/0% orders post no capture leg.
- **VB-P05 — Refund / cancel:** cancel + refund the sandbox order; assert an `rfd-*` `payouts` row (`kind: customer_refund`, **stable idempotency key** so retries collapse), a notify enqueued, and lane-1/lane-2 math (restocking bps 500–1500, floor division) correct.
- **VB-P06 — Reconciliation alert:** force a Lenco-vs-ledger mismatch; run the recon tick; assert a `reconciliation_reports` row + an **actionable alert** (no silent drift).

## 9. Security
- Redact all PII / payment refs / Lenco tokens in evidence docs (aggregates + redacted ids only, per the audit-contract). Sandbox creds live in host env, never in repo. Confirm `payments/gate.py` still blocks money on non-sandbox envs.

## 10. Tests / verification (RUN before reporting)
- `scripts/db/ledger-invariants.sql` returns zero imbalanced transactions and zero orphan legs after each stage.
- `python load/invariant-check.py` (zero oversell / ledger-balance / gapless-invoice) passes on the sandbox data.
- `uv run pytest services/api/tests/test_ledger.py test_release_accounting.py test_refund_execute.py test_reconcile.py -q` green (unit backstop).

## 11. Acceptance criteria / DoD (maps to S1–S3, G3)
- [ ] MoMo + card sandbox pay → balanced `CHARGE_RECEIVED` ledger; redacted Lenco match attached.
- [ ] Webhook replay → single ledger txn; bad signature 401.
- [ ] Release: commission captured before vendor net; escrow→0; double-tick safe.
- [ ] Refund: single `rfd-*` payout on retry; lane math correct.
- [ ] Forced recon mismatch → actionable alert.
- [ ] **Zero production money; flags unchanged.** All evidence redacted.

## 12. IMPLEMENTATION REPORT
**PEBBLE:** VB-P01…P06 — Money & escrow staging-verification evidence pack
**STATUS:** COMPLETE | PARTIAL | BLOCKED
**FILES:** each evidence doc + `ledger-invariants.sql`
**DEVIATIONS:** any departure from spec, and why (or "none")
**TESTS:** paste invariant-SQL + `invariant-check.py` + pytest output (redacted ledger ids)
**EXCERPTS:** the ledger-invariant SQL + a redacted balanced-transaction proof
**QUESTIONS:** uncertainties needing a reviewer decision (or "none")
