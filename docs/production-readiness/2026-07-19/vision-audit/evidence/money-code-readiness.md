# Money-code readiness — independent CODE_COMPLETE verification (Wave 2, verifier half)

**Date:** 2026-07-19 · **Executor:** Claude (autonomous, read-only + local test harness) · **Base:** `master @ 619c994`
**Authorization / safety:** No Lenco credentials used. No production contact. No money flag touched. All work ran against a **throwaway local Postgres** stood up in this session; amounts below are synthetic test fixtures (no PII, no real payment refs).

> **Why this doc exists.** Every Wave-2 money gate (S1–S6) is `FAIL` in `release-gates.md` for the *same* reason — *"CODE_COMPLETE but never run against Lenco sandbox."* The whole Go/No-Go leans on that **"money is CODE_COMPLETE and correct"** claim (`VB-P01-06` §1; `release-gates.md` G3). The live sandbox walk needs founder creds + an isolated stack (both unavailable to MCP). But the *claim itself* is code-testable now — so this is the verifier half of Wave 2: prove the code is correct **before** the founder spends time on sandbox setup, so any latent ledger/idempotency/refund bug surfaces in a read, not mid-walk.

## TL;DR verdict

**The "CODE_COMPLETE and correct" claim is UPHELD** — verified at both the Python layer (fakes) **and** the DB-trigger layer (real Postgres), which no prior run had exercised. Two **non-blocking** follow-ups found (one date-coupled test time-bomb, one CI-coverage gap) — **both now fixed on this branch** (F-1/F-2 below); neither was a money-correctness defect. The live Lenco round-trip (S1–S6) remains correctly founder-gated, but the code those gates exercise is now independently proven.

| Layer | What ran | Result |
| ----- | -------- | ------ |
| **Python (fakes)** | full money surface — ledger, settlement, webhook, payment/order SM, refund, payout, gate, Lenco client, money conversion | **259 passed** (2 batches: 138 + 121) |
| **DB-trigger (real PG16 + pgvector)** | release accounting, service escrow, event release, order SM guard/concurrency — the SQL triggers fakes can't cover | **release 13 · service_escrow+event_release 33 · reconcile 17 · commissions_invoicing 15 · order_state 724**, each green in isolation |
| **Schema** | all **56** migrations replayed from scratch, incl. the Wave-1 `0051/0053–0056` applied to prod in VA-P02 | **clean replay** |
| **Float audit** | `grep`/tests for float on money | **clean** — see below |

## Method (reproducible)

The DB-integration money tests (`test_release`, `test_service_escrow`, `test_event_release`, …) `pytest.skip()` when Postgres is unreachable at `127.0.0.1:54322` — so they had **never run** in this environment. Stood up the target locally, mirroring CI's bare-Postgres shim (`scripts/ci/migration-replay.sh`):

```bash
sudo apt-get install -y postgresql-16-pgvector          # only 'vector' was missing (pg_trgm/pgcrypto present)
sudo pg_createcluster 16 vergeo --port 54322 -- -U postgres --auth-local=trust --auth-host=trust
# + host trust for 127.0.0.1, + supabase_admin / supabase_auth_admin roles (GoTrue roles 0051 needs;
#   the pytest bootstrap creates anon/authenticated/service_role but not these — CI gets them from the
#   Supabase CLI stack, which is why the bare pytest harness omits them).
cd services/api && uv run pytest tests/test_release.py …    # apply_migrations() self-bootstraps auth schema
```

`apply_migrations()` (`tests/rls/conftest.py`) runs `AUTH_BOOTSTRAP_SQL` then replays all 56 migrations, so a vanilla PG16 becomes the schema under test. PG **16.13**, 56 migrations, all green on replay.

## Invariants confirmed (code map + tests)

- **Integer ngwee only — no float on money.** `payments/money.py` is `Decimal`-only and **raises `TypeError` on float** (`major_str_to_ngwee`); bps is integer floor (`(x*bps)//10_000`); the Lenco client embeds the pre-validated major-unit string as a raw JSON numeric literal (no float round-trip). Regression-guarded (`test_money.py::test_money_module_has_no_float_literals_in_computation`). The only floats in scope are non-monetary (HTTP timeouts, DB-pool, KYC match-score). → **G3 "no float money math" ✅ at code level.**
- **Ledger zero-sum — double-enforced.** Python `_assert_balanced` (sum==0, non-empty, no zero legs) **plus** the DB deferred constraint trigger `enforce_ledger_transaction_balance` (`0006_money.sql`). Both exercised green.
- **Settlement fail-closed.** `settle_prepaid_collection` posts `CHARGE_RECEIVED` **before** the payment→SUCCESS transition; a ledger failure blocks marking paid (`test_prepaid_settlement.py::test_ledger_failure_blocks_payment_success`).
- **Release ordering.** `COMMISSION_CAPTURE` before `RELEASE_TO_VENDOR`; escrow nets to 0; double-tick captures once (`test_release.py`, `test_release_accounting.py`). Synthetic proof: gross **200000** → commission **16000** (800 bps) + net **184000**, `16000+184000==200000`.
- **Webhook idempotency + signature.** `webhook_events` UNIQUE(provider,event_id) → `23505` no-op; missing/blank/bad signature → **401 before any parse**; `event:data.id` composite disambiguates successful-vs-settled (`test_webhooks.py`).
- **State machines never raw-UPDATE status.** Payment SM = optimistic-locked conditional UPDATE (`.eq(status,from)`→409); order SM = `SELECT … FOR UPDATE` row-lock (→409); guard trigger blocks non-service-role status flips (`test_order_state.py`, 724 green).
- **Refund = ledger-orchestrated `rfd-*` payout.** Double-exec guarded (`_find_existing_refund` + `23505` catch); reference derived from a **stable idempotency key** so retries collapse to one payout; DB backstop `0032` partial-unique; lane math integer, floored, never negative (`test_refund_execute.py`, `test_refunds.py`).
- **Payout never double-pays.** Retry re-queries status before re-send; dead-letters after 5 attempts; customer-refund routing skips the vendor `PAYOUT_EXECUTED` leg (`test_payouts.py`).

