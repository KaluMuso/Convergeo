# Product signals and filter boxes

Status: spec + implementation (feat/product-signals-filters). No DB migration.
Owner of the rules: `services/api/app/services/signals/`. Wire field: `signals` (`ListingSignals`).

## 1. Principles

- **Computed server-side, once**, from tables we already trust; the client only renders. A signal never
  appears on a listing that cannot be bought now (out of stock = no badges, no deal).
- **Honest or absent.** Unknown inputs (no GPS, no lead time, no approved claim) omit the signal; nothing is
  guessed. Reviews are verified-purchase only (order item join, `status = 'published'`).
- **Trust is auditable.** The ribbon reads approved `kyc_records`, never the bare `vendors.kyc_tier`
  (see `kyc/eligibility.py`).
- **Budget.** Max **1 ribbon** and **2 badges** per card; the existing image chips (sold-out / sample /
  W8 offer pill / discount %) keep their own slot and precedence. B2B tier prices stay hidden per D28.
- **Zero new bytes on the hot path.** Cards get a ~60 byte `signals` object; PDP additions are lazy.

## 2. Signals

Computed in `signals/rules.py` (pure, `now` injected). Thresholds are constants in `signals/models.py`.

| Signal         | Kind                        | Exact rule                                                                                                                                            | Source                                                         |
| -------------- | --------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------- |
| Verified / KYC | ribbon                      | `preferred` if `vendors.preferred_badge`; else `verified_business` if highest **approved** kyc tier >= 2; else `verified_id` if tier 1; else none     | `vendors`, `kyc_records` (batch, 2 min cache)                  |
| Deal           | image chip (`deal_percent`) | in stock and `compare_at > price`; `round((compare_at - price) * 100 / compare_at)` in integer math; shown only if >= 5%                              | `vendor_listings.compare_at_ngwee`                             |
| Cheapest       | badge                       | >= 2 distinct in-stock retail shops carry the canonical product and this listing's price <= the lowest of them (ties all win)                         | `vendor_listings` by `product_id`, wholesale and demo excluded |
| Near you       | badge                       | shopper point supplied and seller coordinates known and haversine <= 5 km; also emits `distance_km`                                                   | `vendor_locations` lat/lng; shopper `lat`/`lng` query params   |
| Made in Zambia | badge                       | `made_in_zambia_status = 'approved'` (admin-approved claim only). Probe is fail-soft: column absent (PR #973 not deployed) = signal and filter hidden | `vendor_listings`                                              |
| Top rated      | badge                       | >= 5 verified-purchase reviews and mean >= 4.5                                                                                                        | `reviews` via `order_item_products`                            |
| Fast delivery  | badge                       | stocked (not made-to-order), in Lusaka delivery radius, `lead_time_days` known and <= 1                                                               | `vendor_listings`, `is_lusaka_delivery_available`              |
| Low stock      | badge                       | `stock_mode = 'tracked'` and `0 < stock_qty <= 5`                                                                                                     | `vendor_listings`                                              |
| New            | badge                       | listing created within 14 days                                                                                                                        | `vendor_listings.created_at`                                   |
| In N shops     | line (not a badge)          | `seller_count` = distinct in-stock shops >= 2, with `lowest_price_ngwee` ("In 3 shops from K45"); links to compare                                    | same market query as Cheapest                                  |
| Tier pricing   | price display               | supplies listings only, and only for a verified business buyer (D28); renders `price_tiers` as a quantity ladder. Retail shoppers never receive tiers | `vendor_listings.price_tiers` via `BusinessAccess`             |

### Precedence

- **Badges** (take the first two earned): `cheapest > near_you > made_in_zambia > top_rated > fast_delivery >
low_stock > new`. Rationale: price and proximity decide a purchase; provenance and social proof next;
  logistics and urgency fill the rest; `new` is last because it says nothing about quality.
- **Ribbon**: `preferred > verified_business > verified_id`. One only.
- **Image chips** (unchanged order): sold out > sample > W8 offer pill; the discount % chip stacks above.
- Product (canonical) hits in search use the signals of their cheapest in-stock seller, minus `cheapest`.

### Visuals (tokens only, no hex)

- Ribbon: `CornerRibbon`-style strip on the lower-left of the card media, tint of `--success` (verified
  business), `--info` (ID verified), `--accent` (preferred); label text stays `--text` for 4.5:1.
- Badges: `SignalBadge` chips under the title, `--primary-tint` / `--surface` + 1px `--border`, icon + label;
  `low_stock` uses `--warning`, `new` uses `--primary`. Never red (red is reserved for sold out / discount).
- All motion respects `prefers-reduced-motion`; all labels are i18n keys (`signals.*`), 5 locales, `bem`/`nya`
  fall back to English.

### Where shown

| Surface                                            | Ribbon | Badges                         | In N shops      | Distance      |
| -------------------------------------------------- | ------ | ------------------------------ | --------------- | ------------- |
| Listing card (category, search, home feed, stream) | yes    | 2                              | yes (card meta) | in badge copy |
| PDP buy box / seller rows                          | yes    | 2 per seller row (lazy island) | header line     | per row       |
| Compare table                                      | yes    | 2 per row                      | n/a             | per row       |

### Caching

- Catalog: signals derive from the already cached candidate set (45 s) plus the per-product market cache.
- `signals:market:v1:<product_id>` 60 s, `signals:tier:v1:<vendor_id>` 120 s (ttl cache, shared).
- Public feed and stream pages are cached for everyone, so they are **location-free**: `near_you` is never
  computed there. Catalog / search / comparison responses that carry `lat`/`lng` are keyed by URL
  (CDN `s-maxage=30` for anonymous callers) and `Vary: Authorization`.
- Query budget per surface (cold): 1 listing read (search/feed only), 1 market read per uncached product batch,
  1 `kyc_records`, 1 review join, 1 Made-in-Zambia probe (backed off 10 min when the column is absent).
- Every loader is fail-soft: a failure yields `signals: null`; search filters **fail closed** (no results
  rather than unfiltered "verified").

## 3. Filter boxes

Plain lists become **boxes**: titled cards (`FilterBox`) holding chip groups or toggle chips; 44 px targets,
count on every chip (disjunctive facet counts), applied state mirrored in the URL (`?verified=1&deals=1&...`)
and in the applied-filter bar. Mobile: the same boxes inside the existing bottom-sheet drawer; desktop: sticky
sidebar. Applying a chip navigates (replace, `scroll: false`); no "Apply" button needed except price.

| Box          | Control                                                      | Param                                                     | Category page | Search |
| ------------ | ------------------------------------------------------------ | --------------------------------------------------------- | ------------- | ------ |
| Category     | chip group (child categories / facet paths)                  | `category_path`                                           | yes           | yes    |
| Price        | band chips (under K500, K500-2k, K2k-5k, over K5k) + min/max | `min_price`, `max_price` (kwacha in URL)                  | yes           | yes    |
| Seller       | toggle chips: Verified sellers, Made in Zambia               | `verified=1`, `made_in_zambia=1`                          | yes           | yes    |
| Nearby       | toggle: Near me (5 km) using the saved area or GPS           | `lat`, `lng`, `radius_km=5`                               | yes           | yes    |
| Deals        | toggle: Deals only                                           | `deals=1`                                                 | yes           | yes    |
| Availability | toggle: In stock                                             | `availability=in_stock` (catalog) / `in_stock=1` (search) | yes           | yes    |
| Rating       | chip group: 4+ stars, 3+ stars                               | `min_rating`                                              | yes           | yes    |
| Condition    | chip group                                                   | `condition`                                               | yes           | no     |

Made in Zambia is hidden until the claim API exists **and** at least one approved claim is in the result set.
Counts for a box ignore that box's own selection (disjunctive), as the existing facet code already does.
Search signal filters run on the ranked candidate window before pagination so `total` is exact.

## 4. Open questions

1. **Made in Zambia** depends on PR #973 (`vendor_listings.made_in_zambia_status`). Until it lands the signal
   and filter are absent by design. Confirm column name/values (`approved`) are final.
2. **Near you radius**: 5 km is a Lusaka-metro default; Copperbelt towns may want a larger radius. Per-city
   config in `platform_config`?
3. **Fast delivery** needs `lead_time_days` which many stocked listings leave empty, so the badge will be rare
   until vendors fill it (or logistics exposes a dispatch SLA per zone).
4. **Tier pricing** on cards: show "from K.. / 50+" only for verified business buyers (D28); confirm no consumer
   teaser is wanted (it would leak B2B price structure).
5. **Top rated** thresholds (5 reviews, 4.5) are guesses; revisit with real review volume.
6. **Home feed is location-free**; a per-shopper "Near you" rail would need a non-cached endpoint.
7. Bare `vendors.kyc_tier` is still used by the legacy "verified" sort and the PDP `verified` flag; they should
   move to approved tiers (follow-up, out of scope here).
