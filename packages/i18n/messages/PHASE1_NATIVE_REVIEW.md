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

**Courier dispatch v1 (2026-11-09):** `vendor.orders.courier.*` was added to bem/nya as **EN passthrough** for key parity (CCP-03f). Treat the subtree as untranslated until a native reviewer signs it off. The surface is behind the `courier_dispatch` flag (default off).

**Listing variants + PDP zoom (2026-11-07):** `catalog.pdp.variants` and `catalog.pdp.lightbox` are Phase-1 critical, so bem/nya carry **draft** translations (loanword style matching the existing PDP copy: cart, picture, screen) — they decide what a buyer picks and pays for, so a native reviewer must sign them off before bem/nya are indexed. `checkout.variant`, `orders.detail.variantOption|variantSeparator`, `vendor.listings.variants` and `vendor.orders.items.variantOption|variantSeparator|sku` are **EN passthrough** for key parity; treat those subtrees as untranslated until signed off.

**W8 bundles & offers (2026-11-15):** `vendor.offers.*`, `vendor.shell.nav.offers`, `catalog.offers.*` and `checkout.cart.{offerSavings,offerSaving,offerGift,offerGiftWorth}` were added to bem/nya as **EN passthrough prefixed with `⚠ `** for key parity. Treat these subtrees as untranslated until a native reviewer signs them off. The surface is behind the `bundles` flag (default off).

**CCP-03e verticals (2026-07-20):** `services`, `events`, `directory` exist for bem/nya with key parity to EN (best-effort vernacular; **pending native-speaker review** — not a SEO-flip blocker by themselves, but do not claim native-complete).

**Catalog selection and canonical details (2026-10-01):** `events.filters.subcategoryLabel` and `vendor.listings.newCanonical.details.{about,heading,help,name,value,add,remove,invalid}` in both bem/nya are **English fallback values**, copied from EN for key parity. These 18 entries remain untranslated pending native-speaker review; their presence is not translation approval.

**Product-detail recommendations and image viewer (2026-10-04):** `catalog.pdp.related.{vendorHeading,categoryHeading,loading,unavailable}` and `catalog.pdp.gallery.{zoomOpen,zoomClose,zoomTitle,zoomIn,zoomOut}` now have AI-authored provisional Bemba and Nyanja wording for key and ICU completeness. A second AI reviewer checked source-label alignment and confirmed that both `vendorHeading` values retain `{vendor}` while flagging uncertain wording; this is **not** fluent or native-speaker approval. In particular, the image-viewer controls and Bemba zoom wording remain uncertain. Keep these 18 values pending recorded native-speaker review before production; do not mark the sign-off table complete or change SEO publication based on CI passing.

**Pay at the door (2026-11-13):** `orders.doorPay.*` (19 values incl. `errors.*`) has AI-authored **draft** Bemba and Nyanja wording, loanword style ("rider", "mobile money", "cash", "PIN"). This is money/USSD copy: it tells a buyer when to approve a mobile-money prompt and when to hand over their code, so a wrong word can cost money. Check especially `pending`, `paid`, `cash`, `noAttemptsLeft` and the plural forms of `attemptsLeft`. The surface is behind `pay_at_door` (default off). Pending recorded native-speaker review; not a sign-off.

**OG image tagline (2026-11-07):** `common.app.tagline` was added (EN/FR/ZH translated; bem/nya are AI-authored provisional wording — "Isoko lya mu Zambia — ukushita na escrow" / "Msika wa ku Zambia — kugula ndi escrow"). It renders in the social-share (Open Graph) image for each locale. Pending recorded native-speaker review; not a sign-off.

**Coupons, gift orders and birthday greetings (2026-11-13):** new keys under `checkout.checkout.coupon`, `checkout.checkout.gift`, `checkout.checkout.review.discount`, `orders.detail.discount`, `orders.gift`, `account.birthday`, `notifications.inApp.customer.birthday_greeting`, `vendor.coupons` and `vendor.shell.nav.coupons`, plus `notifications.whatsapp.{gift_recipient_notice,gift_ready_pickup,birthday_greeting}` (EN passthrough in bem/nya; the Meta templates themselves need approval per locale). In bem/nya only the short decision-critical labels are **AI-authored drafts** (section toggles, field names, "Apply"/"Remove", gift/receipt titles, birthday day/month/18+ line, month names, the in-app birthday line); every other value in those subtrees is **EN passthrough** for key parity. The 18+ confirmation, the birthday marketing-consent line and the gift recipient-consent line are consent copy and must be signed off by a native reviewer before bem/nya ship them. All three surfaces are behind `coupons` / `gift_orders` / `birthday_greetings` (default off).

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

