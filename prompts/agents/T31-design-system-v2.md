# Task T31: Design system v2 — modern, neutral by default, colour icons, motion

**Agent:** Cursor. **Model:** Composer 2.5. **Branch:** `cursor/design-system-v2` from `master`. Open one PR to `master`; don't merge.
**Board:** claim row T31 in `docs/ops/agent-board.md` first. Set it to `ready for review` when done.
**This task blocks T32, T33 and T34** (customer, vendor and admin polish). Keep the public API of existing `packages/ui` components backwards compatible so the apps keep building.

**Owns (edit only these):**

- `packages/ui/**` (tokens, `styles/base.css`, `styles/theme.css`, `theme-*.ts(x)`, `icons.tsx`, new components, tests, snapshots)
- `packages/i18n/messages/*/common.json` (`theme.*` keys only)
- the customer showcase page `apps/customer/app/[locale]/ui/**`
- the theme preference UI: customer Account → Preferences, vendor Settings, admin Settings (only the block that renders `ThemePreference`)

## Why

King (founder), 24 Nov: the admin, vendor and customer apps feel amateur and dated. He wants:

- a modern, professional look with transitions and animations;
- images, and professional **coloured icons** of a reasonable size;
- the **default theme white/black, following the system**, with the current **green available as an option**.

References:

- the clean, white, illustrated style of Google Business Profile: soft line illustrations, coloured icon tiles, generous white space;
- Linear, Vercel and Shopify Admin for dashboards;
- `docs/designs/SELECTION.md` for animation ideas (page-in, shimmer, card lift).

## Build

1. **Neutral default palette** (the "Mono" accent):
   - true neutral greys (zinc-like);
   - light: white ground, near-black primary buttons with white text;
   - dark: near-black ground (#0a0a0b–#111113), near-white primary with black text.
   - Keep the semantic tokens (success, danger, warning, info) and their WCAG AA pairs.
2. **Accent choice per person**, separate from light/dark:
   - Accents: `mono` (default), `green` (today's #0b5d45 family), `blue`, `gold`.
   - Stored like the theme choice, in `localStorage` with try/catch, and set as `data-accent` on `<html>` by the existing `ThemeScript` before paint, so there's no flash.
   - Extend `ThemePreference` with an accent row of swatches.
   - Admin seasonal presets still apply globally, but a person's own accent wins.
   - All four accents must pass AA in both modes; add tests like the existing `brand-theme.test.ts`.
3. **Colour icon system:**
   - `IconTile` component: sizes 32/40/48/56, rounded-xl, soft tinted background (about 12% alpha), duotone icon (stroke in the hue, fill in the hue at 20%).
   - 10 named hues with light and dark values: blue, green, amber, orange, red, pink, purple, teal, cyan, slate.
   - Add `lucide-react` (tree-shaken) to `packages/ui`. Export a curated set of about 60 icons: commerce, services, events, logistics, money, people, settings, status. Each takes a `duotone` prop.
   - Add a category → hue + icon map for the top-level categories, so category grids get colour automatically.
   - Keep the existing `icons.tsx` exports working by re-exporting or aliasing them.
4. **Motion** (CSS first, no animation library):
   - tokens for duration (120/200/320 ms) and easing (standard, emphasised, spring);
   - utilities: `animate-page-in` (fade plus 8 px rise), `animate-pop`, skeleton shimmer, card hover lift (translateY −2 px plus shadow), press scale 0.98, dialog and bottom-sheet enter/exit, toast slide;
   - everything turns off under `prefers-reduced-motion`.
5. **Surfaces:**
   - refreshed radius (8/12/16/24), elevation levels 0–3 with soft layered shadows, hairline borders;
   - a sticky translucent header (`backdrop-blur`, solid background where blur isn't supported);
   - a consistent `PageHeader` (title, subtitle, actions, breadcrumb), `StatCard` (icon tile, value, delta chip, sparkline slot), `SectionCard` and `Skeleton` set.
6. **Spot illustrations:**
   - 8 inline SVG spot illustrations in a soft line-and-tint style (like Google Business Profile): empty cart, no orders, no products yet, verify your ID, payment success, no results, offline, welcome shop;
   - they use `currentColor` and accent tokens, so they follow the theme;
   - each is under 3 KB, and `EmptyState` takes an `illustration` prop.
7. **Typography:**
   - keep DM Sans for body text;
   - tune the scale (12/14/16/18/20/24/30/36), with tabular numbers for prices and stats.
   - Bricolage stays for display, but use it less (page titles and hero only).
8. **Showcase:** the customer `/[locale]/ui` page shows every token, both modes, all four accents, icon tiles, motion demos and illustrations, so T32–T34 and King can see them.

## Tests (required)

- Contrast tests for every accent × mode.
- `ThemeScript` sets `data-accent` from storage and falls back to mono when storage throws.
- `IconTile` renders each size and hue.
- `EmptyState` with an illustration; reduced-motion CSS test (extend `motion-css.test.ts`).
- Update the snapshots on purpose and say so in the PR.

## Done means

All three apps build and look neutral black/white by default (system mode). Switching to Green brings back today's look. The showcase page demonstrates everything. The customer route budget still holds (≤150 KB gz JS): icons must tree-shake, so check with the bundle guard and report the numbers in the PR.

## Rules

1. Claim your board row (`in progress — cursor`) in your first commit. One agent per row.
2. Work only in the files you OWN. Need another file? Stop and note it on the board.
3. Testing: run only related tests, one command at a time (`pnpm --filter @vergeo/ui exec vitest run`, then `pnpm --filter customer typecheck`, `pnpm --filter vendor typecheck`, `pnpm --filter admin typecheck`, and lint). Never the full e2e suite.
4. Never touch `supabase/`, `scripts/ci/`, `.github/`, `infra/`, payments, escrow, ledger, payouts, webhooks, auth or checkout money logic. No secrets. Never merge, force-push or `git stash`.
5. bem, nya, fr and zh: copy the English text and mark it for review.
6. When done: row to `ready for review`, one line of notes, PR link in Slack #convergeo-dev.
