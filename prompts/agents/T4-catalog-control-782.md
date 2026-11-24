# Task T4: bring catalogue control PR #782 up to date and green

**Agent:** Cursor. **Model:** Composer 2.5 (Grok 4.7 only if stuck twice or for hard merge conflicts). **Branch:** #782's own branch `feat/admin-ads-merchandising` (`gh pr checkout 782`). Push with no `--force`. Don't merge.
**Board:** claim row T4 first. Set it to `ready for review` when done.

## Rules

- No `--force`. Never merge. Merge master in; do not rebase.
- Do not change `supabase/migrations/`, `scripts/ci/`, `.github/workflows/`, or payments, auth, RLS or money code without Claude's review. If a fix needs one of these, stop and post in #convergeo-dev for Claude.
- Every new user-facing string gets a key in all 5 locales: en, bem, nya, fr, zh. No hardcoded text.
- Design tokens only from `packages/ui`. No ad-hoc colours or spacing.
- Run `pnpm typecheck`, `pnpm lint` and `pnpm test` for the apps you touched. For API changes also run `uv run pytest`, `uv run ruff check .` and `uv run mypy app tests scripts` in `services/api`.
- If you touch customer routes, run `pnpm --filter customer build` then `node scripts/ci/bundle-guard.mjs`.
- This PR blocks suspended vendors from cart, checkout and order create. That is purchase gating: do not change the gating logic. Only fix merge conflicts and tests around it. Claude reviews the money and auth parts.

## Problem

#782 (admin catalogue control, typed ad targets, suspended-vendor purchase block; base master) is `dirty`. It touches apps/admin (12 files), services/api (10 app, 5 test files), packages/i18n, packages/types, apps/customer, 1 migration (`20261123100000`).
Last CI failures:
- `JavaScript / TypeScript`: `import/order` lint error, `../../_components/admin-request` must come before `AdminLoadFailure` (2 admin files).
- `Python API`: `remote missing repository migrations: 20261123100000`.
- Coordinator and migration checks: `Qualified 153-input source inventory differs`. That is Claude's migration and CI part.

## Steps

1. `git fetch origin && git merge origin/master` (merge, not rebase). Resolve conflicts in admin, API, i18n and customer files.
2. Fix the `import/order` errors in the admin files.
3. Keep the purchase-block tests passing, and make sure failure-path tests exist for cart, checkout and order create with a suspended vendor.
4. Run the checks above, then push.
5. Anything in the migration, `scripts/ci` or payments code: stop and post in #convergeo-dev for Claude.

## Done means

No conflicts, lint, typecheck and tests green for admin, customer and API, the board row updated, and the PR link posted in Slack #convergeo-dev for Claude's money and auth review.