**Storefront redesign toasts (2026-11-08):** `common.toast.*` (21 keys: cart/wishlist/copy/auth/save/upload/moderation confirmations) , `common.share.label` and `common.fab.*` (floating Ask Vergeo + footer toggle, 13 keys) and `directory.profile.{follow,following,newSeller,newSellerJoined,tabAbout,tabReviews}` , `catalog.backInStock.*` and `catalog.plp.sort.{best,verified,bundles,cheapestChip}` , `vendor.profile.brand.*` and `catalog.{deals,qa,saveSearch}.*` were added to bem/nya as **English passthrough** for key parity. These are short transient confirmations outside the Phase-1 critical prefixes; a wrong vernacular guess in an error toast ("couldn't add to cart") misleads more than English does. Treat the subtree as untranslated pending native-speaker review.

**PDP recommendation rails (2026-11-09):** `catalog.pdp.related.{storeHeading,similarHeading}` have AI-authored provisional Bemba/Nyanja wording (the `pdp` prefix is Phase-1 critical, so EN passthrough fails CI). Pending native-speaker review.
**Follow feed (2026-11-09):** `account.nav.following` has AI-authored provisional Bemba/Nyanja wording (critical `nav` prefix); `account.following.*` is EN passthrough. Pending native review.
**Delivery estimates (2026-11-09):** `catalog.delivery.*` (outside critical prefixes) is EN passthrough in bem/nya, pending native review.
**Notification center (2026-11-13):** `notifications.center.*` (bell, badge label, list/page chrome, push opt-in, errors) and `notifications.inApp.{fallback,customer.*,vendor.*,admin.*}` (one line per in-app event: order placed/confirmed/rejected/packed/shipped/ready-for-pickup/delivered, quote received, ticket issued, KYC submitted/approved/rejected, RFQ received, job matched, dispute opened) have AI-authored provisional Bemba/Nyanja drafts — loanwords kept for "order", "quote", "app", "QR code", "KYC". Outside the Phase-1 critical prefixes; pending native-speaker review. `notifications.center.bellUnread` is an ICU plural read aloud by screen readers — please check the plural forms first.
**Home "Popular now" stream (2026-11-13):** `catalog.home.feed.stream.{title,loadMore,moreLoaded}` is EN passthrough in bem/nya (the `home.feed` subtree sits outside the Phase-1 critical prefixes, and the stream also reuses `home.feed.{loadingMore,end,loadError,retry}`, which are passthrough too). Pending native-speaker review.
**Vendor plans + shared product photos (2026-11-13, `feat/capacity-plans-photos`):** `vendor.plans.*` (plan card, usage, upgrade prompt, listing/photo limit messages) and `vendor.listings.images.{duplicate,dedupCanonical}` are **EN passthrough** in bem/nya. They sit outside the Phase-1 critical prefixes and talk about plan prices and limits, so a wrong vernacular guess could mislead a vendor about money. fr/zh are full translations; admin strings are admin-only (no bem/nya admin namespace). Pending native-speaker review.
**Business Home (2026-11-13):** `directory.profile.home.*` (the /v/[slug] page: story, find us, hours, open/closed, compare with other shops, verified-only reviews note, clips, offers, service price lines, browse other shops) and `directory.elsewhere.*` (the "From other shops" rail under product, service and event pages) are EN passthrough in bem/nya, outside the Phase-1 critical prefixes. Exceptions with AI-authored provisional drafts: `directory.profile.home.{storyHeading,findUsHeading,serviceQuote}`. Pending native-speaker review.

## Vendor UX pass

**Vendor UX pass (2026-11-12, `feat/ux-vendor-pass`, pilot 13 Nov):** new vendor guidance copy (home next steps, KYC checklist, order next-step / COD / dispatch cut-off / timeline, listing tips and status guide, payouts pilot notice). EN is authoritative; fr/zh are full translations.

In **bem/nya**, only short labels and headings carry **AI-authored provisional drafts** (not native-reviewed). Everything that tells a vendor what to do with money, deadlines or documents is **EN passthrough** on purpose, matching the vendor-namespace precedent above (a wrong guess on COD, payouts or the 14:00 cut-off costs a pilot vendor money). Pending native-speaker review:

