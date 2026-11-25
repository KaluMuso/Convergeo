# Task T36: Customer value on product, service and event pages

**Agent:** Cursor, up to 4 agents in 2 waves (36A, 36B, 36C parallel; then 36D). **Model:** Composer 2.5. **Branches:** `cursor/value-product`, `cursor/value-service-event`, `cursor/value-shared`, `cursor/value-wiring`, each from `master`. One PR per agent to `master`; don't merge.
**Board:** claim your row (T36A, T36B, T36C, T36D) in `docs/ops/agent-board.md` first. Set it to `ready for review` when done.
**Run order:** 36A, 36B and 36C start together. 36D starts only after 36A, 36B and 36C are merged (it edits the same page files they own).

## Problem (King)

Customers don't get enough value from the product, service and event pages. The founder's vision is: customers value the option to compare and decide. The pages already show a lot, so most of this work is surfacing data we already have, in the order a Zambian buyer on a 360px phone on 3G decides: total cost, how soon, can I trust them, can I pay my way.

## What exists today (checked 24 Nov, do not rebuild)

**Product page** `apps/customer/app/[locale]/(shop)/p/[slug]/page.tsx` + `(shop)/_components/pdp/**`:
gallery, variants, buy box (stock + low-stock label), sticky mobile add-to-cart, seller list `comparison.tsx` (price, condition, rating, delivery/pickup yes/no, distance, lowest-price badge), `/compare` page, `buyer-trust-panel.tsx` (escrow, returns, delivery estimate, pills), vendor block, notify-back-in-stock, wishlist button, details tabs (overview, specs, reviews with distribution + photos + vendor replies), Q&A, offers box, other-shops rail, related rails, report listing, JSON-LD.
**Service page** `s/[slug]/page.tsx`: hero, from-price, response-time badge, packages, what's included, portfolio grid, service area, reviews, request-quote / free request / book, other-shops rail.
**Event page** `e/[slug]/page.tsx`: hero, dates with spots left, ticket picker (tiers, early bird, perks line, platform fee), venue + maps link, organiser card with verified badge, JSON-LD.
**Shared:** `_components/share-link-button.tsx` (native share, used only on the vendor page), `wishlist-local.ts`, `HomeRecentlyViewedRail`, `lib/delivery-estimate.ts`, `HomeTrustStrip`.

## Gaps where the data already exists (cheapest wins)

| Data we already have                                                     | Where                       | Not used by the UI                                                        |
| ------------------------------------------------------------------------ | --------------------------- | ------------------------------------------------------------------------- |
| Per-listing `stock_qty`, `in_stock`, `fulfilment_mode`, `lead_time_days` | `GET /products/{slug}`      | Seller list shows none of it; the buyer can't see who can deliver soonest |
| `GET /events/{slug}/calendar.ics`                                        | `routers/event_ics.py`      | No "Add to calendar" button on the event page                             |
| `age_restriction`                                                        | `EventDetailResponse`       | Never shown                                                               |
| `ListingAlertIn kind="price_drop"`                                       | `POST /me/listing-alerts`   | Only `back_in_stock` has UI                                               |
| Review aggregate (avg, count, photos)                                    | fetched on the product page | No rating next to the title; reviews sit in a tab                         |
| `response_time_tier`, `preferred_badge`, reviews                         | service page                | Only a badge; no trust text, no provider card                             |
| Tier `qty_cap - tickets_sold`                                            | event ticket types          | Only instance-level spots shown                                           |

Gaps needing a small API change: delivery fee per seller (comparison), seller verified + member-since (product detail vendor), event refund policy (`refund_policy_key` is stored, not returned).

## The 16 improvements

Legend: UI = no API change. API = needs the named field. Bundle = JS added to the customer route.

