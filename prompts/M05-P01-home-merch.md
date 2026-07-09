> **Prepend `prompts/_header.md` (PROJECT HEADER) above this prompt.** Branch from and PR against **`master`**. Wave 7 runs 8 pebbles in parallel — **touch ONLY your files below**. **⚠ SCHEMA FROZEN** (no migrations, no `db.ts`). Stay dep-free.

# M05-P01 — Customer home with merchandising slots

## 1. Context

**Wave 7 (parallel ×8).** Grounded against as-built `master`:

- Customer app: Next.js 15, `localePrefix:"always"`, `@vergeo/ui` (deep imports, no barrel), `@vergeo/i18n`. Existing groups: `[locale]/(marketing)`, `(auth)`, `account`. **There is a placeholder home at `apps/customer/app/[locale]/page.tsx`.** You introduce the **`(shop)` route group** for the storefront (home/PLP/PDP/search share its chrome) — **you own `(shop)/layout.tsx` (shop chrome: TopNav + BottomNav from `@vergeo/ui`) and `(shop)/page.tsx` (home), and you MUST delete `[locale]/page.tsx`** (route groups don't add a path segment, so `(shop)/page.tsx` and `[locale]/page.tsx` would both resolve to `/{locale}` — a Next.js route collision).
- **`merch_slots`** (`0008`): `slot_key, variant_key, payload jsonb, schedule_from, schedule_to, position, active`. Public-read. Home is composed entirely from active, in-schedule slots (ISR 60s).
- i18n: **`catalog` namespace** (`packages/i18n/messages/en/catalog.json`) is shared this wave by M05-P01/P02/P03 — see the **catalog.json rule** below (you own the `home` section).
  Spec: `docs/plan/02-pebbles/M05-catalog-search-discovery.md` §M05-P01.

## 2. Objective & scope

A config-driven customer home (hero variant, banner row, featured collections, **events row first**, category grid) rendered from `merch_slots`, ISR 60s, LCP = preloaded hero.
**Non-goals:** no PLP/PDP/search (siblings), no admin merch editor (M13-P08), no live cart.

## 3. Files (create/modify ONLY these)

- **Create:** `apps/customer/app/[locale]/(shop)/layout.tsx` · `(shop)/page.tsx` · `(shop)/_components/{hero,banner-row,featured-collections,events-row,category-grid}.tsx` · `packages/ui/src/merch/*` (hero variant components keyed by `variant_key`; deep-import, **no barrel**) · a data loader (server) reading `merch_slots` + categories (via the public API/SSR read)
- **Delete:** `apps/customer/app/[locale]/page.tsx` (placeholder — replaced by `(shop)/page.tsx`)
- **Modify:** `packages/i18n/messages/en/catalog.json` (add a nested `home` section — catalog.json rule)
  **Guardrail: nothing else. Do NOT create `(shop)/{c,p,search}/…` (siblings), no `request.ts`, no schema/db.ts, no other namespace.**

## 4. Implementation spec

- **`(shop)/layout.tsx`:** shop chrome (TopNav w/ search entry stub, BottomNav) from `@vergeo/ui`; wraps all shop routes.
- **Home (`page.tsx`, server, ISR 60s):** read active + in-schedule `merch_slots` ordered by `position`; render hero (variant from `packages/ui/src/merch` by `variant_key`, **preload the hero image** for LCP), banner row, featured collections, **events row first per IA**, category grid (pastel fills). **Empty/missing-variant fallback must be sane** (a default hero/skeleton, never a crash).
- All copy via `catalog` namespace (`home.*`); tokens only; 360px-first; images via `@vergeo/ui` `CloudinaryImage` (f_auto/q_auto, srcset).

## 5–8. UI/UX · Responsiveness · Performance · SEO

Editorial home per SELECTION; **LCP ≤2.5s (hero preloaded)**; ISR 60s; indexable (SEO home); category grid data-frugal.

## 9. Security

Public read only (no auth); `merch_slots` payload is admin-authored (render as data, escape user-facing text); no secrets.

## 10. Tests (RUN before reporting)

Slot-render from fixture configs incl. **scheduled + expired slots** (expired not shown); **missing-variant fallback** renders; events-row-first ordering; i18n completeness `catalog.home.*` (nested). `pnpm --filter customer build`, `pnpm typecheck`, `pnpm lint`, `pnpm test`.

## 11. Acceptance criteria / DoD

- [ ] Home composed from `merch_slots` (ISR 60s); a config change reflects ≤1min (no deploy).
- [ ] Empty-slot + missing-variant fallbacks sane; events row first; LCP = preloaded hero.
- [ ] `[locale]/page.tsx` removed (no route collision); `catalog.home.*` nested; repo green.

## catalog.json rule (shared with M05-P02 + M05-P03 this wave)

`catalog.json` is edited by three shop pebbles. **Append ONLY your nested `home` section; do NOT reorder/reformat sibling sections.** The later-merging shop PR combines sections; keep changes disjoint.

## 12. IMPLEMENTATION REPORT

Output exactly:
**PEBBLE:** M05-P01 — Customer home with merchandising slots
**STATUS:** COMPLETE | PARTIAL | BLOCKED
**FILES:** each path + one-line description
**DEVIATIONS:** (or "none")
**TESTS:** paste slot-render (scheduled/expired) + fallback + build output
**EXCERPTS:** none expected — state "none"
**QUESTIONS:** (or "none")
