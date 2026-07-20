# Product discovery redesign — implementation plan

**Date:** 2026-07-20  
**Working branch:** `feat/customer-commerce-discovery`  
**Base SHA (from latest `master`):** `bbec8e8c66a4e196d5d4500622b6b75876c18a14`  
**Confirmed:** `git merge-base HEAD origin/master` == base SHA (branch cut from latest intended master).  
**Pre-checkout HEAD (prior agent branch):** `1afc911b4bedd014229d84f35bad859c7615428f` (not used as base).

## Findings (before edits)

### Established dependencies (do not replace)

- Design-system foundation (charcoal dark, fonts, tokens) — already on master.
- Nav + homepage redesign — already on master.
- PLP ProductCard Tailwind polish + SAMPLE gate + AppliedFilterBar (#361).
- Progressive load + Save-Data-aware Load more (#315).
- Sticky PDP ATC / compare (#363) — **out of scope** for this task.

### Current discovery surface

| Surface          | Route                | Strengths                                                               | Gaps vs audit                                                                               |
| ---------------- | -------------------- | ----------------------------------------------------------------------- | ------------------------------------------------------------------------------------------- |
| Category PLP     | `/c/[...slug]`       | Facets, sort, applied chips, progressive load, honest empty/unavailable | No child-category chips; no mobile filter drawer; result count quiet                        |
| Search           | `/search`            | Kind tabs, zero/unavailable/invalid, progressive tabs                   | Products use `SearchResultCard` not ProductCard; no product facets; weak commercial density |
| Categories index | `/categories`        | Tree + children                                                         | OK; light polish only                                                                       |
| ProductCard      | `@vergeo/ui`         | Tokenised; handlers optional                                            | No compact variant; search not reused; wishlist/compare unwired (no fake handlers)          |
| Analytics        | `search` event typed | Server search log exists                                                | Client `track("search")` unwired                                                            |

### Pagination (audit source of truth)

**Retain progressive cursor + Load more** (not infinite-scroll-only). Keep Save-Data button-only. Enhance: end-of-results copy, retry, aria-live (already present — tighten), stable keys (already listing id).

### Product-card strategy

**One composed `ProductCard` + thin adapters**, not boolean explosion:

- `ProductCard` (canonical) — media, title, price, rating, optional badge/actions.
- Optional density via `size?: "default" | "compact"` (layout only).
- `ListingGrid` maps catalog API → card.
- Search product hits map → same card when slug + price exist; keep compact row for non-product kinds.

### Honesty constraints

- No invented ratings, discounts, delivery ETAs, or seller badges.
- Wishlist only if persisted locally with real toggle UX (no server API yet) **or** omit control.
- SAMPLE badges stay production-gated.

## Implementation waves (this PR)

1. **Card system** — compact density; optional fulfillment pills only when `deliveryAvailable`/`pickupAvailable` exist on listing; local wishlist toggle via `localStorage` (honest, no fake API); compare link only when multi-offer signal exists (skip if no data).
2. **Category PLP** — child-category discovery strip; clearer product count; mobile filter drawer (Sheet) sharing FacetPanel state via URL; denser grid tokens.
3. **Search results** — product kind uses ProductCard grid; result count + query presentation; wire client `search` analytics when results resolve; keep empty/error honesty.
4. **States & a11y** — tighten loading skeletons, end-of-list, filter chip announcements; reduced-motion respect (existing utilities).
5. **Tests + browser verify** — card variants, filters, sort, empty/error, progressive end; lint/typecheck/build.

## Out of scope

- PDP redesign.
- Vendor/admin apps.
- Backend contract changes.
- Fake recommendations / recently viewed without storage design (recently-viewed rail deferred unless trivial localStorage rail fits).
