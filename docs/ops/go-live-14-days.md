# Go-live in 14 days: real payments and payouts (23 Nov to 7 Dec 2026)

**Owner:** King (business, money and config switches) · Claude (coordinator, database, security, production switch-on) · Cursor (app code)
**Rule:** nothing that moves real money is switched on without King's explicit yes in chat.

## Where we are (checked 23 Nov)

- **Payment code:** built and merged. It covers:
  - MoMo push for MTN and Airtel, and the card widget;
  - the signed, deduplicated webhook `POST /webhooks/lenco`;
  - the escrow ledger, release, refunds-as-payouts and vendor payouts;
  - daily reconciliation.
- **Production database:** the ledger accounts exist (platform_cash, escrow, fees, commission_revenue, delivery_revenue, cod_receivable, vendor_payable for each active vendor). The COD cap is K500, and release is 48 h after delivery.
- **Production has never processed a payment:** 0 payments, 0 orders, 0 payouts.
- **Active n8n money jobs:** payment reconciliation (webhook drain every 1 min, poll, sweeper, daily report), order auto-jobs, escrow release tick, ticket issue and release, and unpaid-order cancel.

## Blockers

| # | Blocker | Owner | Size |
|---|---|---|---|
| B1 | Production API has `LENCO_ENV=sandbox`, and `PAYMENTS_ENABLED`, `PAYMENTS_ALLOW_PRODUCTION` and `PAYOUTS_ENABLED` are unset. The live key must be confirmed as the one in `LENCO_API_TOKEN`. | King (token), Claude (flags, with King's yes) | S |
| B2 | The Lenco settlement account for the Convergeo key is "Zedcv". It must be "Convergeo Online Services". `LENCO_ACCOUNT_ID` must be that account's UUID. | King | S |
| B3 | Webhook URL in Lenco: `https://api.vergeo5.com/webhooks/lenco` (Lenco → APIs → Convergeo → Webhook) | King | S |
| B4 | No vendor has a payout number. 0 of 3 active vendors have `payout_msisdn` and `payout_rail` set, and KYC name-match is required before any payout. | King (onboarding), Cursor (UI polish if needed) | M |
| B5 | The payout n8n workflow "[PROD] Vendor Payout Batch and Retry" (PvAyQTFrXfylLCfX) is inactive. Refunds also need it. | King publishes after the first manual payout is proven | S |
| B6 | Money workflows are not bound to the error alert workflow, so failures would go unnoticed. | Claude | S |
| B7 | The card widget needs `NEXT_PUBLIC_LENCO_PUBLIC_KEY` (live public key) on the customer app | King | S |
| B8 | The Vercel customer and vendor apps are paused (Hobby limit). Move to the Pro trial team, then to Pro. | King | S |
| B9 | Lenco 2FA (Token App) is not set up | King | S |

## Day plan

| Day | Date | Work | Who |
|---|---|---|---|
| 1 | Mon 23 | Vercel Pro trial: move the 3 projects. Lenco: settlement account, webhook URL, 2FA. | King |
| 2 | Tue 24 | Claude binds error alerts (B6), merges #860 and #861, and tops up any missing ledger accounts. Cursor: payout-method form check (vendor app), merging Web Push and catalogue control. | Claude, Cursor |
| 3 | Wed 25 | **Switch-on (King's yes):** set `LENCO_ENV=production`, `PAYMENTS_ENABLED=true`, `PAYMENTS_ALLOW_PRODUCTION=true`, and redeploy the API. Payouts stay **off**. | King + Claude |
| 3 | Wed 25 | **Live test 1:** King buys a K5 item from his own test vendor with MTN or Airtel MoMo, then a K5 item by card. Check the payment row, the ledger `escrow_hold`, the Lenco dashboard and the daily reconciliation. | King + Claude |
| 4 | Thu 26 | **Live test 2:** mark delivered, then confirm received → escrow release → `vendor_payable`. Refund one order (lane 1). | King + Claude |
| 5 | Fri 27 | **Payout switch-on (King's yes):** `PAYOUTS_ENABLED=true`. Run one manual payout to King's own test vendor number (resolve and name-match). After it succeeds, publish the payout workflow (B5) set to daily. | King + Claude |
| 6–9 | 28 Nov–1 Dec | Onboard 3–5 real vendors (KYC, payout number, 10–20 products each). Fix bugs from the tests. Cursor works on app polish from the UI audit. | King, Cursor |
| 10–13 | 2–5 Dec | Soft launch to friends and family. Read the daily reconciliation report every morning. Fix issues. | All |
| 14 | 6–7 Dec | Decide on Vercel Pro (card on the trial team) and go public. | King |

## Out of scope for go-live

These stay off:
- Zamtel collections;
- pay-at-door;
- event escrow and refund ticks, unless events launch;
- service RFQ deposits, unless services launch.

## Open business items (King)

- Ask Lenco in writing to confirm:
  - marketplace use (collecting for vendors and paying them out);
  - whether the transfers API needs an IP allowlist (give them the Hetzner server IP);
  - the transfer limits;
  - the MoMo and card fee schedule.
- Choose who pays the Lenco collection fee (customer or Convergeo). The daily reconciliation must book it.
- Legal sign-off on the escrow and settlement wording (F4).
