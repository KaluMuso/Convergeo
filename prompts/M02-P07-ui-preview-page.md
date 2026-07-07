> **Prepend `prompts/_header.md` (PROJECT HEADER) above this prompt.** Branch from and PR against **`master`**. Wave 3 runs 5 pebbles in parallel — **touch ONLY your files below**; do NOT touch `pnpm-lock.yaml`, any `packages/ui/src/*` component, `supabase/**`, or `messages/*.json`.

# M02-P07 — Component preview page

## 1. Context

**Wave 3 (parallel ×5).** The full M02 kit is merged on `master` under `packages/ui/src/`: form controls (button, input, select, textarea, otp-field, checkbox, radio, switch, form-field), cards (product/event/service/vendor-card, badge, corner-ribbon, pill, price-block, star-rating, tier-price-table), overlays (modal, bottom-sheet, toast, skeleton, spinner, empty-state, error-state, confirm-dialog), nav (top-nav, bottom-nav, tabs, breadcrumbs, stepper, pagination), media (`media/cloudinary-image`, `media/image-gallery`, `media/upload-dropzone`). Deep imports: `@vergeo/ui/src/<name>` (no barrel). Global styles/keyframes: import `@vergeo/ui/styles/base.css`. Spec: `docs/plan/02-pebbles/M02-design-system.md` §P07.

## 2. Objective & scope

A dev-gated gallery route in the customer app rendering EVERY exported kit component in all meaningful states, plus a CI export-coverage check.
**Non-goals:** no component changes (if one looks broken, record under DEVIATIONS — do not fix), no Storybook dependency, no prod exposure.

## 3. Files (create ONLY these)

- `apps/customer/app/[locale]/(dev)/ui/page.tsx` + section files `apps/customer/app/[locale]/(dev)/ui/_sections/*.tsx` (one per component family: forms, cards, overlays, nav, media, states)
- `apps/customer/app/[locale]/(dev)/ui/layout.tsx` (imports `base.css`, **production gate**: `notFound()` when `process.env.NODE_ENV === "production"` and no `NEXT_PUBLIC_ENABLE_UI_PREVIEW` flag)
- `scripts/ci/ui-preview-coverage.mjs` — diffs component modules under `packages/ui/src` (excluding tests/tokens/styles/fonts) against imports in the preview sections; exits non-zero on uncovered components
  **Guardrail: nothing else.**

## 4. Implementation spec

- Each section renders its family's components across states: variants/sizes/disabled/loading (forms), skeleton + populated + long-Nyanja-string (cards), open overlays via trigger buttons (modal/sheet/confirm/toasts), active/badge states (nav), gallery with sample publicIds + dropzone (media).
- PriceBlock demos use integer ngwee fixtures. Cards get placeholder `media` slots (styled divs — no external images; CloudinaryImage demo may point at a placeholder publicId that 404s gracefully).
- This is a **dev-only** page: add a file-level `/* eslint-disable @vergeo/no-hardcoded-strings */` with a comment (never ships to prod — the gate above) instead of creating an i18n namespace.
- Coverage script: glob `packages/ui/src/**/*.tsx` minus `*.test.tsx`, compare module names against static imports in `(dev)/ui/**`; print missing list.

## 5–8. UI/UX · Responsiveness · Performance · SEO

Sections anchored + linked from a top index; page usable at 360px; `robots` noindex meta on the route; not part of any prod bundle path (route-group isolated).

## 9. Security

Prod gate tested; no secrets; placeholder data only.

## 10. Tests (RUN before reporting)

- `node scripts/ci/ui-preview-coverage.mjs` → exit 0 (paste output); temporarily comment one import → exits non-zero (demonstrate, restore).
- Prod-gate unit test or documented manual check (`NODE_ENV=production` build → route 404s).
- `pnpm --filter customer build`, `pnpm typecheck`, `pnpm lint`, `pnpm test`.
- Lighthouse a11y on the page if runnable locally (else note for CI): target ≥95 — fix contrast/label issues found in YOUR page markup only.

## 11. Acceptance criteria / DoD

- [ ] Every exported component appears (coverage script proves it).
- [ ] Page 404s in production builds without the flag.
- [ ] Renders clean at 360px; overlays operable; repo green.

## 12. IMPLEMENTATION REPORT

When finished, output an **Implementation Report** in exactly this format:
**PEBBLE:** M02-P07 — Component preview page
**STATUS:** COMPLETE | PARTIAL | BLOCKED
**FILES:** each path + one-line description
**DEVIATIONS:** (or "none")
**TESTS:** paste coverage-script + build output
**EXCERPTS:** none expected — state "none"
**QUESTIONS:** (or "none")
