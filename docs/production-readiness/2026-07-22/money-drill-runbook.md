# Money-path sandbox drill — S1–S3 runbook (MoMo → ledger → release → payout)

**Date:** 2026-07-22 · **Scope:** Lenco **sandbox only** · **Goal:** flip S1 (MoMo→ledger), S2 (card→ledger, optional), S3 (release accounting) from FAIL → PASS_SANDBOX_ONLY, then activate the payment-reconciliation n8n workflow.

Supersedes the blocked 07-20 attempt (`../2026-07-20/lenco-sandbox-money-drill.md`). **What's cleared since then:** API health is **200** (`/healthz`,`/readyz`,`/fingerprint`), DB is at **`0066`** with `0064` FORCE RLS + `0065` `source_key` applied. **One blocker remains: F9b (Lenco sandbox creds).**

---

## 0. Hard rules (do not break)

- **Sandbox only.** `LENCO_ENV=sandbox`; never paste sandbox or prod tokens into git.
- **No real charges / no real PII.** Use the deterministic sandbox MoMo numbers below; use throwaway drill users.
- **Keep `public_launch=false`** and **`PAYMENTS_ALLOW_PRODUCTION` unset** for the entire drill.
- Log evidence (redacted IDs, ngwee tables) in `docs/ops/drill-log.md`; do **not** commit tokens/webhook secrets/full payloads.

## 1. Preconditions (founder / ops on the API host)

Set on the API host env file, then restart the API container. **These are the F9b unblock:**

| Env var | Value | Purpose |
|---|---|---|
| `LENCO_API_TOKEN` | sandbox token (from support@lenco.co) | server auth |
| `LENCO_ENV` | `sandbox` | switches base URL to sandbox + gates Zamtel |
| `LENCO_SANDBOX_BASE_URL` | default `https://api.sandbox.lenco.co/access/v2` — override only if Lenco gives a different base | sandbox REST base |
| `LENCO_ACCOUNT_ID` | sandbox debit account uuid (`GET /accounts`) | payout `accountId` |
| `PAYMENTS_ENABLED` | `true` | lifts the safe-by-default kill switch → gate returns `enabled_sandbox` |
| `PAYMENTS_ALLOW_PRODUCTION` | **unset / false** | ⚠ must stay off — otherwise gate could go live |
| `NEXT_PUBLIC_LENCO_PUBLIC_KEY` | sandbox public key (Vercel customer project) | card widget (S2 only) |

Register the **staging webhook** with Lenco support: `https://api.vergeo5.com/webhooks/lenco` (F9e). Signature = HMAC-SHA512 of the raw body, key = SHA256-hex of the API token — rotating the token rotates the webhook key.

Verify the gate before starting:
```bash
curl -s https://api.vergeo5.com/fingerprint   # env=production, but LENCO_ENV=sandbox keeps money in sandbox
# The payments gate should read enabled_sandbox — confirm via a drill checkout landing on 'pending', not 'disabled'.
```

