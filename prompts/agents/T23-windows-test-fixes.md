# Task T23: Fix two Windows-only failing customer tests (test-only)

**Agent:** Cursor. **Model:** Composer 2.5. **Branch:** `cursor/windows-test-fixes` from `master`. Open one PR to `master`; don't merge.
**Board:** claim row T23 in `docs/ops/agent-board.md` first. Set it to `ready for review` when done.
**Owns (edit only these):** `apps/customer/app/[locale]/(auth)/_components/login-shell-oauth-identify.test.tsx` and `apps/customer/lib/no-localhost-in-browser-build.test.ts`

## Problem

Both tests fail on King's Windows machine and pass on Linux CI (T1 board note: the OAuth identify 20 ms race, and Windows path slashes). Fix the tests, not the product code.

## Steps

1. Run each alone: `pnpm --filter customer exec vitest run <file>`, one at a time. Record the failure.
2. `no-localhost-in-browser-build.test.ts`: it builds paths with `join` and compares against forward-slash entries (`AUDITED_FAIL_CLOSED_RESOLVERS`). Normalise `relative(...)` output to `/` before comparing (`split(sep).join("/")`), including in failure messages.
3. `login-shell-oauth-identify.test.tsx`: replace any fixed-delay waiting (20 ms timers or sleeps) with `waitFor` / `findBy*` or fake timers, so it does not depend on machine speed. Keep every assertion's meaning.
4. Do not edit `login-shell.tsx` or any non-test file. If the product code has a real race, write it on the board instead.

## Done means

Both files pass alone, 3 runs in a row each, and nothing weaker than before is asserted. Typecheck and lint pass. Say in the PR that these were run on Windows if you can, or Linux if not.

## Rules

1. Claim your board row (`in progress — cursor`) in your first commit. One agent per row.
2. Work only in the files you OWN. Need another file? Stop and note it on the board.
3. Testing: run only related tests, one command at a time: `pnpm --filter customer exec vitest related <files> --run`, then `pnpm --filter customer typecheck` and `pnpm --filter customer lint`. Never the full suite.
4. Never touch `supabase/`, `scripts/ci/`, `.github/`, `infra/`, payments, escrow, ledger, payouts, webhooks, auth or checkout money logic. No secrets. Never merge, force-push or `git stash`.
5. When done: row to `ready for review`, one line of notes, PR link in Slack #convergeo-dev.
