> **Prepend `prompts/_header.md` (PROJECT HEADER) above this prompt.** Branch from and PR against **`master`**. Wave 8 runs 10 pebbles in parallel — **touch ONLY your files below**. **⚠ SCHEMA FROZEN.** Stay dep-free.

# M07-P03 — Cart UI

## 1. Context

**Wave 8 (parallel ×10).** Grounded against as-built `master`:

- **Cart backend is merged (M07-P01):** `services/api/app/routers/cart.py` — guest (signed httpOnly token) + authed cart, add/update/remove, per-vendor grouping, **server-computed totals**, merge-on-login. **Reservations/revalidation merged (M07-P02):** `app/services/stock/revalidate.py` returns price/stock change notices. **Call these — do NOT change the backend.**
- **PDP is merged (M05-P03):** the buy-box (`(shop)/_components/pdp/buy-box.tsx`) has a **disabled add-to-cart stub** you wire up. **Interface edge with M05-P04 (same wave):** M05-P04 owns `p/[slug]/page.tsx` (comparison + selected-listing state passed to the buy-box). **You own ONLY `buy-box.tsx`** (make the add-to-cart button functional using the listing prop it already receives) — do NOT touch `page.tsx` or `comparison.tsx`.
- The `(shop)` group + layout exist (M05-P01). i18n `checkout` namespace registered; **`checkout.json` is shared with M07-P04 this wave** — you own the **`cart`** section (append-rule below). Money via `formatK`; **all totals from the server** (never client-computed).
  Spec: `docs/plan/02-pebbles/M07-cart-checkout.md` §M07-P03.

## 2. Objective & scope

Vendor-grouped cart page + mini-cart drawer with per-group subtotals + delivery hints, free-delivery-≥K200 progress nudge, stock/price-change banners, empty state; and wiring add-to-cart into the PDP buy-box.
**Non-goals:** no checkout (M07-P04), no cart backend (M07-P01), no reservations (M07-P02 — surface its notices).

## 3. Files (create/modify ONLY these)

- **Create:** `apps/customer/app/[locale]/(shop)/cart/page.tsx` · `(shop)/_components/cart/{line-items,vendor-groups,qty-stepper,change-notices,mini-cart-drawer}.tsx`
- **Modify:** `apps/customer/app/[locale]/(shop)/_components/pdp/buy-box.tsx` (wire add-to-cart into the stub — M05-P03 built it, sequenced after that wave) · `packages/i18n/messages/en/checkout.json` (add a nested `cart` section — append-rule)
  **Guardrail: nothing else. Do NOT touch `p/[slug]/page.tsx`/`comparison.tsx` (M05-P04), `cart.py`, `checkout/*` (M07-P04), `main.py`, schema.**

## 4. Implementation spec

- **Cart page:** vendor-grouped line items with per-group subtotals + **delivery hints**, **free-delivery-≥K200 progress nudge** (from server totals), **stock/price change banners** (from M07-P02 revalidation notices), empty state. **All totals come from the server** cart response. Optimistic qty update with **rollback on API error**.
- **Mini-cart drawer:** count + summary, opens from nav.
- **Buy-box:** add-to-cart → `cart.py` add endpoint (guest token or authed); success feedback + mini-cart update. Uses the listing the buy-box already receives.
- All copy via `checkout` (`cart.*`); tokens; 360px one-handed.

## 5–9. UI/UX · Responsiveness · Performance · SEO · Security

360px one-handed; **guest cart persists across sessions** (httpOnly token); totals server-authoritative; no secrets.

## 10. Tests (RUN before reporting)

Component: render states (empty, changed prices, out-of-stock line); **optimistic qty update rollback on API error**; add-to-cart from buy-box; free-delivery nudge. i18n completeness `checkout.cart.*` (nested). `pnpm --filter customer build`, `pnpm typecheck`, `pnpm lint`, `pnpm test`.

## 11. Acceptance criteria / DoD

- [ ] All totals from server; 360px one-handed; guest cart persists.
- [ ] Change-notice banners render; optimistic rollback works; buy-box add-to-cart functional (buy-box only).
- [ ] `checkout.cart.*` nested (append-rule); repo green.

## checkout.json rule (shared with M07-P04 this wave)

Append ONLY your nested `cart` section; do NOT reorder/reformat siblings. The later-merging checkout PR combines sections.

## 12. IMPLEMENTATION REPORT

**PEBBLE:** M07-P03 — Cart UI
**STATUS/FILES/DEVIATIONS/TESTS** (paste render-states + optimistic-rollback + build) **/EXCERPTS** (none) **/QUESTIONS**
