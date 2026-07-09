> **Prepend `prompts/_header.md` (PROJECT HEADER) above this prompt.** Branch from and PR against **`master`**. Wave 8 runs 10 pebbles in parallel — **touch ONLY your files below**. **⚠ SCHEMA FROZEN.** Stay dep-free. **Run the FULL `uv run pytest` before reporting.**

# M12-P04 — Listing management

## 1. Context

**Wave 8 (parallel ×10).** Grounded against as-built `master`:

- **Listing create merged (M12-P03):** `vendor_listings.py` (create/validate; `require_role('vendor')` + `require_listing_cap`). **Image manager merged (M12-P05):** `listings/_components/image-manager.tsx`. **Reservations merged (M07-P02):** `app/services/stock/revalidate.py` — a **price change must revalidate carts** via that hook. `vendor_listings(price_ngwee, stock_qty, stock_mode, condition, wholesale, price_tiers, moq, returnable, return_window_hours, status)`; **orders/order_items** exist (delete-guard checks open orders).
- Vendor app `localePrefix:"always"` → pages at **`apps/vendor/app/[locale]/listings/`** (spec's `app/listings/` is stale). M12-P03 (merged) owns `listings/new/`; you create `listings/page.tsx` (the list) + `listings/[id]/edit/`. API routers auto-discover (never edit `main.py`); service-role via `app.deps.get_supabase_client` (import-guard; local `Protocol`).
- **`vendor.json` shared with M12-P06 + M12-P09 this wave** — you own a nested **`listings.manage`** section (append-rule below).
  Spec: `docs/plan/02-pebbles/M12-vendor-portal.md` §M12-P04.

## 2. Objective & scope

Listing list (status/stock at a glance) + edit (price/stock/condition/returnable+window/tier prices, pause/unpause, delete-with-guard), stock quick-adjust, price-change cart revalidation, delete blocked with open orders.
**Non-goals:** no create (M12-P03), no images (M12-P05), no CSV (M12-P06), no new schema.

## 3. Files (create/modify ONLY these)

- **Create:** `apps/vendor/app/[locale]/listings/page.tsx` (list) · `listings/[id]/edit/page.tsx` (+ `_components/*`) · `services/api/app/routers/vendor_listings_manage.py` · `services/api/tests/test_listing_manage.py`
- **Modify:** `packages/i18n/messages/en/vendor.json` (add nested `listings.manage` section — append-rule)
  **Guardrail: nothing else. Do NOT touch `vendor_listings.py` (M12-P03), `image-manager.tsx` (M12-P05), `listings/new/` or `listings/import/` (M12-P06), `main.py`, schema.**

## 4. Implementation spec

- **`vendor_listings_manage.py`** (`require_role('vendor')` + ownership): list own listings; edit price/stock/condition/returnable+window/tier prices; **pause/unpause** (status); **delete-with-guard** — **blocked if the listing has open orders (pause instead)**. **Price change triggers cart revalidation** (M07-P02 hook). **Tier edits validated** (ascending qty, descending unit price — reuse `is_valid_price_tiers`). Vendor-scoped (A cannot edit B's listing → 403).
- **List page:** status + stock at a glance; stock quick-adjust (+/− steppers). **Edit page:** the fields above; edits reflect on PDP ≤1min (revalidate). All copy via `vendor` (`listings.manage.*`).

## 5–9. UI/UX · Responsiveness · Performance · SEO · Security

360px-first; vendor-scoped (cross-vendor edit denied — tested); price integer ngwee; no secrets.

## 10. Tests (RUN before reporting — full `uv run pytest` + ruff + mypy)

`test_listing_manage.py`: **delete-with-open-order guard** (blocked → pause); **tier validation** (ascending qty / descending price); **cart-revalidation trigger** on price change; **authz** (A cannot edit B). `pnpm --filter vendor build`, `pnpm typecheck`, `pnpm lint`, `pnpm test`. **Full API suite (import guard).**

## 11. Acceptance criteria / DoD

- [ ] Edits reflect on PDP ≤1min (revalidate); delete-guard correct (open orders → pause); tier edits validated.
- [ ] Cross-vendor edit denied; `listings.manage.*` nested (append-rule); full API suite + repo green.

## vendor.json rule (shared with M12-P06 + M12-P09 this wave)

Append ONLY your nested `listings.manage` section; do NOT reorder/reformat siblings. The later-merging vendor PR combines sections.

## 12. IMPLEMENTATION REPORT

**PEBBLE:** M12-P04 — Listing management
**STATUS/FILES/DEVIATIONS/TESTS** (paste delete-guard + tier-validation + revalidation + authz + full-pytest tail) **/EXCERPTS** the delete-guard + tier validation — nothing else **/QUESTIONS**
