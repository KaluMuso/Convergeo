/**
 * Local recently-viewed product history for the PDP rail.
 * Cap kept small for 3G / localStorage frugality.
 */

export const RECENTLY_VIEWED_STORAGE_KEY = "vergeo5:recently-viewed:v1";
export const RECENTLY_VIEWED_MAX = 8;

export type RecentlyViewedItem = {
  slug: string;
  name: string;
  imagePublicId: string | null;
  fromPriceNgwee: number | null;
  viewedAt: string;
};

function canUseStorage(): boolean {
  return typeof window !== "undefined" && typeof window.localStorage !== "undefined";
}

export function readRecentlyViewed(): RecentlyViewedItem[] {
  if (!canUseStorage()) {
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
    return parsed
      .filter((item): item is RecentlyViewedItem => {
        if (!item || typeof item !== "object") {
          return false;
        }
        const row = item as Record<string, unknown>;
        return (
          typeof row.slug === "string" &&
          row.slug.length > 0 &&
          typeof row.name === "string" &&
          (row.imagePublicId === null || typeof row.imagePublicId === "string") &&
          (row.fromPriceNgwee === null || typeof row.fromPriceNgwee === "number") &&
          typeof row.viewedAt === "string"
        );
      })
      .slice(0, RECENTLY_VIEWED_MAX);
  } catch {
    return [];
  }
}

export function writeRecentlyViewed(items: RecentlyViewedItem[]): void {
  if (!canUseStorage()) {
    return;
  }
  window.localStorage.setItem(
    RECENTLY_VIEWED_STORAGE_KEY,
    JSON.stringify(items.slice(0, RECENTLY_VIEWED_MAX)),
  );
}

/** Upsert current product to the front of the rail history. */
export function recordRecentlyViewed(
  item: Omit<RecentlyViewedItem, "viewedAt"> & { viewedAt?: string },
): RecentlyViewedItem[] {
  const next: RecentlyViewedItem = {
    slug: item.slug,
    name: item.name,
    imagePublicId: item.imagePublicId,
    fromPriceNgwee: item.fromPriceNgwee,
    viewedAt: item.viewedAt ?? new Date().toISOString(),
  };
  const rest = readRecentlyViewed().filter((entry) => entry.slug !== next.slug);
  const items = [next, ...rest].slice(0, RECENTLY_VIEWED_MAX);
  writeRecentlyViewed(items);
  return items;
}

/** Items to show on a PDP — never include the product currently being viewed. */
export function recentlyViewedExcluding(currentSlug: string): RecentlyViewedItem[] {
  return readRecentlyViewed().filter((item) => item.slug !== currentSlug);
}
