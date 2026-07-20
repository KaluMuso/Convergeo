# Design-system foundation — implementation notes

**Date:** 2026-07-20  
**Source of truth:** [`vergeo5-ui-ux-audit.md`](./vergeo5-ui-ux-audit.md) §6–§8, §11 PR1–PR2 (partial)  
**Branch scope:** tokens, shared primitives, customer fonts, theme relocation — **not** homepage/nav redesign.

## What changed

### Colour tokens (`packages/ui`)

| Token                              | Light                             | Dark                                                |
| ---------------------------------- | --------------------------------- | --------------------------------------------------- |
| `--bg` / `--bg-2`                  | cream `#FAF7F2` / `#F3EDE3`       | charcoal `#141312` / `#1C1A18`                      |
| `--surface` / `--surface-elevated` | white                             | `#22201E` / `#2A2826`                               |
| `--panel*`                         | warm charcoal `#1A1816` family    | same (chrome only — **not** aliased to page ground) |
| `--text-3`                         | raised to `#7A6A52` (AA on cream) | `#8A837A`                                           |
| `--on-danger`                      | `#FFFFFF`                         | `#FFFFFF`                                           |
| `--price` / `--discount`           | ink / danger                      | light ink / soft red                                |

**Removed:** aubergine `#241B30` / `#2E2440` / lilac muted as global dark grounds.

### Typography

Customer locale layout wires `fontVariables()` from `@vergeo/ui/fonts` on `<html>` and `font-body` on `<body>`.

### Components

| Component                          | File                                   | Notes                                                        |
| ---------------------------------- | -------------------------------------- | ------------------------------------------------------------ |
| Button                             | `packages/ui/src/button.tsx`           | RSC-safe; destructive uses `text-on-danger`                  |
| LinkButton                         | `packages/ui/src/link-button.tsx`      | **new** — shared variants                                    |
| Input / Select / Textarea          | `*.tsx` + `field-styles.ts`            | Shared field chrome; RSC-safe                                |
| SearchField                        | `packages/ui/src/search-field.tsx`     | **new** — pill search shell                                  |
| Badge                              | `packages/ui/src/badge.tsx`            | CSS-var classes; sale/stock/sponsored/sample                 |
| PriceBlock                         | `packages/ui/src/price-block.tsx`      | `--price` / `--discount`                                     |
| Skeleton / EmptyState / ErrorState | `*.tsx`                                | SVG defaults; dark-safe retry CTA                            |
| Footer                             | `packages/ui/src/footer.tsx`           | CSS vars (no frozen JS hex)                                  |
| ThemePreference                    | `packages/ui/src/theme-preference.tsx` | **new** — radios for Preferences                             |
| ThemeToggle                        | `theme-toggle.tsx`                     | Kept for vendor/admin; **removed from customer shop chrome** |

### Theme architecture

- Default remains **`system`** (`ThemeProvider` + `ThemeScript` + `vg-theme` localStorage).
- Customer primary navbar no longer hosts the theme control.
- Control lives in **Account → Preferences** (`ThemePreference`).
- Quiet footer link “Display preferences” → `/account/preferences`.

### Motion

- Fixed invalid chained `@keyframes` under `prefers-reduced-motion`.
- `.card-lift` no longer displaces under reduced motion; hover lift reduced to 2px.

## Migration guidance (later page redesigns)

1. Prefer semantic utilities: `bg-bg`, `bg-surface`, `bg-surface-elevated`, `text-text`, `text-text-2`, `border-border`, `bg-panel` (chrome only).
2. Solid CTAs: use `Button` / `LinkButton` with `rounded` (12px) — reserve `rounded-pill` for search/chips.
3. Danger buttons: `text-on-danger` (never assume `text-surface` in dark).
4. Prices: `PriceBlock` or `text-[var(--price)]` + `text-discount` for sale chips.
5. Search chrome: prefer `SearchField` over one-off pill inputs.
6. Empty/error: shared `EmptyState` / `ErrorState` — no emoji icons.
7. Containers: `.ds-container` or `max-w-7xl` + `var(--container-gutter)`.
8. Do **not** set page backgrounds to `bg-panel` — panel is footer/hero chrome.

## Intentionally deferred (audit items)

| Item                                         | Why deferred                                                 |
| -------------------------------------------- | ------------------------------------------------------------ |
| SVG shop icon set / emoji nav replacement    | Audit P0 but out of this task’s “no nav redesign” constraint |
| Bottom-nav IA (Orders tab)                   | Explicitly deferred                                          |
| Homepage / PLP / PDP redesign                | Explicitly deferred                                          |
| Vendor/admin theme toggle relocation         | Customer-only per task; shared tokens still apply            |
| `next/image` Cloudinary split                | Performance P2, not foundation tokens                        |
| LinkButton adoption across ~85 one-off Links | Foundation ships component; page migration later             |

## Component inventory delta

See audit §7. Updates from this work:

- Tokens / base.css → **refactored** (charcoal)
- fontVariables → **wired** (customer)
- ThemeToggle → **relocated** (customer); ThemePreference **added**
- Footer → **refactored** (CSS vars)
- Button → **refactored** (RSC-safe + on-danger)
- LinkButton / SearchField / ThemePreference → **added**
- Badge / PriceBlock / Empty / Error → **refactored**
