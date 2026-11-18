"use client";

import { emitToastKey } from "@vergeo/ui/src/toast";
import { useCallback, useEffect, useMemo, useState, useSyncExternalStore } from "react";

import {
  clearWishlistLocal,
  getWishlistServerSnapshot,
  getWishlistSnapshot,
  parseWishlistSnapshot,
  removeWishlistLocal,
  resetWishlistStoreForTests,
  subscribeWishlist,
  toggleWishlistLocal,
} from "../../../../../lib/wishlist-local";

/**
 * Server sync is fire-and-forget, so the engagement client loads on demand and
 * stays out of the first-load bundle of every route that renders a wishlist heart.
 */
function syncWishlistWithServer(): Promise<void> {
  return import("../../../../../lib/engagement-api")
    .then((mod) => mod.syncWishlistWithServer())
    .catch(() => undefined);
}

/** Test helper — clears in-memory store between vitest cases. */
export function resetLocalWishlistStoreForTests(): void {
  resetWishlistStoreForTests();
}

export function removeWishlistSlug(productSlug: string): void {
  removeWishlistLocal({ slug: productSlug });
}

/**
 * Browser-local wishlist by product slug, with optional server sync when signed in.
 * Saving an item does not reserve stock or price.
 */
export function useLocalWishlist(productSlug: string | null): {
  isWishlisted: boolean;
  toggleWishlist: () => void;
  enabled: boolean;
} {
  const snapshot = useSyncExternalStore(
    subscribeWishlist,
    getWishlistSnapshot,
    getWishlistServerSnapshot,
  );
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
  }, []);

  const isWishlisted = Boolean(
    productSlug &&
    parseWishlistSnapshot(snapshot).some((entry) => entry.slug === productSlug),
  );

  const toggleWishlist = useCallback(() => {
    if (!productSlug) {
      return;
    }
    const saved = toggleWishlistLocal({ slug: productSlug });
    emitToastKey(saved ? "wishlistAdded" : "wishlistRemoved", {
      type: saved ? "success" : "info",
    });
    void syncWishlistWithServer();
  }, [productSlug]);

  return {
    isWishlisted,
    toggleWishlist,
    enabled: mounted && Boolean(productSlug),
  };
}

/** Ordered wishlist slugs for the Saved items page (newest first). */
export function useLocalWishlistSlugs(): {
  slugs: string[];
  hydrated: boolean;
  remove: (slug: string) => void;
  clear: () => void;
} {
  const snapshot = useSyncExternalStore(
    subscribeWishlist,
    getWishlistSnapshot,
    getWishlistServerSnapshot,
  );
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
    void syncWishlistWithServer();
  }, []);

  const clear = useCallback(() => {
    clearWishlistLocal();
    void syncWishlistWithServer();
  }, []);

  const remove = useCallback((slug: string) => {
    removeWishlistLocal({ slug });
    void syncWishlistWithServer();
  }, []);

  // Stable identity per snapshot: consumers use `slugs` as an effect dependency,
  // and a fresh array each render caused an endless render loop on Saved items
  // (state set in the effect -> re-render -> new array -> effect again), which
  // starved router transitions so links stopped navigating.
  const slugs = useMemo(
    () => parseWishlistSnapshot(snapshot).map((entry) => entry.slug),
    [snapshot],
  );

  return {
    slugs,
    hydrated: mounted,
    remove,
    clear,
  };
}
