> **Prepend `prompts/_header.md` (PROJECT HEADER) above this prompt.** Composer sessions share no memory — the header is required context.

# R02-P17 — Warehouses/lots + wholesale RFQ `[CODE]` ⚠ money-adjacent

## 1. Context
**Wave W6.** Sequence **after R02-P05/P06** (D36 semantics + B2B guards) and **R02-P08** (per-branch stock).

**Scope note — read first:** D28 fenced multi-warehouse/lots and wholesale RFQ **out** of v1. **D36 (2026-08-01) moved exactly these two into R02 scope** and left credit/Net terms, buyer organisations & roles, account managers, and wallet/financing **out**. Do not drift past that line; if a requirement seems to need Net terms, stop and raise it.

Reusable seams: `services/rfq/**` and the services quote flow already implement request→quote→accept for services — the B2B goods RFQ should follow that shape rather than invent a second negotiation model. Per-branch stock lands in R02-P08; warehouses are the B2B generalisation of the same idea, not a competing one.

**Type:** `[CODE]` — money-adjacent, heightened review.

## 2. Objective & scope
Warehouse-held stock with lot/batch identity, and a wholesale RFQ that produces a real, priced, expiring quote.
**Non-goals:** FIFO costing/accounting valuation, Net terms, credit limits, buyer orgs/roles.

## 3. Files (edit ONLY these)
- `supabase/migrations/NNNN_warehouses_lots_rfq.sql` — **verify next-free at branch time** (expected `0088`)
- `services/api/app/services/inventory/{warehouses,lots}.py` (new)
- `services/api/app/services/rfq/wholesale.py` (new — reuse the services RFQ patterns)
- `services/api/app/routers/{vendor_warehouses,wholesale_rfq}.py` (new; auto-discovered)
- `apps/vendor/**`, `apps/customer` supplies surfaces
- `packages/i18n/messages/en/{supplies,vendor}.json`
- Tests

## 4. Implementation spec
- `warehouses` (vendor-owned, may map to a `vendor_locations` branch or stand alone); `stock_lots` (`warehouse_id`, `listing_id`, `lot_code`, `quantity`, `expires_on nullable`, `received_on`). FORCE RLS; quantities not client-writable.
- Allocation reuses **R02-P08's atomic claim**; a lot with an `expires_on` in the past is **never allocatable** — derive that, never store an `is_expired` flag (same reasoning as R02-P12's licences).
- **Wholesale RFQ:** verified business (via `app/services/business/access.py` — the single resolver) submits quantity + delivery need → vendor responds with a **priced quote in integer ngwee**, with a **`valid_until`** — an unexpiring quote is a pricing liability, and the expiry must be enforced server-side at acceptance, not merely displayed.
- Acceptance creates an order through the **existing order/escrow path** — no parallel money flow, no new ledger legs. If the existing path cannot express it, stop and raise it rather than branching the money engine.
- Every state move is a guarded transition with an `audit_log` row.

## 5. Security / conventions
Integer ngwee only; RLS + FORCE RLS everywhere; RFQ visible only to its two parties and admin; quotes immutable once accepted (mirror the `orders_commission_snapshot_immutable` trigger pattern from `0069`); all mutations rate-limited and validated.

## 10. Tests (RUN before reporting)
- `test_expired_lot_is_never_allocated` (clock advance, no write)
- `test_lot_allocation_cannot_oversell_under_concurrency` (threads, real PG)
- `test_quote_cannot_be_accepted_after_valid_until` (server-side)
- `test_accepted_quote_is_immutable`
- `test_rfq_invisible_to_third_party_and_to_consumers` (RLS + D36)
- `test_accepted_quote_uses_existing_order_and_escrow_path` (no new ledger legs)
- `test_no_float_in_quote_pricing`
- Migration replay; RLS matrix; money DB-trigger integration job; full suites.

## 11. Acceptance criteria / DoD
- [ ] Lots allocate through the existing atomic claim; zero oversell; expiry derived.
- [ ] Quotes expire server-side and are immutable once accepted.
- [ ] Acceptance rides the existing order/escrow path.
- [ ] RFQ strictly two-party + admin.
- [ ] Scope fence respected: no Net terms, credit, buyer orgs or wallet.

## 12. IMPLEMENTATION REPORT
**PEBBLE:** R02-P17 — Warehouses/lots + wholesale RFQ
**STATUS:** COMPLETE | PARTIAL | BLOCKED
**FILES:** … · **DEVIATIONS:** … · **TESTS:** paste concurrency + expiry results · **EXCERPTS:** the allocation claim + the acceptance path · **QUESTIONS:** …
