# Load test results — Vergeo5 checkout & browse

Findings from the k6 load suite (`load/`) and the post-run money-safety invariant check.

> **Status: scripts + invariant check delivered and offline-validated. The live 100cc
> staging run and its p95 numbers are FOUNDER / STAGING-GATED and NOT YET CAPTURED.**
> No p95 figures below are fabricated — the results table stays empty until the founder
> runs the suite against a deployed staging API with seeded data and a Lenco stub.

## Scope

| Deliverable                                                                             | State                                |
| --------------------------------------------------------------------------------------- | ------------------------------------ |
| `load/k6/checkout-load.js` — 100cc cart→reserve→order→payment-initiate (Lenco stub)     | Delivered, structure-validated       |
| `load/k6/browse-load.js` — search + PLP + suggest read mix                              | Delivered, structure-validated       |
| `load/invariant-check.py` — oversell / ledger / invoice-gap, non-zero exit on violation | Delivered, `py_compile` clean        |
| `load/README.md` — run procedure, env, thresholds, tuning log                           | Delivered                            |
| Live 100cc run + p95 measurement                                                        | **Deferred — founder/staging-gated** |

## Encoded thresholds (authoritative in the scripts)

- Checkout (100 VUs): `http_req_duration{scenario:checkout_100cc} p95<500`,
  `order_create_ms p95<500`, `checkout_session_ms p95<500`, `http_req_failed rate<0.01`,
  `checks rate>0.99`, `oversell_errors count==0`, `orders_created count>0`.
- Browse: `search p95<400`, `plp p95<400`, `suggest p95<250`, `http_req_failed rate<0.01`,
  `checks rate>0.99`.

## Money-safety invariants (the authoritative gate)

Grounded against as-built `master`:

1. **Zero oversells.** `stock_reservations` are claimed by an in-place decrement guarded by
   `stock_qty >= qty` (`services/api/app/services/stock/claim.py`), and `vendor_listings`
   carries `CHECK (stock_qty >= 0)` (`0003_catalog.sql`). A lost race on the last unit would
   drive `stock_qty` negative. Check: any tracked listing with `stock_qty < 0`, plus any
   active hold on an out-of-stock listing.
2. **Ledger balanced.** `ledger_postings` are debit-positive / credit-negative and must
   zero-sum per `transaction_id` (deferred constraint trigger `ledger_postings_zero_sum`,
   `0006_money.sql`). Check: any `transaction_id` whose postings sum ≠ 0, plus the
   system-wide sum ≠ 0 (a lost sibling leg = money created/destroyed).
3. **Invoice numbers gapless.** `next_invoice_no()` allocates sequentially under a row lock;
   `unique(series, no)` blocks duplicates. Check: any `series` where `min(no) <> 1` or
   `max(no) <> count(*)` (a hole = allocated number whose invoice row rolled back).

`invariant-check.py` exits non-zero if any of the three is violated.

## Offline validation performed in the build env (no staging, no k6, no DB)

- `node --check` on both k6 scripts (copied to `.mjs`) — **PASS** (ES-module structure and
  syntax valid).
- `python3 -m py_compile load/invariant-check.py` — **PASS**.
- Invariant SQL reviewed against the as-built schema (`0003`, `0005`, `0006`, `0013`,
  `0015`) — column/table names and signing convention confirmed.

_Paste console output of these checks into a run entry when re-validating._

## Live run results (founder to complete against staging)

| Date       | Commit          | Scenario       | VUs | p50 | p95 | p99 | err rate | oversell_errors | orders_created | invariant-check                                      |
| ---------- | --------------- | -------------- | --- | --- | --- | --- | -------- | --------------- | -------------- | ---------------------------------------------------- |
| 2026-07-20 | `d9839db`       | checkout_100cc | 100 | —   | —   | —   | —        | —               | —              | NOT_RUN (ops-drills: k6 absent; API 502; no staging) |
| 2026-07-20 | `d9839db`       | browse_mix     | 100 | —   | —   | —   | —        | n/a             | n/a            | n/a                                                  |
| _pending_  | _staging-gated_ | checkout_100cc | 100 | —   | —   | —   | —        | —               | —              | —                                                    |
| _pending_  | _staging-gated_ | browse_mix     | 100 | —   | —   | —   | —        | n/a             | n/a            | n/a                                                  |

## Interpreting a run

- **All k6 thresholds green AND `invariant-check.py` exits 0** → pass. Record numbers in the
  tuning log in `load/README.md`.
- **Thresholds green but invariant-check fails** → a correctness/money bug hid under load;
  the run FAILS regardless of latency. Open a defect and do not ship.
- **p95 over budget but invariants clean** → performance-tuning task (DB pool, PgBouncer
  transaction mode, API worker count, reservation TTL); money is safe but the SLO is missed.

## Follow-ups (staging-gated)

- [ ] Founder: stand up staging + seed carts/listings/JWTs + Lenco stub, run the suite,
      paste p95/p99 and invariant-check output here.
- [ ] Add a deliberately scarce listing and a contention burst to prove the oversell guard
      under a hot-row race, then confirm `invariant-check.py` still passes.
