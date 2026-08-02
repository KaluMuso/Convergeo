> **Prepend `prompts/_header.md` (PROJECT HEADER) above this prompt.** Composer sessions share no memory — the header is required context.

# R02-P11 — Map/list toggle + route modes `[CODE]` ⚠ data-budget critical

## 1. Context
**Wave W4.** Sequence after **R02-P10**.

Distance already works: `haversine_m` + radius filtering in `routers/directory.py:404`, distance SQL in `routers/catalog.py:128`, and `distance_m` is already on the response. **Do not rebuild ranking or distance.** The gap is presentational: there is no map view, and no "how do I get there".

**The budget is the design constraint.** Customer routes are capped at **≤150KB gz JS** with **LCP ≤2.5s on Fast-3G/360px**, CI-enforced. A typical map SDK is 100–200KB gz on its own and would blow the entire route budget for one view — the same arithmetic that made M17 reject `hls.js` (~70KB) for a recycled native `<video>`. Assume you cannot afford an SDK unless you prove otherwise with a measured number.

**Type:** `[CODE]`.

## 2. Objective & scope
A map/list toggle that is honest on 3G, and route hand-off to the user's own maps app.
**Non-goals:** turn-by-turn navigation; live traffic; storing routes; a mapping account.

## 3. Files (edit ONLY these)
- `apps/customer/app/[locale]/directory/**` and the PLP location view
- `apps/customer/app/[locale]/**/_components/map-*.tsx` (new)
- `packages/i18n/messages/en/directory.json`
- Tests + a bundle-budget check

## 4. Implementation spec
- **List stays the default.** The map is opt-in, lazy-loaded on interaction, and never on the critical path of first render.
- Prefer, in order: (a) static map image via the existing **Cloudinary** pipeline or an equivalent already-paid-for source — note `apps/customer/.../static-map-preview.tsx` already exists, so check it first and reuse; (b) a lightweight vector/tile view **only** if measured inside budget; (c) if neither fits, ship list + "Open in Maps" and record the measurement that ruled the map out. Option (c) is an acceptable outcome, not a failure.
- **Route modes** are a hand-off, not an implementation: a `geo:` / Google / Apple Maps deep link built from `lat`/`lng` plus the `landmark` as the label, with a copyable landmark string for the very common case of directing a driver by phone.
- Respect `prefers-reduced-motion`; no autoplaying pan/zoom animation.
- Report the **measured first-load gz** for every route touched, before and after.

## 5. Security / conventions
No API key in client code. No third-party script that phones home with user coordinates — location is PII and this is a Zambia-DPA product. If a tile provider is used, record what it receives. Zero hardcoded strings.

## 10. Tests (RUN before reporting)
- Bundle guard: `node scripts/ci/bundle-guard.mjs` (or the CI equivalent) — every touched customer route ≤150KB gz. **Paste the numbers.**
- `test_map_bundle_not_loaded_until_toggled` — the map chunk is absent from the initial payload.
- Deep-link builder unit tests, including a landmark containing spaces and non-ASCII.
- `pnpm lint typecheck test build`; Lighthouse mobile on the directory route.

## 11. Acceptance criteria / DoD
- [ ] List default; map lazy and opt-in.
- [ ] Every touched route within budget, with measurements pasted.
- [ ] Route hand-off works to at least Google Maps + a generic `geo:` link; landmark copyable.
- [ ] No API key or coordinate leak to a third party without it being recorded.
- [ ] Distance/ranking code untouched.

## 12. IMPLEMENTATION REPORT
**PEBBLE:** R02-P11 — Map/list + route modes
**STATUS:** COMPLETE | PARTIAL | BLOCKED
**FILES:** … · **DEVIATIONS:** … · **TESTS:** paste before/after route sizes · **EXCERPTS:** the lazy boundary · **QUESTIONS:** …
