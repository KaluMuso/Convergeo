> **Prepend `prompts/_header.md` (PROJECT HEADER) above this prompt.** Branch from and PR against **`master`**. Wave 7 runs 8 pebbles in parallel — **touch ONLY your files below**. **⚠ SCHEMA FROZEN** (no migrations, no `db.ts`). Stay dep-free.

# M05-P03 — PDP core

## 1. Context

**Wave 7 (parallel ×8).** Grounded against as-built `master`:

- **The `(shop)` group + `layout.tsx` come from M05-P01** — add pages under `(shop)/`, do NOT create the layout/home.
- **Catalog schema (`0003`) — grep exact columns:** `products(id, name, slug, category_id, spec jsonb, aliases, status …)`, `vendor_listings(id, product_id, vendor_id, title_override, price_ngwee, condition, stock_mode, stock_qty, wholesale, status …)`, `listing_images(listing_id, url/public_id, position, is_cover …)`, `vendors(display_name, slug, preferred_badge, …)`. A **merged-product redirect**: check for a moderation/merge pointer (grep `0003`/`0013` for a `merged_into`/redirect column; if none, 404 for unknown slug).
- `@vergeo/ui` has the **ImageGallery** (M02-P08) + cards/badges; price via **`formatK`** (`@vergeo/i18n`). Deep imports.
- API: routers auto-discover (never edit `main.py`).
- i18n: **`catalog` namespace** shared — you own the `pdp` section (catalog.json rule).
  Spec: `docs/plan/02-pebbles/M05-catalog-search-discovery.md` §M05-P03.

## 2. Objective & scope

Canonical product page: gallery (≤8), spec table (from `spec` jsonb), selected-listing **buy box** (price via formatK, stock state, qty stepper, add-to-cart CTA **stub**), vendor block. ISR with on-demand revalidate.
**Non-goals:** no add-to-cart wiring (M07-P03 — CTA is a stub), no comparison (M05-P04), no reviews list (M15), no PLP/home/search.

## 3. Files (create/modify ONLY these)

- **Create:** `apps/customer/app/[locale]/(shop)/p/[slug]/page.tsx` · `(shop)/_components/pdp/{gallery,buy-box,specs-table,vendor-block,condition-badge}.tsx` · `services/api/app/routers/products.py` · `services/api/tests/test_products.py`
- **Modify:** `packages/i18n/messages/en/catalog.json` (add nested `pdp` section — catalog.json rule)
  **Guardrail: nothing else. Do NOT touch `(shop)/layout.tsx`/`page.tsx` (M05-P01), `catalog.py` (M05-P02), `main.py`, schema/db.ts, or other namespaces.**

## 4. Implementation spec

- **`products.py`** `GET /products/{slug}`: return the canonical product + its `spec`, images (≤8, ordered, cover first), and its **active listings** with buy-box data (price, condition, stock_mode/stock_qty, vendor block: display_name, badge, rating, location/landmark). **404 for unknown; redirect (301) if the product was merged** into another canonical (if a merge pointer exists).
- **PDP page** (`p/[slug]`, server, **ISR + on-demand revalidate** on listing change): ImageGallery (`@vergeo/ui`), specs table from jsonb, buy box for the selected listing (price `formatK`, stock state, qty stepper, **add-to-cart CTA stub** — a disabled/placeholder button wired by M07-P03), vendor block, condition badge. **Out-of-stock + single-vendor states correct.**
- All copy via `catalog` (`pdp.*`); tokens only; 360px layout matches design.

## 5–8. UI/UX · Responsiveness · Performance · SEO

360px-first; ISR + on-demand revalidate; SEO product page (metadata, schema.org Product where sensible); gallery lazy.

## 9. Security

Public read; only active listings + published product shown; no secrets; escape user-authored fields.

## 10. Tests (RUN before reporting)

`test_products.py`: **render states** — in-stock, out-of-stock, no-reviews, quick-list-without-canonical; **404 unknown**; **merged-product 301 redirect** (if merge pointer exists — else document 404). Component: buy-box stock/qty states. `pnpm --filter customer build`, `pnpm typecheck`, `pnpm lint`, `pnpm test`; `uv run pytest`, `ruff`, `mypy`.

## 11. Acceptance criteria / DoD

- [ ] PDP renders gallery/specs/buy-box/vendor; out-of-stock + single-vendor states correct at 360px.
- [ ] ISR + on-demand revalidate on listing change; 404/merge-redirect correct.
- [ ] Add-to-cart is a stub (M07-P03); `catalog.pdp.*` nested; repo + API green.

## catalog.json rule (shared with M05-P01 + M05-P02 this wave)

Append ONLY your nested `pdp` section; do NOT reorder/reformat siblings. The later-merging shop PR combines sections.

## 12. IMPLEMENTATION REPORT

Output exactly:
**PEBBLE:** M05-P03 — PDP core
**STATUS:** COMPLETE | PARTIAL | BLOCKED
**FILES:** each path + one-line description
**DEVIATIONS:** (or "none") — state whether a merge-redirect column exists
**TESTS:** paste render-states + 404/redirect + build output
**EXCERPTS:** none expected — state "none"
**QUESTIONS:** (or "none")
