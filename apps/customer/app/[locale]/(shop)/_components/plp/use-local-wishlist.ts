"use client";

import { useCallback, useEffect, useState, useSyncExternalStore } from "react";

const STORAGE_KEY = "vergeo5:wishlist:v1";

type WishlistStore = {
  slugs: Set<string>;
  hydrated: boolean;
  listeners: Set<() => void>;
};

const store: WishlistStore = {
  slugs: new Set(),
  hydrated: false,
  listeners: new Set(),
};

function readSlugs(): Set<string> {
  if (typeof window === "undefined") {
    return new Set();
  }
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) {
      return new Set();
    }
    const parsed = JSON.parse(raw) as unknown;
    if (!Array.isArray(parsed)) {
      return new Set();
    }
    return new Set(
      parsed.filter((entry): entry is string => typeof entry === "string" && entry.length > 0),
    );
  } catch {
    return new Set();
  }
}

function writeSlugs(slugs: Set<string>): void {
  if (typeof window === "undefined") {
    return;
  }
  window.localStorage.setItem(STORAGE_KEY, JSON.stringify([...slugs]));
}

function emit(): void {
  for (const listener of store.listeners) {
    listener();
  }
}

function ensureHydrated(): void {
  if (store.hydrated || typeof window === "undefined") {
    return;
  }
  store.slugs = readSlugs();
  store.hydrated = true;
}

function subscribe(listener: () => void): () => void {
  ensureHydrated();
  store.listeners.add(listener);
  return () => {
    store.listeners.delete(listener);
  };
}

function getSnapshot(): string {
  ensureHydrated();
  return [...store.slugs].sort().join("\0");
}

function getServerSnapshot(): string {
  return "";
}

/** Test helper — clears in-memory store between vitest cases. */
export function resetLocalWishlistStoreForTests(): void {
  store.slugs = new Set();
  store.hydrated = false;
  emit();
}

/**
 * Browser-local wishlist by product slug. No server API yet — honest client persistence only.
 */
export function useLocalWishlist(productSlug: string | null): {
  isWishlisted: boolean;
  toggleWishlist: () => void;
  enabled: boolean;
} {
  const snapshot = useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot);
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
  }, []);

  const isWishlisted = Boolean(
    productSlug && (snapshot === productSlug || snapshot.split("\0").includes(productSlug)),
  );

  const toggleWishlist = useCallback(() => {
    if (!productSlug) {
      return;
    }
    ensureHydrated();
    const next = new Set(store.slugs);
    if (next.has(productSlug)) {
      next.delete(productSlug);
    } else {
      next.add(productSlug);
    }
    store.slugs = next;
    writeSlugs(next);
    emit();
  }, [productSlug]);

  return {
    isWishlisted,
    toggleWishlist,
    enabled: mounted && Boolean(productSlug),
  };
}
