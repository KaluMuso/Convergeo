> **Prepend `prompts/_header.md` (PROJECT HEADER) above this prompt.** Branch from and PR against **`master`**. Wave 8 runs 10 pebbles in parallel — **touch ONLY your files below**. **⚠ SCHEMA FROZEN.** Stay dep-free. **Run the FULL `uv run pytest` before reporting.**

# M05-P11 — Events discovery (browse tab + event detail display)

## 1. Context

**Wave 8 (parallel ×10).** Grounded against as-built `master`:

- `public.events` + ticket types + event instances/dates live in **`0004_services_events.sql`** — grep exact columns (`events(id, slug, organiser_vendor_id, title, description, status ('published'|…), category …)`, instances/dates, ticket types with prices). Publish state for browse = `'published'`.
- **TZ is Africa/Lusaka** — date-window filters ("Tonight / This Weekend") must compute in that TZ. The `(shop)` group + layout exist. API routers auto-discover (never edit `main.py`); service-role via `app.deps.get_supabase_client` (import-guard; local `Protocol`).
- i18n `events` namespace registered; `events.json` exists — **you solely own it** (nest).
  Spec: `docs/plan/02-pebbles/M05-catalog-search-discovery.md` §M05-P11. **Ticket purchase is M10-P03 — the ticket CTA is a display-only stub.**

## 2. Objective & scope

Events tab (grid + "Tonight/This Weekend" default filter chips, 6-category filter, calendar-lite) + event detail (images, venue+landmark/map-lite, instances/dates, ticket types + prices **display only**, organiser block).
**Non-goals:** no ticket purchase (M10-P03 — CTA stub), no ticketing schema, no dynamic-QR.

## 3. Files (create/modify ONLY these)

- **Create:** `apps/customer/app/[locale]/(shop)/events/page.tsx` · `(shop)/e/[slug]/page.tsx` · `(shop)/_components/events/{event-grid,date-filter-chips}.tsx` · `services/api/app/routers/events_public.py` · `services/api/tests/test_events_public.py`
- **Modify:** `packages/i18n/messages/en/events.json` (nest + fill)
  **Guardrail: nothing else. Do NOT touch services/events schema, `main.py`, or other namespaces.**

## 4. Implementation spec

- **`events_public.py`:** `GET /events` (browse: published only; **date-window filters — Tonight/This Weekend/category — computed in Africa/Lusaka TZ; past events excluded from browse**) + `GET /events/{slug}` (detail: images, venue+landmark, instances/dates ordered, ticket types + prices display-only, organiser; **detail stays reachable for past events**; **sold-out state**).
- **Events page:** grid + date-filter chips (default Tonight/This Weekend) + category filter + calendar-lite. **Detail** (`e/[slug]`): ticket CTA is a **disabled/stub** button (M10-P03). Free-RSVP display. All copy via `events` namespace.

## 5–9. UI/UX · Responsiveness · Performance · SEO · Security

360px-first; TZ-correct windows; past excluded from browse but detail reachable; public read; no secrets.

## 10. Tests (RUN before reporting — full `uv run pytest` + ruff + mypy)

`test_events_public.py`: **TZ/date-window unit tests** (correct across month boundaries, Africa/Lusaka); **instance ordering**; **free-RSVP display**; past excluded from browse; sold-out state. `pnpm --filter customer build`, `pnpm typecheck`, `pnpm lint`, `pnpm test`. **Full API suite.**

## 11. Acceptance criteria / DoD

- [ ] Date-window filters correct across month boundaries (Lusaka TZ); past excluded from browse, detail reachable; sold-out shown.
- [ ] Ticket CTA is a stub (M10-P03); `events.json` nested; full API suite + repo green.

## 12. IMPLEMENTATION REPORT

**PEBBLE:** M05-P11 — Events discovery
**STATUS/FILES/DEVIATIONS/TESTS** (paste TZ-window + ordering + full-pytest tail) **/EXCERPTS** (none) **/QUESTIONS**
