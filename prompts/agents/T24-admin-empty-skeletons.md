# Task T24: Admin boards: empty states and loading skeletons

**Agent:** Cursor. **Model:** Composer 2.5. **Branch:** `cursor/admin-empty-skeletons` from `master`. Open one PR to `master`; don't merge.
**Board:** claim row T24 in `docs/ops/agent-board.md` first. Set it to `ready for review` when done.
**Owns (edit only these):** `apps/admin/app/[locale]/accounts/accounts-board.tsx`, `support/_components/SupportInbox.tsx`, `orders/_components/OrderSearch.tsx` (+ their tests) and `packages/i18n/messages/*/admin.json` (new keys under `boards.states` only)

## Problem

`DisputeQueue.tsx` shows a skeleton while loading and an empty state when there is nothing. `accounts-board.tsx` and `SupportInbox.tsx` have no skeleton, and `OrderSearch.tsx` shows nothing helpful before a search or when nothing matches. Check each file first; skip any that already has both.

## Steps

1. Read `disputes/_components/DisputeQueue.tsx` for the pattern. Use `@vergeo/ui/src/skeleton` and `@vergeo/ui/src/empty-state` only; no new components.
2. For each of the three files: while loading show 4 skeleton rows (`aria-busy`, no layout jump); when loaded and empty show an `EmptyState` with a title and one line saying what to do next; keep the existing error state.
3. Add keys `boards.states.{accounts,support,orders}.{emptyTitle,emptyBody}` to `admin.json` for en. For other locales add the same keys in English for review, don't translate.
4. Add one test per file for the empty state (mock the data call to return `[]`).

## Done means

Each board shows a skeleton, then data or a clear empty state. Tests, typecheck and lint pass. Under 250 lines changed.

## Rules

1. Claim your board row (`in progress — cursor`) in your first commit. One agent per row.
2. Work only in the files you OWN. Need another file? Stop and note it on the board.
3. Testing: run only related tests, one command at a time: `pnpm --filter admin exec vitest related <files> --run`, then `pnpm --filter admin typecheck` and `pnpm --filter admin lint`. Never the full suite.
4. Never touch `supabase/`, `scripts/ci/`, `.github/`, `infra/`, payments, escrow, ledger, payouts, webhooks, auth or checkout money logic. No secrets. Never merge, force-push or `git stash`.
5. When done: row to `ready for review`, one line of notes, PR link in Slack #convergeo-dev.
