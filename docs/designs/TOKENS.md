# Vergeo5 Design Tokens

**Authoritative implementation:** `packages/ui/src/tokens.ts` + `packages/ui/src/styles/base.css` + `packages/ui/tailwind-preset.ts`.  
**Product direction:** [`docs/design/vergeo5-ui-ux-audit.md`](../design/vergeo5-ui-ux-audit.md) §6 (supersedes aubergine dark panels from SELECTION.md §5).  
**Foundation notes:** [`docs/design/design-system-foundation.md`](../design/design-system-foundation.md).

Changing a value in `tokens.ts` propagates to the Tailwind preset (`buildTailwindTheme()`); `base.css` mirrors the same values as CSS custom properties for non-Tailwind consumers.

---

## Color tokens

| Token                 | Light value             | Dark value              | Tailwind key                              |
| --------------------- | ----------------------- | ----------------------- | ----------------------------------------- |
| `--bg`                | `#FAF7F2`               | `#141312`               | `bg-bg`                                   |
| `--bg-2`              | `#F3EDE3`               | `#1C1A18`               | `bg-bg-2`                                 |
| `--surface`           | `#FFFFFF`               | `#22201E`               | `bg-surface`                              |
| `--surface-elevated`  | `#FFFFFF`               | `#2A2826`               | `bg-surface-elevated`                     |
| `--border`            | `#E8DFD0`               | `rgba(255,255,255,.10)` | `border-border`                           |
| `--panel`             | `#1A1816` (charcoal)    | same (chrome only)      | `bg-panel`                                |
| `--panel-2`           | `#242220`               | same                    | `bg-panel-2`                              |
| `--panel-text`        | `#F2EDE6`               | same                    | `text-panel-text`                         |
| `--panel-muted`       | `#A39E96`               | same                    | `text-panel-muted`                        |
| `--panel-border`      | `rgba(255,255,255,.08)` | same                    | `border-panel-border`                     |
| `--text`              | `#2A2118`               | `#F2EDE6`               | `text-text`                               |
| `--text-2`            | `#6B5A3E`               | `#B0A99F`               | `text-text-2`                             |
| `--text-3`            | `#7A6A52`               | `#8A837A`               | `text-text-3`                             |
| `--display-ink`       | `#23324E`               | `#F2EDE6`               | `text-display-ink`                        |
| `--primary`           | `#2D4A7A`               | `#7AA0D4`               | `text-primary`, `bg-primary`              |
| `--primary-deep`      | `#1F3557`               | `#5A82B8`               | `bg-primary-deep`                         |
| `--primary-tint`      | `#E8F0FA`               | `#2A323C`               | `bg-primary-tint`                         |
| `--primary-btn-fg`    | `#FFFFFF`               | `#141312`               | use `text-[var(--primary-btn-fg)]`        |
| `--primary-btn-hover` | `#1F3557`               | `#8BB0DC`               | use `hover:bg-[var(--primary-btn-hover)]` |
| `--accent`            | `#C8861A`               | `#D4A04A`               | `text-accent`                             |
| `--success`           | `#3A7A4A`               | (unchanged)             | `text-success`                            |
| `--danger`            | `#C0392B`               | (unchanged)             | `text-danger`                             |
| `--on-danger`         | `#FFFFFF`               | `#FFFFFF`               | `text-on-danger`                          |
| `--warning`           | `#D4A020`               | (unchanged)             | `text-warning`                            |
| `--info`              | `#2A6A9A`               | (unchanged)             | `text-info`                               |
| `--price`             | `#2A2118`               | `#F2EDE6`               | use `text-[var(--price)]`                 |
| `--discount`          | `#C0392B`               | `#E57368`               | `text-discount`                           |
| `--cat-*`             | pastel fills            | (unchanged)             | `bg-cat-*`                                |

Default Tailwind palette colors (`red`, `blue`, `slate`, etc.) are **not** included in the preset. Arbitrary color utilities are discouraged.

**Do not** alias page `--bg` to `--panel`. Panel is marketing chrome (footer / dark heroes only).

### Tag tint recipe

`tagTint(hex)` → `{ bg: hex+'1A', border: hex+'33', text: hex }` (10% / 20% alpha on 6-digit hex).

---

## Typography

| Token                      | Value                                | Tailwind key               |
| -------------------------- | ------------------------------------ | -------------------------- |
| `--font-display`           | DM Serif Display stack               | `font-display`             |
| `--font-display-alt`       | Cormorant Garamond (inactive preset) | `font-display-alt`         |
| `--font-body`              | DM Sans stack                        | `font-body`, `font-sans`   |
| `--font-mono`              | JetBrains Mono stack                 | `font-mono`                |
| `--fs-hero` … `--fs-price` | clamp / rem scale                    | `text-hero` … `text-price` |

Fonts load via `next/font` helpers in `@vergeo/ui/fonts`. Customer locale layout applies `fontVariables()` on `<html>`.

---

## Spacing / container / radii / elevation / motion

Unchanged 4px spacing scale (`--sp-1`…`--sp-16`).

| Token                                    | Value                                       |
| ---------------------------------------- | ------------------------------------------- |
| `--container-max`                        | `80rem`                                     |
| `--container-gutter`                     | `16px` (24px at `lg`)                       |
| `--r-sm` / `--r` / `--r-lg` / `--r-pill` | `8` / `12` / `16` / `999`                   |
| `--shadow-1`…`3`, `--focus-ring`         | warm light / black-based dark               |
| `--dur-fast` / `--dur` / `--dur-slow`    | 150 / 250 / 400ms                           |
| easings                                  | `--ease-out`, `--ease-std`, `--ease-spring` |

Utility: `.ds-container` for max-width + gutters.

---

## Dark mode

`[data-theme="dark"]` on `<html>` (set pre-paint by `ThemeScript`, runtime by `ThemeProvider`).  
Default user choice: **`system`**. Customer theme control: Account → Preferences (`ThemePreference`), not the primary navbar.

---

## WCAG AA contrast pairs (normal text ≥ 4.5:1)

Asserted in `packages/ui/src/tokens.test.ts` via `contrastPairs` (includes dark pairs and `on-danger`).

### K-pricing display

- Current price: `--price` + `--fs-price` weight 700 via `PriceBlock`
- Struck old price: `--text-3`
- Savings / discount chip: `--discount`
