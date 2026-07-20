# Phase-1 bem/nya — native-speaker review list

Best-effort vernacular overlays for CUST-I18N-01. CI completeness requires every critical key; the strings below need a native Bemba / Nyanja review before production.

**Process owner:** CCP-02 (`docs/production-readiness/2026-07-20/code-completion-programme.md`). SEO flip is a **separate PR** after sign-off — do not add `bem`/`nya` to `SEO_INDEXABLE_LOCALES` until all criteria below are met.

## Native-speaker sign-off (authoritative)

Record each review session in the table. One row per reviewer × locale batch (or one row covering both locales if the same reviewer signs both).

| Reviewer (name + role) | Date (YYYY-MM-DD) | Locale(s) | Namespace(s) covered | Checklist sections signed | Notes |
| ---------------------- | ----------------- | --------- | -------------------- | ------------------------- | ----- |
| _pending_              | —                 | —         | —                    | —                         | —     |

**Namespaces in scope for Phase-1 money/trust copy:** `catalog`, `checkout`, `orders`, `account`, `search`, `common`, `notifications`, `marketing` (present today). **`legal`** — sign off only when bem/nya `legal.json` exists (CCP-03d); until then, criterion 3 blocks SEO flip for vernacular legal pages.

## Noindex removal criteria (authoritative)

All four must be true before opening the SEO-flip PR (`cursor/ccp-02-seo-flip-bem-nya-da3e`):

1. **Phase-1 critical prefixes green in CI** — `phase1-critical` tests pass (`packages/i18n/src/phase1-critical.ts` and related test suite).
2. **Checklist signed** — escrow, COD, USSD, consent, refunds, and any vernacular **legal** pages that exist are signed off in the table above for each locale being published.
3. **No unchecked machine-only strings** — no legal/checkout strings marked “pending human review” (or equivalent) remain for the locales being published.
4. **Code flip** — add `"bem"` and/or `"nya"` to `SEO_INDEXABLE_LOCALES` in `packages/i18n/src/seo-publication.ts`; update `seo-publication.test.ts` and sitemap/json-ld tests to expect indexable locales.

Until then, **bem** and **nya** stay routable but are **not** SEO-published (`noindex,follow`; omitted from hreflang + sitemap).

## SEO publication (after native sign-off)

**Single flip after approval:** add `"bem"` and/or `"nya"` to `SEO_INDEXABLE_LOCALES` in `packages/i18n/src/seo-publication.ts` (step 4 above only).

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
- `search.pagination.moreLoaded` / `endOfResults` / `loadError` / `retry` (progressive load)
- `common.theme.*` / `common.install.*`
