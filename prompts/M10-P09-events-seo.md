> **Prepend `prompts/_header.md` (PROJECT HEADER) above this prompt.** Branch from and PR against **`master`**. Wave 16 (parallel). **Touch ONLY your files below.** **Run `pnpm --filter customer build/typecheck/lint/test` + `uv run pytest tests/test_event_ics.py` before reporting.**

# M10-P09 — Events SEO & discovery polish

## 1. Context

**Grounded against as-built `master` (events detail + JSON-LD helpers MERGED):**

- **Event detail route exists:** `apps/customer/app/[locale]/(shop)/e/[slug]/page.tsx` (+ `_components/`). Add the JSON-LD component under `_components/`.
- **Reuse the shared SEO helpers** (`packages/ui/src/seo/json-ld.tsx`): `ngweeToZmwDecimal(ngwee)`, `buildAbsoluteUrl(path)`, `JsonLdOfferInput`, `getSiteUrl`. **Do NOT edit `json-ld.tsx`** — import and use; define an `Event`-shaped JSON-LD object locally in your component (schema.org `Event` with `offers`, `availability`, `performer`/`organiser`, `location`, `startDate`).
- **Sitemap:** `apps/customer/app/sitemap.ts` exists. Add a NEW `apps/customer/app/sitemap-events.ts` events chunk (own it); if `sitemap.ts` must reference the chunk, you own that one edit (no other Wave-16 pebble touches sitemap.ts).
- **Money is ngwee** → offers `price` must be decimal ZMW via `ngweeToZmwDecimal`.
  Spec: `docs/plan/02-pebbles/M10-events-ticketing.md` §M10-P09.

## 2. Objective & scope

Event JSON-LD (validates in Google Rich Results: `Event` + `offers` availability + organiser/performer), a `.ics` add-to-calendar endpoint, an events sitemap chunk, and past-event `noindex` (after event end + 30d).
**Non-goals:** no event data/schema change; no ticket purchase/verify change; reuse the existing detail page data.

## 3. Files (create/modify ONLY these)

- **Create:** `apps/customer/app/[locale]/(shop)/e/[slug]/_components/event-jsonld.tsx` (Event schema, offers with `ngweeToZmwDecimal`, `InStock`/`SoldOut` availability, organiser) · `apps/customer/app/sitemap-events.ts` (events sitemap chunk; exclude events ended >30d) · `services/api/app/routers/event_ics.py` (`GET /events/{slug}/calendar.ics` → RFC-5545 VEVENT) · `services/api/tests/test_event_ics.py`
- **Modify (only if needed):** `apps/customer/app/sitemap.ts` (reference the events chunk) · the `e/[slug]/page.tsx` **only** to mount `<EventJsonLd/>` in `<head>`/metadata and set `robots noindex` for past-events (if the page doesn't already expose a mount point, add the minimal wiring — record it in DEVIATIONS)
  **Guardrail: nothing else. Do NOT edit `json-ld.tsx` (reuse), event data services, ticket routers, db.ts, migrations.**

## 4. Implementation spec

- **`event-jsonld.tsx`:** build a `schema.org/Event` object — `name`, `startDate` (instance `starts_at`), `location` (venue + address), `organiser`/`performer`, `image`, and `offers` (per ticket type: `price` = `ngweeToZmwDecimal(price_ngwee)`, `priceCurrency: "ZMW"`, `availability`: `SoldOut` when the instance is sold out else `InStock`, `url`, `validFrom`). Emit as `<script type="application/ld+json">`.
- **`event_ics.py`** (public, uniform envelope on errors): `GET /events/{slug}/calendar.ics` → `text/calendar` VEVENT (`DTSTART`/`DTEND` from instance, `SUMMARY`, `LOCATION`, `DESCRIPTION`, `UID` = event/instance id). Sold-out still downloadable.
- **`sitemap-events.ts`:** list published events; exclude events whose latest instance ended >30d ago (those are `noindex`). Past-but-recent events stay listed.
- **noindex logic:** event pages with all instances ended >30d ago → `robots: { index: false }`.

## 5–9. Security / SEO / perf

Public read-only; JSON-LD must pass Rich Results for paid + free events; ZMW decimals correct; `.ics` valid for Google/Outlook import; no secrets; minimal added JS (JSON-LD is inline, no client component needed).

## 10. Tests (RUN before reporting)

`test_event_ics.py`: `.ics` format (valid VEVENT, correct DTSTART/DTEND, escaping); sold-out event still downloadable. Frontend: JSON-LD goldens (ngwee→decimal ZMW offers for paid + free; `SoldOut` vs `InStock`); `noindex` after +30d logic. `pnpm --filter customer build/typecheck/lint/test`, `uv run pytest tests/test_event_ics.py -q`, `uv run ruff check`, `uv run mypy`.

## 11. Acceptance criteria / DoD

- [ ] Rich Results validates for paid + free fixture events; `.ics` imports correctly; sold-out reflected in offers `availability`; past-event (>30d) `noindex`.
- [ ] Offers use `ngweeToZmwDecimal` (no float); sitemap-events excludes stale events; customer build + `event_ics` tests green.

## 12. IMPLEMENTATION REPORT

**PEBBLE:** M10-P09 — Events SEO & discovery polish
**STATUS/FILES/DEVIATIONS** (the Event JSON-LD shape; ics VEVENT; noindex + sitemap exclusion logic; any page.tsx mount wiring) **/TESTS** (paste JSON-LD goldens + ics-format + noindex + build tails) **/EXCERPTS** the offers/availability builder (`ngweeToZmwDecimal`) + the VEVENT builder — nothing else **/QUESTIONS**
