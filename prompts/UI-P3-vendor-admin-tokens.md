> **Prepend `prompts/_header.md`.** Branch `agent/ui-p3-vendor-admin-tokens` from + PR against **`master`**. **⚙ Do NOT use `git stash`** (shared refs/stash across worktrees). Foreground blocking only. Commit trailers required:
> `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`
> `Claude-Session: https://claude.ai/code/session_0182ebfSrQf83JNZCiKqjAby`
> PR title: `UI-P3: vendor & admin token migration + dark-mode correctness`.

# UI-P3 — Vendor + Admin apps: migrate raw hex → design tokens, make dark mode correct

## Context (grounded)

UI-P1 (#174, merged) made the `packages/ui` tokens real under Tailwind v4 (`packages/ui/src/styles/theme.css`, `@theme inline`) and added dark mode (`[data-theme="dark"]` + a mounted `ThemeToggle`) to **all three** apps, including vendor and admin. But vendor and admin still paint with **raw hex colors** in many places, so they **do not respond to the tokens or to dark mode**. Migrate them onto the token utilities.

Valid color utilities are ONLY those backed by a `--color-*` entry in `theme.css`: `bg-bg`, `bg-bg-2`, `bg-surface`, `bg-panel`/`bg-panel-2`, `text-panel-text`/`text-panel-muted`, `text-text`, `text-text-2`, `text-text-3`, `text-muted`, `bg-primary`/`text-primary`/`bg-primary-deep`/`bg-primary-tint`, `border-border`/`border-panel-border`, `bg-success`/`bg-danger`/`bg-warning`/`bg-info`, and the `cat-*` set. Admin is a **dark-chrome console** by design — prefer the `panel*` tokens for its surfaces so it reads correctly in both themes.

Footprint (approx, verify): **admin ~57 files** with raw hex, **vendor ~2 files** with raw hex + **~26 files** with dead legacy color classes.

## Tasks

1. **Migrate raw hex → token utilities** across `apps/vendor` and `apps/admin`. For each hex UI color, pick the closest existing token utility (or `var(--token)` in an inline `style` where a utility can't express it, e.g. gradients). Leave non-color hex (SVG path data, ids, encoded values) untouched. Find them: `grep -rE "#[0-9a-fA-F]{3,8}\b" apps/vendor apps/admin`.
2. **Dead color-class sweep** in `apps/vendor` (and admin if any): bare `text-2`, `bg-2`, `text-text-1`, `bg-bg-1`, `border-border-1` are no-ops under v4. Replace with the intended valid utility (`text-text-1`→`text-text`, `bg-bg-1`→`bg-bg`, `border-border-1`→`border-border`, bare `text-2`→`text-muted`, bare `bg-2`→`bg-bg-2`), verifying each target exists in `theme.css`. Do NOT touch unrelated utilities (`text-2xl`, `gap-2`, `p-2`).
3. **Migrate the shim** `apps/vendor/app/[locale]/listings/new/_lib/ui.ts` (any hardcoded color strings → token references).
4. **Dark-mode correctness pass**: after migration, both apps' primary surfaces (page bg, cards/panels, text, borders) must derive from tokens so toggling the theme actually re-themes them. Spot-check the shells + a few dense screens.

**No structural, routing, data, or logic changes** — this is a color-token migration only.

## Files (ownership — touch ONLY these)

- `apps/vendor/**` and `apps/admin/**` (styling/color only)
- **Do NOT touch** `apps/customer`, `packages/ui` (tokens are already correct — consume them, don't edit them), `packages/**` generally, `services/api`, `supabase/migrations`, `packages/types/src/db.ts`, `pnpm-lock.yaml` (no new deps), `ci.yml`/`perf.yml`, `lighthouserc.json`.

## Constraints

- **No new dependencies.** Consume existing token utilities.
- Zero hardcoded user-facing strings introduced; no new i18n keys (color migration only).
- Preserve every component's structure, props, and behavior — only class/style color values change.
- Admin stays on its separate hardened origin; do not alter its security headers / CSP / origin config.

## Build/verify (scoped — do NOT run a full-monorepo turbo build; avoid OOM)

Run, and paste tails:

```
pnpm --filter @vergeo/vendor typecheck
pnpm --filter @vergeo/vendor lint
pnpm --filter @vergeo/vendor test
pnpm --filter @vergeo/vendor build
pnpm --filter @vergeo/admin typecheck
pnpm --filter @vergeo/admin lint
pnpm --filter @vergeo/admin test
pnpm --filter @vergeo/admin build
```

## Report (IMPLEMENTATION REPORT)

STATUS / FILES (count per app + list) / DEVIATIONS / WHAT-MOVED (hex→token count per app, dead classes swept, shim migrated, dark-mode surfaces verified) / TESTS (paste the 8 command tails) / QUESTIONS.
