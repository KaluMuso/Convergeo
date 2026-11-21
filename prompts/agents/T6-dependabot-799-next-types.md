# Task T6: make Dependabot PR #799 (15 JS minor and patch updates) pass

**Agent:** Cursor. **Model:** Composer 2.5. **Branch:** #799's own branch (`gh pr checkout 799`). Push to it with no `--force`. Don't merge.
**Board:** claim row T6 first. Set it to `ready for review` when done.

## Problem

After the bump, `JavaScript / TypeScript` fails with type errors in `apps/*/middleware.ts`: two copies of `next` resolve with different versions, so the `NextRequest` and `NextResponse` types clash.

## Steps

1. `pnpm why next`: find which package pins the older `next`.
2. Make every workspace use **one** `next` version. Either align the version range in the app `package.json` files, or add a `pnpm.overrides` entry for `next` in the root `package.json`. Then `pnpm install` and commit the lockfile.
3. Run `pnpm typecheck`, `pnpm lint`, and `pnpm --filter customer test`, `pnpm --filter vendor test`, `pnpm --filter admin test`.
4. If another package in the group causes a failure you can't fix in 20 lines, revert just that package's bump and note it on the board.

## Done means

All required checks are green on #799, the board row is updated, and the PR link is posted in Slack #convergeo-dev.
