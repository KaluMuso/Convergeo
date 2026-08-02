> **Prepend `prompts/_header.md` (PROJECT HEADER) above this prompt.** Composer sessions share no memory — the header is required context.

# R02-P16 — Product-class activation: per-measure, made-to-order, condition evidence `[CODE]` ⚠ money-adjacent

## 1. Context
**Wave W6.** Today a listing is implicitly "one discrete new-or-refurbished unit": `vendor_listings.condition` is `check (condition in ('new','refurbished'))` (`0003_catalog.sql:93`) and price is per unit. Zambian retail is not only that shape — cloth, cable, timber, sand, maize and paint are sold **per measure**; furniture, tailoring and signage are **made to order**; and a large second-hand market needs **evidence**, not adjectives.

Money rule is absolute: **integer ngwee everywhere; `Decimal` only at the Lenco boundary; float on money is a review-blocking bug.** Per-measure pricing is where a float will try hardest to sneak in — 2.5 metres × K37.50 is exactly the shape that tempts one.

**Type:** `[CODE]` — money-adjacent, heightened review.

## 2. Objective & scope
Three activations: per-measure quantities, made-to-order lead times, and condition evidence for used goods.
**Non-goals:** auctions; per-measure *wholesale* tiers (defer, note it); custom quote flows (that is services/RFQ, already built).

## 3. Files (edit ONLY these)
- `supabase/migrations/NNNN_product_classes.sql` — **verify next-free at branch time** (expected `0087`)
- `services/api/app/services/listings/{pricing,measures}.py`
- cart/checkout quantity path (grep `stock_qty` / line totals) — extend, do not fork
- `apps/vendor/**/listings/**`, `apps/customer` PDP + cart
- `packages/i18n/messages/en/{product,vendor,cart}.json`
- Tests

## 4. Implementation spec

**Per-measure**
- `sale_unit` (`each|metre|kg|litre|bag|sqm`), `unit_step` (smallest sellable increment), `min_quantity`.
- Quantity is stored as an **integer count of `unit_step`**, never a decimal. 2.5 m at a 0.5 m step is `5` steps. Line total = `steps × price_per_step_ngwee` — pure integer arithmetic, no rounding decision at all.
- Display converts steps → human units at the edge only, via i18n number formatting.

**Made-to-order**
- `fulfilment_mode` (`stocked|made_to_order`), `lead_time_days`.
- Made-to-order bypasses stock reservation but **must** surface the lead time on PDP, in cart, and at checkout — and it interacts with escrow timing: the customer is agreeing to wait, so the auto-release clock must not treat "not yet delivered" as a dispute. **Do not change escrow timing in this pebble** — record the interaction and flag it for a decision.

**Condition evidence**
- Extend `condition` additively to include `used` (keep `new`, `refurbished` valid — additive-only, and existing rows must not need a backfill to stay legal).
- For `used`: require ≥1 real photo of the actual item and a structured defect note. Reuse the existing image pipeline and the ≤8-image cap.
- **Verified-purchase reviews already exist** — do not weaken that rule here.

## 5. Security / conventions
Integer ngwee; `unit_step` and quantities integer; every price path re-derived server-side. Additive migration with a documented backfill (or none). Zero hardcoded strings.

## 10. Tests (RUN before reporting)
- `test_no_float_in_any_price_path` (assert `Decimal`/int types; a float literal in a money path fails the test)
- `test_line_total_is_exact_for_half_metre_steps`
- `test_min_quantity_and_step_enforced_server_side`
- `test_made_to_order_skips_reservation_but_shows_lead_time`
- `test_used_listing_requires_photo_and_defect_note`
- `test_existing_new_and_refurbished_listings_unaffected` (regression on 134 live-shaped rows)
- Migration replay; full API + web suites; `ruff`; `mypy`.

## 11. Acceptance criteria / DoD
- [ ] Per-measure quantities are integer steps; no float touches money.
- [ ] Lead time surfaced at PDP, cart and checkout; escrow interaction flagged, not silently changed.
- [ ] `used` requires evidence.
- [ ] Existing listings unaffected; migration additive.

## 12. IMPLEMENTATION REPORT
**PEBBLE:** R02-P16 — Product-class activation
**STATUS:** COMPLETE | PARTIAL | BLOCKED
**FILES:** … · **DEVIATIONS:** … · **TESTS:** paste the money-type test · **EXCERPTS:** the step arithmetic · **QUESTIONS:** raise the escrow/lead-time interaction for a founder decision
