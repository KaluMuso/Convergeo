> **Prepend `prompts/_header.md` (PROJECT HEADER) above this prompt.** Branch from and PR against **`master`**. Wave 16 (parallel). **Touch ONLY your files below.** **Run `pnpm --filter vendor build/typecheck/lint/test` + the FULL `uv run pytest` before reporting.**

# M12-P10 — Vendor analytics

## 1. Context

**Grounded against as-built `master`:**

- **Data sources exist:** `orders`/`order_items` (sales), `funnel_events` (M07-P08, merged — views/impressions incl. `cart_add`/`checkout_start`), search impressions (search_documents / query analytics). Aggregate from these — **numbers must reconcile with orders truth.**
- **Ledger-derived money** where relevant (like M12-P08's vendor payouts view). Vendor-scoped only.
- **Data-frugal:** 7/30-day cards + inline-SVG sparklines — **no chart lib >10KB**; route JS <50KB.
  Spec: `docs/plan/02-pebbles/M12-vendor-portal.md` §M12-P10.

## 2. Objective & scope

A lightweight vendor analytics page: 7/30-day sales/orders/views trend cards, top listings, a conversion hint, inline-SVG sparklines; aggregates from orders + funnel events + search impressions; vendor-scoped.
**Non-goals:** no new chart dependency, no cross-vendor data, no funnel/search schema change, no migration.

## 3. Files (create/modify ONLY these)

- **Create:** `apps/vendor/app/[locale]/analytics/page.tsx` (+ `_components/*` cards + inline-SVG sparkline) · `services/api/app/routers/vendor_analytics.py` (vendor-scoped aggregates: sales/orders/views by day, top listings, conversion) · `services/api/tests/test_vendor_analytics.py`
- **Modify (APPEND-RULE):** `packages/i18n/messages/en/vendor.json` (append `vendor.analytics.*`) — **you are the sole Wave-16 editor of vendor.json.**
  **Guardrail: nothing else. Do NOT edit funnel/search services, orders services, `main.py`, db.ts, migrations, other apps.**

## 4. Implementation spec

- **`vendor_analytics.py`** (auth, **vendor-scoped**, uniform envelope): `GET /vendor/analytics?window=7|30` → `{ sales_ngwee_by_day, orders_by_day, views_by_day (from funnel_events), top_listings: [{listing_id, title, units, revenue_ngwee}], conversion_hint }`. Money in ngwee (client renders via `formatK`). Cross-vendor access impossible (scope to the authed vendor). Empty-history → zeros, not error.
- **Page:** 7/30-day toggle; stat cards; inline-SVG sparklines (no lib); top-listings list; 360px; copy via `vendor.analytics.*`. Keep route JS <50KB.

## 5–9. Security / perf

Vendor-scoped (own data only, cross-vendor → empty/403); numbers reconcile with orders truth; view counts from `funnel_events`; inline-SVG only (no chart lib); route JS <50KB; data-frugal payloads; no secrets.

## 10. Tests (RUN before reporting)

`test_vendor_analytics.py`: **aggregate correctness** vs fixtures (sales/orders reconcile with orders rows; views from funnel_events); **date-range boundaries** (7 vs 30 day windows); **empty-history** state (zeros); vendor-scope isolation (vendor A can't see vendor B). Full `uv run pytest`, `uv run ruff check .`, `uv run mypy .`. `pnpm --filter vendor build/typecheck/lint/test` (assert the analytics route JS stays <50KB — check the build output).

## 11. Acceptance criteria / DoD

- [ ] Numbers reconcile with orders truth; views from funnel events; renders <50KB route JS; empty-history handled.
- [ ] Vendor-scoped; `vendor.analytics.*` appended; full API suite green; vendor build green; ruff/mypy clean.

## 12. IMPLEMENTATION REPORT

**PEBBLE:** M12-P10 — Vendor analytics
**STATUS/FILES/DEVIATIONS** (aggregate sources + how sales reconcile with orders; the inline-SVG sparkline; route JS size) **/TESTS** (paste aggregate + boundary + empty + scope + build-size tails) **/EXCERPTS** the vendor-scoped aggregate query + authz — nothing else **/QUESTIONS**
