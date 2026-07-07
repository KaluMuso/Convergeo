# Vergeo5 Design Tokens

Source of truth: [`SELECTION.md` §5](./SELECTION.md) (Proposed unified token set). Implementation: `packages/ui/src/tokens.ts` + `packages/ui/src/styles/base.css` + `packages/ui/tailwind-preset.ts`.

Changing a value in `tokens.ts` propagates to the Tailwind preset (`buildTailwindTheme()`); `base.css` mirrors the same values as CSS custom properties for non-Tailwind consumers.

---

## Color tokens

| Token            | Value                   | SELECTION.md §5 source                 | Tailwind key                 |
| ---------------- | ----------------------- | -------------------------------------- | ---------------------------- |
| `--bg`           | `#FAF7F2`               | L119 `/* cream page ground */`         | `bg-bg`                      |
| `--bg-2`         | `#F3EDE3`               | L120 `/* recessed cream */`            | `bg-bg-2`                    |
| `--surface`      | `#FFFFFF`               | L121 `/* cards */`                     | `bg-surface`                 |
| `--border`       | `#E8DFD0`               | L122                                   | `border-border`              |
| `--panel`        | `#241B30`               | L124 `/* aubergine */`                 | `bg-panel`                   |
| `--panel-2`      | `#2E2440`               | L125 `/* elevated aubergine */`        | `bg-panel-2`                 |
| `--panel-text`   | `#EEEAE3`               | L126                                   | `text-panel-text`            |
| `--panel-muted`  | `#9F94B0`               | L126                                   | `text-panel-muted`           |
| `--panel-border` | `rgba(255,255,255,.08)` | L126                                   | `border-panel-border`        |
| `--text`         | `#2A2118`               | L128 `/* warm near-black body ink */`  | `text-text`                  |
| `--text-2`       | `#6B5A3E`               | L129                                   | `text-text-2`                |
| `--text-3`       | `#9C8A72`               | L129                                   | `text-text-3`                |
| `--display-ink`  | `#23324E`               | L130 `/* dark navy serif headlines */` | `text-display-ink`           |
| `--primary`      | `#2D4A7A`               | L132 `/* navy — actions, links */`     | `text-primary`, `bg-primary` |
| `--primary-deep` | `#1F3557`               | L133                                   | `bg-primary-deep`            |
| `--primary-tint` | `#E8F0FA`               | L133                                   | `bg-primary-tint`            |
| `--accent`       | `#C8861A`               | L134 `/* gold — sale, stars, flash */` | `text-accent`                |
| `--success`      | `#3A7A4A`               | L135                                   | `text-success`               |
| `--danger`       | `#C0392B`               | L135                                   | `text-danger`                |
| `--warning`      | `#D4A020`               | L135                                   | `text-warning`               |
| `--info`         | `#2A6A9A`               | L135                                   | `text-info`                  |
| `--cat-beauty`   | `#C9A88A`               | L137                                   | `bg-cat-beauty`              |
| `--cat-health`   | `#7AAB8A`               | L137                                   | `bg-cat-health`              |
| `--cat-food`     | `#C9836A`               | L137                                   | `bg-cat-food`                |
| `--cat-fitness`  | `#7A9AB5`               | L137                                   | `bg-cat-fitness`             |
| `--cat-home`     | `#B5A07A`               | L137                                   | `bg-cat-home`                |
| `--cat-auto`     | `#8A8AB5`               | L137                                   | `bg-cat-auto`                |

Default Tailwind palette colors (`red`, `blue`, `slate`, etc.) are **not** included in the preset — only the tokens above resolve. Arbitrary color utilities (`bg-[#ff0000]`) are discouraged; use token keys.

### Tag tint recipe

Per SELECTION.md L139: `tagTint(hex)` → `{ bg: hex+'1A', border: hex+'33', text: hex }` (10% / 20% alpha on 6-digit hex).

---

## Typography

| Token                | Value                                | SELECTION.md §5 source  | Tailwind key             |
| -------------------- | ------------------------------------ | ----------------------- | ------------------------ |
| `--font-display`     | DM Serif Display stack               | L141                    | `font-display`           |
| `--font-display-alt` | Cormorant Garamond (inactive preset) | L141 `/* alt preset */` | `font-display-alt`       |
| `--font-body`        | DM Sans stack                        | L142                    | `font-body`, `font-sans` |
| `--font-mono`        | JetBrains Mono stack                 | L143                    | `font-mono`              |
| `--fs-hero`          | `clamp(2rem, 6vw, 3.9rem)`           | L144                    | `text-hero`              |
| `--fs-h1`            | `1.75rem`                            | L145                    | `text-h1`                |
| `--fs-h2`            | `clamp(1.35rem, 2.4vw, 2.1rem)`      | L145                    | `text-h2`                |
| `--fs-h3`            | `1.0625rem`                          | L146                    | `text-h3`                |
| `--fs-body`          | `.9375rem` (15px)                    | L147                    | `text-body`              |
| `--fs-sm`            | `.8125rem`                           | L147                    | `text-sm`                |
| `--fs-micro`         | `.6875rem`                           | L147                    | `text-micro`             |
| `--fs-price`         | `1.02rem`                            | L148                    | `text-price`             |

Fonts load via `next/font` helpers in `@vergeo/ui/fonts` (DM Sans, DM Serif Display, JetBrains Mono; Cormorant Garamond wired as inactive alternate).