Apply `scripts/ops/staging-money-drill-fixtures.sql` — it now preps **catalog visibility** (5 COD-eligible listings off the `demo/` prefix), **stock** (bumps the drill listings to ≥100 tracked units), and the **vendor payout destination** (sandbox MoMo `payout_msisdn`/`payout_rail`, hold cleared) so the release→payout leg can send. Idempotent + reversible; run the read-only verify block at the bottom to confirm readiness. The **buyer** is an operator step (phone-OTP sign-in — can't be fixtured). Primary SKU: `tea-coffee-standard` (K28.97). Preflight: `../2026-07-20/staging-money-drill-preflight.md`.

## 2. Section A — MoMo collection → ledger (gate **S1**)

Customer flow (customer app or curl with a buyer JWT):
1. `POST /checkout/session` → `session_id`.
2. `POST /checkout/steps/contact` → buyer phone.
3. `POST /checkout/steps/fulfilment` → landmark (creates address).
4. `GET /checkout/steps/payment-options`; `POST /checkout/steps/payment` with method `momo`, operator `mtn`, phone **`0961111111`** (sandbox MTN **success**) → order created, payment initiated.
5. `POST /payments/retry` if the push needs (re)driving; `GET /payments/status` → **`pending`** (customer authorises on phone). **This must NOT read as paid yet.**
6. Lenco sends `collection.successful` → `POST /webhooks/lenco` settles the hold.

**Assert (SQL, service-role):**
```sql
-- exactly one successful payment for the order
select count(*) from payments where order_id = :oid and status = 'success';           -- = 1
-- CHARGE_RECEIVED + ESCROW_HOLD posted exactly once each
select t.kind, count(*) from ledger_transactions t where t.order_id = :oid group by 1; -- charge_received=1, escrow_hold=1
-- every transaction's postings zero-sum
select transaction_id, sum(amount_ngwee) s from ledger_postings
  where transaction_id in (select id from ledger_transactions where order_id = :oid)
  group by 1 having sum(amount_ngwee) <> 0;                                            -- 0 rows
-- escrow hold equals the order gross (integer ngwee)
```
**S1 PASS** = pending-before-callback, exactly-one success payment, `charge_received`+`escrow_hold` once each, all postings zero-sum, hold = expected ngwee.

## 3. Section D — false-success proof (gate S6 slice)

Repeat §2 step 4 with each sandbox failure number and assert the order **never** reads paid/completed and **no** ledger/settlement rows appear:

| Number | Expected | Assert |
|---|---|---|
| `0962222222` | insufficient funds → `failed` | payment `failed`, 0 ledger txns |
| `0966666666` | timeout | stays `pending`/`failed`, 0 ledger txns |
| Airtel `0972222222` | wrong PIN → `failed` | as above |

The client never trusts HTTP 200 — it branches on `data.status` (`lenco/client.py`), so a 200-with-`failed` must surface as failed.

## 4. Section C — webhook replay idempotency

Re-POST the **same** `collection.successful` body (same signature) to `/webhooks/lenco`, then a concurrent duplicate. Assert: still exactly one payment, one `charge_received`, one `escrow_hold`, no new settlement/ledger rows. Idempotency key = `event:data.id` (`webhooks_lenco.py`).

## 5. Section E — release accounting (gate **S3**)

Drive the order to a release-eligible lifecycle (delivered/confirmed), then run the internal ticks (n8n does this in prod; drive by hand for the drill):
```bash
curl -sX POST https://api.vergeo5.com/internal/order-jobs/auto-confirm \
  -H "X-Internal-Token: $INTERNAL_ORDER_JOBS_TOKEN"
curl -sX POST https://api.vergeo5.com/internal/order-jobs/auto-release \
  -H "X-Internal-Token: $INTERNAL_ORDER_JOBS_TOKEN"
# (or the standalone release job: POST /internal/release-job/tick with $INTERNAL_RELEASE_JOB_TOKEN)
```
**Assert:** `commission_capture` posts **before/with** `release_to_vendor`; both once; escrow remaining balance correct; a **second** release run posts **nothing** (idempotent). All postings zero-sum. **S3 PASS.**

## 6. Section — vendor payout (transfer leg)

```bash
curl -sX POST https://api.vergeo5.com/internal/payouts/retry-tick \
  -H "X-Internal-Token: $INTERNAL_PAYOUTS_TOKEN"
```
Assert a `payouts` row moves `pending → processing → success` against the sandbox transfer, using `LENCO_ACCOUNT_ID`; `GET /vendor/payouts` balances reflect the release; no float anywhere (integer ngwee end to end).

## 7. Activate reconciliation (only after S1+S3 pass)

Publish the money n8n workflow `Vergeo5 — payment reconciliation crons` (`C1MpTNjrfLACMG3f`, currently inactive). It POSTs `/internal/reconciliation/{poll-tick,daily-report}`, webhook drain, and payment sweeper. Then force one mismatch and confirm it **detects + alerts** without destructive auto-correct.

## 8. Evidence to log (`docs/ops/drill-log.md`)

Per section: order id + checkout_group_id, sandbox `pay-*`/`ord-*` reference (redacted), pending→paid transition, the ngwee posting table, release/payout run outputs, and an explicit **PASS / FAIL** per gate. Update `../2026-07-20/lenco-sandbox-money-drill.md` gate table (or a fresh 07-22 verdict) once green.

## 9. Non-goals

Do **not** flip `public_launch`; do **not** set `PAYMENTS_ALLOW_PRODUCTION`; do **not** use production Lenco keys. This drill produces `PASS_SANDBOX_ONLY`, not a production-money GO (F4 legal review still stands).
