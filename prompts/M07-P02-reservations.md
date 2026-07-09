> **Prepend `prompts/_header.md` (PROJECT HEADER) above this prompt.** Branch from and PR against **`master`**. Wave 7 runs 8 pebbles in parallel — **touch ONLY your files below**. **⚠ SCHEMA FROZEN — no migration** (tables exist). Stay dep-free.

# M07-P02 — Stock revalidation & reservations (race-critical)

## 1. Context

**Wave 7 (parallel ×8).** Grounded against as-built `master` — **use existing tables, no migration:**

- **`public.vendor_listings`** (`0003`): `id, stock_mode ('tracked'|'always_available'), stock_qty integer (null-allowed), price_ngwee, status …`. **`always_available` listings skip reservation.**
- **`public.stock_reservations`** (`0005`): `id, listing_id → vendor_listings, checkout_group_id → checkout_groups, qty int > 0, expires_at, unique(listing_id, checkout_group_id)`. **`checkout_groups`** exists (`0005`).
- **TTL** from config: `platform_config` key `reservation_ttl_min` (validated 10–15 in M13-P07). Read it.
- API: routers auto-discover (never edit `main.py`); service-role client confined to `app/supabase_client.py`. **`app/services/` is an implicit namespace package** — create `app/services/stock/` (own `__init__.py`); **do NOT create `app/services/__init__.py`**.
  Spec: `docs/plan/02-pebbles/M07-cart-checkout.md` §M07-P02. **This is the oversell-safety pebble — the concurrency test is the point.**

## 2. Objective & scope

Atomic reservation claim at checkout entry (no oversell), TTL-based release/sweeper restock, and price/stock revalidation with change notices on cart view + checkout steps.
**Non-goals:** no cart CRUD (M07-P01 merged), no checkout/payment (M08), no UI.

## 3. Files (create/modify ONLY these)

- **Create:** `services/api/app/services/stock/__init__.py` + `{claim,release,sweep,revalidate}.py` · `services/api/app/routers/internal_stock_sweeper.py` (internal cron endpoint) · `services/api/tests/test_reservations.py` · `infra/n8n/reservation-sweeper.json`
  **Guardrail: nothing else. Do NOT create `app/services/__init__.py`, edit `main.py`, add schema/db.ts, or touch `app/services/cart` (M07-P01).**

## 4. Implementation spec

- **Atomic claim (`claim.py`):** for a `tracked` listing, claim x units via a **single atomic statement** — `UPDATE vendor_listings SET stock_qty = stock_qty - x WHERE id = :id AND stock_mode='tracked' AND stock_qty >= x RETURNING stock_qty` — and, only if it affected a row, upsert a `stock_reservations` row `(listing_id, checkout_group_id, qty, expires_at = now() + ttl)`. **If the UPDATE affects 0 rows → out-of-stock (no reservation).** `always_available` → skip (no claim, always succeeds). Use the service-role client.
- **Release (`release.py`):** on abandon/expiry, restore `stock_qty += qty` and delete the reservation — **exactly once** (guard against double-restock: delete-returning, restock only if a row was deleted).
- **Sweeper (`sweep.py` + `internal_stock_sweeper.py`):** cron tick finds `expires_at < now()` reservations, releases each (idempotent under re-run); internal/service-role-guarded endpoint (not public); `infra/n8n/reservation-sweeper.json` calls it on cadence.
- **Revalidate (`revalidate.py`):** given cart/checkout lines, re-check current price + stock vs. the cart's snapshot; return **change notices** (price changed / now out of stock / qty reduced) as a structured payload the cart/checkout surfaces.

## 5–9. UI/UX · Responsiveness · Performance · SEO · Security

N/A UI. **Security:** claim/release via service-role only (clients cannot mutate stock directly); internal sweeper not publicly callable; no float money.

## 10. Tests (RUN before reporting — `uv run pytest`, `ruff`, `mypy --explicit-package-bases`)

- **Race test (headline):** two concurrent claims for the last unit — **exactly one succeeds, one gets out-of-stock; stock never goes negative** (threaded/parallel double-claim against a real Postgres — use the local stack or a test DB).
- **Sweeper idempotency** under re-run (expiry restocks **exactly once**); **TTL boundary** (not-yet-expired kept, expired swept); `always_available` skips reservation; **revalidation notice payloads** (price-change / oos / qty-reduced).

## 11. Acceptance criteria / DoD

- [ ] Two concurrent buyers **cannot oversell the last unit** (tested); stock never negative.
- [ ] Expiry restocks exactly once; `always_available` skips; sweeper idempotent.
- [ ] Revalidation returns change notices; claim/release service-role-only; ruff+mypy+pytest green.

## 12. IMPLEMENTATION REPORT

Output exactly:
**PEBBLE:** M07-P02 — Stock revalidation & reservations
**STATUS:** COMPLETE | PARTIAL | BLOCKED
**FILES:** each path + one-line description
**DEVIATIONS:** (or "none")
**TESTS:** paste the concurrency/oversell test + sweeper-idempotency + TTL output
**EXCERPTS:** the atomic claim statement + the exactly-once release — nothing else
**QUESTIONS:** (or "none")
