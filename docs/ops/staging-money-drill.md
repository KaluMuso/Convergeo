# Staging money drill (post place-order wiring)

> Code side of conversion is wired: checkout creates an address for delivery,
> `POST /orders`, then MoMo `/payments/retry` / card session / COD pending.
> This drill proves the **live staging** rails before any real-money flip.

## Preconditions (founder / ops)

- [ ] Staging API + customer app healthy (`/healthz`, `/en/health`)
- [ ] Migration `0066_user_wishlist_recently_viewed.sql` applied on staging
- [ ] Lenco **sandbox** credentials only (`LENCO_SANDBOX` / non-prod keys)
- [ ] Seed buyer with phone OTP path; cart with in-stock listing
- [ ] `public_launch` remains **false**

## Drill script

1. Sign in → add listing → open cart → confirm `/cart/revalidate` notices (or none).
2. Checkout fulfilment: landmark for delivery → continue (address created).
3. Payment: MoMo MTN sandbox push → land on pending → webhook settles hold.
4. Repeat for Airtel (if sandbox rail available) and COD ≤K500 path.
5. Card: hosted widget session opens; abandon without charging prod.
6. Confirm ledger Σ postings = 0 for the sandbox charge; no prod reference charset.

## Evidence to attach

- Staging order id + checkout_group_id
- Lenco sandbox payment reference (`pay-*` / `ord-*`)
- Screenshot or log of pending → paid transition
- Note any 422 on missing `address_id` (regression)

## Explicit non-goals

- Do **not** flip `public_launch`
- Do **not** use production Lenco keys
- WhatsApp delivery of receipts is optional for this drill
