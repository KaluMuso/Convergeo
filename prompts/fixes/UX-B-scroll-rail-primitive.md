> **Prepend `prompts/_header.md`.** Branch from + PR against **`master`**. **No migration. No i18n changes.** Run `pnpm --filter @vergeo/ui test && pnpm --filter customer typecheck && pnpm --filter customer lint`. Manual 360px check: horizontal scroll + hidden scrollbar + focus-visible on rail items.

# UX-B — Shared `Rail` scroller (dedupe the overflow-x idiom)

## Findings (docs/design audit §6 — mobile h-scroll)

No generic rail exists in `packages/ui/src` (only `merch/hero-carousel`, `media/image-gallery`). Four components repeat the identical idiom `flex … overflow-x-auto [-ms-overflow-style:none] [scrollbar-width:none] [&::-webkit-scrollbar]:hidden` — drift risk on scrollbar hiding, snap, and reduced-motion.

## Required fix

1. Add `packages/ui/src/rail.tsx` — RSC-safe `Rail` (deep import, **no barrel**): a wrapper encapsulating the overflow-x + hidden-scrollbar + optional `snap-x snap-mandatory` classes. Props `{ as?: "div" | "ul", snap?: boolean, className?: string, children }`; keep gap/padding caller-supplied (do not bake spacing in). Do not force `scroll-smooth` — leave motion to the caller / `prefers-reduced-motion`. Add `rail.test.tsx`: renders children; applies snap classes only when `snap`; merges `className`; default element is `div`.
2. Adopt in the four sites, preserving each one's CURRENT responsive behavior exactly (especially `category-grid`, which is scroll-on-mobile → `md:grid`):
   - `apps/customer/app/[locale]/(shop)/_components/category-grid.tsx:132` (keep `snap-x snap-mandatory` + the `md:grid …` breakpoint switch)
   - `apps/customer/app/[locale]/(shop)/_components/home-recently-viewed-rail.tsx:54`
   - `apps/customer/app/[locale]/(shop)/services/_components/vertical-filter-chips.tsx:56`
   - `apps/customer/app/[locale]/account/_components/account-nav.tsx:53`

## Files (ONLY)

`packages/ui/src/rail.tsx`, `packages/ui/src/rail.test.tsx`, and the four component files listed above.

## Tests (RUN)

`pnpm --filter @vergeo/ui test` (new rail tests green + no regressions); `pnpm --filter customer typecheck`; `pnpm --filter customer lint`. Verify on a real 360px viewport that each rail still scrolls horizontally with no visible scrollbar and keyboard focus reaches each item.

## Report

STATUS / FILES / DEVIATIONS / TESTS / EXCERPTS (Rail API + one adoption before→after) / QUESTIONS.
