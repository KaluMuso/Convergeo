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
 *   5a. per-user / unlisted API GETs     → NetworkOnly (PRIVACY: phones are
 *       shared within households; nothing personal is ever persisted).
 *   5b. allowlisted PUBLIC API GETs      → NetworkFirst (anonymous only).
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

import { parsePushPayload, safeNotificationUrl } from "./lib/push-payload";
import { CLEAR_USER_CACHES_MESSAGE, USER_CACHE_NAMES } from "./lib/clear-user-caches";

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

/**
 * API paths that are genuinely public and non-personal. ALLOWLIST (not a
 * denylist): any API GET not listed here is NetworkOnly. A request that carries
 * an `Authorization` header is never cached either, because some public paths
 * (home feed, catalog) personalise their response for signed-in users.
 */
const PUBLIC_API_PATH_PATTERN =
  /^\/(?:catalog|products|search|categories|directory|discovery|public\/config|home\/feed)(?:\/|$)/;

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

/** True only for anonymous GETs to allowlisted public, non-personal API paths. */
export function isPublicApiRequest(
  url: URL,
  request: Pick<Request, "method" | "headers">,
): boolean {
  if (request.method !== "GET" || !isApiRequest(url)) return false;
  if (!PUBLIC_API_PATH_PATTERN.test(url.pathname)) return false;
  // B2B supplies feed is gated by business identity — never public.
  if (url.searchParams.get("wholesale") === "true") return false;
  // Signed-in requests may be personalised — never persist them.
  if (request.headers?.has("Authorization")) return false;
  return true;
}

export function isWalletPage(pathname: string): boolean {
  return WALLET_PAGE_PATTERN.test(pathname);
}

/** Wallet API responses — folded from the M10 `sw-wallet.ts` fragment. */
export function isWalletApi(url: URL): boolean {
  return isApiRequest(url) && url.pathname.startsWith(WALLET_API_PATH_PREFIX);
}

/** Notification center + Web Push endpoints on our API origin. */
export function isNotificationsApi(url: URL): boolean {
  return (
    isApiRequest(url) &&
    (url.pathname.startsWith("/me/notifications") ||
      url.pathname.startsWith("/me/push-subscriptions") ||
      url.pathname === "/me/web-push")
  );
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
    matcher: ({ url, request }) => request.method === "GET" && isWalletApi(url),
    handler: new NetworkFirst({
      cacheName: "ticket-wallet-api-v1",
      networkTimeoutSeconds: 5,
      plugins: [
        new ExpirationPlugin({ maxEntries: 48, maxAgeSeconds: 60 * 10 }),
        {
          // Avoid uncaught `no-response` when the API is down and cache is empty.
          handlerDidError: async () =>
            new Response(JSON.stringify({ error: "unavailable" }), {
              status: 503,
              headers: { "Content-Type": "application/json", "Cache-Control": "no-store" },
            }),
        },
      ],
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
    // 5. Notification center API — per-user and live (badge counts, read
    //     state): NetworkOnly so one signed-in user's feed is never served
    //     from the shared runtime cache to another user of the same phone.
    name: "notifications-network-only",
    matcher: ({ url }) => isNotificationsApi(url),
    handler: new NetworkOnly(),
  },
  {
    // 5a. PRIVACY — every other API request (per-user: /me, /cart, /orders,
    // /account, /wishlist, /notifications, …) is NetworkOnly and never cached.
    name: "api-private",
    matcher: ({ url, request }) =>
      request.method === "GET" &&
      isApiRequest(url) &&
      !isWalletApi(url) &&
      !isPublicApiRequest(url, request),
    handler: new NetworkOnly(),
  },
  {
    // 5b. Allowlisted public API GETs — network-first (offline fall-back to cache).
    name: "api",
    matcher: ({ url, request }) => isPublicApiRequest(url, request),
    handler: new NetworkFirst({
      cacheName: "api-v1",
      networkTimeoutSeconds: 5,
      plugins: [
        new ExpirationPlugin({ maxEntries: 50, maxAgeSeconds: 60 * 5 }),
        {
          // API down / origin unreachable: return 503 instead of rejecting the
          // FetchEvent (which surfaced as `no-response` console errors).
          handlerDidError: async () =>
            new Response(JSON.stringify({ error: "unavailable" }), {
              status: 503,
              headers: { "Content-Type": "application/json", "Cache-Control": "no-store" },
            }),
        },
      ],
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
type WaitableEvent = { waitUntil: (promise: Promise<unknown>) => void };
type PushEventLike = WaitableEvent & { data?: { text: () => string } | null };
type NotificationClickLike = WaitableEvent & {
  notification: { close: () => void; data?: { url?: unknown } };
};
type WindowClientLike = {
  url: string;
  focus: () => Promise<unknown>;
  navigate?: (url: string) => Promise<unknown>;
};
type ServiceWorkerScope = {
  __SW_MANIFEST?: (PrecacheEntry | string)[];
  skipWaiting: () => Promise<void>;
  addEventListener: ((
    type: "message",
    listener: (event: { data?: { type?: string } }) => void,
  ) => void) &
    ((type: "push", listener: (event: PushEventLike) => void) => void) &
    ((type: "notificationclick", listener: (event: NotificationClickLike) => void) => void);
  registration: {
    showNotification: (title: string, options: Record<string, unknown>) => Promise<void>;
  };
  clients: {
    matchAll: (options: {
      type: "window";
      includeUncontrolled: boolean;
    }) => Promise<WindowClientLike[]>;
    openWindow: (url: string) => Promise<unknown>;
  };
  navigator?: { setAppBadge?: (count?: number) => Promise<void> };
};

/** Fallback tap target when a push carries no usable link. */
const PUSH_FALLBACK_URL = "/en/account/notifications";

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

  // Web Push display path (flag `web_push`, default OFF — no subscription can
  // exist until the founder enables it). Payload contract: lib/push-payload.ts.
  sw.addEventListener("push", (event) => {
    const display = parsePushPayload(event.data?.text() ?? null, PUSH_FALLBACK_URL);
    const badge = display.badge;
    event.waitUntil(
      Promise.all([
        sw.registration.showNotification(display.title, {
          body: display.body,
          icon: "/brand/convergeo-icon-192.png",
          badge: "/brand/convergeo-icon-192.png",
          tag: "vergeo-notification",
          data: { url: display.url },
        }),
        badge !== null && typeof sw.navigator?.setAppBadge === "function"
          ? sw.navigator.setAppBadge(badge).catch(() => undefined)
          : Promise.resolve(),
      ]),
    );
  });

  sw.addEventListener("notificationclick", (event) => {
    event.notification.close();
    const url = safeNotificationUrl(event.notification.data?.url, PUSH_FALLBACK_URL);
    event.waitUntil(
      sw.clients.matchAll({ type: "window", includeUncontrolled: true }).then((windows) => {
        const open = windows[0];
        if (open) {
          return open.focus().then(() => open.navigate?.(url));
        }
        return sw.clients.openWindow(url);
      }),
    );
  });

  // Sign-out: purge every per-user runtime cache so a shared phone never
  // serves the previous user's data.
  sw.addEventListener("message", (event) => {
    if (event.data?.type === CLEAR_USER_CACHES_MESSAGE) {
      void Promise.all(USER_CACHE_NAMES.map((name) => caches.delete(name)));
    }
  });

  // Update prompt handshake: the page asks the waiting SW to take over.
  sw.addEventListener("message", (event) => {
    if (event.data?.type === "SKIP_WAITING") {
      void sw.skipWaiting();
    }
  });
}
