# Lenco sandbox money drill — runbook

> **Scope:** CR-D evidence collector for gates **S1–S6** (money subset), **G3/G4**,
> and the 24-row staging acceptance matrix.
> **Environment:** Lenco **sandbox only** (`LENCO_ENV=sandbox`). Never production creds.
> **Harness:** `scripts/drills/lenco_sandbox_money_drill.py`

---

## Why this exists

The Lenco integration is code-complete but was never proven against a real Lenco rail.
Launch checklist §3 and release gates S1–S6 require a scripted, idempotent money drill
that asserts ledger balance at each step. The harness now separates a synthetic
`PASS` (assertion code works) from a live certification verdict. A live `PASS` also
requires a complete, source-bound 24-row evidence file; missing/skipped legs produce
`BLOCKED_EXTERNAL`, never a full acceptance claim.

---

## 1. Obtain sandbox credentials (F9b)

| Variable                       | Source                               | Notes                                             |
| ------------------------------ | ------------------------------------ | ------------------------------------------------- |
| `LENCO_API_TOKEN`              | Lenco support / dashboard (sandbox)  | Bearer token; also webhook HMAC key               |
| `LENCO_ENV`                    | Set to `sandbox`                     | **Required** — script refuses production          |
| `LENCO_SANDBOX_BASE_URL`       | Lenco support (optional override)    | Default: `https://api.sandbox.lenco.co/access/v2` |
| `LENCO_ACCOUNT_ID`             | `GET /accounts` on sandbox           | Needed for payout leg (S3)                        |
| `NEXT_PUBLIC_LENCO_PUBLIC_KEY` | Lenco sandbox public key             | Card widget leg (S2) — UI only                    |
| `LENCO_ACCOUNT_ID`             | Configured account returned by Lenco | Never select the first account implicitly         |

**Founder checklist (F9b):**

1. Email Lenco support for sandbox API token + public key (see `docs/ops/lenco/lenco-api-distilled.md` §Open items).
2. Register staging webhook URL: `https://<staging-api>/webhooks/lenco`.
3. Store creds in the **isolated staging stack only** (env / secrets manager — never git).
4. Confirm `PAYMENTS_ENABLED=true` and `LENCO_ENV=sandbox` on that stack.
5. Do **not** set `PAYMENTS_ALLOW_PRODUCTION` for sandbox drills.

---

## 2. Preconditions

### Infrastructure

- [ ] API `GET /healthz` and `GET /readyz` return **200**
- [ ] Migrations at repo tip applied on the **isolated** money target (incl. `refunds.source_key` when running refund matrix)
- [ ] `public_launch=false`; production checkout disabled
- [ ] Internal cron tokens configured (`INTERNAL_RECONCILIATION_TOKEN`, `INTERNAL_RELEASE_JOB_TOKEN`, `INTERNAL_PAYOUTS_TOKEN`)

### Test data

- [ ] Synthetic buyer with phone OTP path (`DRILL_BUYER_TOKEN`)
- [ ] Admin JWT for refund leg (`DRILL_ADMIN_TOKEN`)
- [ ] Cart + pending checkout group (`DRILL_CHECKOUT_GROUP_ID`) — see `scripts/ops/staging-money-drill-fixtures.sql`
- [ ] Sandbox MoMo test MSISDN: `0961111111` (MTN auto-approve) or `0971111111` (Airtel)

### Hard stops (script enforces)

- `LENCO_ENV` must be `sandbox`
- `PAYMENTS_ENABLED` must be truthy
- API host must not be `api.vergeo5.com` (production)
- Script never weakens `payments_enabled()` or flips `public_launch`

---

## 3. Running the drill

### Quick start (no creds — CI / agent)

```bash
uv run python scripts/drills/lenco_sandbox_money_drill.py --mode dry-run
```

Replays the bundled cassette (`scripts/drills/fixtures/lenco_sandbox_cassette.json`) and
validates assertion logic. Verdict `PASS` here means **harness OK**, not STAGING_VERIFIED.

### Live sandbox

