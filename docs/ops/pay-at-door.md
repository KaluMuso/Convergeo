# Pay at the door (mobile money) and instant payout with a reserve

Status: **pay at the door built, behind `pay_at_door` (default OFF).** Instant payout with a reserve is **design only** (section 2); nothing for it is built.

Source decision: growth blueprint §4 (option C, founder-approved 13 Nov). Contracts: `docs/ops/lenco/lenco-api-distilled.md`.

---

## 1. Pay at the door (built)

### What happens

1. Rider picks up a cash-on-delivery parcel (dispatch `picked_up`, order `shipped`). With the flag on, the customer's handover code is **withheld** (order page, shipped notification and ops verification all refuse it).
2. Rider reaches the door. Ops records it for the rider on the dispatch board ("Rider arrived"), or presses "Request payment", which implies arrival.
3. The customer taps **Pay now on your phone** on the order page (or ops presses "Request payment"). The API sends a Lenco mobile-money collection (USSD push) for the **server-computed order total** (dispatch COD snapshot = items + delivery fee) to the address/profile phone, or to another MTN/Airtel number the customer types.
4. The customer approves with their PIN.
5. A **verified** observation decides: the signed Lenco webhook (`webhook_events` → `process_webhook_event` → `door.apply_webhook`) or our own `GET /collections/status/:reference` (customer/ops "Check status", or the reconciliation tick). The phone screen and the initiation response are never trusted.
6. Exact amount + payable order ⇒ the door session is settled (write-once), the ledger books the collection and the handover code is released. The rider takes the code, ops verifies it, the order is delivered and the existing COD release runs at once.

### Money

| Moment                      | Template (key)                                                                                                                            | Legs                                                                                  |
| --------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------- |
| Lenco confirms exact amount | `door_payment_collected` (`cod-collect-<order>`, shared with cash COD, so cash and mobile money can never both settle one order)          | +platform_cash / −cod_receivable (receivable opened first: +cod_receivable / −escrow) |
| Handover verified           | existing COD drain via `confirm_cod_collection`: `commission_capture`, `delivery_fee_capture` (→ `delivery_revenue`), `release_to_vendor` | escrow nets to 0                                                                      |
| Money that cannot settle    | `door_payment_exception` (`door-exception-<attempt>`)                                                                                     | +platform_cash / −door_payment_suspense                                               |

### Failure handling

| Case                                                       | Behaviour                                                                                                                                                                                                                                                                                                                           |
| ---------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Wrong number / Lenco refuses (e.g. error 12)               | Attempt `failed` with the provider code; retry with another number.                                                                                                                                                                                                                                                                 |
| Prompt not answered                                        | After `pay_at_door_attempt_ttl_seconds` (120) the next status check marks it `expired` (`timeout`); retry or cash. A late approval of an expired prompt still settles if nothing else has.                                                                                                                                          |
| Too many prompts                                           | `pay_at_door_max_attempts` (3) per delivery, then `door_payment_attempts_exhausted`: cash fallback or return.                                                                                                                                                                                                                       |
| Two prompts at once                                        | Refused (`door_payment_in_flight`); DB allows one in-flight attempt per order. Cash is also refused while a prompt is live.                                                                                                                                                                                                         |
| Duplicate / out-of-order webhooks                          | `webhook_events` dedupe + attempt CAS + write-once settlement + keyed ledger posts + one exception per attempt. A late `failed` never undoes a success.                                                                                                                                                                             |
| Partial or wrong amount, non-ZMW                           | Never settles. Exception `amount_mismatch` / `currency_mismatch`; received ngwee booked to suspense; code stays withheld; retry or cash.                                                                                                                                                                                            |
| Paid after cancel / already settled (cash or earlier push) | Exception `order_not_payable` / `already_settled`; suspense booking; **order never revived**.                                                                                                                                                                                                                                       |
| Network loss at the door                                   | Initiation transport errors leave the attempt `initiated` (reference is durable). Customer/ops "Check status" re-queries Lenco; `/internal/reconciliation/door-poll-tick` sweeps open attempts.                                                                                                                                     |
| Zamtel                                                     | Refused before any push (`door_payment_operator_unsupported`); use another MTN/Airtel number or cash.                                                                                                                                                                                                                               |
| Cash fallback                                              | Ops "Take cash instead" (`cod_cap_ngwee`, K500) settles the session as `cash` and releases the code. The cash is booked later by the existing ops COD confirmation after remittance. The per-rider cash limit (`courier_cash_cap_ngwee`) is enforced by the logistics custody work on `feat/logistics-phase1`, not duplicated here. |

### Exception queue

`GET /admin/dispatch/door-payment/exceptions` lists open rows. Ops refunds by payout (Lenco has no refunds API) to the payer number, then `POST /admin/dispatch/door-payment/exceptions/{id}/resolve` with a note. The suspense balance should equal the sum of open exceptions; a later PR should post the refund payout against `door_payment_suspense`.

