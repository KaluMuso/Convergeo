/**
 * Unified customer service worker (serwist) — M16-P02.
 *
 * Precaches the Next.js app shell (via the injected `self.__SW_MANIFEST`) and
 * applies runtime-caching rules. The M10 ticket-wallet offline fragment
 * (formerly `sw-wallet.ts`) is FOLDED IN here — there is exactly one SW.
 *
 * Runtime-cache policy (first match wins, so order matters):
 *   1. checkout / cart / payment / auth → NetworkOnly (HARD INVARIANT: never
 *      cached — no stale-price sale, honest offline messaging).
 *   2. ticket-wallet pages / API        → NetworkFirst (live QR stays fresh).
 *   3. images                            → CacheFirst, capped + expiring.
 *   4. catalog / PDP navigations         → StaleWhileRevalidate.
 *   5. our API GETs                      → NetworkFirst.
 *   6. Next.js static assets             → serwist `defaultCache`.
 *
 * Update lifecycle is SAFE: `skipWaiting` is OFF, so a new SW waits until the
 * app tells it to activate (`SKIP_WAITING` message from the update prompt).
 * No silent skip-waiting that could serve a half-updated app.
 */
import { defaultCache } from "@serwist/next/worker";
import {
  CacheFirst,
  ExpirationPlugin,
  NetworkFirst,
  NetworkOnly,
  Serwist,
  StaleWhileRevalidate,
  type PrecacheEntry,
  type RouteHandler,
  type RouteMatchCallback,
  type RuntimeCaching,
} from "serwist";

/** Default-locale offline shell (precached; served when a navigation fails). */
const OFFLINE_FALLBACK_URL = "/en/offline";

const IMAGE_EXTENSION = /\.(?:png|jpg|jpeg|webp|avif|gif|svg|ico)$/i;

// Locale-prefixed route families. Locale is always the first path segment.
const NEVER_CACHE_PATTERN =
  /^\/[^/]+\/(?:checkout|cart|payment|pay|login|signup|otp|logout|auth)(?:\/|$)/;
const CATALOG_PATTERN =
  /^\/[^/]+\/(?:p|c|v|e|events|services|directory|supplies|categories|compare|calendar)(?:\/|$)/;
const WALLET_PAGE_PATTERN = /^\/[^/]+\/account\/tickets(?:\/|$)/;
const WALLET_API_PATH_PREFIX = "/account/tickets";

/** Same-origin API base (empty → no API matches, e.g. under test). */
function apiOrigin(): string | null {
  const base = process.env.NEXT_PUBLIC_API_BASE_URL;
  if (!base) return null;
  try {
    return new URL(base).origin;
  } catch {
    return null;
  }
}

// ── Route predicates (exported for the SW-rules unit test) ──────────────────

/** HARD INVARIANT: checkout/cart/payment/auth are NEVER cached. */
export function isNeverCacheRoute(pathname: string): boolean {
  return NEVER_CACHE_PATTERN.test(pathname);
}

export function isCatalogRoute(pathname: string): boolean {
  return CATALOG_PATTERN.test(pathname) && !isNeverCacheRoute(pathname);
}

export function isImageRequest(url: URL, destination: string): boolean {
  return (
    destination === "image" ||
    url.hostname === "res.cloudinary.com" ||
    IMAGE_EXTENSION.test(url.pathname)
  );
}

export function isApiRequest(url: URL): boolean {
  const origin = apiOrigin();
  return origin !== null && url.origin === origin;
}

export function isWalletPage(pathname: string): boolean {
  return WALLET_PAGE_PATTERN.test(pathname);
}

/** Wallet API responses — folded from the M10 `sw-wallet.ts` fragment. */
export function isWalletApi(url: URL): boolean {
  return isApiRequest(url) && url.pathname.startsWith(WALLET_API_PATH_PREFIX);
}

// ── Runtime-cache rules (named so the test can assert them by name) ─────────

type NamedRule = {
  name: string;
  matcher: RouteMatchCallback;
  handler: RouteHandler;
};

