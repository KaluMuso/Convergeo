# Task T30: Shop location without typing coordinates

**Agent:** Cursor. **Model:** Composer 2.5. **Branch:** `cursor/shop-location-picker` from `master`. Open one PR to `master`; don't merge.
**Board:** claim row T30 in `docs/ops/agent-board.md` first. Set it to `ready for review` when done.
**Depends on:** PR #882, which allows `geolocation` on `/profile` and `/businesses`. Build on master; "Use my current location" works once #882 is merged.

**Owns (edit only these):**

- `apps/vendor/app/[locale]/profile/_components/profile-editor.tsx`
- new `apps/vendor/app/[locale]/_components/location-picker/**` (+ tests)
- the location fields in `apps/vendor/app/[locale]/businesses/**` (reuse the picker)
- `services/api/app/routers/geo.py` (new) and its registration line in `main.py`, plus `services/api/tests/test_geo_search.py`
- the customer storefront "Directions" link and the LocalBusiness JSON-LD in `apps/customer/app/[locale]/(shop)/vendors/[slug]/**`
- `packages/i18n/messages/*/vendor.json` (`profile.location.*` only) and `customer.json` (`storefront.directions` only)
- in `apps/vendor/next.config.ts`, **only** the `img-src` entry of the report-only CSP: add `https://tile.openstreetmap.org`

## Problem (King, 24 Nov)

- Today a vendor must type latitude and longitude by hand. Nobody knows those numbers.
- Saving opening hours shows "Add your location before setting hours." even when the completeness meter shows "Location + landmark ✓". Find out why and fix it.
- Buyers can't easily get directions to a shop.

## Build

1. **Location picker** (one component, used on profile and branch pages), in this order on screen:
   - **Use my current location** (primary button). Use `navigator.geolocation.getCurrentPosition` with `enableHighAccuracy`, a 15 s timeout, and accuracy shown in metres. If permission is denied, show a plain message and point to the next two options.
   - **Search a place or area** (e.g. "Arcades, Lusaka"). It calls our API `GET /geo/search?q=`, never the map service from the browser. Show up to 5 results; picking one moves the pin.
   - **Map with a draggable pin** using Leaflet and OpenStreetMap tiles. Dynamic import, so the map JS loads only when the picker opens. Show the "© OpenStreetMap contributors" attribution. Default centre is Lusaka (-15.4167, 28.2833), zoom 13.
   - **Landmark** stays required (e.g. "Opposite Shoprite, Cairo Road").
   - Latitude and longitude move under an **Advanced** disclosure and are filled in automatically.
   - Saving uses the existing profile payload (`location: {lat, lng, landmark}`). Don't change the API contract.
2. **API `GET /geo/search?q=`** (FastAPI):
   - Auth required (vendor), rate limit 10 per minute per user, q length 3–80.
   - It calls Nominatim `https://nominatim.openstreetmap.org/search?format=jsonv2&countrycodes=zm&limit=5&q=` with a real `User-Agent` (`Convergeo/1.0 (support@vergeo5.com)`), at most 1 request per second across the whole API (a process-wide lock), and a 24 h in-memory cache keyed by the lower-cased query.
   - Return `[{label, lat, lng}]`. On upstream error return 503 with `geo_unavailable`, and the UI falls back to the pin.
3. **Hours bug:** saving hours must work whenever a saved location exists. Add a test for the case King hit.
4. **Buyer side** (customer storefront page):
   - a **Directions** link to `https://www.google.com/maps/dir/?api=1&destination={lat},{lng}`. This is free; no Google API key.
   - LocalBusiness JSON-LD with `geo` and the landmark as `address.streetAddress`, `addressLocality` from the area, and `addressCountry: "ZM"`. This helps the shop show up on Google.

## Tests (required)

- The picker fills lat/lng from a mocked geolocation; denied permission shows the fallback; a search result moves the pin; save sends the payload.
- API: auth, rate limit, cache hit (one upstream call for two identical queries), upstream failure → 503, q too short → 422.
- Hours save works with a saved location (the regression test).
- Storefront: the Directions URL and JSON-LD geo are correct.

## Done means

A vendor sets the shop location in two taps on a phone (Use my location → Save), or by search or pin on a laptop, without seeing coordinates. Buyers get a Directions button. Tests, typecheck and lint pass. Vendor bundle: map code only in the lazy chunk. Customer JS growth 0 KB (the link and JSON-LD are server-rendered).

## Rules

1. Claim your board row (`in progress — cursor`) in your first commit. One agent per row.
2. Work only in the files you OWN. Need another file? Stop and note it on the board.
3. Testing: run only related tests, one command at a time (`pnpm --filter vendor exec vitest related <files> --run`, `cd services/api && uv run pytest tests/test_geo_search.py -q`), then typecheck and lint for the touched packages. Never the full suite.
4. Never touch `supabase/`, `scripts/ci/`, `.github/`, `infra/`, payments, escrow, ledger, payouts, webhooks, auth or checkout money logic. No secrets. Never merge, force-push or `git stash`.
5. bem, nya, fr and zh: copy the English text and mark it for review. Don't invent translations.
6. When done: row to `ready for review`, one line of notes, PR link in Slack #convergeo-dev. Claude reviews the API and headers.
