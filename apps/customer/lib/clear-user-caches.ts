/**
 * Purge per-user service-worker runtime caches on sign-out (shared phones).
 * Shared with `sw.ts`; the SW is also told to clear so
 * an in-flight revalidation cannot repopulate them. Never throws.
 */
export const USER_CACHE_NAMES = [
  "api-v1",
  "ticket-wallet-api-v1",
  "ticket-wallet-pages-v1",
] as const;

/** Message the page posts to the SW on sign-out. */
export const CLEAR_USER_CACHES_MESSAGE = "CLEAR_USER_CACHES";

export async function clearUserCaches(): Promise<void> {
  try {
    if (typeof navigator !== "undefined" && "serviceWorker" in navigator) {
      navigator.serviceWorker.controller?.postMessage({ type: CLEAR_USER_CACHES_MESSAGE });
    }
  } catch {
    // best effort
  }
  try {
    if (typeof caches !== "undefined") {
      await Promise.all(USER_CACHE_NAMES.map((name) => caches.delete(name)));
    }
  } catch {
    // best effort
  }
}
