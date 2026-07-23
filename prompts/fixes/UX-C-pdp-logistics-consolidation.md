> **Prepend `prompts/_header.md`.** Branch from + PR against **`master`**. **No migration.** Reuse EXISTING catalog keys only — **no new i18n keys**. Run `pnpm --filter customer typecheck && pnpm --filter customer lint && pnpm --filter customer test`. 360px visual check on a multi-seller PDP. **This changes PDP visuals — HOLD for founder sign-off before merge.**

# UX-C — One logistics-pill treatment across PLP + PDP

## Findings (docs/design audit §4/§6 — consistency)

The delivery/pickup (+ distance / below-median) signal renders three different ways:

- **PLP card** — colored `Pill` via `(shop)/_components/plp/logistics-pills.tsx` (`buildLogisticsPills` / `ListingLogisticsPills` / `catalogLogisticsLabels`), API-wired from `distance_m` / `below_median` / `delivery_available` / `pickup_available`.
- **PDP comparison** — monochrome `Badge variant="public"` in `pdp/comparison.tsx` (mobile seller cards ~L377-382 + desktop "Options" column ~L455-462).
- **PDP buy-box** — plain `<p>` text lines in `pdp/buyer-trust-panel.tsx:35-38`.

Data on the PDP comes from `/products/{slug}/comparison` (`delivery_available` / `pickup_available`), so no new plumbing is needed — this is a presentation unification only.

## Required fix

Export `buildLogisticsPills` / `ListingLogisticsPills` / `catalogLogisticsLabels` from `plp/logistics-pills.tsx` and reuse them on the PDP so delivery/pickup present as the SAME colored `Pill`:

- `pdp/comparison.tsx` — replace the delivery/pickup `Badge`s (BOTH mobile cards + desktop options) with the shared pill(s), fed by the `delivery_available` / `pickup_available` already in scope. Keep the mono `Badge` for any NON-logistics info.
- `pdp/buyer-trust-panel.tsx` — swap the two delivery/pickup `<p>` lines for the shared pill treatment.
- Reuse existing keys only (`comparison.delivery|pickup`, `pdp.trust.delivery|pickup`, `plp.card.pill.*`) — pick one label set and **add NO keys**. "Never invent tags" — render a pill only when the field is truthy.
- **Do NOT touch `p/[slug]/page.tsx`** (owned by UX-A) — thread through existing props/labels only.

## Files (ONLY)

`apps/customer/app/[locale]/(shop)/_components/plp/logistics-pills.tsx` (widen exports), `_components/pdp/comparison.tsx`, `_components/pdp/buyer-trust-panel.tsx` (+ their `.test.tsx` if present).

## Tests (RUN)

`pnpm --filter customer typecheck`; `pnpm --filter customer lint`; `pnpm --filter customer test` (update comparison / buyer-trust tests to assert pills, not badges/text); blocking i18n-lint stays green. Visually confirm the PDP delivery/pickup pills match the PLP card treatment at 360px.

## Report

STATUS / FILES / DEVIATIONS / TESTS / EXCERPTS (before→after for comparison + buy-box) / QUESTIONS (flag the chosen label set for founder sign-off).
