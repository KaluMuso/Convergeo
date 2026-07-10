/**
 * Serwist runtime-caching fragment for the ticket wallet routes.
 * Merged into the customer service worker by M16-P02 — do not import from pages.
 */

export type WalletRuntimeCaching = {
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

const WALLET_PAGE_PATTERN = /\/[^/]+\/account\/tickets(?:\/|$)/;

function matchesWalletApi(url: URL): boolean {
  const apiBase = process.env.NEXT_PUBLIC_API_BASE_URL;
  if (!apiBase) {
    return false;
  }
  try {
    const apiOrigin = new URL(apiBase).origin;
    return url.origin === apiOrigin && url.pathname.startsWith("/account/tickets");
  } catch {
    return false;
  }
}

/** Wallet HTML routes — network-first so live QR stays fresh when online. */
export const walletPageCache: WalletRuntimeCaching = {
  matcher: ({ url }) => WALLET_PAGE_PATTERN.test(url.pathname),
  handler: "NetworkFirst",
  options: {
    cacheName: "ticket-wallet-pages-v1",
    networkTimeoutSeconds: 3,
    expiration: {
      maxEntries: 24,
      maxAgeSeconds: 60 * 60 * 24,
    },
  },
};

/** Wallet API responses — short-lived cache for offline horizon + detail bootstrap. */
export const walletApiCache: WalletRuntimeCaching = {
  matcher: ({ url }) => matchesWalletApi(url),
  handler: "NetworkFirst",
  options: {
    cacheName: "ticket-wallet-api-v1",
    networkTimeoutSeconds: 5,
    expiration: {
      maxEntries: 48,
      maxAgeSeconds: 60 * 10,
    },
  },
};

export const walletRouteCache: WalletRuntimeCaching[] = [walletPageCache, walletApiCache];
