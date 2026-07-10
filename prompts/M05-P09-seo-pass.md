> **Prepend `prompts/_header.md` (PROJECT HEADER) above this prompt.** Branch from and PR against **`master`**. Wave 9 runs 6 pebbles in parallel — **touch ONLY your files below**. **⚠ SCHEMA FROZEN.** Stay dep-free. **Run the FULL `uv run pytest` before reporting.**

# M05-P09 — SEO pass (JSON-LD, sitemaps, canonicals, OG)

## 1. Context

**Wave 9 (parallel ×6).** Grounded against as-built `master`:

- **All shop routes exist and MERGED** (W7–W8): `(shop)/{page.tsx (home), p/[slug], c/[...slug], search, v/[slug], directory, supplies, events, e/[slug]}` — **each already has a `generateMetadata`** you enrich (title/description/canonical + JSON-LD). You are the **sole editor of these `(shop)` route files in Wave 9** (no other W9 pebble touches them; M07-P05 owns only `checkout/*`). **Do NOT touch `checkout/*` (noindex) or `_components/*`.**
- **No customer `robots.ts`/`sitemap.ts`/`opengraph-image.tsx` exist yet** → you create them (no conflict). **No `packages/ui/src/seo/` exists** → you create `json-ld.tsx`. Data comes from the existing public reads (`products.py`, `directory.py`, `events_public.py`, `catalog.py`) — call them; **do not add endpoints or schema**.
- **Money in Offers:** prices are integer **ngwee** internally — JSON-LD `Offer.price` must be the **decimal-major ZMW** string (e.g. `123456` → `"1234.56"`), currency `ZMW`. Reuse the existing display/`formatK` conversion logic; **no float**.
- Locale: `localePrefix:"always"` — every route is under `[locale]/`. **Canonical URLs exclude filter/query params**; **no cross-locale canonical dupes** (each locale self-canonicals or uses hreflang — pick one and be consistent). Avoid a new i18n namespace / `request.ts` edit — derive metadata from **entity data + existing namespaces**.
  Spec: `docs/plan/02-pebbles/M05-catalog-search-discovery.md` §M05-P09.

## 2. Objective & scope

JSON-LD builders (Product+Offers, LocalBusiness, Event, BreadcrumbList, AggregateRating) injected on PDP/vendor/event pages; canonical URLs (params excluded, locale-consistent); dynamic chunked sitemaps (products/vendors/events/categories) + robots; an OG image template (name + price + brand colors).
**Non-goals:** no new data endpoints, no schema, no perf pass (M16), no checkout SEO (it's noindex).

## 3. Files (create/modify ONLY these)

- **Create:** `packages/ui/src/seo/json-ld.tsx` (Product/Offer/AggregateRating/LocalBusiness/Event/BreadcrumbList builders — pure, unit-testable) · `apps/customer/app/sitemap.ts` · `apps/customer/app/robots.ts` · `apps/customer/app/[locale]/(shop)/opengraph-image.tsx` · a unit test for the builders (e.g. `packages/ui/src/seo/json-ld.test.tsx`)
- **Modify (generateMetadata + JSON-LD injection ONLY — do NOT alter page logic/data fetching):** `(shop)/page.tsx`, `(shop)/p/[slug]/page.tsx`, `(shop)/c/[...slug]/page.tsx`, `(shop)/search/page.tsx`, `(shop)/v/[slug]/page.tsx`, `(shop)/directory/page.tsx`, `(shop)/supplies/page.tsx`, `(shop)/events/page.tsx`, `(shop)/e/[slug]/page.tsx`
  **Guardrail: nothing else. Do NOT touch `checkout/*`, `_components/*`, API routers, `main.py`, `request.ts`, schema, or other namespaces.**

## 4. Implementation spec

- **`json-ld.tsx`:** typed builders returning JSON-LD objects; **`Offer.price` = decimal-major ZMW string from ngwee** (exact, no float), `priceCurrency:"ZMW"`; Product from canonical product + its listings' offers; LocalBusiness from vendor (name/logo/location); Event from event + instances; BreadcrumbList from category path. Injected as `<script type="application/ld+json">` on the relevant server pages.
- **Metadata:** each `generateMetadata` gets title/description + a **canonical** that **strips query/filter params** and is locale-consistent (no dup canonicals across locales). PDP/vendor/event get their JSON-LD; list pages get BreadcrumbList where relevant.
- **`sitemap.ts`:** dynamic, **chunked** across products/vendors/events/categories (from the public reads), valid + gzip-friendly. **`robots.ts`:** allow indexable routes, disallow `checkout`/account/admin-ish paths. **`opengraph-image.tsx`:** name + price + brand colors (design tokens).

## 5–9. UI/UX · Responsiveness · Performance · SEO · Security

Rich Results-valid Product/Event/LocalBusiness; canonical de-dup; public reads only; ngwee→ZMW exact (no float); no secrets.

## 10. Tests (RUN before reporting)

`json-ld.test.*`: **ngwee→ZMW decimal in Offer correct** (`123456`→`"1234.56"`, odd ngwee, 0); Product/Event/LocalBusiness shape goldens; BreadcrumbList from a category path; **canonical strips params** (unit). `pnpm --filter customer build` (sitemap/robots/OG compile + routes still render), `pnpm typecheck`, `pnpm lint`, `pnpm test`. **Full `uv run pytest`** (no API change expected — just confirm green).

## 11. Acceptance criteria / DoD

- [ ] JSON-LD valid for Product/Event/LocalBusiness fixtures; Offer price = exact ZMW decimal from ngwee.
- [ ] Sitemap valid + chunked; robots correct; canonicals strip params with no cross-locale dupes.
- [ ] Only `generateMetadata`/JSON-LD added to the 9 shop pages (no logic change); repo green.

## 12. IMPLEMENTATION REPORT

**PEBBLE:** M05-P09 — SEO pass
**STATUS/FILES/DEVIATIONS** (note the canonical/hreflang locale strategy chosen) **/TESTS** (paste Offer-ngwee→ZMW + canonical-strip + build) **/EXCERPTS** the ngwee→ZMW Offer builder — nothing else **/QUESTIONS**