```bash
export LENCO_ENV=sandbox
export PAYMENTS_ENABLED=true
export LENCO_API_TOKEN=<sandbox>
export SUPABASE_DB_URL=<isolated-db>
export DRILL_API_BASE_URL=https://<staging-api>
export DRILL_BUYER_TOKEN=<jwt>
export DRILL_ADMIN_TOKEN=<admin-jwt>
export DRILL_CHECKOUT_GROUP_ID=<uuid>
export DRILL_ORDER_ID=<uuid>
export DRILL_VENDOR_PAYOUT_ID=<uuid-linked-to-the-observed-transfer>
export DRILL_MOMO_RAIL=mtn
export DRILL_MOMO_NUMBER=0961111111
export DRILL_CARD_NEGATIVE_CHECKOUT_GROUP_ID=<fresh-unpaid-card-checkout>
export DRILL_CARD_POSITIVE_PAYMENT_ID=<different-widget-completed-payment>
export INTERNAL_RECONCILIATION_TOKEN=<token>
export INTERNAL_RELEASE_JOB_TOKEN=<token>
export INTERNAL_PAYOUTS_TOKEN=<token>
export DRILL_ALLOW_SQL_SETUP=1   # ops only: advance order to buyer-confirmed

uv run python scripts/drills/lenco_sandbox_money_drill.py --mode live \
  --acceptance-evidence /restricted/evidence/acceptance-24-rows.json
```

### Airtel collection evidence

Run the Airtel settlement as a separate checkout, not a retry of the MTN order.
Create a new cart, pending checkout group, and order, then run the same command
with:

```bash
export DRILL_MOMO_RAIL=airtel
export DRILL_MOMO_NUMBER=0971111111
export DRILL_CHECKOUT_GROUP_ID=<fresh-airtel-checkout-group-uuid>
export DRILL_ORDER_ID=<fresh-airtel-order-uuid>
```

The report records `entities.momo_rail`. Keep both rail reports as redacted
evidence. The drill rejects any collection rail other than `mtn` or `airtel`.

Optional flags:

- `--skip-release` — MoMo + webhook replay only (S1)
- `--report /path/to/report.json` — custom report location
- `--cassette /path/to/fixture.json` — alternate cassette for dry-run

### What each step does

| Step                      | Exercises                                              | Key assertions                                                                                                                   |
| ------------------------- | ------------------------------------------------------ | -------------------------------------------------------------------------------------------------------------------------------- |
| **preflight**             | Sandbox guards, API/DB reachability                    | `LENCO_ENV=sandbox`, `PAYMENTS_ENABLED`, no prod host                                                                            |
| **momo_collection**       | USSD push → webhook/poll → per-order funding           | Immediate status is not assumed successful; one `escrow_hold` and real idempotency key per order; exact aggregate postings       |
| **webhook_replay**        | Re-POST same signed webhook (Lenco 30min×24h retry)    | HTTP 200, no duplicate event, and the count of all collection ledger transactions is unchanged                                   |
| **release_payout_refund** | Release → payout → post-release refund-as-payout       | Vendor and refund transfers are terminal `paid`, linked by actual payout/refund IDs; post-release refund uses the clawback phase |
| **card_verification**     | Separate fresh negative and positive hosted-card cases | Negative cannot fund; different widget-completed payment has server verification, one receipt and ledger evidence                |

---

## 4. Reading the report

Report path: `scripts/drills/reports/lenco-sandbox-drill-<timestamp>.json`

```json
{
  "verdict": "PASS",
  "ledger_imbalance_ngwee": 0,
  "gates": { "S1": "PASS", "S2": "PASS", "S3": "PASS", "S6": "PASS" },
  "acceptance_evidence": {
    "expected_count": 24,
    "observed_count": 24,
    "passed_count": 24,
    "certifiable": true,
    "issues": []
  },
  "steps": [ { "name": "webhook_replay", "assertions": [ ... ] } ]
}
```

| Field                    | Meaning                                                   |
| ------------------------ | --------------------------------------------------------- |
| `verdict`                | `PASS` · `FAIL` · `BLOCKED_EXTERNAL`                      |
| `ledger_imbalance_ngwee` | **Must be 0**. Any non-zero ⇒ automatic `FAIL`            |
| `gates`                  | Per-gate mapping (see §5)                                 |
| `steps[].assertions[]`   | Per-step expected vs actual                               |
| `blockers`               | Why live mode could not run (F9b, missing checkout, etc.) |

**PASS** on a live run means every required harness step passed and all 24 evidence
rows were independently present, runtime/provider classified as required, and bound
to the candidate, deployment and schema. It does not itself approve policy or launch.
**PASS** on dry-run means only that the explicitly synthetic cassette assertions work.