## Findings (both NON-BLOCKING — neither is a money-correctness defect)

### F-1 · Date-coupled test time-bomb — `test_release_accounting.py::TestReconciliationGrossCommissionNet::test_day_totals_and_order_summary_consistent`
Fails on **any date ≠ 2026-07-18** (fails today, 2026-07-19). Root cause: the test seeds the order at a hardcoded `2026-07-18`, but `evaluate_and_release`'s ledger postings take `ledger_transactions.created_at` from the **DB clock** (real now), not the seeded `now`. `build_release_accounting_day_totals(report_date="2026-07-18")` filters on `lt.created_at` and correctly finds **0** for the 18th because the legs landed on the 19th.
- **The production code is correct.** The per-order summary is exact and balanced; bucketing the same legs on `current_date` returns gross/commission/net = 200000/16000/184000. Only the test's hardcoded date is wrong.
- **RESOLVED (this branch).** The test now derives `report_date` from the day the charge leg actually landed (`SELECT created_at::date FROM ledger_transactions WHERE idempotency_key='prepaid-charge-{order_id}'`) instead of a literal `2026-07-18` — deterministic on any calendar date, no change to ledger `created_at` semantics. Verified green (15/15 in isolation).

### F-2 · Money DB-trigger coverage is dormant in CI — `test_release`, `test_release_accounting`, `test_reconcile`
Their DB-integration cases (release idempotency, reconciliation day-totals, migration-0018 clean replay, poison-pill isolation) run in **no CI job with a live Postgres**: the `python` job (`uv run pytest`) has no DB → they skip; the `rls` job's curated list (`ci.yml` L468) includes `test_event_release`/`test_service_escrow` but **omits these three**. That is why F-1 never fired in CI. Verified green here in isolation.
- **Why not just append to the `rls` step:** each of these files seeds its own **platform ledger-account id family** (`test_release`→`c1…`, `test_release_accounting`→`a1…`, `test_event_release`→`ea…`), and `ledger_accounts_kind_platform_key` is `UNIQUE(kind) WHERE vendor_id IS NULL` — one platform account per kind. Run in one process on a shared schema, the second family collides (`duplicate key … kind_platform_key`). Empirically reproduced: adding these to the curated set → 10 setup errors. They must each run against a **freshly-reset schema**.
- **RESOLVED (this branch).** Added a dedicated `money-db-triggers` CI job (bare `pgvector/pgvector:pg16` service on `:54322`, isolated from the real-stack `rls` job): provisions the `supabase_admin`/`supabase_auth_admin` GoTrue roles (as `scripts/ci/migration-replay.sh` does), then runs each of the three files in its own process after a `DROP SCHEMA … CASCADE` reset (the module `db` fixture re-applies all migrations). The full step shell was simulated locally end-to-end → **13 / 15 / 17 passed**.

### Notes (informational, not defects)
- **Cross-file DB pollution.** Running many money DB-integration files in one process (shared, un-reset DB) yields *non-deterministic* failures (`invoice_counters_pkey` dup, "posts once" count drift) — expected for this harness (`schema_ready` skips reset after the first file); each file is green alone. CI runs them in curated groups, so this doesn't bite there. Flagged so no one reads a consolidated-run red as a code bug.
- **Reviewer flag (from code map).** `payments/initiate.py::initiate_checkout_payment` is referenced **only by tests** — the live MoMo push runs through the retry path (`payment_status.py::_create_retry_payment_attempt`). Confirm the first-attempt wiring during the sandbox walk (VB-P01). Not a defect; possibly dead code.

## Still founder-gated (unchanged)
S1–S6 require the **live Lenco sandbox** on an isolated stack: real MoMo USSD-push (S1), card widget (S2), real webhook signatures + replay (S3), release/refund/recon against the Lenco dashboard (S4–S6). No MCP call originates a Lenco payment and Supabase branching is Pro-gated — so the founder runs the walk; I verify the ledger via Supabase MCP **once its connector is re-authorized** (it dropped auth this session). The code those gates exercise is now independently proven at the Python **and** DB-trigger layers, so the walk is a live-integration formality, materially de-risked.

## Status
Money code **CODE_COMPLETE — verdict UPHELD** · F-1 (test date-coupling) + F-2 (dormant CI coverage) **both RESOLVED this branch** · S1–S6 live walk founder-gated.
