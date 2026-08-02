> **Prepend `prompts/_header.md` (PROJECT HEADER) above this prompt.** Composer sessions share no memory — the header is required context.

# R02-P05 — Implement D36: wholesale omission, not refusal `[CODE]`

## 1. Context
**Wave W2 (B2B correctness).** Governing decision: **D36** in `docs/plan/00-decisions.md` (amends D28, 2026-08-01).

D28 said two things that had drifted apart in the code: "a consumer always sees retail", and (2026-07-15 follow-up) wholesale-only listings are "hidden" from every consumer surface. D36 makes the second precise:

- **Dual-mode listing** (retail price *and* wholesale tiers) → consumer sees **retail inline**. Unchanged.
- **Wholesale-only listing** (no retail price) → **omitted** from every consumer surface, and a **direct fetch by id returns `404`, not `403`**.
- **`403` survives only on the explicit B2B feed** (`/catalog/listings?wholesale=true`), where the caller asserted business intent.

**Why `404`:** a `403` confirms the id names a real listing, so anyone enumerating ids can map the B2B catalogue — its size, its vendors, and by inference its pricing structure — without ever qualifying as a buyer. `404` is indistinguishable from "never existed".

**Type:** `[CODE]`.

## 2. Objective & scope
Make every consumer-facing read path implement D36 exactly, proven by a full eligibility × listing-mode matrix.
**Non-goals:** new B2B features (R02-P17); changing verification lifecycle; touching the demo filter.

## 3. Files (likely; confirm by grep before editing)
- `services/api/app/services/business/access.py` — the **single** eligibility resolver (`BusinessAccess`, `require_wholesale_access`). Reuse it; do not add a second gate.
- `services/api/app/routers/catalog.py`, `products.py`, `comparison.py`, `vendor_profile.py`, `search.py`, `directory.py`
- `services/api/app/services/search/query_builder.py`, `services/api/app/services/search/__init__.py` (`drop_wholesale_listing_hits`)
- `services/api/app/services/ask/retrieve.py` (drops wholesale **unconditionally** — the answer cache is query-keyed, so eligibility-varying results would poison it; keep that)
- Tests under `services/api/tests/`

## 4. Implementation spec
- Introduce one shared predicate for "is this listing wholesale-only" — a listing with wholesale enabled and **no retail price**. Dual-mode is not wholesale-only and must never be hidden.
- Every consumer read path: omit wholesale-only rows from collections **and from counts/facets** (a facet count that includes hidden rows leaks the same fact the 404 protects).
- Direct fetch by id (PDP, comparison, storefront item) as guest/consumer → **404** via the normal not-found path, with the uniform error envelope. It must be **byte-identical** to a genuinely absent listing — no distinct code, no distinct message, no timing tell that is trivially observable.
- Verified business → unchanged: rows visible, tiers and MOQ present.
- `/catalog/listings?wholesale=true` → keep `403` (`business.wholesale_forbidden`).

## 5. Security / conventions
- Uniform envelope `{"error":{"code","message","details"}}`.
- Eligibility comes only from `get_business_access`; never trust a client-supplied flag.
- Money stays integer ngwee.

## 10. Tests (RUN before reporting) — the matrix is the deliverable
For each of **guest · consumer · pending business · verified business** × **wholesale-only · dual-mode · retail-only**, assert on: catalog PLP, facet counts, PDP by id, comparison, vendor storefront, `/search`, `/suggest`, Ask retrieval, and the B2B feed.

Named cases that must exist:
- `test_wholesale_only_listing_is_404_for_guest_by_id`
- `test_wholesale_only_404_is_indistinguishable_from_absent_listing` (same code/message/shape)
- `test_dual_mode_listing_shows_retail_to_consumer`
- `test_facet_counts_exclude_wholesale_only_for_consumers`
- `test_verified_business_sees_wholesale_only_inline`
- `test_b2b_feed_still_403s_for_consumer`
- `test_ask_retrieval_drops_wholesale_unconditionally`

Run: `uv run pytest services/api/tests -q`, `uv run ruff check`, `uv run mypy app tests scripts`.

## 11. Acceptance criteria / DoD
- [ ] Wholesale-only → `404` on every consumer read path, identical to absent.
- [ ] Dual-mode → retail inline for consumers; tiers for verified businesses.
- [ ] Facet/counts leak nothing.
- [ ] `403` remains **only** on `?wholesale=true`.
- [ ] The full matrix is tested and green; no second eligibility gate introduced.

## 12. IMPLEMENTATION REPORT
**PEBBLE:** R02-P05 — D36 wholesale omission
**STATUS:** COMPLETE | PARTIAL | BLOCKED
**FILES:** … · **DEVIATIONS:** … · **TESTS:** paste the matrix results · **EXCERPTS:** the shared predicate + one 404 path · **QUESTIONS:** …
