"use client";

import { useCallback, useEffect, useState, useSyncExternalStore } from "react";

export const RECENTLY_VIEWED_STORAGE_KEY = "vergeo5:recently-viewed:v1";
export const RECENTLY_VIEWED_MAX = 20;

export type RecentlyViewedEntry = {
  slug: string;
  name: string;
  viewedAt: number;
};

type RecentStore = {
  entries: RecentlyViewedEntry[];
  hydrated: boolean;
  listeners: Set<() => void>;
};

const store: RecentStore = {
  entries: [],
  hydrated: false,
  listeners: new Set(),
};

function isEntry(value: unknown): value is RecentlyViewedEntry {
  if (typeof value !== "object" || value === null) {
    return false;
  }
  const record = value as Record<string, unknown>;
  return (
    typeof record.slug === "string" &&
    record.slug.length > 0 &&
    typeof record.name === "string" &&
    typeof record.viewedAt === "number"
  );
}

function readEntries(): RecentlyViewedEntry[] {
  if (typeof window === "undefined") {
    return [];
  }
  try {
    const raw = window.localStorage.getItem(RECENTLY_VIEWED_STORAGE_KEY);
    if (!raw) {
      return [];
    }
    const parsed = JSON.parse(raw) as unknown;
    if (!Array.isArray(parsed)) {
      return [];
    }
    return parsed.filter(isEntry).slice(0, RECENTLY_VIEWED_MAX);
  } catch {
    return [];
  }
}

function writeEntries(entries: RecentlyViewedEntry[]): void {
  if (typeof window === "undefined") {
    return;
  }
  window.localStorage.setItem(RECENTLY_VIEWED_STORAGE_KEY, JSON.stringify(entries));
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
  store.entries = readEntries();
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
  return JSON.stringify(store.entries);
}

function getServerSnapshot(): string {
  return "[]";
}

/** Deduplicate by slug: newest view wins and moves to front. Caps at MAX. */
export function upsertRecentlyViewed(
  entries: RecentlyViewedEntry[],
  next: RecentlyViewedEntry,
): RecentlyViewedEntry[] {
  const without = entries.filter((entry) => entry.slug !== next.slug);
  return [next, ...without].slice(0, RECENTLY_VIEWED_MAX);
}

export function recordRecentlyViewed(slug: string, name: string): void {
  if (!slug) {
    return;
  }
  ensureHydrated();
  store.entries = upsertRecentlyViewed(store.entries, {
    slug,
    name: name.trim() || slug,
    viewedAt: Date.now(),
  });
  writeEntries(store.entries);
  emit();
}

export function clearRecentlyViewed(): void {
  ensureHydrated();
  store.entries = [];
  writeEntries(store.entries);
  emit();
}

export function removeRecentlyViewed(slug: string): void {
  ensureHydrated();
  store.entries = store.entries.filter((entry) => entry.slug !== slug);
  writeEntries(store.entries);
  emit();
}

/** Test helper — clears in-memory store between vitest cases. */
export function resetRecentlyViewedStoreForTests(): void {
  store.entries = [];
  store.hydrated = false;
  emit();
}

/**
 * Device-local recently viewed products. Not synced across devices.
 * Privacy: stored only in this browser; user can clear history.
 */
export function useRecentlyViewed(): {
  entries: RecentlyViewedEntry[];
  hydrated: boolean;
  clear: () => void;
  remove: (slug: string) => void;
} {
  const snapshot = useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot);
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
  }, []);

  const clear = useCallback(() => {
    clearRecentlyViewed();
  }, []);

  const remove = useCallback((slug: string) => {
    removeRecentlyViewed(slug);
  }, []);

  return {
    entries: JSON.parse(snapshot) as RecentlyViewedEntry[],
    hydrated: mounted,
    clear,
    remove,
  };
}
