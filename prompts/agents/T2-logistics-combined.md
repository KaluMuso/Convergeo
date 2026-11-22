# Task T2: combine logistics PRs #788 and #794 onto current master

**Agent:** Cursor. **Model:** Composer 2.5 (Grok 4.7 only if stuck twice or for hard merge conflicts). **Branch:** `feat/logistics-combined` (Claude creates it). Push with no `--force`. Don't merge.
**Board:** claim row T2 first. Set it to `ready for review` when done.
**Wait:** do not start until Claude has pushed `feat/logistics-combined` and the board row says `queued`. Until then the row is `blocked — waiting on Claude migrations`.

## Rules

- No `--force`. Never merge. Merge master in; do not rebase.
- Do not change `supabase/migrations/`, `scripts/ci/`, `.github/workflows/`, or payments, auth, RLS or money code without Claude's review. If a fix needs one of these, stop and post in #convergeo-dev for Claude.
- Every new user-facing string gets a key in all 5 locales: en, bem, nya, fr, zh. No hardcoded text.
- Design tokens only from `packages/ui`. No ad-hoc colours or spacing.
- Run `pnpm typecheck`, `pnpm lint` and `pnpm test` for the apps you touched. For API changes also run `uv run pytest`, `uv run ruff check .` and `uv run mypy app tests scripts` in `services/api`.
- If you touch customer routes, run `pnpm --filter customer build` then `node scripts/ci/bundle-guard.mjs`.
- `supabase/migrations/` and `scripts/ci/` (including `coordinator-gate-inputs.json` digests) are done by Claude on the branch. Leave them alone.

## Problem

- #788 (Phase 1: delivery pricing, rider cash, returns, logistics role) targets `release/2026-11-next` and is `dirty`. It touches services/api (28 app, 18 test files), packages/i18n, apps/admin, apps/vendor, 2 migrations, scripts/ci.
- #794 (area-pair pricing, 2 pm promise, admin editor, shadow mode) is stacked on #788 and `dirty`. It touches api, admin, customer, i18n, packages/types, 2 migrations.
- Last CI on #788: `Coordinator acceptance` failed `AssertionError: 877 != 813` (retained inventory), `Database / typegen drift` and `Financial real-stack` failed, `Python API` exit 1.
- Last CI on #794: `Coordinator acceptance` failed `Retained test/runner source binding differs`; `Python API` failed `TemplateRenderError: payload['orders_url'] must be a non-empty string`; `RLS isolation matrix` failed at role provisioning.
- Latest master migration is `20261117020000`, so both PRs' migrations get renumbered after it. That is Claude's job.

## Steps

1. `git fetch origin && git checkout feat/logistics-combined && git merge origin/master` (merge, not rebase). Resolve conflicts in app, API and i18n files only.
2. Fix API code and tests so `uv run pytest` passes. Start with the `orders_url` template payload failure in the WhatsApp template tests.
3. Union the i18n keys across all 5 locales. Keep one copy of any key both PRs added.
4. Fix admin, vendor and customer type errors, then run the checks above.
5. If a failure comes from migrations, `scripts/ci` or money logic, stop and post it in #convergeo-dev for Claude.

## Done means

`feat/logistics-combined` has green lint, typecheck and tests locally, the board row is `ready for review`, and the branch link is posted in Slack #convergeo-dev. Claude then opens the PR and requalifies CI.
