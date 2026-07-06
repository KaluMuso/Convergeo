# Lenco API — Distilled Implementation Reference (Vergeo5)

Sources: `Lenco_Docs_1.pdf` (guides: widget, webhooks, recipients/resolve, accounts, sandbox data, error codes) + `Lenco_Docs_2.pdf` (OpenAPI endpoint reference). Distilled 2026-07-06. **This file is the payment-contract source of truth for all M08 pebbles/prompts — do not re-read the PDFs.**

## Decisions this forces (binding for M07/M08)

1. **Mobile money (MTN, Airtel):** direct API `POST /collections/mobile-money` (USSD push; status `pay-offline` → webhook + polling `GET /collections/status/:reference`).
2. **Zamtel:** ⚠ collections enum = `airtel|mtn` only (payout enum includes `zamtel`). Doc 1's widget prose mentions Zamtel, Doc 2's API enum does not. **Verify with Lenco support; until confirmed, checkout UI treats Zamtel numbers as unsupported for direct push and offers card/other-number; payouts to Zamtel are fine.** (Founder follow-up F9a.)
3. **Cards:** NEVER the direct card API (raw PAN + JWE ⇒ requires our own PCI DSS certificate). Use the **hosted inline widget** `LencoPay.getPaid({...})` (`https://pay.lenco.co/js/v1/inline.js`, sandbox `pay.sandbox.lenco.co`) with public key; server verifies via `/collections/status/:reference` before fulfilment.
4. **Refunds:** no refunds API exists ⇒ refunds are **payouts** (`POST /transfers/mobile-money` etc.) orchestrated by our escrow ledger, incl. lane-2 fee math and post-release clawback.
5. **Split/escrow:** no subaccounts/splits ⇒ collections settle into the platform Lenco account (`instant` or `next-day` settlement); **our double-entry ledger is the escrow**; vendor payouts via transfers API. (Matches D14; F4 counsel review stands.)
6. **Money handling:** Lenco speaks **decimal major units** — requests `amount` as number (e.g. `10.75`), responses as 2-dp strings (`"20.00"`). Internally Vergeo5 stores **integer ngwee**; the Lenco adapter converts with `Decimal` only (float is forbidden).
7. **Idempotency:** client `reference` (unique, case-sensitive, charset `[-._A-Za-z0-9]`; duplicate ⇒ 400 "Duplicate reference"/errorCode 04). No metadata field ⇒ encode our IDs: `ord-{orderId}-{attempt}` for collections, `pay-{payoutId}` for transfers, `rfd-{refundId}` for refund payouts. Lenco's own id = `lencoReference`.
8. **Never trust HTTP 200:** transfer/collection calls return 200 even when `data.status="failed"` — always branch on `data.status`.
9. **Reconciliation poller is mandatory:** Lenco explicitly warns webhooks can be missed → poll non-terminal collections/transfers every ~15–30 min until terminal; daily ledger-vs-`GET /transactions` reconciliation.

## Auth & environments

- Base: `https://api.lenco.co/access/v2`. **Sandbox REST base not stated in either PDF** — get from Lenco support (widget sandbox exists at `pay.sandbox.lenco.co`). (F9b.)
- Server auth: `Authorization: Bearer <API_TOKEN>` (token issued/rotated via support@lenco.co; treat as password; env `LENCO_API_TOKEN`). Widget uses separate **public key** (env `NEXT_PUBLIC_LENCO_PUBLIC_KEY`).
- Envelope: `{"status": bool, "message": str, "data": obj|arr|null, "meta"?: {total, perPage(100), currentPage, pageCount}}`. `message` is informational only.
- Timestamps ISO-8601 UTC; countries lowercase (`zm`); currency `ZMW`.

## Collections

### POST `/collections/mobile-money`
Req: `amount` (number), `reference`, `phone` ("0977433571"), `operator` (`airtel|mtn` for zm), opt `country` (`zm`), `bearer` (`merchant`|`customer`, default merchant).
Resp `data`: `{id, initiatedAt, completedAt:null, amount:"13.00", fee:null, bearer, currency:"ZMW", reference, lencoReference, type:"mobile-money", status:"pay-offline", source:"api", reasonForFailure:null, settlementStatus:null, settlement:null, mobileMoneyDetails:{country,phone,operator,accountName,operatorTransactionId:null}, bankAccountDetails:null, cardDetails:null}`.
Lifecycle: `pay-offline` (customer authorizes on phone) → `successful` | `failed` (+`reasonForFailure`); on success `fee`, `operatorTransactionId`, later `settlementStatus: pending→settled` + `settlement{amountSettled, type: instant|next-day, accountId}`. Fee example: 0.25 on 10.00 (2.5%) netted from settlement when bearer=merchant.

### Card (hosted widget only)
`LencoPay.getPaid({key, email, reference, amount, currency:"ZMW", label?, bearer?, channels:["card","mobile-money"], customer:{firstName,lastName,phone}, billing:{...}, onSuccess(res: {reference}), onClose, onConfirmationPending})`. Amount = decimal major units. Server MUST verify `/collections/status/:reference` before fulfilment. Direct `POST /collections/card` (JWE `encryptedPayload`, RSA-OAEP-256 + A256GCM via rotating JWK from get-encryption-key; 3DS: `status:"3ds-auth-required"` + `meta.authorization.redirect`) is documented but OFF-LIMITS (PCI).

