# Phase 4.2 — Product-detail & seller comparison

**Base SHA:** `bbec8e8c66a4e196d5d4500622b6b75876c18a14` (`master` / `origin/master`)  
**Working branch:** `cursor/customer-pdp-redesign-077d`  
**PR:** https://github.com/KaluMuso/Convergeo/pull/371  
**Audit refs:** `docs/design/vergeo5-ui-ux-audit.md` §4.4, E10, P1 sticky ATC + mobile compare cards

## Baseline (pre-edit)

Sticky mobile ATC and mobile seller compare cards already shipped on `master`
(`403a42e`). Live audit baseline: `before-live-product-detail-1366.png` (from
`docs/design/evidence/live-product-detail-1366.png`).

## Layout decisions

| Viewport | Composition                                                                                                                                                                                                                    |
| -------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Mobile   | Breadcrumbs → brand/title/seller count → gallery → buy box (price/stock/seller/qty/ATC/wishlist/compare) → trust → seller cards (multi only) → vendor → tabs → related → recently viewed → sticky ATC when buy box leaves view |
| Desktop  | Breadcrumbs + title full width; gallery \| sticky buy box + trust; full-width compare table; vendor; tabs; related; recently viewed                                                                                            |

Seller comparison stays **inline** (cards on mobile, table on desktop) plus the
existing `/compare` route entry — no drawer. Comparison UI is omitted when
`listing_count ≤ 1`.

## Components introduced / consolidated

| Component                                | Role                                                 |
| ---------------------------------------- | ---------------------------------------------------- |
| `NoSellersPanel`                         | Honest zero-offer state                              |
| `PdpWishlistButton` + `wishlist-storage` | Local wishlist near ATC                              |
| `RelatedProducts`                        | Shared `ProductCard` rail                            |
| `RecentlyViewedRail` + storage           | Local recently viewed                                |
| `buildOfferPriceContext`                 | Lowest / delta framing (live offers only)            |
| Buy box enhancements                     | `PriceBlock`, seller summary, compare, wishlist slot |
| `ImageGallery`                           | `prefers-reduced-motion` scroll                      |

## After screenshots (local mock API)

- `pdp-multi-seller-1366.png` / `pdp-multi-seller-360.png`
- `pdp-seller-selected-1366.png`
- `pdp-sticky-atc-360.png`
- `pdp-one-seller-1366.png`
- `pdp-no-sellers-1366.png`

Artifacts also under `/opt/cursor/artifacts/pdp-after/`.

## Known data limitations

- No compare-at / previous price on API → no savings chip.
- No product-level aggregate rating → seller ratings only.
- No variants / buy-now.
- Wishlist and recently viewed are localStorage only.
- Related API is thin (no vendor/rating) → `ProductCard` uses honest no-reviews.

## Remaining conversion / UX risks

- Live Cloudinary / cart API health still gates real conversion (audit E09).
- Sticky ATC competes with bottom nav height on small phones — verify on device.
- Category breadcrumb not wired (`category_id` present; slug resolution deferred).

## Recommended next PR

Wishlist route + server sync seam, or category-aware PDP breadcrumbs once category
slug lookup is cheap on the product payload.
