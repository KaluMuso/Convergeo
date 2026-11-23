# Task T21: Vendor home: clear prompt to add the MoMo payout number

**Agent:** Cursor. **Model:** Composer 2.5. **Branch:** `cursor/vendor-payout-prompt` from `master`. Open one PR to `master`; don't merge.
**Board:** claim row T21 in `docs/ops/agent-board.md` first. Set it to `ready for review` when done.
**Owns (edit only these):** `apps/vendor/app/[locale]/_lib/home-tasks.ts` (+ test), `_components/home-tasks.tsx`, the `buildHomeTasks(...)` call in `orders/_components/order-card.tsx`, and `packages/i18n/messages/*/vendor.json` (home.tasks.items only)

## Problem

Go-live blocker B4 (`docs/ops/go-live-14-days.md`): 0 of 3 vendors have a payout number. The vendor home task list (`buildHomeTasks`) has no step for it, so vendors don't know where to add it.

## Steps

1. The API already exists: `GET /vendor/payouts` returns `payout_msisdn` and `payout_rail` (see `payouts/_lib/payouts-client.ts`, `createPayoutsClient`), and the form at `/payouts/method` posts `POST /vendor/payouts/method`. Don't change either.
2. In `order-card.tsx`, load balances with the existing client (non-blocking; on error treat as unknown and show no task). Pass `payoutMissing: boolean | null` into `buildHomeTasks`.
3. Add task key `payoutMethod`, href `/payouts/method`, tone `warning`, shown when `payoutMissing === true` and KYC is not `needs_fix`. Place it after the KYC tasks and before orders. Respect `MAX_HOME_TASKS`.
4. Add `home.tasks.items.payoutMethod.{title,body}` to `vendor.json` for en, bem, nya, fr, zh. Title: "Add your MoMo number to get paid". Body: say the money goes to this number and the name must match their ID. Plain words. Mark non-English as English copy for review, don't invent translations.
5. Extend the `home-tasks` test: shown when missing, hidden when set or unknown.

## Done means

A vendor without a payout number sees the task on home and one tap opens the form. Tests, typecheck and lint pass. Under 200 lines changed.

## Rules

1. Claim your board row (`in progress — cursor`) in your first commit. One agent per row.
2. Work only in the files you OWN. Need another file? Stop and note it on the board.
3. Testing: run only related tests, one command at a time: `pnpm --filter vendor exec vitest related <files> --run`, then `pnpm --filter vendor typecheck` and `pnpm --filter vendor lint`. Never the full suite.
4. Never touch `supabase/`, `scripts/ci/`, `.github/`, `infra/`, payments, escrow, ledger, payouts, webhooks, auth or checkout money logic. No secrets. Never merge, force-push or `git stash`.
5. When done: row to `ready for review`, one line of notes, PR link in Slack #convergeo-dev.
