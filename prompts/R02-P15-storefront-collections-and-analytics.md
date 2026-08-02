> **Prepend `prompts/_header.md` (PROJECT HEADER) above this prompt.** Composer sessions share no memory — the header is required context.

# R02-P15 — Vendor storefront collections + genuine impression/search analytics `[CODE]`

## 1. Context
**Wave W6.** Two related gaps: a vendor cannot merchandise their own storefront, and the analytics they are shown must be **earned numbers, not flattering ones**.

Existing and reusable: `search_analytics` (`0027`), `funnel_events` (`0025`), `analytics_unify` (`0029`), the analytics retention sweep (active n8n workflow, DPA: person-links nulled after 30 days), and `vendor_profile.py`.

The trap to avoid: counting an "impression" for every row returned by a query. That inflates every denominator, makes conversion look broken, and quietly teaches the vendor to distrust the dashboard. An impression should mean **the card was actually rendered to a human**, and if that cannot be measured honestly, the metric should be named for what it does measure.

**Type:** `[CODE]`.

## 2. Objective & scope
Vendor-curated collections on the storefront, plus impression/search analytics whose definitions are documented and honest.
**Non-goals:** ad products, paid placement, cross-vendor recommendations.

## 3. Files (edit ONLY these)
- `supabase/migrations/NNNN_storefront_collections.sql` — **verify next-free at branch time** (expected `0086`)
- `services/api/app/routers/vendor_collections.py` (new), `vendor_profile.py` (render)
- `services/api/app/services/analytics/impressions.py` (new)
- `apps/vendor/**/storefront/**`, `apps/customer/**` storefront render
- `packages/i18n/messages/en/{vendor,storefront}.json`
- Tests

## 4. Implementation spec
- `storefront_collections` (`vendor_id`, `title`, `slug`, `sort_order`, `status`) + `storefront_collection_items` (`collection_id`, `listing_id`, `sort_order`). FORCE RLS; vendor owns their own; public read for active collections of active vendors. A collection may only contain **that vendor's own** listings — enforce with a trigger, mirroring M17's `clip_products_guard` (a vendor must not be able to merchandise a rival's listing onto their storefront and harvest the traffic).
- **D36 interaction:** a wholesale-only listing inside a collection must be omitted for ineligible viewers, and the collection must not reveal a gap in its numbering that implies a hidden item.
- **Impressions:** batch client-side, send on idle/visibility with the existing analytics transport, and **only count a card that entered the viewport**. Dedupe per (viewer-session, listing, day) with a unique key so a scroll-back does not double-count — the same "idempotent by constraint" discipline M17 used for views. Write the definition into `docs/ops/analytics-events.md`; if the honest name is "cards rendered", use that name.
- **Search analytics:** surface a vendor's own query→click data from `search_analytics`; never expose another vendor's.
- Retention: person-links respect the existing 30-day sweep; do not create a new long-lived identifier.

## 5. Security / conventions
RLS on every new table; no cross-vendor leakage in any aggregate; DPA retention honoured; zero hardcoded strings; customer routes stay within budget.

## 10. Tests (RUN before reporting)
- `test_collection_cannot_contain_another_vendors_listing` (DB trigger refuses)
- `test_wholesale_only_item_hidden_in_collection_for_consumer` (D36)
- `test_impression_deduped_per_session_listing_day`
- `test_impression_not_counted_without_viewport_entry`
- `test_vendor_cannot_read_another_vendors_search_analytics` (RLS)
- `test_retention_sweep_nulls_person_links`
- Migration replay; RLS matrix; bundle budget; full test suites.

## 11. Acceptance criteria / DoD
- [ ] Collections are vendor-scoped and trigger-enforced.
- [ ] D36 respected inside collections.
- [ ] Impression definition documented and matches the implementation.
- [ ] Dedupe by constraint, not application logic.
- [ ] No cross-vendor analytics leakage; retention honoured.

## 12. IMPLEMENTATION REPORT
**PEBBLE:** R02-P15 — Storefront collections + analytics
**STATUS:** COMPLETE | PARTIAL | BLOCKED
**FILES:** … · **DEVIATIONS:** … · **TESTS:** … · **EXCERPTS:** the ownership trigger + the dedupe key · **QUESTIONS:** …
