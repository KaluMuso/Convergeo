# Task T19: Search page: one search field, no skeleton flash on empty

**Agent:** Cursor. **Model:** Composer 2.5. **Branch:** `cursor/search-single-input` from `master`. Open one PR to `master`; don't merge.
**Board:** claim row T19 in `docs/ops/agent-board.md` first. Set it to `ready for review` when done.
**Owns (edit only these):** `apps/customer/app/[locale]/(shop)/_components/shop-header.tsx`, `desktop-header-search.tsx`, `mobile-header-search.tsx` and their `.test.tsx` files

## Problem

UI audit (`docs/ops/ui-audit-2026-11-22.md`, rows "Search results"): on `/search` the header search and the in-page search both show, so two fields compete for space (393 and 1280). The results grid can also flash skeletons before a stable empty state.

## Steps

1. Confirm both are still true on `master` by reading `shop-header.tsx` and `search/page.tsx` (read only). If one is already fixed, skip it and say so on the board.
2. Hide the header search on `/{locale}/search` only (use `usePathname`; keep it everywhere else). Keep the icon-only link to `/search` on mobile if the header has no other way back.
3. Add a test per header component: search hidden on `/en/search`, shown on `/en`.
4. Do not edit `search/page.tsx`. If the skeleton flash needs a page change, write it on the board as a follow-up.
5. Keep the diff under 150 lines. No new i18n keys.

## Done means

On `/search` only one search field shows at 393 and 1280, other pages unchanged, tests, typecheck and lint pass, bundle guard unaffected (no new imports of heavy modules).

## Rules

1. Claim your board row (`in progress — cursor`) in your first commit. One agent per row.
2. Work only in the files you OWN. Need another file? Stop and note it on the board.
3. Testing: run only related tests, one command at a time: `pnpm --filter customer exec vitest related <files> --run`, then `pnpm --filter customer typecheck` and `pnpm --filter customer lint`. Never the full suite.
4. Never touch `supabase/`, `scripts/ci/`, `.github/`, `infra/`, payments, escrow, ledger, payouts, webhooks, auth or checkout money logic. No secrets. Never merge, force-push or `git stash`.
5. When done: row to `ready for review`, one line of notes, PR link in Slack #convergeo-dev.
