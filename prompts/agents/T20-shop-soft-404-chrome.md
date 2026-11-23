# Task T20: Shop soft-404 keeps the header and nav

**Agent:** Cursor. **Model:** Composer 2.5. **Branch:** `cursor/shop-soft-404-chrome` from `master`. Open one PR to `master`; don't merge.
**Board:** claim row T20 in `docs/ops/agent-board.md` first. Set it to `ready for review` when done.
**Owns (edit only these):** `apps/customer/app/[locale]/(shop)/not-found.tsx` (new) and `not-found.test.tsx` (new)

## Problem

UI audit rows "Product (PDP)": a missing product slug calls `notFound()`, and the page lands on the bare root `app/[locale]/not-found.tsx`, with no shop header or bottom nav. There is no `not-found.tsx` inside `(shop)` (check with `ls`).

## Steps

1. Read `apps/customer/app/[locale]/not-found.tsx` (read only, don't edit it). Reuse its `marketing.notFound` keys and layout so no new i18n keys are needed.
2. Add `(shop)/not-found.tsx` as a server component that renders the same message and links, inside the shop layout (header and nav come from `(shop)/layout.tsx`).
3. Add a test that renders it and checks the heading and a link back to `/{locale}`.
4. Run `node scripts/ci/bundle-guard.mjs` after `pnpm --filter customer build`; the change must add under 1 KB.

## Done means

`/en/p/does-not-exist` shows the shop header and nav with the same 404 message, the HTTP status stays 404, and tests, typecheck and lint pass. Note on the PR that the status code was checked.

## Rules

1. Claim your board row (`in progress — cursor`) in your first commit. One agent per row.
2. Work only in the files you OWN. Need another file? Stop and note it on the board.
3. Testing: run only related tests, one command at a time: `pnpm --filter customer exec vitest related <files> --run`, then `pnpm --filter customer typecheck` and `pnpm --filter customer lint`. Never the full suite.
4. Never touch `supabase/`, `scripts/ci/`, `.github/`, `infra/`, payments, escrow, ledger, payouts, webhooks, auth or checkout money logic. No secrets. Never merge, force-push or `git stash`.
5. When done: row to `ready for review`, one line of notes, PR link in Slack #convergeo-dev.
