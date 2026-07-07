> **Prepend `prompts/_header.md` (PROJECT HEADER) above this prompt.** Composer sessions share no memory — the header is required context.

# M02-P01 — Design tokens & Tailwind theme

## 1. Context
**Wave 1 (parallel with M02-P02 and M01-P08 — your files are disjoint from theirs; touch nothing outside your list).** Wave 0 is merged. As-built state you rely on: three Next.js apps consume a Tailwind preset **from `@vergeo/config`** (`packages/config/src/tailwind-preset.ts` — currently an empty stub); `packages/ui` **does not exist yet**. Spec source: `docs/plan/02-pebbles/M02-design-system.md` §P01. Token source of truth: **`docs/designs/SELECTION.md` §5** (read it in full — every value comes from there, none invented).

## 2. Objective & scope
Create `packages/ui` with the real token system (CSS custom properties + Tailwind 4 theme + exported token object + fonts + global keyframes), flip the `@vergeo/config` stub to re-export it, and document the token map.
**Non-goals:** no components (P03+), no app-level changes (apps already consume the preset via `@vergeo/config` — they pick the real tokens up transitively), no i18n (M02-P02's lane).

## 3. Files (create/modify ONLY these)
- **Create:** `packages/ui/package.json` · `packages/ui/tsconfig.json` · `packages/ui/tailwind-preset.ts` · `packages/ui/src/tokens.ts` · `packages/ui/src/styles/base.css` · `packages/ui/src/tokens.test.ts` · `docs/designs/TOKENS.md`
- **Modify:** `packages/config/src/tailwind-preset.ts` (replace stub body with a re-export of the `@vergeo/ui` preset — one-liner; keeps all three apps' `tailwind.config.ts` untouched)
- `pnpm-lock.yaml` will change from the new workspace package — that is expected; **you are the only Wave-1 pebble allowed to touch it** (add no other new external deps beyond what fonts/tailwind strictly require).
**Guardrail: nothing else — especially not `packages/i18n/**`, `packages/config/eslint*`, `supabase/**`, or any `apps/**` file.**

## 4. Implementation spec
- **`src/tokens.ts`:** typed token object encoding SELECTION.md §5 exactly — ground/surfaces (`#FAF7F2`, `#F3EDE3`, `#FFFFFF`, border `#E8DFD0`), aubergine panels (`#241B30`, `#2E2440`, panel text/muted/border), ink (`#2A2118`/`#6B5A3E`/`#9C8A72`, display ink `#23324E`), brand navy `#2D4A7A` (+deep/tint), gold accent `#C8861A`, semantics, 6 category pastels, type scale (fs-hero clamp → fs-micro, fs-price), 4px spacing scale, radii (8/12/18/pill), warm-black shadows, focus ring, motion durations + the three easings. Include the **tint recipe helper** `tagTint(hex)` → `{bg: hex+'1A', border: hex+'33', text: hex}`.
- **`tailwind-preset.ts`:** Tailwind 4 preset mapping tokens into `theme` (colors, fontFamily, fontSize, spacing, borderRadius, boxShadow, transitionDuration/TimingFunction). **Disallow arbitrary color values** where Tailwind config allows enforcement, so ad-hoc colors fail lint/build.
- **`src/styles/base.css`:** `:root` CSS custom properties for every token; `.dark` remap to the aubergine panel set; global keyframes `page-in, toast-in, toast-out, shimmer, float-a, float-b, fadeSlideUp, pulse-dots`; `prefers-reduced-motion` media query disabling all but opacity fades.
- **Fonts:** export a `next/font` helper (DM Sans body, DM Serif Display display, JetBrains Mono; Cormorant Garamond wired as the inactive alternate preset per SELECTION.md).
- **`docs/designs/TOKENS.md`:** table mapping every token → its SELECTION.md §5 source line + documented **WCAG AA contrast pairs** (text-on-ground, panel-text-on-panel, primary-on-tint, etc.).
- Deep imports only — **no `src/index.ts` barrel** (binding convention; parallel M02 pebbles each own their files).

## 5. UI/UX & styling
This IS the styling source. K-pricing display note: gold accent for sale/stars per SELECTION.md; struck old price in `--text-3`.

## 6–7. Responsiveness · Performance
Type scale is 360px-first (clamp-based hero). Font loading via `next/font` (self-hosted, no layout shift); keep the CSS payload lean — tokens + keyframes only, no utility dumps.

## 8. SEO
N/A.

## 9. Security
No external fetches beyond `next/font`; no secrets.

## 10. Tests (RUN before reporting)
- Snapshot test of the resolved Tailwind theme object (preset exports all required keys).
- **Contrast assertions (WCAG AA ≥4.5:1 normal text)** on the documented token pairs — compute programmatically in `tokens.test.ts`.
- `tagTint('#C8861A')` returns `#C8861A1A`/`#C8861A33`/`#C8861A`.
- All three apps still build with the real preset: `pnpm --filter customer --filter vendor --filter admin build`; `pnpm typecheck`, `pnpm test`, `pnpm lint`.

## 11. Acceptance criteria / DoD
- [ ] Changing a token in ONE file (`tokens.ts`/`base.css`) propagates to all apps via the preset chain.
- [ ] TOKENS.md maps every token to its SELECTION.md source; contrast pairs pass AA (tested).
- [ ] Arbitrary color values rejected by config where enforceable.
- [ ] No barrel file in `packages/ui`; apps' tailwind configs untouched.
- [ ] All apps build; reduced-motion honored.

## 12. IMPLEMENTATION REPORT
When finished, output an **Implementation Report** in exactly this format:
**PEBBLE:** M02-P01 — Design tokens & Tailwind theme
**STATUS:** COMPLETE | PARTIAL | BLOCKED
**FILES:** each path + one-line description of the change
**DEVIATIONS:** any departure from spec, and why (or "none")
**TESTS:** paste the actual test/build output incl. contrast assertions
**EXCERPTS:** none expected — state "none"
**QUESTIONS:** uncertainties needing a reviewer decision (or "none")