- Provisional drafts: `vendor.home.tasks.heading`, `vendor.home.tasks.intro`, `vendor.onboarding.checklist.{heading,progress,reasonLabel,ctaFinish,ctaFix}`, `vendor.onboarding.checklist.items.*.title`, `vendor.onboarding.checklist.states.*`, `vendor.listings.guide.heading`, `vendor.listings.manage.statusHint.*`, `vendor.orders.guide.{headingNow,headingNext}`, `vendor.orders.timeline.{stateDone,stateCurrent,stateUpcoming}`, `vendor.queue.nextStep.*`, `vendor.payouts.pilot.badge`
- EN passthrough (untranslated): `vendor.home.tasks.items.*`, `vendor.onboarding.checklist.{items.*.why,fix.*,pendingNote}`, `vendor.listings.guide.{photos,title,price,stock}.*`, `vendor.listings.manage.statusGuide.*`, `vendor.orders.actions.after.*`, `vendor.orders.guide.{scanCta,paidExplainer,unpaidExplainer,cod.*,steps.*}`, `vendor.orders.timeline.srState`, `vendor.orders.errors.retryHint`, `vendor.queue.{emptyNeedsAction,emptyFiltered,cutoff,errors.retryHint}.*`, `vendor.payouts.pilot.*` (except `badge`), `vendor.payouts.errors.retryHint`
- EN wording changed (bem/nya now carry the new EN): `vendor.home.analytics.gmv`, `vendor.onboarding.status.approved.body`, `vendor.listings.kycGate.body`, `vendor.listings.manage.edit.returnableHelp`, `vendor.tickets.fields.priceHelp`
  **UX pass 4 — checkout/COD guidance and order timeline (2026-11-12):** AI-authored provisional Bemba/Nyanja drafts (loanword style: rider, order, cash, seller, stock) for `checkout.checkout.fulfilment.guide.*` (delivery/pickup help, landmark tips, 14:00 Lusaka dispatch cut-off), `checkout.checkout.payment.subtitle`, `checkout.checkout.payment.codGuide.*` (COD explainer, cap and over-cap guidance), `checkout.checkout.review.codGuide.*` (COD "how you'll pay" steps, fulfilment summary, place-order label), `checkout.checkout.pending.cod.*` (COD confirmation: order number, next steps, change/cancel help), `checkout.cart.emptyTrustEscrow` and `checkout.cart.escrowTeaser` (rewritten COD-first — online payment is not live in the pilot), `orders.timeline.explain.*`, `orders.timeline.now` and `orders.help.*`. These are COD / money-trust copy: pending recorded native-speaker review; not a sign-off. Also `auth.otp.help.*` ("Didn't get a code?" troubleshooting on the OTP screen) — provisional bem/nya drafts, pending review.

