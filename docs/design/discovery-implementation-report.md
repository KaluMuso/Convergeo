# Product discovery redesign — implementation report

## Base SHA

| Field                        | Value                                                                                                            |
| ---------------------------- | ---------------------------------------------------------------------------------------------------------------- |
| **Base SHA**                 | `bbec8e8c66a4e196d5d4500622b6b75876c18a14`                                                                       |
| **Branch**                   | `feat/customer-commerce-discovery`                                                                               |
| **Confirmed**                | Branch created from latest `origin/master`; `git merge-base HEAD origin/master` matched the base SHA at cut time |
| Pre-task HEAD (other branch) | `1afc911b4bedd014229d84f35bad859c7615428f` — not used as base                                                    |

Plan: [`discovery-implementation-plan.md`](./discovery-implementation-plan.md)

## Findings before implementation

- Design-system foundation, nav, and homepage already on master — retained.
- Canonical card already lives in `packages/ui` `ProductCard` (post-#361); search used a separate row card.
- Category PLP already had facets, sort, applied chips, progressive Load more + Save-Data.
- Gaps: no mobile filter drawer, no child-category strip, wishlist unwired, search products not on ProductCard grid, client `search` analytics unwired.
- Live/API drift in this VM: catalog/search/categories return unavailable (no Supabase/API) — same as production audit E08 class when API is down. UI honesty states retained.

## What changed

### Retained

- Progressive cursor + Load more (audit pagination strategy)
- AppliedFilterBar, SortBar, FacetPanel logic / URL sync
- SAMPLE production gate
- Empty vs unavailable separation
- Shop chrome / homepage / PDP (out of scope)

### Consolidated / extended

- **ProductCard** — `density`, `unavailable`, `meta` slots (no boolean explosion)
- **ListingCard** (client) + **ListingGrid** (RSC shell) — local wishlist via `localStorage`
- **Search** product hits → compact ProductCard grid; non-products keep row cards
- **MobileFilterDrawer** — Modal + FacetPanel; desktop sidebar `hidden lg:block`
- **ChildCategoryNav** — subcategory discovery on PLP
- **SearchAnalytics** — consent-aware `track("search")`

### Removed / avoided

- No fake ratings, discounts, delivery ETAs, or seller names on search hits (uses category or “Marketplace listing”)
- No quick-add without cart listing id (still omitted)
- No PDP redesign

## Files changed (primary)

- `packages/ui/src/product-card.tsx` (+ tests)
- `apps/customer/.../plp/{listing-grid,listing-card,use-local-wishlist,mobile-filter-drawer,child-category-nav,facet-panel}.*`
- `apps/customer/.../c/[...slug]/page.tsx`
- `apps/customer/.../search/{page.tsx,results-tabs.tsx,search-analytics.tsx,search-components.test.tsx}`
- `packages/i18n/messages/*/catalog.json` + `search.json`
- `docs/design/discovery-implementation-plan.md`, `discovery-implementation-report.md`, `evidence/discovery/*`

## Tests & build evidence

| Check                            | Result                                                                                                                                                         |
| -------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `@vergeo/ui` ProductCard tests   | 9 passed                                                                                                                                                       |
| Customer PLP + search unit tests | 37 passed                                                                                                                                                      |
| Customer `eslint`                | passed                                                                                                                                                         |
| Customer `tsc --noEmit`          | passed                                                                                                                                                         |
| `next build`                     | Type/lint phase OK; **prerender failed** on unrelated `/zh/help/how-escrow-works` (`PageNotFoundError` / `_document` Html) — not introduced by discovery files |

## Accessibility

- Wishlist `aria-pressed` + labels (save/remove)
- Filter modal uses shared `Modal` focus management
- Result counts use `aria-live="polite"`
- Child category links meet `min-h-11`
- Progressive load controls unchanged (announcements / retry / end)

## Performance observations

- Product grids still use reserved aspect ratios (4:3 / square compact)
- Search page max width widened to `lg:max-w-5xl` for product density
- Wishlist is localStorage-only — no extra network
- Client islands limited to listing cards, filter drawer, search tabs, analytics beacon

## Browser verification

Baselines / afters under `docs/design/evidence/discovery/` and `/opt/cursor/artifacts/screenshots/`.

API unavailable in this environment — verified chrome: mobile Filters control, desktop facet sidebar, search query chrome, honest unavailable empties.

## Known limitations

1. No live product data in this VM → cannot visually verify populated grids here.
2. Wishlist is device-local only (no sync / wishlist route yet — audit P4).
3. Search hits lack vendor/rating fields → card shows category or marketplace fallback; no invented seller/rating.
4. Customer production build currently blocked by unrelated marketing help prerender error.
5. Vercel preview may still be rate-limited.

## Recommended follow-ups

1. Wishlist account page + server sync when API exists.
2. Wire quick-add only with listing-id-backed cart API on PLP.
3. Recently viewed rail (localStorage) on home.
4. Cloudinary RSC image split (audit P2).
5. Fix marketing help prerender / build flake on master.
6. Populate staging catalog so visual QA can exercise real grids at 360/1366.
