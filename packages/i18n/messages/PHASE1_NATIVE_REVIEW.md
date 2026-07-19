# Phase-1 bem/nya — native-speaker review list

Best-effort vernacular overlays for CUST-I18N-01. CI completeness requires every critical key; the strings below need a native Bemba / Nyanja review before production.

## Escrow triad (pay → hold → release)

- `catalog.home.hero.escrowLine`
- `catalog.home.hero.escrowStep1` / `escrowStep2` / `escrowStep3`
- `catalog.home.trust.escrow`
- `catalog.pdp.trust.escrow`
- `checkout.checkout.review.escrowTitle`
- `checkout.checkout.review.escrowStep1` / `escrowStep2` / `escrowStep3`
- `orders.timeline.paymentHeld`
- `orders.timeline.completed`
- `orders.escrow.held` / `released` / `refunded` / `cod`

## COD cap

- `checkout.checkout.payment.cod`
- `checkout.checkout.payment.codIneligible`
- `checkout.checkout.payment.codRejected`
- `checkout.checkout.review.methodCod`
- `checkout.checkout.pending.codTitle` / `codBody`
- `orders.list.paymentCod`
- `orders.timeline.paymentCod`
- `orders.escrow.cod`

## Returns / refunds labels

- `catalog.home.trust.returns`
- `catalog.pdp.trust.returns`
- `catalog.returnableBadge.label`
- `orders.status.refunded`
- `orders.timeline.refunded`
- `orders.escrow.refunded`

## Payment disabled

- `checkout.checkout.payment.paymentsDisabled`
- `checkout.checkout.card.widgetUnavailable`

## USSD / PIN copy

- `checkout.checkout.payment.payerHelp`
- `checkout.checkout.ussd.title` / `subtitle` / `mtnHelp` / `airtelHelp` / `genericHelp` / `waiting` / `doNotClose`
- `checkout.checkout.pending.timeoutBody` / `retry` / `retrying`

## Consent / Terms labels

- `checkout.checkout.review.consentLabel`
- `checkout.checkout.review.consentRequired`

## Refund / confirmation timeline wording

- `orders.timeline.*` (full set)
- `checkout.checkout.pending.confirmingBody`
- `checkout.checkout.card.successBody` / `heldBody` / `pendingBody`

## Low-confidence / loanword-heavy (still CI-pass vernacular)

- `catalog.home.sellCta.*` (invite-only seller beta)
- `catalog.home.hero.placeholder.*` (merchandising slots)
- `checkout.checkout.payment.cardExplainer` / `checkout.checkout.card.secureNote` (PCI / Lenco)
- `account.nav.business` / `preferences` / `privacy`
- `search.results.degraded` (semantic search)
- `common.theme.*` / `common.install.*`
