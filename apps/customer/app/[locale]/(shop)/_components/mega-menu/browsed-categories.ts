/**
 * Client-side "Categories for you": the last few categories the shopper opened
 * from the menu. localStorage only (never sent anywhere); every access is
 * guarded because storage can be unavailable (private mode, blocked cookies).
 */
export const BROWSED_CATEGORIES_KEY = "vergeo5:browsed-categories:v1";
export const BROWSED_CATEGORIES_MAX = 8;

export type BrowsedCategory = {
  slug: string;
  label: string;
  href: string;
};

function isBrowsed(value: unknown): value is BrowsedCategory {
  if (typeof value !== "object" || value === null) {
    return false;
  }
  const record = value as Record<string, unknown>;
  return (
    typeof record.slug === "string" &&
    record.slug.length > 0 &&
    typeof record.label === "string" &&
    typeof record.href === "string" &&
    record.href.startsWith("/")
  );
}

export function readBrowsedCategories(): BrowsedCategory[] {
  try {
    const raw = window.localStorage.getItem(BROWSED_CATEGORIES_KEY);
    if (!raw) {
      return [];
    }
    const parsed: unknown = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed.filter(isBrowsed).slice(0, BROWSED_CATEGORIES_MAX) : [];
  } catch {
    return [];
  }
}

export function recordBrowsedCategory(entry: BrowsedCategory): void {
  try {
    const rest = readBrowsedCategories().filter((item) => item.href !== entry.href);
    const next = [entry, ...rest].slice(0, BROWSED_CATEGORIES_MAX);
    window.localStorage.setItem(BROWSED_CATEGORIES_KEY, JSON.stringify(next));
  } catch {
    // Storage unavailable — the menu simply omits "Categories for you".
  }
}