| #   | Improvement                                                                           | Value                                    | Type             | Wave     |
| --- | ------------------------------------------------------------------------------------- | ---------------------------------------- | ---------------- | -------- |
| 1   | Seller table: stock, "ready in" ETA, made-to-order days, COD / escrow chips, verified | See who can deliver soonest and safest   | UI               | A        |
| 2   | Delivery fee per seller + "Total you pay" sort                                        | Cheapest price is not the cheapest total | API              | A        |
| 3   | "Total you pay" breakdown in the buy box (item x qty + delivery + MoMo/COD line)      | No surprise at checkout                  | UI (uses #2)     | A        |
| 4   | Rating chip + "N photo reviews" link under the title                                  | Social proof above the fold              | UI               | A        |
| 5   | "Tell me if the price drops" (target price)                                           | Bring the buyer back                     | UI               | A        |
| 6   | Seller trust card: verified, member since, response time, shop landmark               | Who am I paying                          | API              | A        |
| 7   | Recently viewed rail on the product page                                              | Resume comparing                         | UI               | C+D      |
| 8   | Service: trust strip, "usually replies in", how it works, sticky mobile CTA           | Confidence to request a quote            | UI               | B        |
| 9   | Service: provider card, JSON-LD, portfolio lightbox                                   | Proof of work, Google rich results       | UI               | B        |
| 10  | Event: Add to calendar (.ics) + Directions                                            | Turns interest into attendance           | UI               | B        |
| 11  | Event: countdown, age limit, per-tier "N left", perks list, early-bird end            | Decide which ticket                      | UI               | B        |
| 12  | Event: refund policy in plain words                                                   | Removes the top buying fear              | API              | B        |
| 13  | Share to WhatsApp with name + price/date + link                                       | Zambia shares on WhatsApp                | UI               | C then D |
| 14  | Save (heart) on services and events                                                   | Come back later                          | UI               | C then D |
| 15  | Shared trust strip (escrow, verified, returns, MoMo/COD)                              | One consistent promise                   | UI               | C then D |
| 16  | Listing card: "N sellers from K..." + delivers-today pill, only if the field exists   | Compare from the grid                    | UI (conditional) | C        |

## Wave 36A: Product page

**Owns:** `apps/customer/app/[locale]/(shop)/p/[slug]/**`, `apps/customer/app/[locale]/(shop)/_components/pdp/**`, `apps/customer/lib/delivery-estimate.ts` (+tests), `services/api/app/routers/comparison.py` and `services/api/app/routers/products.py` (vendor summary only) + their tests (`services/api/tests/test_comparison*.py`, `test_products*.py`), `packages/i18n/messages/*/catalog.json` (`pdp.value.*`, `comparison.*` only).

**Steps**

1. **#1 Seller table.** Join the comparison rows with the listing data already on the page (`productListings`, matched by listing id) in `pdp-interactive-body.tsx`. Add to each row: stock label ("In stock", "Only 3 left" using the existing low-stock threshold, "Out of stock"), delivery/pickup ETA from `estimateDelivery()` (reuse the labels already built for the trust panel), "Made to order, ready in N days" when `fulfilment_mode` is made-to-order, and chips "Pay on delivery" (only when the listing total is at most K500, i.e. 50000 ngwee, and COD is enabled in storefront config) and "Escrow protected". Never show a stock number when `stock_mode` is `always_available`. No invented urgency text.
2. **#2 Delivery fee (API).** In `comparison.py` add to `ComparisonListingItem`: `delivery_fee_ngwee: int | None` (None = unknown, e.g. seller outside the delivery area or no delivery) and `delivery_funding: "customer" | "vendor" | "platform" | None`. Compute it for the default Lusaka zone by calling the existing pure helpers in `services/logistics/delivery_pricing.py` and the zone-fee loader that `checkout.py` uses. **Read and import only; do not edit `checkout.py` or `delivery_pricing.py`.** If you cannot do it without editing them, stop, write the exact missing function on the board and ship #1, #3-#6 only. Integer ngwee only. Keep the response backward compatible (new optional fields).
   UI: add a sort "Lowest total" (price + fee, nulls last) and show "+ K45 delivery" or "Free delivery" per row. Default sort stays as today.
3. **#3 Buy box breakdown.** Under the price show: `Item x qty`, `Delivery to Lusaka (estimate)` from #2 or "calculated at checkout", `Total you pay`. Everything through `formatK()`. One line: "Pay with MTN or Airtel MoMo" and, when eligible, "or cash on delivery". Server-render the static parts; only the quantity-dependent total is client-side (it already is).
4. **#4 Rating chip.** In `pdpHeader` show stars + average + count (from the review aggregate the page already fetches), linking to `#reviews` and opening the reviews tab. Show "N reviews with photos" when the review rows include photos. No chip when there are no verified reviews.
5. **#5 Price-drop alert.** Next to `notify-back-in-stock.tsx`, add `price-drop-alert.tsx` (dynamic import, same pattern). It calls the existing `POST /me/listing-alerts` with `kind: "price_drop"` and `target_price_ngwee` (integer). Offer "Any drop", "10% lower", "20% lower" as presets (integer maths). Reuse `subscribeBackInStock`'s sign-in redirect flow in `lib/engagement-api.ts` by adding a sibling function there (only that function).
6. **#6 Seller trust card (API).** `products.py`: add `verified: bool` (kyc_tier at or above the "verified" tier, same rule the catalogue search already uses) and `member_since: str | None` (vendor `created_at`, date only) to the vendor summary. Update `vendor-block.tsx` to show: Verified seller, "Selling since {month year}", rating, shop landmark, "View store". Don't expose KYC details.

**Tests:** comparison row shows stock/ETA/COD chip only when eligible (K500 boundary: 50000 yes, 50001 no); `Lowest total` sort with a null fee; total breakdown arithmetic with qty 3; rating chip hidden without reviews; price-drop alert posts integer target and handles signed-out; API: new fields present, old fields unchanged, null fee for out-of-area, `verified` mapping. All in `*.test.tsx` / pytest next to the code.
**Bundle:** +3 KB gz at most (table and breakdown are in the existing client body; price-drop is a lazy chunk).

## Wave 36B: Service and event pages

**Owns:** `apps/customer/app/[locale]/(shop)/s/[slug]/**`, `apps/customer/app/[locale]/(shop)/e/[slug]/**`, `services/api/app/routers/events_public.py` (response model + builder only) + `services/api/tests/test_events_public*.py`, `packages/i18n/messages/*/services.json` and `events.json`.

**Steps (service)** 7. **#8 Trust and response time.** Under the hero price add one line from `response_time_tier` ("Usually replies within an hour / the same day / a few days"; map `fast`, `same_day`, `slow`; none when null). Add a "How it works" 3-step block (Request a quote, Compare replies, Pay safely) and, for bookable services, the escrow sentence ("Your payment is held until the job is done"). A sticky bottom bar on mobile with the primary action (Request quote / Book / Request free), hidden on `lg`. Don't duplicate the existing sidebar CTA on desktop. 8. **#9 Provider card, JSON-LD, lightbox.** Provider card above reviews: name, preferred badge, rating from the reviews already fetched, link to `/v/{slug}`. Add `Service` JSON-LD (name, description, provider, areaServed, offers with `priceCurrency: "ZMW"` and price from ngwee by integer maths, `aggregateRating` only with reviews) using `JsonLdScript`; if `packages/ui/src/seo/json-ld.tsx` needs a builder, write it locally in `s/[slug]/_lib/service-jsonld.ts` instead of editing the shared file. Portfolio images open in a lightbox (reuse `pdp/lightbox.tsx` via import; don't edit it).

**Steps (event)** 9. **#10 Calendar and directions.** Button "Add to calendar" linking to the existing API `GET /events/{slug}/calendar.ics` (use `absoluteApiUrl`; one link per instance when several dates). Replace the maps link with "Directions": `https://www.google.com/maps/dir/?api=1&destination={lat},{lng}`; keep landmark text. No API key. 10. **#11 Countdown and tiers.** Server-rendered "Starts in 3 days" / "Today at 18:00" / "Ended" from `starts_at` on the Lusaka clock (Africa/Lusaka, UTC+2) in `_lib/countdown.ts`; no client timer. Show the age limit badge (`age_restriction`, e.g. "18+"). Per tier show "N left" only when `qty_cap` is set and `qty_cap - tickets_sold` is at most 20 (honest, from data); show perks as a short list (split on newline) instead of one line; show "Early bird ends {date}" when `early_bird_until` is in the future. 11. **#12 Refund policy (API).** `events_public.py`: add `refund_policy_key: str | None` to `EventDetailResponse` and its builder (it is already stored; copy the value, no logic). UI: map the key to plain text with i18n keys `events.detail.refund.{key}`; get the valid keys from `organiser_events.py` / `services/events/refund_jobs.py` (read only). Unknown key shows "Ask the organiser about refunds". Put it next to the ticket picker, above Buy.

**Tests:** response-time text per tier and none for null; sticky bar only renders one primary action; Service JSON-LD price in kwacha from ngwee (123450 gives `"1234.50"`) and no rating without reviews; event `.ics` link per instance; Directions URL exact; countdown on Lusaka clock across midnight UTC; "N left" shown at 20, hidden at 21 and when `qty_cap` is null; refund key mapping incl. unknown; API: `refund_policy_key` returned and null-safe.
**Bundle:** 0 KB JS from server components; sticky bar and lightbox less than 2 KB gz (lazy).

## Wave 36C: Shared primitives, listing cards, vendor and home touch-ups

**Owns:** new `apps/customer/app/[locale]/(shop)/_components/value/**` (+tests), `apps/customer/app/[locale]/_components/share-link-button.tsx` (+test), `apps/customer/lib/wishlist-local.ts` (+test), `apps/customer/app/[locale]/(shop)/_components/plp/listing-card.tsx` (+tests), `apps/customer/app/[locale]/(shop)/_components/recently-viewed/**`, `packages/i18n/messages/*/common.json` (`value.*` only).

**Steps** 12. **#13 WhatsApp share.** Extend `ShareLinkButton` with an optional `text` prop. On devices with `navigator.share`, pass `{title, text, url}`; otherwise open `https://wa.me/?text={encodeURIComponent(text + " " + url)}`; last fallback copies the link (current behaviour). Keep existing call sites working unchanged. Build `value/whatsapp-share.tsx` as a thin wrapper that takes `{title, line, url}` where `line` is e.g. "Samsung A15, from K2,450 on Vergeo5". 13. **#14 Save for services and events.** Extend `wishlist-local.ts` to store `kind: "product" | "service" | "event"` with a migration that keeps old product-only entries valid. Build `value/save-button.tsx` (heart, 44px target, `aria-pressed`). Don't change the `/wishlist` page (not owned); entries of the new kinds just have to not break it. Add a test that old stored data still loads. 14. **#15 Trust strip.** `value/trust-strip.tsx`: server component, props are already-translated strings, shows up to four icon + short-line items: escrow ("Held by Vergeo5 until you're happy"), verified seller, returns, MoMo/COD. Items render only when the caller passes the string. Reuse icons from `buyer-trust-panel.tsx` by copying the SVG path, not importing. 15. **#7 Recently viewed on a detail page.** `value/recently-viewed-strip.tsx`: reads the same local storage as `HomeRecentlyViewedRail`, hides the current slug, shows up to 6 compact cards with price, loads lazily (dynamic import, below the fold). Reuse the data helper; don't edit the home rail. 16. **#16 Listing card (conditional).** First check the `CatalogListing` fields the catalogue API returns. If it already returns a seller count and lowest price for a product, show "N sellers from K..."; if it returns delivery flags, show a "Delivers today (Lusaka)" pill when `estimateDelivery()` says today. If a field is missing, skip that part and say so on the board. No API change in this wave.

**Tests:** share falls back wa.me then clipboard, `AbortError` does nothing; wishlist migration; trust strip hides missing items; recently viewed excludes current slug, caps at 6; listing card shows nothing extra when the fields are absent.
**Bundle:** share and save are under 1.5 KB gz; the recently viewed strip is a lazy chunk.

## Wave 36D: Wiring (starts after A, B, C are merged)

**Owns:** the three page files only for the mounts below: `p/[slug]/page.tsx`, `s/[slug]/page.tsx`, `e/[slug]/page.tsx`, plus the label objects they pass; `packages/i18n/messages/*/{catalog,services,events}.json` (new `*.value.*` keys only).

1. Product: `WhatsAppShare` + `SaveButton` (existing wishlist button stays) near the title; `RecentlyViewedStrip` after the related rails.
2. Service: `WhatsAppShare` + `SaveButton` in the header; `TrustStrip` in the sidebar (escrow only when bookable).
3. Event: `WhatsAppShare` ("Event name, Sat 12 Dec, Venue, from K150") + `SaveButton`; `TrustStrip` next to the ticket picker (QR ticket by WhatsApp, refund policy line from #12).
4. Check OG/Twitter metadata on `s/[slug]` has an image (the product and event pages do); add one if missing so the WhatsApp preview shows a picture.
   **Tests:** each page renders the new controls with the right share text; no hardcoded strings (lint).

## Done means

On a 360px phone, a buyer can: compare sellers by total cost and ETA on one screen; see rating and trust before scrolling; set a price alert; add an event to their calendar and get directions; see the refund policy before paying; share any product, service or event to WhatsApp in one tap. Tests, typecheck and lint pass for touched packages. Customer route JS stays at or below 150 KB gz (report the number before and after from `pnpm --filter customer build` bundle output in the PR). Server-rendered parts add 0 KB.

## Rules

1. Claim your board row (`in progress — cursor`) in your first commit. One agent per row.
2. Work only in the files you OWN. Need another file? Stop and note it on the board.
3. Money: integer ngwee everywhere; display only through `formatK()`; `Decimal` or integer maths for any kwacha string (JSON-LD). Float on money is a review-blocking bug.
4. Zero hardcoded user-facing strings. next-intl keys in the namespaces you own. bem, nya, fr and zh: copy the English text and mark it for review; don't invent translations.
5. Customer route JS budget is 150 KB gz. New client code goes behind `dynamic()` or stays in a server component. Don't add dependencies.
6. Never touch `supabase/`, `scripts/ci/`, `.github/`, `infra/`, payments, escrow, ledger, payouts, webhooks, auth or checkout money logic (importing the pure delivery helpers read-only in #2 is the one allowed exception; do not edit them). No secrets. Never merge, force-push or `git stash`.
7. API changes are additive only: new optional response fields, no renames, no new tables. Don't add a migration; if a field needs one, stop and note it on the board.
8. Show only what the data says. No fake urgency, no invented "X people viewing", no made-up delivery times. If the data is missing, hide the element.
9. Testing: run only related tests, one command at a time: `pnpm --filter customer exec vitest related <files> --run`, `cd services/api && uv run pytest tests/<file> -q`, then `pnpm --filter customer typecheck` and `pnpm --filter customer lint` (and `uv run ruff check` + `uv run mypy` for API files). Never the full suite.
10. When done: row to `ready for review`, one line of notes (include the bundle numbers), PR link in Slack #convergeo-dev. Claude reviews the API changes (#2, #6, #12).
