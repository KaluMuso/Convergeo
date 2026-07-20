/**
 * Unified local wishlist store (slug + optional productId).
 * Migrates legacy v1 shapes: string[] (PLP) and Record<productId, ISO> (PDP).
 */

export const WISHLIST_STORAGE_KEY_V1 = "vergeo5:wishlist:v1";
export const WISHLIST_STORAGE_KEY = "vergeo5:wishlist:v2";

export type WishlistEntry = {
  productId?: string;
  slug: string;
  savedAt: string;
};

type WishlistStore = {
  entries: WishlistEntry[];
  hydrated: boolean;
  listeners: Set<() => void>;
};

const store: WishlistStore = {
  entries: [],
  hydrated: false,
  listeners: new Set(),
};

function canUseStorage(): boolean {
  return typeof window !== "undefined" && typeof window.localStorage !== "undefined";
}

function isEntry(value: unknown): value is WishlistEntry {
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    return false;
  }
  const record = value as Record<string, unknown>;
  return typeof record.slug === "string" && record.slug.length > 0;
}

function migrateV1(raw: string): WishlistEntry[] {
  try {
    const parsed = JSON.parse(raw) as unknown;
    if (Array.isArray(parsed)) {
      return parsed
        .filter((entry): entry is string => typeof entry === "string" && entry.length > 0)
        .map((slug) => ({
          slug,
          savedAt: new Date(0).toISOString(),
        }));
    }
    if (parsed && typeof parsed === "object") {
      return Object.entries(parsed as Record<string, unknown>)
        .filter(
          ([key, value]) => typeof key === "string" && key.length > 0 && typeof value === "string",
        )
        .map(([productId, savedAt]) => ({
          productId,
          // Legacy PDP map had no slug — use productId as a temporary key until PDP re-saves.
          slug: productId,
          savedAt: String(savedAt),
        }));
    }
  } catch {
    // ignore corrupt legacy payload
  }
  return [];
}

function readEntries(): WishlistEntry[] {
  if (!canUseStorage()) {
    return [];
  }
  try {
    const v2 = window.localStorage.getItem(WISHLIST_STORAGE_KEY);
    if (v2) {
      const parsed = JSON.parse(v2) as unknown;
      if (Array.isArray(parsed)) {
        return parsed.filter(isEntry);
      }
    }
    const v1 = window.localStorage.getItem(WISHLIST_STORAGE_KEY_V1);
    if (v1) {
      const migrated = migrateV1(v1);
      writeEntries(migrated);
      window.localStorage.removeItem(WISHLIST_STORAGE_KEY_V1);
      return migrated;
    }
  } catch {
    return [];
  }
  return [];
}

function writeEntries(entries: WishlistEntry[]): void {
  if (!canUseStorage()) {
    return;
  }
  window.localStorage.setItem(WISHLIST_STORAGE_KEY, JSON.stringify(entries));
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

export function subscribeWishlist(listener: () => void): () => void {
  ensureHydrated();
  store.listeners.add(listener);
  return () => {
    store.listeners.delete(listener);
  };
}

export function getWishlistSnapshot(): string {
  ensureHydrated();
  return JSON.stringify(store.entries);
}

export function getWishlistServerSnapshot(): string {
  return "[]";
}

export function parseWishlistSnapshot(snapshot: string): WishlistEntry[] {
  try {
    const parsed = JSON.parse(snapshot) as unknown;
    return Array.isArray(parsed) ? parsed.filter(isEntry) : [];
  } catch {
    return [];
  }
}

/** Test helper — clears in-memory store between vitest cases. */
export function resetWishlistStoreForTests(): void {
  store.entries = [];
  store.hydrated = false;
  emit();
}

export function listWishlistEntries(): WishlistEntry[] {
  ensureHydrated();
  return [...store.entries];
}

export function listWishlistSlugs(): string[] {
  return listWishlistEntries()
    .map((entry) => entry.slug)
    .filter((slug) => slug.length > 0);
}

function entryMatches(
  entry: WishlistEntry,
  identity: { productId?: string | null; slug?: string | null },
): boolean {
  if (identity.productId && entry.productId && entry.productId === identity.productId) {
    return true;
  }
  if (identity.slug && entry.slug && entry.slug === identity.slug) {
    return true;
  }
  return false;
}

export function isWishlistedLocal(identity: {
  productId?: string | null;
  slug?: string | null;
}): boolean {
  ensureHydrated();
  return store.entries.some((entry) => entryMatches(entry, identity));
}

export function upsertWishlistLocal(input: { productId?: string | null; slug: string }): void {
  ensureHydrated();
  const slug = input.slug.trim();
  if (!slug) {
    return;
  }
  const productId = input.productId?.trim() || undefined;
  const without = store.entries.filter((entry) => !entryMatches(entry, { productId, slug }));
  store.entries = [{ productId, slug, savedAt: new Date().toISOString() }, ...without];
  writeEntries(store.entries);
  emit();
}

export function removeWishlistLocal(identity: {
  productId?: string | null;
  slug?: string | null;
}): void {
  ensureHydrated();
  const next = store.entries.filter((entry) => !entryMatches(entry, identity));
  if (next.length === store.entries.length) {
    return;
  }
  store.entries = next;
  writeEntries(next);
  emit();
}

/** Toggle by slug and/or productId. Returns true when saved after toggle. */
export function toggleWishlistLocal(input: { productId?: string | null; slug: string }): boolean {
  const identity = { productId: input.productId, slug: input.slug };
  if (isWishlistedLocal(identity)) {
    removeWishlistLocal(identity);
    return false;
  }
  upsertWishlistLocal(input);
  return true;
}

export function clearWishlistLocal(): void {
  ensureHydrated();
  store.entries = [];
  writeEntries([]);
  emit();
}

export function replaceWishlistLocal(entries: WishlistEntry[]): void {
  ensureHydrated();
  store.entries = entries.filter(isEntry);
  writeEntries(store.entries);
  emit();
}
