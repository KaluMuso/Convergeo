# Phase 4.2 — Product-detail & seller comparison

**Base SHA:** `bbec8e8c66a4e196d5d4500622b6b75876c18a14` (`master` / `origin/master`)  
**Working branch:** `cursor/customer-pdp-redesign-077d`  
**Audit refs:** `docs/design/vergeo5-ui-ux-audit.md` §4.4, E10, P1 sticky ATC + mobile compare cards

## Baseline (pre-edit)

Sticky mobile ATC and mobile seller compare cards already shipped on `master`
(`403a42e`). This PR focuses on conversion hierarchy, honest offer states,
gallery/motion polish, related cards, local wishlist + recently viewed, and
tests.

Live reference: https://vergeo5.com/en/p/tecno-spark-20 (and seed products).

## Implementation plan

### Layout

| Viewport | Composition                                                                                                                                                                                                       |
| -------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Mobile   | Breadcrumbs → brand/title → gallery → buy box (price/stock/seller/qty/ATC/wishlist/compare) → trust → seller cards (multi only) → vendor → tabs → related → recently viewed → sticky ATC when buy box leaves view |
| Desktop  | Breadcrumbs + title full width; gallery \| sticky buy box + trust; full-width compare table; vendor; tabs; related; recently viewed                                                                               |

### Honest data rules

- No previous-price / savings without API compare-at fields.
- No product-level star aggregate (API has seller ratings only) — surface selected seller rating near purchase when present.
- No variants / buy-now (unsupported).
- No comparison UI when `listing_count ≤ 1`.
- Dedicated empty when zero listings; keep API-unavailable EmptyState.

### Components

| Change                                           | Notes                                          |
| ------------------------------------------------ | ---------------------------------------------- |
| Visible `Breadcrumbs`                            | Home → product name (JSON-LD already present)  |
| `NoSellersPanel`                                 | Zero-listing honesty                           |
| Buy box seller summary + compare link + wishlist | Wishlist = localStorage only                   |
| Comparison preference chips                      | Lowest price / selected — real deltas only     |
| Related rail → `ProductCard`                     | Thin data: price + no-reviews                  |
| `RecentlyViewedRail`                             | localStorage, exclude current                  |
| Gallery                                          | `prefers-reduced-motion` scroll; clearer empty |
| Loading skeleton                                 | Title before gallery (matches mobile order)    |

### Out of scope

Cart/checkout redesign, payment logic, inventing delivery ETAs, wishlist server sync.
