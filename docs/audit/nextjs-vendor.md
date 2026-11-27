# Next.js feature audit: apps/vendor

Scope: `apps/vendor` (Next.js 15.5, App Router, next-intl 4, 54 pages, 201 component files). Measured from `next build` (First Load JS), the i18n catalogs, and code paths. Date: 2026-11-27. Companion to `nextjs-admin.md`.

Numbers marked "measured" come from a local `next build` (fonts mocked, no network) or from the catalogs; "estimated" numbers are derived from code paths because the sandbox cannot reach the production API. No production timing was taken.

## Summary

| # | Finding | Impact | Status |
|---|---|---|---|
| 1 | Layout shipped all four catalogs to every page | 144.9 KB of JSON in every RSC payload (measured) | Fixed, PR #946 |
| 2 | `/notifications` pulled supabase-js into its page bundle | 194 kB vs 125 kB first load (measured) | Fixed, PR #958 |
| 3 | Only 2 of 54 pages had `loading.tsx` | Blank content area on slow routes, skeleton shape changed twice | Fixed, PR #957 |
| 4 | Nav capability probe: 4 `feature_flags` queries + serial intake lookups on every request | 4 round trips on every hard load, bounded only by the 2 s budget | Fixed, PR #948 |
| 5 | `/vendor/orders/dashboard` and `/queue` read all history, `in_()` lists in the URL | Slow for busy vendors, URL length risk, silent 1000-row truncation | Fixed, PR #952 |
| 6 | Profile logo/cover rendered full uploads in 80/112 px boxes | One full image per preview | Fixed, PR #960 |
| 7 | Glass (frosted) styling for header, bottom nav, sheets | Pending the shared utility | Blocked on PR #945 (open) |
| 8 | PWA shell for the scanner is not wired | Scanner cannot boot offline despite the IndexedDB store | Open (see below) |
| 9 | Home view downloads the full listings list to count "in review" | Heavy request on the busiest page | Open (needs an API count) |
| 10 | Whole-app client rendering: 111 of 201 component files are `"use client"`, data is fetched after hydration | Waterfall: HTML, JS, session, API | Open (architectural) |

## Feature by feature

### Server / client boundaries
- Status: 50 of 54 pages are server components that render one client view; every data fetch happens in the client view after `useSession()` resolves (token lives in browser storage, not a cookie the server reads).
- Impact: the dependency chain on every page is HTML, hydrate, session, API. Streaming does not help because the server never fetches page data.
- Fix: moving fetches server-side needs a cookie-based session (the layout already reads Supabase cookies for capabilities). Not attempted: it changes every page and the auth model. Recommended as its own project, starting with the dashboard and orders list.

