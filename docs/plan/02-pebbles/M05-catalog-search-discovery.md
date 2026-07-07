# M05 — Catalog, Search & Discovery — Pebbles

11 pebbles. Customer-facing routes: SSR/ISR, ≤150KB gz JS, LCP ≤2.5s Fast-3G/360px, all images via `CloudinaryImage`. Owns i18n namespaces `catalog`, `search`, `supplies`, `directory` (+ events browse strings in `events`).

---

### M05-P01 — Customer home with merchandising slots `L`
**Deps:** M02, M03-P07/P10 · **Files:** `apps/customer/app/[locale]/(shop)/page.tsx` (replaces placeholder), `(shop)/_components/hero.tsx`, `banner-row.tsx`, `featured-collections.tsx`, `events-row.tsx`, `category-grid.tsx`, `packages/ui/src/merch/` (hero variant components keyed by variant id from design variants)
Home composed entirely from `merch_slots` config (ISR 60s): hero variant, banner slots, featured collections, **events row first** per IA, category grid with pastel fills.
**AC:** admin config change (M13-P08) reflects ≤1min without deploy; empty-slot fallback sane; LCP element is the hero image (preloaded).
**Tests:** slot-render from fixture configs incl. scheduled/expired slots; missing-variant fallback.

### M05-P02 — Category browse & PLP `L`
**Deps:** M02, M03-P02 · **Files:** `apps/customer/app/[locale]/(shop)/c/[...slug]/page.tsx`, `(shop)/_components/plp/` (facet-panel, sort-bar, listing-grid, load-more), `services/api/app/routers/catalog.py` (list endpoint w/ facets)
Facets: category/price-range/location/rating/availability/condition; sorts: relevance, cheapest, nearest (lat/lng distance), newest; server-driven facet counts; URL-encoded filter state (shareable/SEO-safe); "load more" pagination.
**AC:** facet math correct on seed data; filter state survives reload/share; PLP LCP ≤2.5s lab.
**Tests:** API facet/count tests incl. empty-result; sort-by-distance ordering; URL state round-trip.

### M05-P03 — PDP core `L`
**Deps:** M02-P08, M03-P02 · **Files:** `apps/customer/app/[locale]/(shop)/p/[slug]/page.tsx`, `(shop)/_components/pdp/` (gallery, buy-box, specs-table, vendor-block, condition-badge), `services/api/app/routers/products.py`
Canonical product page: gallery ≤8 (M02 ImageGallery), spec table from jsonb, selected-listing buy box (price via formatK, stock state, qty stepper, add-to-cart CTA stub wired in M07-P03), vendor block (name, badge, rating, location/landmark).
**AC:** ISR with on-demand revalidate on listing change; out-of-stock & single-vendor states correct; 360px layout matches design.
**Tests:** render states (in/out of stock, no reviews, quick-list without canonical); API 404/merged-product redirect.

### M05-P04 — Multi-vendor comparison `M`
**Deps:** P03 · **Files:** `apps/customer/app/[locale]/(shop)/p/[slug]/_components/comparison.tsx`, `services/api/app/routers/comparison.py`
"N vendors selling this" on PDP: table of listings for the canonical product — price (formatK), condition, distance from user (geolocation opt-in, fallback Lusaka CBD), vendor rating/badges, delivery/pickup availability; sort by price/distance; select swaps the buy box.
**AC:** sorts stable and correct; single-listing products hide the block; EXPLAIN uses product_id index.
**Tests:** ordering tests; distance fallback; suspended-vendor listings excluded.

### M05-P05 — Search API (hybrid RRF) `L`
**Deps:** M03-P08 · **Files:** `services/api/app/routers/search.py`, `app/services/search/` (query builder, embedding client for query-time vectors, synonym expansion), `services/api/tests/test_search.py`
`GET /search`: FTS + trgm + vector lanes fused via `search_rrf`, faceted filters, entity_kind filter (products/services/events/supplies/vendors), pagination; `GET /search/suggest` autocomplete (prefix + trgm, ≤80ms target); synonym/alias expansion (Bemba/Nyanja) pre-query; graceful degrade to keyword-only when embedding call fails; zero-result logging hook.
**AC:** exact ("itel A70"), fuzzy ("chitange"), semantic ("dress for kitchen party") all return relevant seed results; degrade path tested; p95 <150ms keyword lane on seed data.
**Tests:** the three query classes; degrade on embedding failure; facet filters compose; injection-safe (raw tsquery escaped).

