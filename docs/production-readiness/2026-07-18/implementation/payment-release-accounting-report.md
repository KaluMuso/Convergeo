# Payment release accounting report — 2026-07-18

**Branch:** `cursor/payment-release-accounting-1002`  
**Depends on:** PR #274 (`CHARGE_RECEIVED` before prepaid success), PR #288 (M08-P08b product/service capture)  
**Out of scope (honoured):** deploy, live payment enablement, provider credential changes, live payouts, production backfills

## Verdict

Release-side accounting now captures commission from the **purchase-time** `orders.commission_snapshot` **before** `RELEASE_TO_VENDOR` on product, service, event, and COD paths. Retries are idempotent. Ledger posting failures fail closed. **Staging reconciliation proof is still required before any claim that live prepaid enablement is safe.**

## Accounting invariants

| #   | Invariant                                                                                                                 | Enforcement                                                                                                                    |
| --- | ------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------ |
| A1  | Collection posts gross into escrow (`CHARGE_RECEIVED` / `ESCROW_HOLD` / COD receivable)                                   | PR #274 + COD receivable open                                                                                                  |
| A2  | At release, commission is computed **only** from purchase-time `commission_snapshot` — never from live `commission_rates` | `compute_release_amounts` / `capture_order_commission`                                                                         |
| A3  | `COMMISSION_CAPTURE` posts **before** `RELEASE_TO_VENDOR`                                                                 | Product `evaluate_and_release`, service `confirm_job_completion`, event `evaluate_event_release`, COD `confirm_cod_collection` |
| A4  | `commission_ngwee + net_ngwee == gross_ngwee` (integer ngwee; floor `(gross * bps) // 10_000`)                            | `ReleaseAccountingAmounts` + engine                                                                                            |
| A5  | After charge → capture → release, escrow for the order nets to **0**                                                      | DB-backed lifecycle tests                                                                                                      |
| A6  | Idempotency: one capture set + one valid release under retry / concurrency                                                | Ledger unique idempotency keys                                                                                                 |
| A7  | Fail-closed: invalid snapshot, refund/cancel/dispute, or ledger error → no silent release                                 | `not_eligible` / `held` / raised `LedgerError`                                                                                 |
| A8  | COD remains on `cod-commission-*` / `cod-release-*` keys (no double capture via prepaid sweeper)                          | COD skip + key isolation test                                                                                                  |

### Lifecycle (prepaid product / service / event)

| Event              | Template             | platform_cash |      escrow | commission_revenue | vendor_payable | Idempotency key                                                                      |
| ------------------ | -------------------- | ------------: | ----------: | -----------------: | -------------: | ------------------------------------------------------------------------------------ |
| Collection success | `CHARGE_RECEIVED`    |        +gross |      −gross |                    |                | `prepaid-charge-{payment_id}`                                                        |
| Commission capture | `COMMISSION_CAPTURE` |               | +commission |        −commission |                | `{prefix}-commission-{listing\|index}`                                               |
| Vendor release     | `RELEASE_TO_VENDOR`  |               |        +net |                    |           −net | `release-{order_id}` / `event-release-{order_id}-{phase}` / `cod-release-{order_id}` |

Prefixes:

- Product / service: `release-{order_id}`
- Event / tickets: `event-release-{order_id}` (capture once before first phase)
- COD: `cod-commission-{order_id}`

### Rounding

Commission uses integer floor division only: `(gross_ngwee * rate_bps) // 10_000`. Net absorbs the remainder so `commission + net == gross` exactly.

### Reversal / refund / dispute / cancel

| State                                        | Release behaviour                                             |
| -------------------------------------------- | ------------------------------------------------------------- |
| Open dispute                                 | `held` / `dispute_open`                                       |
| Order `cancelled`                            | `not_eligible` / `order_cancelled`                            |
| Active refund row or `refund_lane1/2` ledger | `not_eligible` / `order_refunded`                             |
| Event cancelled                              | `blocked_cancelled` + mass-refund flag                        |
| Pre-release refund                           | Escrow drained by refund templates; release blocked           |
| Post-release refund                          | Clawback from `vendor_payable` (commission not reversed here) |

### Retry / concurrency

- Ledger `idempotency_key` unique constraint + lookup-before-insert.
- Capture-before-release ordering: if release fails after capture, re-drive completes without double-capture.
- Concurrent `evaluate_and_release` → one capture + one release (covered by ThreadPool test).

## Commission snapshot immutability (gate check)

