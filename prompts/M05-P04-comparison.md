> **Prepend `prompts/_header.md` (PROJECT HEADER) above this prompt.** Branch from and PR against **`master`**. Wave 8 runs 10 pebbles in parallel — **touch ONLY your files below**. **⚠ SCHEMA FROZEN** (no migrations, no `db.ts`). Stay dep-free. **Run the FULL API suite (`uv run pytest`, not just your test file) before reporting** — the service-role import guard is repo-wide.

# M05-P04 — Multi-vendor comparison

## 1. Context

**Wave 8 (parallel ×10).** Grounded against as-built `master`:

- **PDP is merged (M05-P03):** `apps/customer/app/[locale]/(shop)/p/[slug]/page.tsx` + `(shop)/_components/pdp/{gallery,buy-box,specs-table,vendor-block,condition-badge}.tsx`. The page fetches `GET /products/{slug}` (`products.py`) → canonical product + its **active listings** with buy-box + vendor data. The buy-box renders a **selected listing**.
- **Interface edge with M07-P03 (same wave, cart UI):** M07-P03 modifies **`buy-box.tsx`** (add-to-cart wiring). **You do NOT touch `buy-box.tsx`.** You own `p/[slug]/page.tsx` (add the comparison block + manage the "selected listing" state passed to the buy-box) + a new `comparison.tsx`. So: your comparison's "select" updates the page's selected-listing state → the buy-box re-renders that listing (buy-box already takes a listing prop); M07-P03's cart-add uses whatever listing the buy-box is given. Disjoint files.
- API: routers auto-discover (never edit `main.py`); service-role client via **`app.deps.get_supabase_client`** (do NOT `from app.supabase_client import …` — repo import guard); type it with a local `Protocol` (`.client`). `vendor_listings(product_id, vendor_id, price_ngwee, condition, status)` + `vendors(status, display_name, preferred_badge, lat/lng or address)`. Suspended-vendor listings excluded.
  Spec: `docs/plan/02-pebbles/M05-catalog-search-discovery.md` §M05-P04.

## 2. Objective & scope

"N vendors selling this" on the PDP: a table of all active listings for the canonical product — price (`formatK`), condition, distance from the user (geolocation opt-in, fallback Lusaka CBD), vendor rating/badges, delivery/pickup availability; sort by price/distance; **selecting a row swaps the buy box** (via page state).
**Non-goals:** no cart-add (M07-P03 owns buy-box), no PDP core (M05-P03), no SEO pass (M05-P09).

## 3. Files (create/modify ONLY these)

- **Create:** `apps/customer/app/[locale]/(shop)/_components/pdp/comparison.tsx` · `services/api/app/routers/comparison.py` · `services/api/tests/test_comparison.py`
- **Modify:** `apps/customer/app/[locale]/(shop)/p/[slug]/page.tsx` (render `<Comparison>` + hold the selected-listing state passed to the buy-box) · `packages/i18n/messages/en/catalog.json` (add a nested `comparison` section — you are the only W8 pebble touching catalog.json)
  **Guardrail: nothing else. Do NOT touch `buy-box.tsx` (M07-P03), `products.py`/`catalog.py`, `main.py`, schema/db.ts, or other namespaces.**

## 4. Implementation spec

- **`comparison.py`** `GET /products/{slug}/comparison` (or `/comparison?product_id=`): active listings for the canonical product, joined to vendors (name, badges, rating, location); **only active listings of active vendors** (suspended excluded); returns price_ngwee, condition, vendor block, delivery/pickup flags, and lat/lng for client-side distance. **EXPLAIN uses the `product_id` index** (paste the plan).
- **`comparison.tsx`:** table of listings; **distance** computed client-side from geolocation (opt-in; **fallback Lusaka CBD** if denied); **sort by price / distance** (stable); each row selectable → calls an `onSelect(listingId)` prop. **Single-listing products hide the block.**
- **`page.tsx`:** lift the "selected listing" to page state; render `<Comparison onSelect=…>`; pass the selected listing to the existing buy-box.
- All copy via `catalog` (`comparison.*`); tokens; 360px-first.

## 5–9. UI/UX · Responsiveness · Performance · SEO · Security

360px-first; distance opt-in with fallback; public read; only active listings/vendors surface; no secrets.

## 10. Tests (RUN before reporting — `uv run pytest` FULL SUITE + ruff + mypy)

`test_comparison.py`: **ordering** (price, distance) stable + correct; **distance fallback** (no geo → Lusaka CBD); **suspended-vendor listings excluded**; single-listing → block hidden (component). EXPLAIN uses `product_id` index (paste). Component: select swaps buy-box (page state). `pnpm --filter customer build`, `pnpm typecheck`, `pnpm lint`, `pnpm test`. **Full `uv run pytest` (import guard).**

## 11. Acceptance criteria / DoD

- [ ] Comparison lists active listings (suspended excluded); sorts stable; single-listing hides block.
- [ ] Select swaps the buy-box via page state (buy-box untouched); EXPLAIN uses product_id index.
- [ ] `catalog.comparison.*` nested; full API suite (incl. import guard) green; repo green.

## 12. IMPLEMENTATION REPORT

**PEBBLE:** M05-P04 — Multi-vendor comparison
**STATUS/FILES/DEVIATIONS/TESTS** (paste ordering + suspended-excluded + EXPLAIN + full-pytest tail) **/EXCERPTS** (none) **/QUESTIONS**
