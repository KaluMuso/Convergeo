> **Prepend `prompts/_header.md` (PROJECT HEADER) above this prompt.** Composer sessions share no memory — the header is required context.

# R02-P06 — B2B RLS + pricing risk pass `[CODE]`

## 1. Context
**Wave W2.** Sequence **after R02-P05** (shares `access.py` and the catalog/cart paths).

Wholesale must not be activated until the money-shaped half of D28/D36 is proven, not assumed. Two risks:

1. **Identity** — `business_buyers` carries a server-controlled `pending→verified/rejected/suspended` lifecycle. If RLS or a guard lets a buyer influence their own status, wholesale pricing is self-service.
2. **Pricing** — `merge.py` re-derives the wholesale flag from listing **and** buyer eligibility, so a consumer merging a wholesale line falls back to retail. That is the correct design; this pebble proves it still holds on every path into a cart, including a **stale** cart whose owner was verified when the line was added and has since been **suspended**.

**Type:** `[CODE]`.

## 2. Objective & scope
Prove — with failure-path tests — that no path yields wholesale pricing to a party who is not currently a verified business, and that status is unwritable by its subject.
**Non-goals:** new B2B workflows (R02-P17); changing tier maths.

## 3. Files (edit ONLY these)
- `services/api/app/services/business/access.py`
- `services/api/app/services/cart/merge.py` (confirm exact path by grep)
- `services/api/app/routers/business.py`, `admin_business.py` (names to confirm)
- `supabase/migrations/NNNN_business_buyers_guard.sql` — **only if** a DB-level guard is missing. **Verify next-free number at branch time** (currently `0080`).
- `services/api/tests/test_business_access.py`, `test_cart.py`, `services/api/tests/rls/test_matrix.py`

## 4. Implementation spec
- **Status is server-controlled or it is not controlled.** If a buyer can `UPDATE` their own `status` under RLS, add a column-level guard trigger in the style of `0057_vendor_lifecycle_client_guards.sql` — the repo's established pattern for exactly this. Prefer the DB guard over a router check: a router can be bypassed by the next endpoint someone writes.
- **Suspension takes effect immediately**, including on carts priced while verified. Re-derive at merge, at checkout, and at order creation — never trust a stored line price.
- Confirm the RLS matrix covers `business_buyers` for owner/other-buyer/admin/anon and that `tests/rls/test_no_untested_tables.py` cannot pass while it is missing.
- MOQ is enforced **only** for eligible businesses; a consumer must never be blocked by, or benefit from, a wholesale MOQ.

## 5. Security / conventions
RLS on every table; service-role key server-side only; audit every admin verify/reject via `AdminAuditedRoute`. Money stays integer ngwee — **float on money is a review-blocking bug.**

## 10. Tests (RUN before reporting) — failure paths are mandatory
- `test_buyer_cannot_self_verify` — direct UPDATE under the buyer's own token is refused **at the database**.
- `test_suspended_business_loses_wholesale_price_on_existing_cart` — verified → line added at tier price → suspended → merge/checkout re-derives to **retail**.
- `test_consumer_merging_wholesale_line_gets_retail`
- `test_moq_not_enforced_for_consumer`
- `test_admin_verify_writes_audit_row`
- `test_pending_business_is_not_eligible`
- RLS matrix green; `uv run pytest services/api/tests -q`; `ruff`; `mypy`.

## 11. Acceptance criteria / DoD
- [ ] No path gives wholesale pricing to a non-verified party, including stale carts.
- [ ] Status is unwritable by its subject, enforced at the DB.
- [ ] Suspension is immediate on every pricing path.
- [ ] RLS matrix covers `business_buyers`.
- [ ] Every admin decision is audited.

## 12. IMPLEMENTATION REPORT
**PEBBLE:** R02-P06 — B2B RLS + pricing risk
**STATUS:** COMPLETE | PARTIAL | BLOCKED
**FILES:** … · **DEVIATIONS:** … · **TESTS:** paste the failure-path results · **EXCERPTS:** the guard + the re-derivation · **QUESTIONS:** …