### Endpoints

Customer (order owner only, 404 otherwise): `GET /account/orders/{id}/door-payment`, `POST …/door-payment` (`{phone?}`), `POST …/door-payment/poll`.
Admin (acts for the rider): `GET|POST /admin/dispatch/requests/{dispatch_id}/door-payment[/arrived|/request|/poll|/cash]`; board field `door_payment_state`.
Cron: `POST /internal/reconciliation/door-poll-tick` (runs whatever the flag says, so requested money still reaches an outcome).

### Rollout

1. Lenco sandbox (F9b) end to end with the sandbox numbers (`0961111111` success, `0966666666` timeout, `0972222222` wrong PIN).
2. Schedule the door-poll tick every 2 minutes in n8n.
3. Turn on `courier_dispatch` then `pay_at_door` for the pilot; watch `door_payment_exception` alerts and the prompt success rate.
4. Switching `pay_at_door` off returns to the cash behaviour immediately; already-settled sessions keep their code released.

Known limits: checkout wording and the higher mobile-money cap (blueprint phase B) are not built; pickup orders are not covered; no rider login yet (ops acts for the rider until the rider link lands).

---

## 2. Instant payout with a reserve (design only, not built)

A paid vendor feature (blueprint §4.4): release to the vendor when the handover code is confirmed and pay most of it out at once, keeping a rolling reserve for disputes. Every payment still passes through Convergeo; buyer protection is unchanged.

### Today

- Prepaid release: release job after `release_after_delivered_hours` (48 h, D5) once delivered; payouts require `MIN_ESCROW_HOLD_HOURS` (`services/payouts/hold.py`).
- COD (cash or door): released when collection is confirmed (door: at handover).
- Payouts: `services/payouts/*` (eligibility from released `vendor_payable`, velocity caps per KYC tier, batching, `pay-*` references).

### Proposal

| Piece              | Design                                                                                                                                                                                                                                                                                               |
| ------------------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Entitlement        | `vendor_features(vendor_id, feature='instant_payout', reserve_bps, reserve_days, active_from, active_to, plan_ref)`. Granted by admin after billing; gated by KYC tier ≥ 2, ≥ 50 completed orders, dispute rate < 2 % (configurable). Flag `instant_payout` default off.                             |
| Release timing     | For entitled vendors, release at handover verification (prepaid and door) instead of after the 48 h window. Disputes open within the window still work, now against the reserve.                                                                                                                     |
| Reserve            | At release, split the vendor net: `release_to_vendor` for `net − reserve` and a new `reserve_hold` template (+escrow / −vendor_reserve, a new vendor account kind) for `reserve = floor(net × reserve_bps / 10 000)` (e.g. 10 % = 1 000 bps). Integer ngwee; the remainder goes to the payable part. |
| Reserve release    | Daily sweep: reserve rows older than `reserve_days` (e.g. 7) with no open dispute/refund post `reserve_release` (+vendor_reserve / −vendor_payable). Keys `reserve-<order>` / `reserve-release-<order>`.                                                                                             |
| Disputes / refunds | Refund lanes drain `vendor_reserve` first, then claw back `vendor_payable` (existing `clawback`), then flag a negative balance (payouts blocked until it clears).                                                                                                                                    |
| Payout             | `MIN_ESCROW_HOLD_HOURS` is skipped for entitled vendors, only for amounts released through the instant path; velocity caps still apply. Payout fee (Lenco transfer fee, F9c) is passed through or included in the plan price.                                                                        |
| Pricing            | Monthly plan (e.g. K150) or a per-payout fee (e.g. 1 %); Convergeo's float cost is roughly 2 days of the vendor's GMV.                                                                                                                                                                               |
| Vendor UI          | Per order: paid → held → released → paid out (with reserve amount and its release date); a reserve balance card.                                                                                                                                                                                     |
| Risk controls      | Automatic downgrade (entitlement ends) on dispute rate breach or a negative balance; reserve percentage can rise per vendor; admin kill switch per vendor and global flag.                                                                                                                           |
| Audit              | Entitlement changes via `audit_log`; every money move via ledger templates (never raw balance writes).                                                                                                                                                                                               |

### Open questions for the founder

1. Plan price vs. per-payout fee; who bears the Lenco transfer fee.
2. Reserve defaults (10 % for 7 days suggested) and whether they vary by category.
3. Whether instant release also applies to pickup orders (vendor already holds goods and customer).
4. Legal (L3): wording that the reserve is held by Convergeo and when it is paid out.

Rough effort: M (one migration: account kind + entitlement table + 2 templates; release/payout branches; daily sweep; vendor dashboard lines).