### Per-route message namespaces
- Status before: `layout.tsx` loaded `vendor` (121 KB), `services` (18 KB), `events` (10 KB) and the notification center (about 1 KB) and passed them to one `NextIntlClientProvider`, so every page and every RSC navigation carried 144.9 KB of JSON (170 KB of raw files). `onboarding` and `listings/new` wrapped the whole vendor catalog a second time.
- Status after (PR #946): layout ships 4.5 KB (shell chrome). Route segment layouts add what their views read.
- Numbers (en, measured, base included): plan 6.4 KB, returns 5.4 KB, settings 6.0 KB, analytics 6.3 KB, payouts 8.6 KB, profile 12.8 KB, home/orders 17.4 KB, listings 30.9 KB, events 41.0 KB, services 44.5 KB. Typical page: about 90% smaller.
- Guard: `lib/route-messages.test.ts` walks each route's import graph and fails when a client view reads a key its route does not ship, so a missing branch cannot reach production as a raw key. The old `KNOWN_GAPS = ["auth"]` entry was stale: `accept-invite/layout.tsx` already provides `auth` (all 14 keys the form reads exist).
- Follow-up: bem/nya/fr merge over English, so their payloads are the same size.

### loading.tsx and Suspense streaming
- Status before: `profile` and `extras` only.
- Status after (PR #957): 33 routes, built from the skeletons the client views already use (`ListSkeleton`, `OrderDetailSkeleton`, `AnalyticsSkeleton`, `VendorPageSkeleton`), localised label from `common.common.loading`. Not added at `[locale]/` root: it would wrap the bare login/otp/reset pages, and the home dashboard keeps its client `DashboardSkeleton`.
- Limit: because data is fetched on the client, `loading.tsx` covers the segment transition only; the client skeleton covers the data wait.

### error.tsx / not-found
- Status: one `error.tsx` and one `not-found.tsx` at `[locale]`, plus `global-error.tsx`. Adequate: a route-level error boundary would only matter once pages fetch on the server. `not-found.tsx` correctly loads `nav` itself (the request config only ships `common`).

### Data-fetching waterfalls
- Layout: capabilities already run in parallel with catalogs (#939). Remaining cost was the probe itself (finding 4).
- Dashboard (`VendorHomeView`): `getDashboard`, `kyc`, `analytics` run in parallel (good); payouts balances and the full listings list are separate effects after the session, also parallel. The listings request exists only to count products in moderation (finding 9).
- Orders dashboard API: sequential orders, then items, then payments, then confirm events, each with every order id. Now windowed and concurrent (finding 5).
- Not changed (out of scope: payout logic): `/vendor/payouts` loads the vendor, bumps a rate-limit counter via the database, reads payout fields in a second vendor query, then computes balances. Merging the two vendor reads and moving the rate-limit bump off the critical path would save at least two round trips.

### Caching of read-mostly data
- Capabilities: API route probes were already cached 300 s via `fetch(... next.revalidate)`. `feature_flags` (world-readable) was queried per request; now one batched query reused for 30 s (PR #948). On a slow probe the nav keeps the last resolved items instead of dropping Offers/Payouts/Scan.
- Categories, plan: fetched client-side per page view; no HTTP caching headers are set on those API reads. Recommendation: `Cache-Control: private, max-age=60` on category and plan endpoints, or SWR on the client.

### next/image and uploads
- Status: Cloudinary renditions are used for event images and review photos (`CloudinaryImage`, f_auto/q_auto). Logo and cover previews used the raw upload URL (fixed, PR #960). `intake` keeps a raw `<img>` on purpose (quarantined asset must not be proxied).
- `next/image` is not used anywhere; with Cloudinary `f_auto,q_auto,w_N` as the transform layer that is acceptable and avoids a second optimiser.

### Dynamic imports for heavy code
- Status: good. leaflet, jsqr, `@sentry/nextjs` and the browser Supabase client are all behind `import()`. Check: `/events/[id]/scan` 128 kB and `/scan` 124 kB first load.
- One miss, now fixed: `/notifications` imported `getBrowserAccessToken` from the `@vergeo/auth` barrel, adding a 55 kB gzip supabase chunk (194 kB to 125 kB, PR #958). `apps/admin` has the same import in three files.
- Largest remaining first loads (measured): `/` and `/orders` 148 kB, `/listings/[id]/edit` 149 kB, `/listings/new` 141 kB, `/profile` 140 kB. Cause on `/` and `/orders`: one 1,045-line `order-card.tsx` holds the home view, the queue and the card, and imports the KYC, payouts, analytics and listings clients. Splitting `VendorHomeView` from `OrdersQueueView` is the next bundle win (est. 15-25 kB on `/orders`).

### Link prefetch
- Status: default `next/link` prefetch everywhere; the bottom nav and sidebar use `Link`. Pages are mostly `generateStaticParams` SSG shells, so prefetch is effective. The ten `[id]` routes are dynamic by design (see `protected-dynamic-routes.test.ts`).

### Optimistic UI (useOptimistic / useActionState)
- Status: not used. Not adopted deliberately for two flows:
  - Stock adjustments are replay-safe operations (an operation id persisted in `sessionStorage`, retried verbatim). An optimistic number would hide the pending/retry state the flow depends on.
  - Order actions (confirm, pack, ship) run through guarded state machines with payment gating and a dispatch cut-off; the API response decides the next actions, so the UI should wait.
- Candidates that are safe: listing active/inactive toggle and coupon enable/disable (single boolean, idempotent). Worth doing once those lists read through a shared mutation helper.

### PWA / offline for order scanning
- Status: `scan/_lib/offline-store.ts` (IndexedDB pre-event ticket sync, offline check-in queue) exists and has tests. But `sw-scanner.ts` is an unmerged fragment ("awaiting merge into the vendor app's service worker"), there is no web manifest, and the only registered worker is `public/push-sw.js`. The scanner works offline only if the page is already open.
- Fix (not done, larger): add a Serwist worker for the vendor app that precaches the `/scan` and `/events/[id]/scan` shells and merges `sw-scanner.ts`, plus a manifest. Needs the camera Permissions-Policy and CSP worker-src checks already in `next.config.ts`.

### Bundle sizes per route (measured, First Load JS, kB; shared 103)
`/` 148, `/orders` 148, `/listings/[id]/edit` 149, `/listings/new` 141, `/profile` 140, `/services/[id]/edit` 137, `/events/[id]/edit` 137, `/events/new` 136, `/services/new` 134, `/onboarding` 132, `/orders/[id]` 132, `/listings` 131, `/events/[id]/tickets` 129, `/settings` 128, `/payouts` 127, `/analytics` 125, `/notifications` 125 (was 194), `/plan` 123, `/returns` 123, `/reviews` 122, `/extras` 121. The 150 KB budget in CLAUDE.md is written for customer routes, but applied here every vendor route is under it; `/listings/[id]/edit` (149) and `/` (148) are within 2 kB.

## Debug sweep

- Raw i18n keys: covered by the new route test. One real dependency surfaced: `service-form` reads `vendor.listings.fields.priceInvalid` (now shipped to the services routes).
- Accept-invite: the `auth` gap in the brief is already closed by `accept-invite/layout.tsx`; keys verified.
- Dead links: scanned every `href` and `` `/${locale}/...` `` against the 54 routes. None dead. `event-ops-panel` shows `/{locale}/account/event-team/accept` as share text; that route exists in the customer app, but the text is a bare path without the customer origin, so a recipient who pastes it has no host. Worth using `customer-app.ts` to build an absolute link.
- Hydration: every `Date.now()`/`Math.random()` use is inside a client component that renders after its client-side fetch or on a user action (`vendor-reviews-queue`, `instance-editor`, `scanner-view`, `pricing-editor`), so no SSR/CSR mismatch was found. `suppressHydrationWarning` is on `<html>` for the theme script only. `scanner-view` computes `Date.now()` during render; it is only reached after the event sync, but should move into an effect if the scanner is ever server-rendered with data.
- Stale comment: `protected-dynamic-routes.test.ts` says capability probes use `cache: "no-store"`; they use `next.revalidate: 300`. Behaviour is correct, the comment is wrong.

## Slow API endpoints (from code, not measured)

| Endpoint | Cause in code | Status |
|---|---|---|
| `/vendor/orders/dashboard` | all orders, then `in_()` of every id for items, payments, confirm events, sequential | Fixed, PR #952 |
| `/vendor/orders/queue` | items and payments for every order regardless of filter | Fixed, PR #952 |
| `/vendor/payouts` | vendor read, rate-limit RPC, payout fields read, then balances, all sequential | Not changed (payout logic out of scope) |
| `/kyc/status`, `/vendor/businesses`, `/deals` | not reviewed in this pass | Open |

Handlers are plain `def` (threadpool), so none block the event loop; the cost is round trips and unbounded reads, which is what #935's HTTP/1.1 keep-alive change also targeted.

## Glass styling

Plan once PR #945 (`glassClass`, `.v-glass--bar|bar-bottom|overlay|card`) merges: sticky header in `vendor-shell.tsx` (`bar`), mobile bottom nav in `vendor-nav.tsx` (`bar-bottom`), the more-menu sheet and order action sheets (`overlay`). No ad-hoc colours are added before then.