**COD-only pilot trust copy (2026-11-13):** the site-wide header strip `catalog.home.serviceBar.message`, mega-menu promo `nav.shop.featuredPromo`, new footer keys `common.paymentTrust.{footerSeal,footerPaymentNote}` (replace the footer's "Held by Convergeo" seal and "MoMo · Airtel · Zamtel · Card" note), `orders.escrow.cod`, plus EN/FR `checkout.checkout.pending.cod.amountDueLabel` were rewritten COD-first: online payment / escrow is not live in the pilot, so it is shown only as "coming soon" or not at all. AI-authored provisional Bemba/Nyanja drafts (loanword style: cash on delivery, order, delivery, pickup) — bem: "Cash on delivery · Delivery ya Lusaka · Pickup nationwide", "Lipileni mu cash ilyo order yafika", "Cash on delivery · Ukulipila pa intaneti kukesa", "Lipileni mu cash ilyo mwapokelela order yenu."; nya: "Cash on delivery · Delivery ku Lusaka · Pickup nationwide", "Lipirani mu cash order ikafika", "Cash on delivery · Kulipira pa intaneti kukubwera posachedwa", "Lipirani mu cash mukalandira order yanu.". Money-trust copy: pending recorded native-speaker review; not a sign-off. When online payment goes live these keys must be revisited (they deliberately make no escrow claim).
**Over-COD-cap checkout notice (2026-11-13):** `checkout.checkout.overCodCap` (shown at checkout start when the total is over the COD cap while online payments are off) has AI-authored provisional Bemba/Nyanja drafts — bem: "Order yenu yacila pali {cap}, ifyo cash on delivery ingasuma. Payment ya online teyaisa nomba. Fumyeni fimo mu cart pa kuti mupwishe ukushita." · nya: "Order yanu yaposa {cap}, ndalama zomwe cash on delivery ingalipire. Payment ya online silipo pano. Chotsani zinthu zina mu cart kuti mumalize kugula." Pending native-speaker review.

**Multi-branch businesses (2026-11-15, `feat/multi-branch-business`, flag `multi_branch` off):** `vendor.branches.*` (switcher, "My businesses & shops", add-shop flow, PACRA registration, evidence upload, errors) and `directory.profile.{otherBranches,otherBranchesAria,partOfBusiness,branchWithLandmark}` are **EN passthrough** in bem/nya. They talk about payout numbers, plan add-on prices and registration rules, so a wrong vernacular guess could mislead a vendor about money or compliance. fr/zh are full translations; `admin.branches.*`, `admin.vendorPlans` entitlement fields and `admin.config.platform.branchMinDistance` are admin-only (no bem/nya admin namespace). Pending native-speaker review.
**Delivery-partner consent (2026-11-13, Zambia DPA):** `checkout.checkout.review.deliveryConsent.{label,hint,saveFailed}` (critical `checkout.review` prefix) and `account.privacy.deliveryConsent.*` (privacy settings toggle) have AI-authored provisional Bemba/Nyanja drafts (loanword style: courier, address, order, delivery, pickup, licence). Key lines — bem label: "Peeleni courier ishina lyandi, foni ne address pa kuleta iyi order"; nya label: "Patsani courier dzina langa, foni ndi address kuti abweretse order iyi". This is consent wording under the Data Protection Act: it must be reviewed by a native speaker **and** checked against the legal notice before the pilot relies on it. Pending review; not a sign-off.

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
**Vendor listing + onboarding QA pass (2026-11-15, `fix/vendor-listing-onboarding`):** EN is authoritative; fr/zh are full translations. In bem/nya the following new `vendor.*` keys are **EN passthrough** (marked with the `⚠ ` prefix) pending native-speaker review, because they explain listing rules, fulfilment, identity verification or settings and a wrong vernacular guess costs a vendor more than English does:

- Field-level listing errors and hints: `vendor.listings.fieldErrors.*`, `vendor.listings.errors.{draftInvalid,publishBlocked}`, the new `vendor.listings.fields.*` hints (condition/Class D explanation, defect notes, fulfilment options: Lusaka delivery, pickup at shop or branch, nationwide pickup, made-to-order lead time).
- Removed listing state: `vendor.listings.manage.removed.*`.
- Single name for verification, "Verify your ID" (`vendor.onboarding.steps.kyc`, `onboarding.kyc.heading`, `onboarding.status.heading`, `home.kycBanner.*`, `home.tasks.items.kyc*.title`, `listings.kycGate.cta`, `payouts.errors.kycRequired`, `events.errors.kyc_required`) rewritten in EN, fr, zh; bem/nya carry the EN wording.
- Onboarding: `vendor.onboarding.back`, `vendor.onboarding.saveLater.*`.
- Settings page: `vendor.shell.nav.settings`, `vendor.settings.*` (language names are endonyms and identical in every locale).
- Scanner with a blocked camera: `vendor.scan.camera.{deniedNote,retry}`, `vendor.scan.eventCheckIn.camera.{deniedNote,retry}`.
- Organiser gate on the Events page: `vendor.events.gate.*` (Become an organiser / Run an event with a verified organiser, collaboration is a "coming soon" stub), `vendor.events.errors.{recurrenceRuleRequired,recurrenceSeedRequired}` (previously hardcoded English).
- Checkout: `checkout.checkout.fulfilment.notOffered` (shown when a seller does not offer delivery or pickup for an item).

**Events collaboration (2026-11-15, flag `events_collaboration`):** EN is authoritative; fr/zh are full translations. In bem/nya every new key is an **EN passthrough** (marked with the `⚠ ` prefix) pending native-speaker review: `vendor.events.collab.*` (proposal form, readiness checklist, equipment/permit states, revenue-share explanation, organiser inbox, approve/decline/changes copy, errors), `vendor.events.gate.collaborate.open` and `vendor.settings.collab.*`. The revenue-share and accountability wording is money/trust copy; a wrong vernacular guess costs more than English does.

**Plans follow-up (2026-11-15, `feat/branches-plans-followup`):** `vendor.{plans.picker,plans.usageActive,plans.publishLimitReached,plans.trialNoCharge,trial,extras,shell.nav.plan,shell.nav.extras,branches.shops,listings.import.errors.planLimit}`, `directory.profile.branch*` and `notifications.inApp.vendor.extras_*` are **"⚠ " + English** in bem/nya (prices, trials and quotes are money copy; pending native-speaker review). fr/zh are full translations; `admin.{extras,trials,plans.publishLimit,nav.extras,nav.trials,config.platform.planAnnualDiscount}` and `notifications.inApp.admin.extras_requested` are admin-facing.