export const cacheRules: NamedRule[] = [
  {
    // 1. HARD INVARIANT — checkout/cart/payment/auth: NetworkOnly, never cached.
    name: "never-cache",
    matcher: ({ url, sameOrigin }) => sameOrigin && isNeverCacheRoute(url.pathname),
    handler: new NetworkOnly(),
  },
  {
    // 2a. Ticket-wallet pages (M10) — network-first so the live QR stays fresh.
    name: "ticket-wallet-pages",
    matcher: ({ url, sameOrigin }) => sameOrigin && isWalletPage(url.pathname),
    handler: new NetworkFirst({
      cacheName: "ticket-wallet-pages-v1",
      networkTimeoutSeconds: 3,
      plugins: [new ExpirationPlugin({ maxEntries: 24, maxAgeSeconds: 60 * 60 * 24 })],
    }),
  },
  {
    // 2b. Ticket-wallet API (M10) — short-lived offline horizon / detail bootstrap.
    name: "ticket-wallet-api",
    matcher: ({ url }) => isWalletApi(url),
    handler: new NetworkFirst({
      cacheName: "ticket-wallet-api-v1",
      networkTimeoutSeconds: 5,
      plugins: [new ExpirationPlugin({ maxEntries: 48, maxAgeSeconds: 60 * 10 })],
    }),
  },
  {
    // 3. Images — cache-first, capped so we never blow the storage budget.
    name: "images",
    matcher: ({ url, request }) => isImageRequest(url, request.destination),
    handler: new CacheFirst({
      cacheName: "images-v1",
      plugins: [
        new ExpirationPlugin({
          maxEntries: 60,
          maxAgeSeconds: 60 * 60 * 24 * 30,
          purgeOnQuotaError: true,
        }),
      ],
    }),
  },
  {
    // 4. Catalog / PDP navigations — stale-while-revalidate for instant repeat views.
    name: "catalog",
    matcher: ({ url, request, sameOrigin }) =>
      sameOrigin && request.destination === "document" && isCatalogRoute(url.pathname),
    handler: new StaleWhileRevalidate({
      cacheName: "catalog-pages-v1",
      plugins: [new ExpirationPlugin({ maxEntries: 50, maxAgeSeconds: 60 * 60 * 24 })],
    }),
  },
  {
    // 5. Our API GETs — network-first (fresh data, offline fall-back to cache).
    name: "api",
    matcher: ({ url }) => isApiRequest(url) && !isWalletApi(url),
    handler: new NetworkFirst({
      cacheName: "api-v1",
      networkTimeoutSeconds: 5,
      plugins: [new ExpirationPlugin({ maxEntries: 50, maxAgeSeconds: 60 * 5 })],
    }),
  },
];

export const runtimeCaching: RuntimeCaching[] = [
  ...cacheRules.map(({ matcher, handler }) => ({ matcher, handler })),
  // 6. Next.js framework assets (_next static, fonts, data, image opt, …).
  ...defaultCache,
];

/**
 * SAFE update policy — both OFF so a new SW never takes over silently. The
 * app surfaces an update prompt and posts `SKIP_WAITING` on user confirm.
 */
export const SW_UPDATE_POLICY = { skipWaiting: false, clientsClaim: false } as const;

// ── Service-worker instantiation (skipped outside a SW context, e.g. tests) ──

// Minimal shape of the service-worker global — the customer tsconfig lib does
// not ship the full `webworker` types, so we model only what we touch.
type ServiceWorkerScope = {
  __SW_MANIFEST?: (PrecacheEntry | string)[];
  skipWaiting: () => Promise<void>;
  addEventListener: (
    type: "message",
    listener: (event: { data?: { type?: string } }) => void,
  ) => void;
};

function inServiceWorkerContext(): boolean {
  return (
    typeof self !== "undefined" &&
    typeof (self as { skipWaiting?: unknown }).skipWaiting === "function" &&
    "clients" in self
  );
}

if (inServiceWorkerContext()) {
  const sw = self as unknown as ServiceWorkerScope;
  const serwist = new Serwist({
    // `self.__SW_MANIFEST` is the injection point replaced by @serwist/next at
    // build time — keep this literal member access so injection succeeds.
    precacheEntries: (self as unknown as { __SW_MANIFEST?: (PrecacheEntry | string)[] })
      .__SW_MANIFEST,
    // SAFE update lifecycle: do NOT auto-skip-waiting or claim clients — the app
    // prompts the user, then posts SKIP_WAITING to activate the new version.
    skipWaiting: SW_UPDATE_POLICY.skipWaiting,
    clientsClaim: SW_UPDATE_POLICY.clientsClaim,
    navigationPreload: true,
    runtimeCaching,
    fallbacks: {
      entries: [
        {
          url: OFFLINE_FALLBACK_URL,
          matcher: ({ request }) => request.mode === "navigate",
        },
      ],
    },
  });
  serwist.addEventListeners();

  // Update prompt handshake: the page asks the waiting SW to take over.
  sw.addEventListener("message", (event) => {
    if (event.data?.type === "SKIP_WAITING") {
      void sw.skipWaiting();
    }
  });
}