### Status/query
- `GET /collections/status/:reference` (poll by our reference — primary verify)
- `GET /collections/:id` (uuid), `GET /collections?page&from&to&status&type&country`
- Status enum: `pending|successful|failed|pay-offline` (+`3ds-auth-required` card, `otp-required` seen in settlement-embedded objects).

## Payouts / transfers

Common req: `accountId` (our 36-char debit account uuid), `amount` (number), `reference`; opt `narration`, `transferRecipientId`. Status: `pending|successful|failed` (HTTP 200 regardless). Resp incl. `fee` (e.g. "8.50" on a "20.00" bank transfer — get the real fee table from Lenco, F9c), `creditAccount{type, accountName, accountNumber|bank{id,name,country}|phone|operator|walletNumber|tillNumber}`, `reasonForFailure`, `lencoReference`.

- `POST /transfers/mobile-money` — `phone` + `operator` (**`airtel|mtn|zamtel`** for zm) or `transferRecipientId`; opt `country`.
- `POST /transfers/bank-account` — `accountNumber` + `bankId` (from `GET /banks?country=zm`) or `transferRecipientId`.
- `POST /transfers/lenco-money` (`walletNumber`) · `POST /transfers/lenco-merchant` (`tillNumber`) · `POST /transfers/account` (`creditAccountId`, internal move).
- Status: `GET /transfers/status/:reference` · `GET /transfers/:id` · `GET /transfers?…`.
- Bulk transfers exist (errorCodes 07/08 reference a `transfers` array) but endpoint undocumented — ask Lenco (F9d); otherwise loop with per-item references.

### Pre-payout verification (use before first payout to a vendor)
`POST /resolve/mobile-money` (`phone`, `operator: airtel|mtn|zamtel`) → `accountName` (⇒ KYC name-match check T1); `POST /resolve/bank-account` (`accountNumber`,`bankId`); `/resolve/lenco-money|lenco-merchant`. Beneficiaries: `POST /transfer-recipients/{mobile-money|bank-account|lenco-money|lenco-merchant}`, `GET /transfer-recipients[/:id]`.

## Accounts / settlement / ledger

- `GET /accounts` → `{id, details{type:"lenco-merchant",accountName,tillNumber}, status, currency:"ZMW", availableBalance, ledgerBalance}` · `GET /accounts/:id` · `GET /accounts/:id/balance`.
- `GET /settlements?status&type&collectionType&from&to` + `GET /settlements/:id` — settlement objects `{id, amountSettled, createdAt, settledAt, status: pending|settled, type: instant|next-day, accountId, collection{...}}`.
- `GET /transactions?type=credit|debit&from&to&search&accountId` + `/:id` — running-balance ledger `{id, amount, currency, narration ("Transfer / 240730006" — contains lencoReference), type, datetime, accountId, balance}`. **This is the reconciliation source.**

## Webhooks

- Registration: manual — email support@lenco.co with the URL (no dashboard/API flow). One URL. (F9e: register staging + prod URLs.)
- Signature: header **`X-Lenco-Signature`** = HMAC-SHA512 hex of raw body, key = **SHA256-hex of the API token**. ⚠ rotating the API token silently rotates the webhook key.
- Events: `collection.successful`, `collection.failed`, `collection.settled`, `transfer.successful`, `transfer.failed`, `transaction.credit`, `transaction.debit`. Payload `{"event": name, "data": <full collection|transfer|transaction object>}`.
- Delivery: must ack 200/201/202 **fast** (process async); else retried every 30 min for 24h ⇒ duplicates possible ⇒ idempotent handlers keyed on (`event`,`data.id`).

## Errors

Envelope with `status:false` + optional `errorCode`: 01 validation · 02 insufficient funds · 03 transfer limit exceeded (values unknown) · 04 invalid/duplicate reference · 05 invalid recipient · 06 debit-account restriction · 07/08 bulk reference/array errors · 09 auth denied · 10 general · 11 not found · 12 invalid mobile number · 13 access denied. HTTP: 400/401/404/5xx; no rate limits documented (assume + client-side throttle with backoff).

## Sandbox test data (deterministic)

MoMo zm: MTN `0961111111` ✓ · `0962222222` insufficient funds · `0963333333` limit exceeded · `0964444444`/`0965555555` unauthorized · `0966666666` timeout; Airtel `0971111111` ✓ · `0972222222` wrong PIN · `0973333333` invalid amount · `0974444444` payment invalid · `0975555555` insufficient funds · `0976666666`/`0978888888` failed · `0977777777` timeout. Cards: Visa `4622 9431 2701 3705` cvv 838 · Visa `4622 9431 2701 3747` cvv 370 · MC `5555 5555 5555 4444` any cvv, any future expiry.

## Open items for Lenco support (founder F9)

a) Zamtel **collections** — supported anywhere (widget?)? b) sandbox REST base URL + sandbox API token; c) fee schedule (MoMo collection %, MoMo payout fee, card %, bank transfer fee) + min/max limits; d) bulk transfer endpoint spec; e) webhook URL registration (staging+prod) + IP allowlist if any; f) settlement type default for our account (instant vs next-day) per rail.