---

## Spacing (4px base)

| Token     | Value  | SELECTION.md §5 source | Tailwind key       |
| --------- | ------ | ---------------------- | ------------------ |
| `--sp-1`  | `4px`  | L150                   | `p-1`, `m-1`, etc. |
| `--sp-2`  | `8px`  | L150                   | `*-2`              |
| `--sp-3`  | `12px` | L150                   | `*-3`              |
| `--sp-4`  | `16px` | L150                   | `*-4`              |
| `--sp-5`  | `20px` | L150                   | `*-5`              |
| `--sp-6`  | `24px` | L151                   | `*-6`              |
| `--sp-8`  | `32px` | L151                   | `*-8`              |
| `--sp-12` | `48px` | L151                   | `*-12`             |
| `--sp-16` | `64px` | L151                   | `*-16`             |

---

## Radii

| Token      | Value   | SELECTION.md §5 source | Tailwind key   |
| ---------- | ------- | ---------------------- | -------------- |
| `--r-sm`   | `8px`   | L154                   | `rounded-sm`   |
| `--r`      | `12px`  | L154                   | `rounded`      |
| `--r-lg`   | `18px`  | L154                   | `rounded-lg`   |
| `--r-pill` | `999px` | L154                   | `rounded-pill` |

---

## Shadows

| Token          | Value                           | SELECTION.md §5 source | Tailwind key       |
| -------------- | ------------------------------- | ---------------------- | ------------------ |
| `--shadow-1`   | `0 1px 4px rgba(28,19,8,.05)`   | L156                   | `shadow-1`         |
| `--shadow-2`   | `0 4px 24px rgba(28,19,8,.07)`  | L157                   | `shadow-2`         |
| `--shadow-3`   | `0 12px 48px rgba(28,19,8,.13)` | L158                   | `shadow-3`         |
| `--focus-ring` | `0 0 0 3px rgba(45,74,122,.18)` | L159                   | `shadow-focusRing` |

---

## Motion

| Token           | Value                          | SELECTION.md §5 source | Tailwind key    |
| --------------- | ------------------------------ | ---------------------- | --------------- |
| `--dur-fast`    | `150ms`                        | L161                   | `duration-fast` |
| `--dur`         | `250ms`                        | L161                   | `duration`      |
| `--dur-slow`    | `400ms`                        | L161                   | `duration-slow` |
| `--ease-out`    | `cubic-bezier(.2,.8,.3,1)`     | L162                   | `ease-out`      |
| `--ease-std`    | `cubic-bezier(.4,0,.2,1)`      | L163                   | `ease-std`      |
| `--ease-spring` | `cubic-bezier(.34,1.56,.64,1)` | L164                   | `ease-spring`   |

Global keyframes in `base.css`: `page-in`, `toast-in`, `toast-out`, `shimmer`, `float-a`, `float-b`, `fadeSlideUp`, `pulse-dots`. `prefers-reduced-motion` disables transform/position animations; opacity fades remain.

---

## Dark mode

`.dark` remaps ground/surface/text tokens to the aubergine panel set (SELECTION.md L167). Mechanism: CSS custom properties in `base.css`.

---

## WCAG AA contrast pairs (normal text ≥ 4.5:1)

Tested programmatically in `packages/ui/src/tokens.test.ts`.

| Pair                  | Foreground | Background | Ratio   | Pass                   |
| --------------------- | ---------- | ---------- | ------- | ---------------------- |
| text-on-ground        | `#2A2118`  | `#FAF7F2`  | ~14.8:1 | ✓                      |
| text-on-surface       | `#2A2118`  | `#FFFFFF`  | ~15.9:1 | ✓                      |
| text-2-on-ground      | `#6B5A3E`  | `#FAF7F2`  | ~5.5:1  | ✓                      |
| text-3-on-ground      | `#9C8A72`  | `#FAF7F2`  | ~3.2:1  | decorative/muted only* |
| display-ink-on-ground | `#23324E`  | `#FAF7F2`  | ~11.5:1 | ✓                      |
| primary-on-tint       | `#2D4A7A`  | `#E8F0FA`  | ~6.8:1  | ✓                      |
| primary-on-surface    | `#2D4A7A`  | `#FFFFFF`  | ~7.3:1  | ✓                      |
| accent-on-ground      | `#C8861A`  | `#FAF7F2`  | ~3.4:1  | large/bold only*       |
| panel-text-on-panel   | `#EEEAE3`  | `#241B30`  | ~12.5:1 | ✓                      |
| panel-muted-on-panel  | `#9F94B0`  | `#241B30`  | ~5.1:1  | ✓                      |
| success-on-ground     | `#3A7A4A`  | `#FAF7F2`  | ~4.6:1  | ✓                      |
| danger-on-ground      | `#C0392B`  | `#FAF7F2`  | ~5.0:1  | ✓                      |

\* `--text-3` and `--accent` are used for struck prices, stars, and decorative chips per SELECTION.md L169 — not primary body copy. Tests assert the documented pairs in `contrastPairs`; pairs below 4.5:1 are excluded from the AA assertion set.

### K-pricing display

- Sale price / stars: `--accent` (`#C8861A`)
- Struck old price: `--text-3` (`#9C8A72`)
- Price numerals: `--fs-price` at weight 700
