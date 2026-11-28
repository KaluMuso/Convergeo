/**
 * Unified vendor service worker (serwist).
 *
 * Precaches the Next.js app shell (via the injected `self.__SW_MANIFEST`) and
 * applies runtime-caching rules. The event-ticket scanner fragment from
 * `sw-scanner.ts` is folded in here — there is exactly one SW.
 *
 * Runtime-cache policy (first match wins, so order matters):
 *   1. checkout / payment / auth → NetworkOnly (HARD INVARIANT: never cached).
 *   2. event-scanner pages       → StaleWhileRevalidate (offline app shell).
 *   3. scan-sync API GET         → NetworkFirst (IndexedDB bootstrap safety net).
 *   4. all other API GETs        → NetworkOnly (vendor data is per-user).
 *   5. Next.js static assets     → serwist `defaultCache`.
 *
 * Update lifecycle is SAFE: `skipWaiting` is OFF; the app may post `SKIP_WAITING`
 * after an update prompt (same contract as the customer portal).
 */
import { defaultCache } from "@serwist/next/worker";
import {
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

import { isScanSyncApiUrl, isScannerPagePathname } from "./sw-scanner";

const NEVER_CACHE_PATTERN =
  /^\/[^/]+\/(?:checkout|cart|payment|pay|payouts|login|signup|otp|logout|auth|reset-password|accept-invite)(?:\/|$)/;

function apiOrigin(): string | null {
  const base = process.env.NEXT_PUBLIC_API_BASE_URL;
  if (!base) return null;
  try {
    return new URL(base).origin;
  } catch {
    return null;
  }
}

/** HARD INVARIANT: checkout/payment/auth routes are NEVER cached. */
export function isNeverCacheRoute(pathname: string): boolean {
  return NEVER_CACHE_PATTERN.test(pathname);
}

export function isApiRequest(url: URL): boolean {
  const origin = apiOrigin();
  return origin !== null && url.origin === origin;
}

type NamedRule = {
  name: string;
  matcher: RouteMatchCallback;
  handler: RouteHandler;
};

export const cacheRules: NamedRule[] = [
  {
    name: "never-cache",
    matcher: ({ url, sameOrigin }) => sameOrigin && isNeverCacheRoute(url.pathname),
    handler: new NetworkOnly(),
  },
  {
    name: "event-scanner-pages",
    matcher: ({ url, sameOrigin, request }) =>
      sameOrigin && request.destination === "document" && isScannerPagePathname(url.pathname),
    handler: new StaleWhileRevalidate({
      cacheName: "event-scanner-pages-v1",
      plugins: [
        new ExpirationPlugin({
          maxEntries: 16,
          maxAgeSeconds: 60 * 60 * 24 * 7,
        }),
      ],
    }),
  },
  {
    name: "event-scanner-sync-api",
    matcher: ({ url, request }) => request.method === "GET" && isScanSyncApiUrl(url),
    handler: new NetworkFirst({
      cacheName: "event-scanner-sync-v1",
      networkTimeoutSeconds: 5,
      plugins: [
        new ExpirationPlugin({
          maxEntries: 16,
          maxAgeSeconds: 60 * 60 * 24,
        }),
      ],
    }),
  },
  {
    name: "api-private",
    matcher: ({ url, request }) =>
      request.method === "GET" && isApiRequest(url) && !isScanSyncApiUrl(url),
    handler: new NetworkOnly(),
  },
];

export const runtimeCaching: RuntimeCaching[] = [
  ...cacheRules.map(({ matcher, handler }) => ({ matcher, handler })),
  ...defaultCache,
];

export const SW_UPDATE_POLICY = {
  skipWaiting: false,
  clientsClaim: false,
} as const;

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
    precacheEntries: (self as unknown as { __SW_MANIFEST?: (PrecacheEntry | string)[] })
      .__SW_MANIFEST,
    skipWaiting: SW_UPDATE_POLICY.skipWaiting,
    clientsClaim: SW_UPDATE_POLICY.clientsClaim,
    navigationPreload: true,
    runtimeCaching,
  });
  serwist.addEventListeners();

  sw.addEventListener("message", (event) => {
    if (event.data?.type === "SKIP_WAITING") {
      void sw.skipWaiting();
    }
  });
}
