> **Prepend `prompts/_header.md` (PROJECT HEADER) above this prompt.** Composer sessions share no memory — the header is required context.

# R02-P08 — Location/branch-aware stock `[CODE]` ⚠ oversell-critical

## 1. Context
**Wave W3.** Sequence **after R02-P07** (needs branch rows). This is a **genuine gap**, unlike the rest of W3/W4.

Today stock is **listing-level**: `vendor_listings.stock_mode` (`tracked|always_available`) and `stock_qty` (`0003_catalog.sql:94`). A vendor with two branches has one pooled number, so a customer can be promised an item that is physically at the branch they are not going to — which for a pickup-first market is a broken order, not a rounding error.

The oversell-safe reservation path already exists and must be reused, not re-implemented: `services/api/app/services/tickets/inventory.py` demonstrates the house pattern — advisory lock + `SELECT … FOR UPDATE` + an atomic claim gated on a **live count**, deliberately with no denormalised counter (M10-P13's note explains why: a maintained counter must be kept consistent across every claim/void/release path or it mis-gates). Stock reservations live in `stock_reservations` with a sweeper (`reservation-sweeper` n8n workflow, active).

**Type:** `[CODE]` — money/inventory adjacent, heightened review.

## 2. Objective & scope
Stock is held per branch; the customer sees per-branch availability; the claim stays atomic and cannot oversell.
**Non-goals:** warehouses/lots/FIFO (**R02-P17**); transfers between branches.

## 3. Files (edit ONLY these)
- `supabase/migrations/NNNN_listing_location_stock.sql` — **verify next-free at branch time** (expected `0082`)
- `services/api/app/services/inventory/location_stock.py` (new)
- `services/api/app/routers/vendor_stock.py` (new)
- existing cart/checkout reservation path (grep `stock_reservations`) — extend, do not fork
- `apps/vendor/app/[locale]/listings/**` stock editor; `apps/customer` PDP availability
- `packages/i18n/messages/en/{vendor,product}.json`
- Tests

## 4. Implementation spec
- New `listing_location_stock (listing_id, location_id, stock_qty, primary key (listing_id, location_id))`, FORCE RLS, counters **not** client-writable.
- **Migration must be additive and backward-safe:** existing listings keep working. Backfill each tracked listing's current `stock_qty` onto its **primary** location; a listing with no branch rows keeps behaving exactly as today. Do **not** drop `vendor_listings.stock_qty` in this pebble — treat it as the pooled/legacy value and state clearly in the migration comment which one is authoritative when both exist.
- Reservation claims gate on the **(listing, location)** live count inside the same advisory-lock + `FOR UPDATE` transaction as today. **No new counter column.**
- `always_available` listings bypass per-branch counting entirely.
- Customer PDP: per-branch availability, ordered by the existing distance calculation when the request carries a location.
- Cart lines carry the chosen `location_id`; checkout re-validates it — a line whose branch went `closed` (R02-P07) must fail closed with a clear, translated error, never silently re-point to another branch.

## 5. Security / conventions
Integer quantities; RLS + FORCE RLS; column grants exclude the quantity from client UPDATE; every adjustment audited. Guarded transitions, never raw UPDATEs.

## 10. Tests (RUN before reporting) — concurrency is the point
- `test_two_concurrent_claims_at_qty_1_exactly_one_wins` (real Postgres, threads — mirror `tests/` inventory concurrency tests)
- `test_claim_at_branch_a_does_not_consume_branch_b`
- `test_legacy_listing_without_branch_rows_behaves_as_before`
- `test_closed_branch_line_fails_checkout_closed_not_repointed`
- `test_always_available_ignores_branch_counts`
- `test_client_cannot_update_stock_column_directly` (RLS/grant level)
- Full `uv run pytest services/api/tests -q`; migration replay; RLS matrix.

## 11. Acceptance criteria / DoD
- [ ] Per-branch stock enforced inside the existing atomic claim; **zero oversell** under concurrency.
- [ ] Legacy single-location listings unchanged.
- [ ] No denormalised counter introduced.
- [ ] Closed-branch lines fail closed with a translated error.
- [ ] Migration additive; replay green.

## 12. IMPLEMENTATION REPORT
**PEBBLE:** R02-P08 — Location-aware stock
**STATUS:** COMPLETE | PARTIAL | BLOCKED
**FILES:** … · **DEVIATIONS:** … · **TESTS:** paste the concurrency results · **EXCERPTS:** the atomic claim · **QUESTIONS:** …
