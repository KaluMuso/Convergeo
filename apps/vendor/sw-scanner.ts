import { resolveApiBaseUrl } from "./lib/api-base-url";

/**
 * Serwist runtime-caching fragment for the organiser event-ticket scanner.
 * Mirrors apps/customer/sw-wallet.ts -- a standalone fragment awaiting merge
 * into the vendor app's service worker by a later PWA-wiring pebble. Do not
 * import from pages; do not edit the (not-yet-created) vendor serwist config
 * from here.
 *
 * The scanner itself is offline-first via IndexedDB (see
 * app/[locale]/events/[id]/scan/_lib/offline-store.ts), not via the service
 * worker cache -- these entries only make sure the *app shell* (scan route
 * HTML/JS) and the scan-sync payload are available from cache so the PWA can
 * still boot into the scanner UI with zero connectivity after the initial
 * pre-event sync.
 */

export type ScannerRuntimeCaching = {
  matcher: RegExp | ((options: { url: URL }) => boolean);
  handler: "NetworkFirst" | "CacheFirst" | "StaleWhileRevalidate";
  method?: string;
  options?: {
    cacheName?: string;
    expiration?: {
      maxEntries?: number;
      maxAgeSeconds?: number;
    };
    networkTimeoutSeconds?: number;
  };
};

const SCANNER_PAGE_PATTERN = /\/[^/]+\/events\/[^/]+\/scan(?:\/|$)/;

function matchesScanSyncApi(url: URL): boolean {
  const apiBase = resolveApiBaseUrl();
  if (!apiBase) {
    return false;
  }
  try {
    const apiOrigin = new URL(apiBase).origin;
    return (
      url.origin === apiOrigin &&
      /^\/events\/[^/]+\/instances\/[^/]+\/scan-sync$/.test(url.pathname)
    );
  } catch {
    return false;
  }
}

/** Scanner app-shell route -- cache-first so the PWA boots offline after the first visit. */
export const scannerPageCache: ScannerRuntimeCaching = {
  matcher: ({ url }) => SCANNER_PAGE_PATTERN.test(url.pathname),
  handler: "StaleWhileRevalidate",
  options: {
    cacheName: "event-scanner-pages-v1",
    expiration: {
      maxEntries: 16,
      maxAgeSeconds: 60 * 60 * 24 * 7,
    },
  },
};

/**
 * scan-sync GET responses -- network-first with a short timeout. The real
 * offline source of truth is the IndexedDB store the scanner writes on a
 * successful sync; this cache entry is only a secondary safety net in case
 * IndexedDB is unavailable (e.g. private browsing).
 */
export const scanSyncApiCache: ScannerRuntimeCaching = {
  matcher: ({ url }) => matchesScanSyncApi(url),
  handler: "NetworkFirst",
  options: {
    cacheName: "event-scanner-sync-v1",
    networkTimeoutSeconds: 5,
    expiration: {
      maxEntries: 16,
      maxAgeSeconds: 60 * 60 * 24,
    },
  },
};

export const scannerRouteCache: ScannerRuntimeCaching[] = [scannerPageCache, scanSyncApiCache];
