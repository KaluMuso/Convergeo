# Customer web app audit (apps/customer) - read-only, origin/master 0bb3243f

Live checks skipped: https://www.vergeo5.com returns 403 from the agent proxy. All findings are from code review.
Paths below are relative to apps/customer/app/[locale]/(shop)/ unless they start with packages/ or apps/.
Already-known items (payment "coming soon" on PDP/footer, PDP/storefront images, storefront logo/cover, pickup places, /me/follows 422, tech-services link, card padding) are not re-reported, except where the stale copy lives in places the known fix probably does not cover (items 1, 2).

## (a) Top 15 issues, ranked by user impact

1. Help Center is still written for the COD-only pilot (13 MDX files). apps/customer/content/help/*.mdx
   - Summaries start with "Coming soon." (how-escrow-works, is-my-money-safe, mobile-money-payments, when-funds-are-released, how-refunds-work, vendor-payouts).
   - payment-methods, what-is-vergeo5, how-to-place-an-order, returns-change-of-mind and buying-event-tickets say "during the pilot you pay cash" and "online payment is coming soon".
   - Fix: rewrite summaries and bodies for live MoMo, card and escrow (MTN/Airtel push, held then released, COD capped at K500). Update the help index copy and keywords to match.

2. Stale payment and trust copy outside the known PDP/footer fix. packages/i18n/messages/en/
   - checkout.json: cart `escrowTeaser` ("Pay when it arrives (cash on delivery)... "), `codStep1-3` (the cart escrow steps are COD steps), `emptyTrustEscrow` ("Nothing is charged online"), `overCodCap` ("Online payment is not open yet").
   - catalog.json: `escrow` lines at ~L112, L146 ("cash on delivery during the pilot") and L463.
   - common.json `footerPaymentNote`.
   - marketing.json: L14, L32, L38, L127. The sell page says "Online payouts are coming soon".
   - ai.json `ai.faq.escrow.a` and `ai.faq.payment.a`. "Ask Vergeo" will repeat these lines to buyers.
   - events.json `getTicketsSoon` is unused (dead key).
   - Fix: reword to the real flow, "Pay with MoMo or card, we hold it until you confirm delivery; cash on delivery up to K500". The cart should show the escrow ladder (You pay, Held by Convergeo, Released) from checkout.json `escrowStep1-3`. Remove dead keys.
   - Cart wiring: cart/page.tsx passes `escrowSteps: [cart.codStep1..3]` and `escrowTeaser`. Switch these to the escrow strings.

3. Service detail sticky CTA is hidden under the bottom nav, and it fails silently. s/[slug]/_components/service-sticky-cta.tsx L120 and service-page-sticky.tsx
   - Bottom nav is `fixed bottom-0 z-50` (packages/ui/src/bottom-nav.tsx). The service CTA is `fixed bottom-0 z-40`, so on phones the "Book / Request free / Get quote" bar sits underneath the nav.
   - The PDP bar correctly uses `bottom: calc(3.5rem + env(safe-area-inset-bottom))`.
   - `postStickyAction` returns silently when `!session`. It does not redirect to login. The `catch` swallows every error even though `labels.errors.*` is passed in, so a tap on "Book" does nothing.
   - Fix: apply the same 3.5rem offset. If there is no session, `router.push(/login?next=...)`. Render `labels.errors.generic` in an `aria-live` region. Add `s/` and `e/` to `hasStickyBuyBar` in apps/customer/app/[locale]/_components/floating-actions.tsx so the WhatsApp/FAB does not collide with it.

4. Event detail has no ticket CTA on mobile, and unknown slugs show the private-event unlock form. e/[slug]/page.tsx, e/[slug]/_components/private-event-access.tsx
   - Single column order is about, dates, calendar, venue, then the aside (refund policy, TicketPicker). The primary action is several screens down at 360px, and there is no sticky bar (the service page has one).
   - `fetchEvent` returns null for 404, 5xx and network errors alike. The page then renders `<PrivateEventAccess>` (an access-code prompt) with HTTP 200. A mistyped URL or an API blip looks like a private event.
   - Fix:
     - Add a sticky "Get tickets" bar (price from `min_price_ngwee`, anchor to the picker) shown below lg, with the same bottom-nav offset.
     - On mobile put TicketPicker directly under the hero (`order-first lg:order-none` on the aside).
     - Make `fetchEvent` return a discriminated result: 404 and `visibility=private` show the access form only when the API says the event is private (401/403), a true 404 calls `notFound()`, and 5xx shows an unavailable panel.

5. Vendor, service and event pages turn API failures into a hard 404. v/[slug]/page.tsx L195-L412, s/[slug]/page.tsx `fetchService`, e/[slug]/page.tsx `fetchEvent`
   - `!response.ok` and `catch` both return null, then `notFound()`. A transient 5xx becomes a cacheable 404 and a soft-404 for SEO. The PDP already does this correctly with `{kind: "unavailable"}` (fetch-product.ts).
   - Fix: copy the PDP pattern, tri-state 404 / unavailable / ok. Render the existing `SearchUnavailablePanel`-style panel with a retry link. Do not call `notFound()` for non-404.

6. List pages show "no results" when the API failed, and have no pagination. vendors/page.tsx, services/page.tsx, events/page.tsx
   - `fetchDirectory`, `fetchServices` and the events fetch return null on any error. The page then shows the normal empty state ("No vendors found").
   - vendors/page.tsx shows `total` but never requests or renders more than page 1 (no page/cursor param). Same for services and events.
   - Fix: distinguish null (error) from an empty array and show an unavailable state with retry. Add "Load more" or a `?page=` pager. Search and category pages already do the unavailable state well.

7. Storefront product cards show the vendor's rating as every product's rating. v/[slug]/page.tsx L450-L455 (`rating: reviews.rating_avg ?? 0, reviewCount: reviews.rating_count` in `listingsForGrid`)
   - Every card shows the same stars and count, which looks like fake social proof. A vendor with no reviews shows "0".
   - Fix: pass null/0 for per-listing rating unless the API returns per-listing rating. Hide the rating row when `reviewCount === 0`.

8. Account pages have no loading skeleton or error boundary and fetch with no try/catch. account/orders/page.tsx L35 (`await api.listOrders()`), account/*
   - There is no `loading.tsx` under account/. Only (shop) has one, and [locale]/error.tsx is the only boundary, so an orders API error shows the global error page.
   - Orders are not paginated.
   - Fix: add account/loading.tsx (skeleton rows) and account/error.tsx (retry plus "back to account"). Wrap `listOrders` and show an inline error. Add pagination or "Show older orders".

9. Events index: duplicate h1, and a blank list when only one event exists. events/page.tsx L305-L410
   - The hero has `<h1>{browse.title}</h1>` and then `<PageHeader title={browse.title}>` renders another h1. That is two h1s with the same text, and the hero also uses an h2 for the event title.
   - The featured event is removed from the list (`remainingEvents`). With 0 or 1 upcoming events the section under the filters is empty (no EmptyState, no message) because the `items.length === 0` branch never fires.
   - The hero is `min-h-[24rem]` stacked on mobile, so the first screen is mostly hero.
   - Fix: make the hero title a `p`/eyebrow, or drop the PageHeader. Show a "More events coming" or empty state when `remainingEvents.length === 0`. Cut the mobile hero min-height to about 16rem.

10. Vendor logos and covers are CSS `background-image` with a raw URL. v/[slug]/page.tsx L594/L605, _components/directory/vendor-card-grid.tsx L81, _components/home-default.tsx L576, e/[slug]/page.tsx L177 (organiser logo fallback)
    - Problems: no alt or accessible name, not lazy, not optimised (no f_auto/q_auto/srcset), no LCP priority hint, and `url(${logoUrl})` is unquoted, so URLs with spaces or `)` break, and it is a CSS-injection vector if the API ever returns user-controlled strings. The directory grid renders many of these.
    - (The storefront cover/logo wiring is already being fixed. Make the same change for the directory grid, the home vendor rail and the event organiser.)
    - Fix: use `CloudinaryImageStatic` when the value is a public_id and `next/image` or `<img loading="lazy" decoding="async" width height alt="">` for absolute URLs. Always quote the URL if a background is kept.

11. Grid and container inconsistency across browse routes. event-grid.tsx L70 (`md:grid-cols-2 xl:grid-cols-3`), service-grid.tsx L52 (1/2/3/4), directory/vendor-card-grid.tsx L88 (1/2/3), home-default.tsx L502 and L604, plp/listing-grid.tsx L70 (2 to 6 columns, gap-2 vs gap-3/5 elsewhere), v/[slug]/page.tsx L560 (`lg:max-w-6xl` vs `max-w-[1400px]` on s/e pages), cart `max-w-5xl`
    - Gaps vary between gap-2, gap-3 and gap-5, and container widths vary, so the product, service, vendor and event grids look like four different systems at 768 and 1280+. At 1440 the storefront is a narrow 1152px column with 5-6 column product tiles.
    - Fix: define one `browse-grid` token/utility in packages/ui (gap-3 md:gap-4, 1/2/3/4 columns; product tiles 2/3/4/5) and one container width, then apply it to these grids.

12. Service detail redundancies and flow confusion. s/[slug]/page.tsx L330-L470
    - The service area is shown 3 times (hero, a dedicated section, metadata).
    - The sidebar card uses an "Ask for quote" eyebrow with a "From K..." heading, which is contradictory. For free services the card is an empty shell (`is_free` renders only the eyebrow and heading with no body).
    - For priced, non-bookable services the primary CTA "Request quote" links to the generic `/services/post-job?category=` form instead of a direct quote to this provider, while quote-only services use the direct dialog.
    - Fix: drop the duplicate section. Render the sidebar card only if it has an action. Use the direct `ServiceQuoteCta` for all non-bookable services and keep post-job as the secondary "Ask several providers" link.

13. Hard-coded category lists drift from API facets. vendors/page.tsx L130-L135 (`categoryLabels` only electronics, fashion-beauty, home-living, groceries), services/page.tsx L140-L150 (8 fixed categories), events/page.tsx L270-L300 (about 25 keys)
    - Facet values outside the list render as the raw slug with hyphens replaced (e.g. "tech services").
    - Fix: resolve labels via the category tree / `categoryDisplayName` (already in _components/category-display-name.ts) with a title-case fallback. Do not hand-maintain maps.

14. Accessibility and keyboard gaps. v/[slug]/page.tsx L663-L672, share/WhatsApp, e/[slug]/page.tsx
    - Vendor WhatsApp links use `https://wa.me/${vendor.whatsapp_msisdn}` without stripping "+" or spaces and with no prefilled text. `lib/social/phone.ts` already has a helper for this.
    - The WhatsApp button's SVG has no accessible name beyond the text (fine) but the link has `target=_blank` with no "opens in new tab" hint.
    - The event hero text sits on a gradient over a photo (`text-panel-muted` on image) with no minimum contrast guarantee for light images.
    - The PDP/service sticky bars have `aria-label` but no `aria-live` for failures (see item 3).
    - Fix: use the shared wa.me builder with a prefilled "Hi, I found you on Convergeo" message (i18n key). Add a stronger scrim (`from-panel via-panel/80`) on event heroes.

15. Perf: very large client components shipped on all (shop) routes. _components/cart/mini-cart-drawer.tsx (1358 lines), cart/vendor-groups.tsx (821), checkout/_components/step-fulfilment.tsx (911), pdp/pdp-interactive-body.tsx (624), search/results-tabs.tsx (605), events/date-filter-chips.tsx (470)
    - The cart host is already lazy (`LazyCartHostSlot`), but `date-filter-chips.tsx` (calendar grid, 470 lines) loads eagerly on /events and results-tabs on /search.
    - `generateStaticParams` on s/[slug] and e/[slug] returns placeholder slugs ("placeholder", "zed-summer-festival"), which pre-renders garbage pages and is of no SEO use.
    - Fix: `dynamic()` the date calendar popover and the results-tabs filter panel. Return `[]` from `generateStaticParams` on dynamic detail routes (keep `dynamicParams` default) or fetch the top N slugs.

## Other observations (lower priority)
- Brand naming: orders.json uses "Held by Vergeo5" (11 occurrences of Vergeo5 vs 252 of Convergeo). Pick one customer-facing name.
- help/[slug]/page.tsx and sell/page.tsx inject JSON-LD with `JSON.stringify` in `dangerouslySetInnerHTML` without escaping `<`. Content is founder-authored, so low risk, but use the shared `JsonLdScript`.
- Design tokens are clean: no ad-hoc hex/tailwind palette colours except the Zambian flag SVG in top-utility-bar.tsx and the Google button. No hardcoded English JSX found.
- Auth forms look fine: labels, `autocomplete`, `one-time-code` OTP.
- Checkout payment step handles `available_methods`, kill switch and COD cap well. Only the copy is stale (item 2).
- Search and category pages have proper unavailable states. Use them as the pattern for items 5 and 6.

## (b) Implementation batches (exclusive file ownership)

### Batch A - Copy and trust messaging (no TSX logic except cart label wiring)
Items: 1, 2 (+ brand naming)
Files owned:
- packages/i18n/messages/en/{checkout,catalog,common,marketing,ai,events,orders,account}.json (8 files; mirror to other locales if present)
- apps/customer/content/help/*.mdx (all 21 files, mechanical copy edits; the 13 listed in item 1 are the priority)
- apps/customer/app/[locale]/(shop)/cart/page.tsx (swap `escrowSteps` and `escrowTeaser` keys only)
- apps/customer/app/[locale]/(shop)/_components/home-trust-strip.tsx (only if strings are inlined there; verify)
Do not touch: any other tsx.

### Batch B - Route states, flows and data wiring
Items: 3, 4, 5, 6, 7, 8, 9, 12 (+ new shared unavailable panel)
Files owned (about 15):
- (shop)/s/[slug]/page.tsx
- (shop)/s/[slug]/_components/service-sticky-cta.tsx
- (shop)/s/[slug]/_components/service-page-sticky.tsx
- (shop)/e/[slug]/page.tsx
- (shop)/e/[slug]/_components/private-event-access.tsx
- (shop)/e/[slug]/_components/ticket-picker.tsx (anchor id only) and a new `event-sticky-cta.tsx`
- (shop)/v/[slug]/page.tsx (tri-state fetch, per-listing rating; leave cover/logo markup to the known fix)
- (shop)/vendors/page.tsx
- (shop)/services/page.tsx
- (shop)/events/page.tsx
- new (shop)/_components/api-unavailable.tsx (shared panel)
- account/orders/page.tsx, new account/loading.tsx, new account/error.tsx
- the matching unit tests

### Batch C - Visual consistency, a11y and perf
Items: 10 (directory/home/organiser only), 11, 13, 14, 15
Files owned (about 12):
- (shop)/_components/directory/vendor-card-grid.tsx
- (shop)/_components/home-default.tsx
- (shop)/_components/events/event-grid.tsx
- (shop)/_components/events/date-filter-chips.tsx
- (shop)/services/_components/service-grid.tsx
- (shop)/_components/plp/listing-grid.tsx
- (shop)/_components/directory/storefront-products.tsx
- apps/customer/app/[locale]/_components/floating-actions.tsx (add s/ and e/ to `hasStickyBuyBar`)
- (shop)/_components/category-display-name.ts (shared label resolver used for item 13)
- packages/ui/src/ (new browse-grid utility only if it does not collide with existing UI package work)
- (shop)/search/_components or results-tabs.tsx (lazy filter panel)
Do not touch: files owned by A or B. Item 13's label changes in vendors/page.tsx and services/page.tsx are done in Batch B as part of the same edit, using the resolver Batch C provides. Land C's resolver first, or have B inline a fallback.