---

## 5. Gate mapping (S1–S6)

| Gate   | Definition                         | Drill step                                         | PASS criteria                                                                                 |
| ------ | ---------------------------------- | -------------------------------------------------- | --------------------------------------------------------------------------------------------- |
| **S1** | Sandbox MoMo prepaid → ledger      | `momo_collection` + `webhook_replay`               | One `CHARGE_RECEIVED` per checkout; idempotent replay; Σ postings = 0                         |
| **S2** | Sandbox card prepaid → ledger      | `card_verification` positive identity              | Separate hosted-widget payment, server verification, receipt and ledger evidence              |
| **S3** | Release accounting drill           | `release_payout_refund`                            | `COMMISSION_CAPTURE` + `RELEASE_TO_VENDOR`; escrow nets 0; payout + refund-as-payout complete |
| **S4** | n8n release + tickets active       | _Not in this harness_                              | Requires n8n workflow publish — separate Prompt 7 evidence                                    |
| **S5** | KYC lifecycle drill                | _Not in this harness_                              | Admin KYC queue — separate drill                                                              |
| **S6** | False-success E2E                  | `card_verification` negative identity + Playwright | Pending/failed ≠ paid; negative identity remains unfunded; COD isolated                       |
| **G3** | Payment ledger / recon correctness | S1 + S3                                            | Ledger balanced; webhook idempotency proven                                                   |
| **G4** | No false payment-success state     | S6                                                 | `order_confirmed=false` when provider unverified                                              |

Attach the JSON report (redacted IDs) as evidence in launch checklist §3 **Staging money drill**.

---

## 6. Webhook replay — no double-post (reference)

The replay step re-signs the stored webhook body and POSTs it again. Three dedupe layers must hold:

1. **HTTP ingest:** `webhook_events` UNIQUE `(provider, event_id)` → Postgres `23505` → still 200, no second row
2. **Drain processor:** `processed_at` set → `process_webhook_event` returns early
3. **Ledger:** `prepaid-charge-checkout-{checkout_group_id}` idempotency key → at most one `CHARGE_RECEIVED`

Report assertion names: `webhook_events_no_duplicate_row`, `charge_received_unchanged`, `ledger_txn_count_unchanged`.

---

## 7. Troubleshooting

| Symptom                            | Likely cause                           | Action                                                                                 |
| ---------------------------------- | -------------------------------------- | -------------------------------------------------------------------------------------- |
| `BLOCKED_EXTERNAL`                 | Missing F9b creds                      | Supply sandbox token; re-run `--mode live`                                             |
| Payment stays `ussd_pushed`        | Webhook not registered / drain not run | Call `POST /internal/reconciliation/webhook-drain-tick`; check Lenco webhook URL       |
| `escrow_hold_per_order` differs    | Funding allocation/product bug         | STOP; preserve checkout/order/payment identities                                       |
| Release step `not_eligible`        | Order not delivered/confirmed          | Complete the real isolated fixture prerequisites; SQL setup is simulated evidence only |
| Card `held=true` after real charge | Expected until webhook arrives         | Drain webhooks; re-verify                                                              |
| `ledger_imbalance_ngwee` ≠ 0       | Accounting bug                         | FAIL — capture report + SQL snapshot                                                   |

---

## 8. Explicit non-claims

- Dry-run / cassette PASS ≠ STAGING_VERIFIED
- Source/local/CI or explicitly simulated rows can never satisfy the 24-row live verdict
- Missing actor, rail, leg, receipt, payout/refund linkage or provider account evidence blocks the applicable row
- Pending payout/refund, missing admin token, or a negative-only card case is not acceptance
- This drill does not approve production money or flip `public_launch`
- S4 (n8n) and S5 (KYC) require separate drills
- Product bugs found during live runs must be reported as QUESTIONS — not patched in the harness

---

## Related docs

- `docs/ops/lenco/lenco-api-distilled.md` — Lenco contract
- `docs/ops/staging-money-drill.md` — UI-level staging drill
- `docs/plan/launch-checklist.md` §3 — staging-gated proofs
- `docs/production-readiness/2026-07-18/consolidated/release-gates.md` — S1–S6 definitions
- `e2e/specs/checkout-false-success.spec.ts` — S6 Playwright matrix
