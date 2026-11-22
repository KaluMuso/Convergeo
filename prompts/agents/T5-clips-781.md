# Task T5: bring Clips pilot and service packages PR #781 up to date and green

**Agent:** Cursor. **Model:** Composer 2.5 (Grok 4.7 only if stuck twice or for hard merge conflicts). **Branch:** #781's own branch `feat/clips-pilot-service-packages` (`gh pr checkout 781`). Push with no `--force`. Don't merge.
**Board:** claim row T5 first. Set it to `ready for review` when done.

## Rules

- No `--force`. Never merge. Merge master in; do not rebase.
- Do not change `supabase/migrations/`, `scripts/ci/`, `.github/workflows/`, or payments, auth, RLS or money code without Claude's review. If a fix needs one of these, stop and post in #convergeo-dev for Claude.
- Every new user-facing string gets a key in all 5 locales: en, bem, nya, fr, zh. No hardcoded text.
- Design tokens only from `packages/ui`. No ad-hoc colours or spacing.
- Run `pnpm typecheck`, `pnpm lint` and `pnpm test` for the apps you touched. For API changes also run `uv run pytest`, `uv run ruff check .` and `uv run mypy app tests scripts` in `services/api`.
- If you touch customer routes, run `pnpm --filter customer build` then `node scripts/ci/bundle-guard.mjs`.

## Problem

#781 (Clips pilot allowlist, service packages Basic/Standard/Premium; base master) is `dirty`. It touches services/api (14 app, 12 test files), packages/i18n (10), apps/admin, apps/vendor, apps/customer, 2 migrations (`20261113030000`, `20261113045000`), docs/ops runbook.
Last CI failures:
- `JavaScript / TypeScript`: `AuthApiError: Local fixture does not renew sessions` in a test.
- `Python API`: `AssertionError: assert 155 == 153` (migration count test, tied to migration numbering).
- Coordinator, `Financial real-stack` and `Database / typegen drift`: `Qualified 153-input source inventory differs`, `154 != 153`. Those are Claude's migration and CI part.
- `Secret scan (gitleaks)` exited 1. Check the report for a real secret and remove it if present. Never paste it anywhere.

## Steps

1. `git fetch origin && git merge origin/master` (merge, not rebase). Resolve conflicts in API, apps and i18n files.
2. Fix the auth fixture test (`Local fixture does not renew sessions`) in the test only. Do not change auth code.
3. Check that Clips stays fail-closed with comments off, and packages have no payment path. Keep those tests.
4. Run the checks above, then push.
5. Migration numbering and `scripts/ci`: stop and post in #convergeo-dev for Claude.

## Done means

No conflicts, lint, typecheck and tests green for the touched apps and API, the gitleaks failure explained, the board row updated, and the PR link posted in Slack #convergeo-dev.
