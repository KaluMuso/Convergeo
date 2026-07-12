> **Prepend `prompts/_header.md`.** Branch `agent/ui-p2-customer-motion` from + PR against **`master`**. **⚙ Do NOT use `git stash`** (shared refs/stash across worktrees). Foreground blocking only. Commit trailers required:
> `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`
> `Claude-Session: https://claude.ai/code/session_0182ebfSrQf83JNZCiKqjAby`
> PR title: `UI-P2: customer motion, polish & token cleanup`.

# UI-P2 — Customer app: motion/transitions layer, token cleanup, dark polish

## Context (grounded)

UI-P1 (#174, merged) made the `packages/ui` design tokens **real**: `packages/ui/src/styles/theme.css` maps every `--<token>` to a Tailwind v4 utility via `@theme inline`, all 3 apps import it, and dark mode works via `[data-theme="dark"]` + a mounted `ThemeToggle`. Valid color utilities are ONLY those backed by a `--color-*` entry in `theme.css` (e.g. `bg-bg`, `bg-bg-2`, `bg-surface`, `bg-panel`, `text-text`, `text-text-2`, `text-text-3`, `text-muted`, `bg-primary`, `text-primary`, `border-border`, `bg-success/danger/warning/info`, the `cat-*` set). Motion/timing tokens exist in `base.css`: `--dur-fast`, `--dur`, `--dur-slow`, `--ease-out`, `--ease-std`, `--ease-spring`, plus `--radius-*`/`--shadow-*`.

Your surface is **`apps/customer` + a small, additive slice of `packages/ui`**. Do the four tasks below. **No structural/logic refactors** — this is a styling + motion pass only.

## Tasks

1. **Finish the 2 raw-hex customer files** → swap hardcoded hex colors for the correct token utilities (or `var(--token)` in inline style where a utility can't express it):
   - `apps/customer/app/[locale]/account/_components/static-map-preview.tsx`
   - `apps/customer/app/[locale]/account/privacy/page.tsx` (verify; migrate any hex found)
     Grep the whole app for stragglers: `grep -rE "#[0-9a-fA-F]{3,8}\b" apps/customer/app` and migrate any that are UI colors (leave non-color hex like SVG path data / ids alone).

2. **Dead color-class sweep** across `apps/customer`. Bare legacy classes like `text-2`, `bg-2`, `text-text-1`, `bg-bg-1`, `border-border-1` are **no-ops under Tailwind v4** (no matching token utility) → they render nothing and pages fall back to defaults. Replace each with the intended valid token utility, verifying the target exists in `theme.css`:
   - `text-text-1` → `text-text`, `bg-bg-1` → `bg-bg`, `border-border-1` → `border-border`
   - bare `text-2` → `text-muted` (secondary text), bare `bg-2` → `bg-bg-2`
   - Confirm with `grep` before/after; do NOT touch valid multi-token names (`text-2xl`, `gap-2`, `p-2` are unrelated Tailwind utilities — only the color ones above are dead).

3. **Motion / transitions / skeleton layer** — the core of "improve animations, transitions." **CSS-first only — NO new JS animation dependency** (framer-motion etc. would blow the ≤150 KB / 3G-data budget). Build it in `packages/ui/src/styles/theme.css` (keyframes + utility classes driven by the existing `--dur*`/`--ease*` tokens) and a new `packages/ui/src/skeleton.tsx` shimmer component, then apply in the customer app:
   - **Global respect for `prefers-reduced-motion: reduce`** — a media block that zeroes transition/animation durations. MANDATORY.
   - Tasteful, low-cost motion: fade/slide-in on route/section mount, tap/press feedback on buttons & cards (scale/opacity via `active:`), smooth `transition-colors` on the theme toggle and interactive elements, focus-ring transitions.
   - **Skeleton loaders** on the key async customer surfaces (search results / PLP grid, PDP, cart) so 3G loads feel instant — use the new `Skeleton` shimmer. Keep them lightweight.
   - Keep it subtle and fast (≤ `--dur` ~200ms); this is Zambia-on-3G, not a splash reel.

4. **Dark-mode primary-button contrast fix** — in dark mode the primary button bg/text must meet **AA contrast**. Fix in `packages/ui/src/button.tsx` and/or the dark token block in `base.css` (adjust `--primary`/`--primary-deep` or the button's dark text color). Verify against the `.dark`/`[data-theme="dark"]` values.

## Files (ownership — touch ONLY these)

- `apps/customer/**` (styling/motion only — no route/data/logic changes)
- `packages/ui/src/styles/theme.css` (motion keyframes + utility classes)
- `packages/ui/src/skeleton.tsx` (NEW shimmer component) + its export usage via deep import
- `packages/ui/src/button.tsx` (dark contrast only)
- `packages/ui/src/styles/base.css` (only if a token value needs adjusting for #4)
- **Do NOT touch** `apps/vendor`, `apps/admin`, `services/api`, `supabase/migrations`, `packages/types/src/db.ts`, `pnpm-lock.yaml` (no new deps), any router, `ci.yml`/`perf.yml`, `lighthouserc.json` (if a bundle ceiling genuinely trips, STOP and report the delta — do not bump it yourself).

## Constraints

- **No new dependencies** (no pnpm-lock churn). CSS-first motion.
- Customer routes must stay **≤150 KB gz** (motion is CSS, near-zero JS). If any route trips its ceiling, report it — don't bump.
- Zero hardcoded user-facing strings; motion adds none. If a decorative element needs `aria-hidden`, add it (no new i18n keys).
- Keep `packages/ui` snapshot tests green (update snapshots only if a deliberate markup change requires it, and say so).

## Build/verify (scoped — do NOT run a full-monorepo turbo build; avoid OOM)

Run, and paste tails:

```
pnpm --filter @vergeo/ui test
pnpm --filter @vergeo/customer typecheck
pnpm --filter @vergeo/customer lint
pnpm --filter @vergeo/customer test
pnpm --filter @vergeo/customer build      # confirm 46 routes, note any near ceiling
```

## Report (IMPLEMENTATION REPORT)

STATUS / FILES (list every file touched) / DEVIATIONS / WHAT-MOVED (dead classes swept count, hex files migrated, motion utilities added, skeleton surfaces, dark-button fix) / TESTS (paste the 5 command tails + any route sizes near 150 KB) / SCREENSHOT-DESCRIPTION (describe the before/after feel since you can't attach images) / QUESTIONS.
