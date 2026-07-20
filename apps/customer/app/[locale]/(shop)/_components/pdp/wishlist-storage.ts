/**
 * Local-only PDP wishlist (audit P1/P4). Server sync is intentionally out of scope.
 * Keys are product IDs; values are ISO timestamps of when the item was saved.
 */

export const WISHLIST_STORAGE_KEY = "vergeo5:wishlist:v1";

export type WishlistMap = Record<string, string>;

function canUseStorage(): boolean {
  return typeof window !== "undefined" && typeof window.localStorage !== "undefined";
}

export function readWishlist(): WishlistMap {
  if (!canUseStorage()) {
    return {};
  }
  try {
    const raw = window.localStorage.getItem(WISHLIST_STORAGE_KEY);
    if (!raw) {
      return {};
    }
    const parsed = JSON.parse(raw) as unknown;
    if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
      return {};
    }
    const result: WishlistMap = {};
    for (const [key, value] of Object.entries(parsed as Record<string, unknown>)) {
      if (typeof key === "string" && key.length > 0 && typeof value === "string") {
        result[key] = value;
      }
    }
    return result;
  } catch {
    return {};
  }
}

export function writeWishlist(map: WishlistMap): void {
  if (!canUseStorage()) {
    return;
  }
  window.localStorage.setItem(WISHLIST_STORAGE_KEY, JSON.stringify(map));
}

export function isWishlisted(productId: string): boolean {
  return Boolean(readWishlist()[productId]);
}

export function toggleWishlist(productId: string): boolean {
  const map = readWishlist();
  if (map[productId]) {
    delete map[productId];
    writeWishlist(map);
    return false;
  }
  map[productId] = new Date().toISOString();
  writeWishlist(map);
  return true;
}
