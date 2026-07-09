> **Prepend `prompts/_header.md` (PROJECT HEADER) above this prompt.** Branch from and PR against **`master`**. Wave 8 runs 10 pebbles in parallel — **touch ONLY your files below**. **⚠ SCHEMA FROZEN.** Stay dep-free.

# M05-P07 — Supplies tab

## 1. Context

**Wave 8 (parallel ×10).** Grounded against as-built `master`:

- **PLP + catalog API merged (M05-P02):** `GET /catalog/listings` (`catalog.py`) with facets/sorts/pagination over `search_documents` + `vendor_listings`. **Reuse it with a `wholesale=true` filter** — do NOT touch `catalog.py` (M05-P02 owns it). If the endpoint lacks a wholesale filter, call it and filter client-side on the returned `wholesale` flag, and note it in the report (a later catalog pebble can add the server filter).
- `vendor_listings(wholesale bool, price_tiers jsonb, moq int, price_ngwee)`. `@vergeo/ui` has **TierPriceTable** (M02-P04). The `(shop)` group + layout exist (M05-P01).
- i18n `supplies` namespace is registered; `packages/i18n/messages/en/supplies.json` exists — **you solely own it** (nest, no flat keys).
  Spec: `docs/plan/02-pebbles/M05-catalog-search-discovery.md` §M05-P07.

## 2. Objective & scope

A PLP variant filtered to `wholesale=true`: TierPriceTable display, MOQ badges, qty-aware price preview ("120 × K85 = K10,200"), business-y sort; links into PDP with tier context.
**Non-goals:** no cart/MOQ enforcement (M07 — display messaging only), no catalog API changes (reuse), no new schema.

## 3. Files (create/modify ONLY these)

- **Create:** `apps/customer/app/[locale]/(shop)/supplies/page.tsx` · `(shop)/_components/supplies/{tier-price-cards,moq-badge,qty-price-preview}.tsx`
- **Modify:** `packages/i18n/messages/en/supplies.json` (nest + fill)
  **Guardrail: nothing else. Do NOT touch `catalog.py`/`catalog.json`, `(shop)/layout.tsx`, `main.py`, schema, or other namespaces.**

## 4. Implementation spec

- Supplies page: reuse `/catalog/listings` filtered to wholesale; render `@vergeo/ui` TierPriceTable, **MOQ badges**, **qty-aware price preview** (integer ngwee math, `formatK`; e.g. `120 × K85 = K10,200` — exact, no float); **business sort** (MOQ, unit price at qty); each card links to the PDP with tier context (query param). **Non-wholesale listings never appear.** Surface the **T2-only-sellers** rule (informational). All copy via `supplies` namespace.

## 5–9. UI/UX · Responsiveness · Performance · SEO · Security

360px-first; data-frugal; public read; tier math **exact in ngwee** (review-blocking if float); no secrets.

## 10. Tests (RUN before reporting)

Component: **tier-price selection at boundary qtys** (min, between tiers, huge) exact in ngwee; **non-wholesale listings never appear**; MOQ badge + qty preview render. i18n completeness `supplies.*` (nested). `pnpm --filter customer build`, `pnpm typecheck`, `pnpm lint`, `pnpm test`.

## 11. Acceptance criteria / DoD

- [ ] Tier math exact in ngwee at boundary qtys; MOQ messaging surfaced; wholesale-only.
- [ ] `supplies.json` nested; links into PDP with tier context; repo green.

## 12. IMPLEMENTATION REPORT

**PEBBLE:** M05-P07 — Supplies tab
**STATUS/FILES/DEVIATIONS** (note how you filtered wholesale) **/TESTS** (paste tier-boundary + wholesale-only) **/EXCERPTS** (none) **/QUESTIONS**
