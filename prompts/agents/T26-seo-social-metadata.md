# Task T26: SEO: social metadata for deals and help pages

**Agent:** Cursor. **Model:** Composer 2.5. **Branch:** `cursor/seo-social-metadata` from `master`. Open one PR to `master`; don't merge.
**Board:** claim row T26 in `docs/ops/agent-board.md` first. Set it to `ready for review` when done.
**Owns (edit only these):** `apps/customer/app/[locale]/(shop)/deals/page.tsx` and `apps/customer/app/[locale]/(marketing)/help/page.tsx`, `help/[slug]/page.tsx`

## Problem

Product (`p/[slug]`) and category (`c/[...slug]`) pages already call `buildSocialMetadata`. These indexable pages do not, so shared links in WhatsApp have no title card: `deals/page.tsx`, `help/page.tsx`, `help/[slug]/page.tsx`. Verify with `grep -c buildSocialMetadata` before editing; skip any that already have it.

## Steps

1. Copy the pattern from `c/[...slug]/page.tsx`: spread `...buildSocialMetadata({ title, description, locale, url: canonicalPath })` in each `generateMetadata`, reusing the existing title, description and canonical values. No new i18n keys, no images.
2. Keep `robots` as is. Do not touch `opengraph-image.tsx`.
3. Add or extend a small test per page asserting `openGraph.title` and `openGraph.url` are set (follow `v/[slug]/page.test.tsx`).
4. Run `pnpm --filter customer build` then `node scripts/ci/bundle-guard.mjs`. Total JS must not grow by more than 2 KB; paste the guard output in the PR.

## Done means

All three pages emit `openGraph` and `twitter` tags with locale-correct canonical URLs, bundle guard green, tests, typecheck and lint pass. Under 100 lines changed.

## Rules

1. Claim your board row (`in progress — cursor`) in your first commit. One agent per row.
2. Work only in the files you OWN. Need another file? Stop and note it on the board.
3. Testing: run only related tests, one command at a time: `pnpm --filter customer exec vitest related <files> --run`, then `pnpm --filter customer typecheck` and `pnpm --filter customer lint`. Never the full suite.
4. Never touch `supabase/`, `scripts/ci/`, `.github/`, `infra/`, payments, escrow, ledger, payouts, webhooks, auth or checkout money logic. No secrets. Never merge, force-push or `git stash`.
5. When done: row to `ready for review`, one line of notes, PR link in Slack #convergeo-dev.
