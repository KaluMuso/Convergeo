/**
 * PDP wishlist adapter over the unified local store.
 * Keys may be product IDs and/or slugs; v1 map/array payloads are migrated on read.
 */

import {
  isWishlistedLocal,
  listWishlistEntries,
  replaceWishlistLocal,
  toggleWishlistLocal,
  WISHLIST_STORAGE_KEY,
} from "../../../../../lib/wishlist-local";

export { WISHLIST_STORAGE_KEY };

/** Legacy map shape retained for tests that assert productId → ISO. */
export type WishlistMap = Record<string, string>;

export function readWishlist(): WishlistMap {
  const map: WishlistMap = {};
  for (const entry of listWishlistEntries()) {
    if (entry.productId) {
      map[entry.productId] = entry.savedAt;
    }
  }
  return map;
}

export function writeWishlist(map: WishlistMap): void {
  // Test/compat path: replace with productId-keyed entries (slug = productId).
  replaceWishlistLocal(
    Object.entries(map).map(([productId, savedAt]) => ({
      productId,
      slug: productId,
      savedAt,
    })),
  );
}

export function isWishlisted(productId: string): boolean {
  return isWishlistedLocal({ productId, slug: productId });
}

export function toggleWishlist(productId: string, slug?: string): boolean {
  return toggleWishlistLocal({
    productId,
    slug: slug?.trim() || productId,
  });
}
