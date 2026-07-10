> **Prepend `prompts/_header.md` (PROJECT HEADER) above this prompt.** Branch from and PR against **`master`**. Wave 14 runs 9 pebbles in parallel — **touch ONLY your files below**. **Run the FULL `uv run pytest` before reporting.**

# M11-P01 — Service listings & provider profiles

## 1. Context

**Wave 14 (parallel ×9).** Grounded against as-built `master`:

- **`services` table EXISTS (0004_services_events.sql:9):** `from_price_ngwee` (nullable), `status ('draft','active','paused')`, vendor-owned RLS (own in any status; public reads `active`). **No migration.**
- **Search projection MERGED (M05):** `search_documents` triggers exist — **verify services project into unified search** (they should already; assert in a test). Semantic embeddings land via M06-P01 (parallel) — not your concern.
- **Response-time badge** = computed from `job_quotes` history (median first-response), **updated nightly** (an internal/n8n job OR a cached column read). Tiers: **fast <2h / same-day / slow**. Keep the compute pure + tested; the nightly refresh can be a simple internal tick or a cached value (do not add a migration — store in an existing jsonb like `vendors.caps_snapshot` or compute on read with a cache note).
- **8 service verticals + area filter** (D-spec). from-price optional → renders "from K__" or "ask for quote".
  Spec: `docs/plan/02-pebbles/M11-services-rfq.md` §M11-P01. **i18n `services` (append-rule):** you seed the browse/detail keys; **M11-P02 also appends `services.postJob.*` to `services.json` this wave** — disjoint sections, rebase-append on conflict.

## 2. Objective & scope

Service listings: customer browse (8 verticals + area filter) + detail (portfolio gallery, service area, optional from-price, **response-time badge**, request-quote CTA) + vendor-side manage (new/edit); services searchable in unified search.
**Non-goals:** no RFQ/post-a-job (M11-P02), no quotes inbox (M11-P03), no new schema, no embedding pipeline (M06-P01).

## 3. Files (create/modify ONLY these)

- **Create:** `apps/customer/app/[locale]/(shop)/services/page.tsx` (browse) · `apps/customer/app/[locale]/(shop)/s/[slug]/page.tsx` (detail) · `apps/vendor/app/[locale]/services/page.tsx` (+ `new`/`[id]/edit` + `_components`) · `services/api/app/routers/services_listings.py` (browse/detail/manage, RLS-scoped, badge compute) · `services/api/tests/test_services_listings.py`
- **Modify (APPEND-RULE — disjoint section):** `packages/i18n/messages/en/services.json` (append browse/detail/vendor keys under `services.*`)
  **Guardrail: nothing else. Do NOT touch `rfq/*`/`jobs.py` (M11-P02), `search_documents` functions (verify only), `main.py`, schema/db.ts. No migration.**

## 4. Implementation spec

- **`services_listings.py`** (auth where needed, RLS-scoped, uniform envelope): public browse (active only, vertical + area filter), detail; vendor CRUD (own, any status); **`response_time_tier(vendor_id)`** = median first-response from `job_quotes` → fast(<2h)/same-day/slow (pure, tested; cache/refresh note). from-price optional.
- **Pages:** browse grid (verticals + area filter, 360px), detail (portfolio gallery via merged Cloudinary seam, from-price or "ask for quote", badge, request-quote CTA → M11-P02 flow), vendor manage. Copy via `services.*`.

## 5–9. Security etc.

360px; **draft services hidden from public** (RLS test); from-price optional rendering; badge tiers correct; searchable; owner-scoped vendor CRUD; no secrets.

## 10. Tests (RUN before reporting)

`test_services_listings.py`: **badge computation fixtures** (median first-response → fast/same-day/slow boundaries); browse filters (vertical + area); **RLS** (draft hidden from public, other vendor cannot edit); from-price optional rendering; **search projection** (a published service appears in `search_documents`). `pnpm --filter customer build && pnpm --filter vendor build`, `pnpm typecheck`, `pnpm lint`, `pnpm test`. **Full `uv run pytest`.**

## 11. Acceptance criteria / DoD

- [ ] from-price optional renders "from K__" / "ask for quote"; badge tiers correct; service searchable in unified search; draft hidden.
- [ ] `services.*` browse/detail/vendor keys appended (append-rule); 2 app builds + full API suite green.

## 12. IMPLEMENTATION REPORT

**PEBBLE:** M11-P01 — Service listings & provider profiles
**STATUS/FILES/DEVIATIONS** (badge compute source + refresh strategy; search-projection verification result) **/TESTS** (paste badge-fixtures + browse-filters + RLS-draft-hidden + search-projection + full-pytest tail) **/EXCERPTS** the `response_time_tier` compute — nothing else **/QUESTIONS**
