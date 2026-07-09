> **Prepend `prompts/_header.md` (PROJECT HEADER) above this prompt.** Branch from and PR against **`master`**. Wave 7 runs 8 pebbles in parallel — **touch ONLY your files below**. **⚠ SCHEMA FROZEN** (no migrations, no `db.ts`). Stay dep-free.

# M05-P02 — Category browse & PLP

## 1. Context

**Wave 7 (parallel ×8).** Grounded against as-built `master`:

- **The `(shop)` route group + its `layout.tsx` are created by M05-P01** (same wave). You add pages UNDER `(shop)/` — do NOT create `(shop)/layout.tsx` or `(shop)/page.tsx`. If M05-P01 hasn't merged when you branch, your pages still render (they fall back to `[locale]/layout.tsx`); note the edge.
- **Catalog schema (`0003`) — grep exact columns before coding:** `products(id, name, category_id, aliases text[], spec jsonb, status, slug …)`, `vendor_listings(id, vendor_id, product_id, title_override, price_ngwee bigint, condition, stock_mode, stock_qty, wholesale, price_tiers, moq, returnable, status …)`, `categories(materialized path, slug, …)`, `listing_images`. Publish states: products `'active'`, listings `'active'`. **Nearest sort** uses `lat/lng` — the searchable projection is `search_documents` (`0009`, has `lat/lng`, `category_path`, `price_min/max_ngwee`); prefer querying via it or a catalog SQL that filters `is_public`/`active`.
- API: routers auto-discover (never edit `main.py`); optional auth OK (public browse); error envelope standard.
- i18n: **`catalog` namespace** shared this wave — you own the `plp` section (catalog.json rule below).
  Spec: `docs/plan/02-pebbles/M05-catalog-search-discovery.md` §M05-P02.

## 2. Objective & scope

Category browse + PLP: `GET` list endpoint with server-driven facet counts + sorts, and the PLP page (facet panel, sort bar, listing grid, load-more), URL-encoded shareable/SEO-safe filter state.
**Non-goals:** no PDP (M05-P03), no home (M05-P01), no search page (M05-P06 — this is category browse), no cart.

## 3. Files (create/modify ONLY these)

- **Create:** `apps/customer/app/[locale]/(shop)/c/[...slug]/page.tsx` · `(shop)/_components/plp/{facet-panel,sort-bar,listing-grid,load-more}.tsx` · `services/api/app/routers/catalog.py` · `services/api/tests/test_catalog.py`
- **Modify:** `packages/i18n/messages/en/catalog.json` (add nested `plp` section — catalog.json rule)
  **Guardrail: nothing else. Do NOT touch `(shop)/layout.tsx`/`page.tsx` (M05-P01), `products.py` (M05-P03), `main.py`, schema/db.ts, or other namespaces.**

## 4. Implementation spec

- **`catalog.py`** `GET /catalog` (or `/catalog/listings`): filters — category (by `path` prefix), price range, location, rating, availability, condition; **server-computed facet counts**; sorts — **relevance, cheapest, nearest (lat/lng haversine ordering), newest**; **load-more** (cursor/offset) pagination; only public/active rows. Injection-safe (bound params).
- **PLP page** (`c/[...slug]`, server, ISR/SSR + SEO): facet panel + sort bar + listing grid (cards from `@vergeo/ui`, price via `formatK`) + load-more; **filter state URL-encoded** (query params) so reload/share restores it; category slug from the `[...slug]` path → category `path`.
- All copy via `catalog` (`plp.*`); tokens only; 360px-first; images data-frugal (srcset, lazy below fold).

## 5–8. UI/UX · Responsiveness · Performance · SEO

360px-first; **PLP LCP ≤2.5s** (lab); URL-state SEO-safe + shareable; server-driven counts.

## 9. Security

Public read only; injection-safe queries; only active/public listings surface; no secrets.

## 10. Tests (RUN before reporting — seed via `scripts/seed.py`/fixtures)

`test_catalog.py`: **facet counts correct** on seed incl. empty-result; **sort-by-distance ordering** (lat/lng); newest/cheapest ordering; filter combinations compose; injection-safe. Component: **URL filter-state round-trip** (encode→decode restores). `pnpm --filter customer build`, `pnpm typecheck`, `pnpm lint`, `pnpm test`; `uv run pytest`, `ruff`, `mypy`.

## 11. Acceptance criteria / DoD

- [ ] Facet math correct (incl. empty); distance sort orders by lat/lng; load-more paginates.
- [ ] Filter state survives reload/share (URL-encoded); PLP LCP ≤2.5s lab.
- [ ] `catalog.plp.*` nested; only public listings; repo + API green.

## catalog.json rule (shared with M05-P01 + M05-P03 this wave)

Append ONLY your nested `plp` section; do NOT reorder/reformat siblings. The later-merging shop PR combines sections.

## 12. IMPLEMENTATION REPORT

Output exactly:
**PEBBLE:** M05-P02 — Category browse & PLP
**STATUS:** COMPLETE | PARTIAL | BLOCKED
**FILES:** each path + one-line description
**DEVIATIONS:** (or "none") — note exact columns/projection you queried
**TESTS:** paste facet-count + distance-sort + URL-roundtrip + build output
**EXCERPTS:** the facet-count + distance-sort SQL/query in `catalog.py` — nothing else
**QUESTIONS:** (or "none")
