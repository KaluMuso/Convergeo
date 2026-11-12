# Phase-1 bem/nya — native-speaker review list

Best-effort vernacular overlays for CUST-I18N-01. CI completeness requires every critical key; the strings below need a native Bemba / Nyanja review before production.

**Process owner:** CCP-02 (`docs/production-readiness/2026-07-20/code-completion-programme.md`). SEO flip is a **separate PR** after sign-off — do not add `bem`/`nya` to `SEO_INDEXABLE_LOCALES` until all criteria below are met.

## Native-speaker sign-off (authoritative)

Record each review session in the table. One row per reviewer × locale batch (or one row covering both locales if the same reviewer signs both).

| Reviewer (name + role) | Date (YYYY-MM-DD) | Locale(s) | Namespace(s) covered | Checklist sections signed | Notes |
| ---------------------- | ----------------- | --------- | -------------------- | ------------------------- | ----- |
| _pending_              | —                 | —         | —                    | —                         | —     |

**Namespaces in scope for Phase-1 money/trust copy:** `catalog`, `checkout`, `orders`, `account`, `search`, `common`, `notifications`, `marketing` (present today). **`legal`** — sign off only when bem/nya `legal.json` exists (CCP-03d); until then, criterion 3 blocks SEO flip for vernacular legal pages.

**M18-P05 vendor intake (2026-07-27):** `vendor.intake.*` was added to bem/nya for key parity (CCP-03f). It is **almost entirely EN passthrough** — only the screen title was localised, because the copy is operational instructions to a vendor and a wrong guess there costs them a listing. Treat the whole `vendor.intake` subtree as untranslated until a native reviewer signs it off. The surface is behind `waha_vendor_intake` (default off), so nothing ships to a vendor before then.

**M17-P06 vendor clips (2026-07-27):** `vendor.clips.*` was added to bem/nya for key parity (CCP-03f). It is **almost entirely EN passthrough** — only the screen title and the "new clip" action were localised. The rest is upload limits, data-cost warnings and moderation-status copy, where a wrong guess either costs a vendor their bundle or tells them a clip is live when it is not. Treat the whole `vendor.clips` subtree as untranslated until a native reviewer signs it off. The surface is behind the `clips` flag (default off), so nothing ships to a vendor before then.

**Listing variants + PDP zoom (2026-11-07):** `catalog.pdp.variants` and `catalog.pdp.lightbox` are Phase-1 critical, so bem/nya carry **draft** translations (loanword style matching the existing PDP copy: cart, picture, screen) — they decide what a buyer picks and pays for, so a native reviewer must sign them off before bem/nya are indexed. `checkout.variant`, `orders.detail.variantOption|variantSeparator`, `vendor.listings.variants` and `vendor.orders.items.variantOption|variantSeparator|sku` are **EN passthrough** for key parity; treat those subtrees as untranslated until signed off.

**CCP-03e verticals (2026-07-20):** `services`, `events`, `directory`, `supplies` exist for bem/nya with key parity to EN (best-effort vernacular; **pending native-speaker review** — not a SEO-flip blocker by themselves, but do not claim native-complete).

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

## Analytics opt-out (1A-09, 2026-11-12)

Draft bem/nya for the `/account/privacy` Analytics switch. These govern a privacy choice, so a native reviewer must confirm that "off" really reads as "we keep only anonymous counts, nothing is linked to you". "Analytics" and "browser" are kept as loanwords.

- `account.privacy.analytics.title` (bem, nya): "Analytics"
- `account.privacy.analytics.description`
  - bem: "Tumwafwe ukusuma Convergeo pa kutwebelela ukumona ifyo mubomfya, nga amapeji mwingila."
  - nya: "Tithandizeni kukonza Convergeo potilola momwe mumagwiritsira ntchito, mwachitsanzo masamba omwe mumawerenga."
- `account.privacy.analytics.toggleLabel`
  - bem: "Ukwabana ifyo mubomfya"
  - nya: "Gawani zomwe mumagwiritsa ntchito"
- `account.privacy.analytics.on`
  - bem: "Kuli: tulemona amapeji mwingila, kabili panuma ya kwingila tulemulumanya ku akaunti yenu. Ifilumanya fisulwa panuma ya matazi 30."
  - nya: "Yayatsidwa: titha kuona masamba omwe mumapitako ndi kuwalumikiza ku akaunti yanu mukalowa. Maulalo amachotsedwa pakatha masiku 30."
- `account.privacy.analytics.off`
  - bem: "Cilekwa: tusunga fye ubwingi bwa bantu (anonymous counts), nga bangaye bamona peji. Takuli ifyo mwacita ifisungwa, kabili takuli cilumenwe kuli imwe."
  - nya: "Yazimitsidwa: timasunga chiwerengero chopanda dzina chokha, monga kuti anthu angati aona tsamba. Palibe mbiri ya zomwe mwachita, ndipo palibe cholumikizidwa ndi inu."
- `account.privacy.analytics.gpc` (shown when the browser sends Global Privacy Control; switch is off and disabled)
  - bem: "Browser yenu iletuma Global Privacy Control, ico analytics ilekwa. Tulesunga ico browser yenu ilanda."
  - nya: "Browser yanu ikutumiza Global Privacy Control, choncho analytics yazimitsidwa. Timalemekeza zomwe browser yanu yasankha."
