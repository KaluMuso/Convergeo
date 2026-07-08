> **Prepend `prompts/_header.md` (PROJECT HEADER) above this prompt.** Branch from and PR against **`master`**. Wave 6 runs 8 pebbles in parallel — **touch ONLY your files below**. **⚠ SCHEMA FROZEN → additive-only: you add ONE new migration `0012_carts.sql` (new tables only). You are the SOLE `db.ts` editor this wave** (append `carts`+`cart_items`).

# M07-P01 — Cart domain & API

## 1. Context

**Wave 6 (parallel ×8).** Grounded against as-built `master`:

- **`public.vendor_listings`** (grep `0003`/`0005` for exact columns): `id, product_id, vendor_id, title_override, price_ngwee bigint, wholesale, status, stock_qty` (+ tier/MOQ fields for wholesale — confirm exact names before coding). **`stock_reservations`** exists (`0005`). **Money = integer ngwee** everywhere; totals server-computed with `Decimal`-free integer math.
- API: routers auto-discover (never edit `main.py`); `core/auth.py` (`get_current_user` — optional for guest cart), user-token client (RLS), service-role confined to `app/supabase_client.py`. Error envelope standard.
- Migration numbering: last is `0011_rate_counters.sql` → yours is **`0012_carts.sql`**. New tables need RLS + `FORCE` + `session_user` guard + owner-scoped policies (guest via signed token claim, user via `auth.uid()`).
- **`app/services/` does NOT exist** — create `app/services/cart/` (own `__init__.py`); **do NOT create `app/services/__init__.py`** (implicit namespace package; siblings added in parallel).
  Spec: `docs/plan/02-pebbles/M07-cart-checkout.md` §M07-P01. **Non-goal:** stock reservation/oversell (M07-P02) — cart only computes/validates, does not claim stock.

## 2. Objective & scope

Guest (signed httpOnly token) + authed carts, merge-on-login, per-vendor grouping, MOQ enforcement for wholesale, server-computed ngwee totals.
**Non-goals:** no reservations/oversell (M07-P02), no checkout/payment (M08), no cart UI.

## 3. Files (create/modify ONLY these)

- **Create:** `supabase/migrations/0012_carts.sql` · `supabase/tests/0012_carts.test.sql` · `services/api/app/routers/cart.py` · `services/api/app/services/cart/__init__.py` + `{merge,grouping,totals}.py` · `services/api/tests/test_cart.py`
- **Modify:** `packages/types/src/db.ts` (**append** `carts` + `cart_items` only — no sibling reformatting; CI drift-check will validate once Actions is restored)
  **Guardrail: nothing else. Do NOT create `app/services/__init__.py`, edit `main.py`, touch other migrations, or other pebbles' files.**

## 4. Implementation spec

- **`0012_carts.sql`:** `carts(id uuid pk, user_id uuid null references auth.users, guest_token text null, status text check in ('active','converted','abandoned') default 'active', created_at, updated_at, check (user_id is not null or guest_token is not null))`; `cart_items(id, cart_id references carts on delete cascade, listing_id references vendor_listings, qty int check (qty > 0), unit_price_ngwee bigint, wholesale bool default false, created_at, updated_at, unique(cart_id, listing_id))`. Indexes (cart_id, user_id, guest_token). RLS + FORCE + guard: **user reads/writes own (`user_id = auth.uid()`); guest via the signed token** (matched against a claim/param — service-role for guest ops if needed). Comment each policy.
- **`cart.py`:** add/update/remove item, get cart (with per-vendor grouping + server-computed totals), **merge-on-login** (`POST /cart/merge`): qty-sum duplicates, refresh prices from `vendor_listings`, surface conflicts; guest cart via signed httpOnly token (issue/read). **MOQ enforcement** for wholesale lines (reject with i18n error code + `retry`); **tier-price selection by qty** (pick the right wholesale tier). Totals in integer ngwee (no float).
- **`services/cart/`:** `merge` (guest+user matrices), `grouping` (per-vendor + per-group delivery eligibility flag), `totals` (integer ngwee).

## 5–9. UI/UX · Responsiveness · Performance · SEO · Security

N/A UI. **Security:** RLS — only owner reads their cart (tested); guest token signed httpOnly (not guessable); prices/totals server-computed (never trust client prices); no float money.

## 10. Tests (RUN before reporting)

`0012_carts.test.sql`: migrations `0001→0012` apply clean; RLS — owner reads own cart, stranger denied; check constraint (user_id or guest_token). `test_cart.py`: **merge matrix** (guest-only, both, dupes → qty-sum + price refresh + conflict surfaced); **MOQ boundaries** (violating qty → i18n error); **tier-price selection by qty**; **authz** (user A cannot read user B's cart). Append `db.ts`; `pnpm --filter @vergeo/types typecheck`. `uv run pytest`, `ruff`, `mypy`.

## 11. Acceptance criteria / DoD

- [ ] `0012` applies clean in sequence; carts/cart_items RLS owner-scoped.
- [ ] Merge preserves both carts' items (qty-sum, price-refreshed, conflicts surfaced); MOQ-violating qty rejected; totals integer ngwee.
- [ ] Only owner reads cart (tested); db.ts appended; repo green.

## 12. IMPLEMENTATION REPORT

Output exactly:
**PEBBLE:** M07-P01 — Cart domain & API
**STATUS:** COMPLETE | PARTIAL | BLOCKED
**FILES:** each path + one-line description
**DEVIATIONS:** (or "none") — note exact wholesale/MOQ/tier columns you grounded
**TESTS:** paste migration apply + merge-matrix + MOQ + authz output
**EXCERPTS:** the carts/cart_items RLS policies + the merge routine — nothing else
**QUESTIONS:** (or "none")