### M05-P06 — Search UI `M`
**Deps:** P05, M02 · **Files:** `apps/customer/app/[locale]/(shop)/search/page.tsx`, `(shop)/_components/search/` (search-input w/ autocomplete, results-tabs per vertical, zero-results), `packages/i18n/messages/en/search.json`
Search page + TopNav entry: debounced autocomplete, results tabbed by vertical (All/Products/Services/Events/Supplies/Vendors), recent searches (localStorage), zero-results state with category suggestions + "Ask Vergeo" teaser slot (wired M06-P04).
**AC:** keyboard-navigable autocomplete; back-button restores results; data-frugal (no result images above 720w).
**Tests:** autocomplete debounce/keyboard tests; tab counts; zero-result render.

### M05-P07 — Supplies tab `M`
**Deps:** P02 · **Files:** `apps/customer/app/[locale]/(shop)/supplies/page.tsx`, `(shop)/_components/supplies/` (tier-price cards, moq-badge), `packages/i18n/messages/en/supplies.json`
PLP variant filtered `wholesale=true`: TierPriceTable display (M02-P04), MOQ badges, qty-aware price preview ("120 × K85 = K10,200"), business-y sort (MOQ, unit price at qty); links into PDP with tier context.
**AC:** tier math exact in ngwee; MOQ enforced messaging (cart enforcement in M07); T2-only sellers rule surfaced.
**Tests:** tier price selection at boundary qtys (min, between tiers, huge); non-wholesale listings never appear.

### M05-P08 — Directory tab & vendor public profile `M`
**Deps:** M03-P01 · **Files:** `apps/customer/app/[locale]/(shop)/directory/page.tsx`, `(shop)/v/[slug]/page.tsx`, `(shop)/_components/directory/` (vendor-card grid, filter bar), `services/api/app/routers/directory.py`, `packages/i18n/messages/en/directory.json`
Browsable/searchable vendor index (category, location, badges filter); vendor profile page: logo, hours, location + landmark, description, badges, listings grid, reviews summary — doubles as the directory entry (D2).
**AC:** only `active` vendors listed; profile page = shareable URL with LocalBusiness SEO stub (full SEO P09); pending/suspended 404.
**Tests:** visibility rules; filter combos; empty directory state.

### M05-P09 — SEO pass `M`
**Deps:** P01–P08 · **Files:** `packages/ui/src/seo/json-ld.tsx` (Product/Offer/AggregateRating/LocalBusiness/Event/BreadcrumbList builders), `apps/customer/app/sitemap.ts`, `apps/customer/app/robots.ts`, metadata exports in each (shop) route (`generateMetadata` additions), `apps/customer/app/[locale]/(shop)/opengraph-image.tsx`
JSON-LD on PDP (Product+Offers from listings), vendor (LocalBusiness), events (Event); canonical URLs (filter params excluded); dynamic sitemaps (products/vendors/events/categories, chunked); OG image template (name+price+brand colors).
**AC:** Google Rich Results test passes for Product/Event/LocalBusiness fixtures; sitemap valid + gzipped; no canonical dupes across locale routes.
**Tests:** JSON-LD builder unit tests (ngwee→decimal ZMW correct in offers); sitemap generation from seed.

### M05-P10 — Media backend (Cloudinary signing & URL helper) `S`
**Deps:** M01-P02 · **Files:** `services/api/app/routers/media.py` (signed upload params endpoint, per-role folder scoping, size/type limits), `packages/ui/src/media/url.ts` (central URL builder used by CloudinaryImage — **the D26 migration seam**), `docs/ops/media-pipeline.md`
Signed direct-to-Cloudinary uploads (no files through API); folder convention `listings/{vendor_id}/…`; eager `f_auto,q_auto` transforms; URL helper is the single place a CDN swap happens.
**AC:** unsigned/oversized/wrong-type uploads rejected; vendor A cannot sign into vendor B's folder; URL helper covered by contract tests.
**Tests:** signing authz tests; limit enforcement; URL builder goldens.

### M05-P11 — Events discovery (browse tab + event detail display) `M`
**Deps:** M02-P04, M03-P03 · **Files:** `apps/customer/app/[locale]/(shop)/events/page.tsx`, `(shop)/e/[slug]/page.tsx` (display + ticket-CTA stub — purchase wiring is M10-P03), `(shop)/_components/events/` (event grid, date-filter chips), `services/api/app/routers/events_public.py`, `packages/i18n/messages/en/events.json`
Events tab: grid with **"Tonight / This Weekend"** default filter chips, category filter (6 event categories), calendar-lite; event detail: images, venue + landmark/map-lite, instances/dates, ticket types + prices (display only), organiser block.
**AC:** date-window filters correct across month boundaries (Africa/Lusaka TZ); past events excluded from browse but detail stays reachable; sold-out state displayed.
**Tests:** TZ/date-window unit tests; instance ordering; free-RSVP display.
