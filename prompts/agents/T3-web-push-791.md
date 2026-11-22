# Task T3: bring Web Push PR #791 up to date and green

**Agent:** Cursor. **Model:** Composer 2.5 (Grok 4.7 only if stuck twice or for hard merge conflicts). **Branch:** #791's own branch `feat/web-push-delivery` (`gh pr checkout 791`). Push with no `--force`. Don't merge.
**Board:** claim row T3 first. Set it to `ready for review` when done.

## Rules

- No `--force`. Never merge. Merge master in; do not rebase.
- Do not change `supabase/migrations/`, `scripts/ci/`, `.github/workflows/`, or payments, auth, RLS or money code without Claude's review. If a fix needs one of these, stop and post in #convergeo-dev for Claude.
- Every new user-facing string gets a key in all 5 locales: en, bem, nya, fr, zh. No hardcoded text.
- Design tokens only from `packages/ui`. No ad-hoc colours or spacing.
- Run `pnpm typecheck`, `pnpm lint` and `pnpm test` for the apps you touched. For API changes also run `uv run pytest`, `uv run ruff check .` and `uv run mypy app tests scripts` in `services/api`.
- If you touch customer routes, run `pnpm --filter customer build` then `node scripts/ci/bundle-guard.mjs`.

## Problem

#791 (Web Push delivery, flag `web_push` stays off, base master) is `dirty`: it conflicts with master. It touches services/api (5 app, 7 test files, pyproject and uv.lock for `pywebpush`), 1 migration (`20261113140000`), 10 scripts/ci files, packages/types and infra/n8n.
No check run was failing on its last head commit, but that run is old and the branch cannot merge until it is current.
Migration renumbering and `scripts/ci` digests are Claude's job, not yours. Latest master migration is `20261117020000`.

## Steps

1. `git fetch origin && git merge origin/master` (merge, not rebase). Resolve conflicts in API code, tests, `pyproject.toml` and `uv.lock` (re-run `uv lock` rather than hand-editing).
2. Do not touch the migration file or `scripts/ci`. If conflicts are there, stop and post in #convergeo-dev for Claude.
3. Check the sender still fails closed with no VAPID env, keeps quiet hours 22:00-06:00 Lusaka, and never puts PII in the payload. Tests for each must pass.
4. Run the checks above, then push.

## Done means

Merge conflicts are gone, `uv run pytest`, ruff and mypy pass, the board row is updated, and the PR link is posted in Slack #convergeo-dev. Claude does the migration and CI requalification.
