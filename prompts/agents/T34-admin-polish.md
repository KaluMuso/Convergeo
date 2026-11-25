# Task T34: Admin console — modern, professional polish on design system v2

**Agent:** Cursor. **Model:** Composer 2.5. **Branch:** `cursor/admin-polish` from `master`, **after T31 (design system v2) is merged**. Open one PR to `master`; don't merge.
**Board:** claim row T34 in `docs/ops/agent-board.md` first. Set it to `ready for review` when done.
**Owns (edit only these):** `apps/admin/app/**` and `apps/admin/components/**` (presentation only), `packages/i18n/messages/*/admin.json`. **Not** `packages/ui` (ask on the board if a shared component is missing), and not `next.config.ts`, `middleware.ts` or API clients.

## Why

King, 24 Nov: "the user experience for the admin panel, vendor app and customer apps today was amateur and not modern ... more features and professionalism is required ... include visuals, images and professional colored icons of reasonable size." The new design system (T31) gives neutral black/white by default with an optional Green accent, `IconTile` colour icons, motion utilities, `PageHeader`, `StatCard`, `Skeleton` and spot illustrations. Apply it so every screen of the Admin console looks like a polished product in the class of Linear, Vercel and Retool (clean, dense, calm).

## Do this for EVERY route in the app (list them in the PR with before/after screenshots at 360 px and 1280 px, light and dark)

1. **Layout:** a `PageHeader` on every page, consistent spacing (4/8 px grid), and max widths. A dense but airy table style (sticky headers, zebra off, hover rows, row actions), filter chips, a command-palette-style search (UI only), and KPI `StatCard`s on the overview.
2. **Icons:** replace bare or monochrome icons in navigation, cards, quick actions, stats and empty states with `IconTile` (sizes 40–48 for tiles, 20–24 inline), using the category → hue map where it applies.
3. **Images:** vendor and KYC queues show avatars and logos; moderation shows image thumbnails with a zoom dialog; empty queues show a calm illustration ("All caught up").
4. **States:** a `Skeleton` that matches the final layout for every loading state (no spinners on page loads); `EmptyState` with an illustration and one clear next action; friendly error states with retry.
5. **Motion:** page-in on route content, hover lift on cards, press scale on buttons, animated tab and segment indicators, sheet and dialog transitions, toasts. Everything respects reduced motion.
6. **Detail work:** tabular numbers for money (always `formatK`), status chips with consistent colours, truncation and line-clamp instead of overflow, focus rings visible, touch targets ≥ 44 px, sticky action bars on mobile forms.
7. **Density toggle** (comfortable or compact) stored per person, presentation only.

## Tests (required)

Update the affected component and snapshot tests; add tests for any new empty or skeleton state; run axe on the main routes (no serious or critical issues); run the bundle guard (report per-route JS; customer routes ≤150 KB gz).

## Done means

Every route matches the design system, light and dark, mono and green, at 360 px and desktop. No raw hex colours or ad-hoc spacing (lint). Screenshots are in the PR. Tests, typecheck, lint and the bundle guard pass.

## Rules

1. Claim your board row (`in progress — cursor`) in your first commit. One agent per row.
2. Work only in the files you OWN. Need another file? Stop and note it on the board.
3. Testing: run only related tests, one command at a time (`pnpm --filter admin exec vitest related <files> --run`, then `pnpm --filter admin typecheck` and lint). Never the full e2e suite.
4. Never touch `supabase/`, `scripts/ci/`, `.github/`, `infra/`, payments, escrow, ledger, payouts, webhooks, auth or checkout money logic (presentation of checkout may change; amounts, calls and flows may not). No secrets. Never merge, force-push or `git stash`.
5. Zero hardcoded strings. For bem, nya, fr and zh, copy the English text and mark it for review.
6. When done: row to `ready for review`, one line of notes, PR link in Slack #convergeo-dev.
