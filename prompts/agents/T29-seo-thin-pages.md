# Task T29: SEO — keep empty pages out of Google, and check product rich results

**Agent:** Cursor. **Model:** Composer 2.5. **Branch:** `cursor/seo-thin-pages` from `master`. Open one PR to `master`; don't merge.
**Board:** claim row T29 in `docs/ops/agent-board.md` first. Set it to `ready for review` when done.
**Owns (edit only these):** `apps/customer/lib/seo/**` (+ tests), `apps/customer/app/[locale]/(shop)/categories/**` (metadata only), the product page `generateMetadata` and its JSON-LD call, `packages/ui/src/seo/json-ld.tsx` (+ test)

## What Claude found on production (24 Nov)

- The sitemap lists 150 category pages, but the catalogue has **0 live products**. Google treats many empty pages as thin content ("soft 404"), which lowers trust in the whole site.
- The product, vendor, event and service sitemap chunks are empty. That is fine; they fill up as vendors list.
- Canonical and sitemap URLs use `vergeo5.com`, while the site serves `www.vergeo5.com`. **King fixes this with one Vercel setting**; don't change the host in code.

## Steps

1. **Category sitemap:** list a category only when it, or one of its child categories, has at least one live listing. Use the existing public read (anon, RLS) and one query, not one per category. Keep `all`.
2. **Empty category pages:** when a category has no live listings, return `robots: { index: false, follow: true }` from its metadata. The page still renders for people.
3. **Product page structured data:** check that the Product JSON-LD has `name`, `image`, `brand` (when known), `offers` as an `AggregateOffer` with `priceCurrency: "ZMW"`, `lowPrice` and `highPrice` in kwacha (convert from ngwee with integer maths, then format with 2 decimals; no floats on money), `offerCount` and `availability`, plus `aggregateRating` only when there are verified reviews. Add a `BreadcrumbList` (Home → category → product). Fix what is missing.
4. Add `lastModified` to sitemap entries where the data has an `updated_at`.

## Tests (required)

- The category sitemap leaves out empty categories and keeps a parent whose child has a listing.
- An empty category gets `index: false`; a category with listings has no robots override.
- Product JSON-LD: K1,234.50 from 123450 ngwee becomes `"1234.50"`; no `aggregateRating` without reviews; the breadcrumb has 3 items.

## Done means

The sitemap only lists pages with real content, empty categories are `noindex, follow`, and the product JSON-LD passes Google's Rich Results rules. Tests, typecheck, lint and the bundle guard pass (JS growth 0 KB; this is server-side only).

## Rules

1. Claim your board row (`in progress — cursor`) in your first commit. One agent per row.
2. Work only in the files you OWN. Need another file? Stop and note it on the board.
3. Testing: run only related tests, one command at a time: `pnpm --filter customer exec vitest related <files> --run`, then `pnpm --filter customer typecheck` and `pnpm --filter customer lint`. Never the full suite.
4. Never touch `supabase/`, `scripts/ci/`, `.github/`, `infra/`, payments, escrow, ledger, payouts, webhooks, auth or checkout money logic. No secrets. Never merge, force-push or `git stash`.
5. When done: row to `ready for review`, one line of notes, PR link in Slack #convergeo-dev.