| Question                                | Answer                                                                                                                                                 |
| --------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Complete enough for release-time use?   | **YES** — lines carry `rate_bps` + `line_total_ngwee` required for floor math                                                                          |
| DB-immutable?                           | **SOFT** — no column immutability trigger; RLS blocks customer/vendor writes; admin can UPDATE; ticket path may refresh snapshot at claim finalization |
| Present-day rates consulted at release? | **NO** (this PR)                                                                                                                                       |
| Migration required to proceed?          | **NO** for this gate                                                                                                                                   |

Caveats (documented, not blocking this gate):

- Product checkout does not snapshot `wholesale` → supplies +300 bps stack is inactive on that path.
- Delivery fee is in release gross but not in snapshot lines → commission is on items; fee passes through to vendor (existing intentional pattern).
- Hard DB immutability trigger remains a separate pebble if desired.

## What changed

| Area                           | Change                                                                                                                               |
| ------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------ |
| `escrow/release_accounting.py` | **New** — contract helpers: snapshot usability, amounts, refund blocks, order/day reconciliation summaries                           |
| `escrow/release.py`            | Validate snapshot; block cancel/refund; capture-before-release (existing) hardened; COD boolean parse fix (`true`/`false` from psql) |
| `escrow/event_release.py`      | **Gap closed** — capture commission once before first `RELEASE_TO_VENDOR` phase                                                      |
| `payments/reconcile.py`        | Daily summary adds `release_gross_collected_ngwee`, `release_commission_captured_ngwee`, `release_vendor_net_ngwee`                  |
| `payments/settlement.py`       | Docstring updated (release capture is implemented)                                                                                   |
| Tests                          | `test_release_accounting.py` (full matrix); event commission capture + organiser escrow expectation; ticket seed JWT for guards      |

### Migrations

**None.** Additive application code + tests + docs only.

## Test evidence

Command:

```bash
cd services/api
export SUPABASE_DB_URL=postgresql:///vergeo5_rls_test
uv run pytest tests/test_release_accounting.py tests/test_release.py tests/test_event_release.py -q
# → 51 passed
uv run ruff check app/services/escrow app/services/payments/settlement.py app/services/payments/reconcile.py
uv run mypy app/services/escrow/release_accounting.py app/services/escrow/release.py app/services/escrow/event_release.py app/services/payments/settlement.py app/services/payments/reconcile.py
```

| Required case                                    | Coverage                                                                                                |
| ------------------------------------------------ | ------------------------------------------------------------------------------------------------------- |
| Prepaid collection → capture → net release       | `TestPrepaidReleaseLifecycle::test_charge_capture_release_zeroes_escrow` (+ P08b product/service tests) |
| Repeated release attempts                        | `test_repeated_release_attempts_idempotent`                                                             |
| Two concurrent release attempts                  | `test_two_concurrent_release_attempts`                                                                  |
| Exact ngwee rounding                             | `test_exact_ngwee_floor_rounding` (123456 × 333 bps → 4111)                                             |
| Missing/invalid snapshot                         | `test_missing_commission_snapshot_blocks_release`                                                       |
| Failed commission posting                        | `test_failed_commission_posting_fail_closed`                                                            |
| Failed vendor release after capture              | `test_failed_vendor_release_after_commission_capture` (re-drive completes)                              |
| Refunded / cancelled / disputed cannot release   | `TestBlockedReleaseStates`                                                                              |
| Reconciliation gross / commission / net          | `TestReconciliationGrossCommissionNet` + day totals on reconcile summary                                |
| COD path preserved                               | `TestCodPathPreserved`                                                                                  |
| Event capture before release (incl. phased once) | `TestEventCommissionCapture`                                                                            |

## Rollback boundary

- Revert this branch / PR (application code + tests + this report).
- No migration to reverse.
- No production rows written by this change.
- Product/service capture from PR #288 remains independently revertable if needed.
- COD behaviour unchanged except prepaid sweeper now correctly skips COD when `cod::text` is `true` (bugfix).

## Staging proof still required

Before any live prepaid enablement decision:

1. Sandbox MoMo + card: paid order → `CHARGE_RECEIVED` → release tick → `COMMISSION_CAPTURE` + `RELEASE_TO_VENDOR`; escrow → 0.
2. Replay webhook + double release tick → single capture + single release.
3. Daily reconciliation report shows `release_gross_*`, `release_commission_*`, `release_vendor_net_*` consistent with Lenco/platform cash for the day.
4. n8n `release-job` / `event-release` active with successful authenticated ticks (ops gate; not claimed here).

## Explicit non-claims

- **Does not** claim live payment enablement is safe.
- **Does not** activate Lenco credentials, kill-switches, or production payouts.
- **Does not** backfill historical prepaid orders that may have stranded commission in escrow before P08b/event capture.
- **Does not** harden `commission_snapshot` with a DB immutability trigger (soft immutability remains).
