import type { CategoryRow } from "../merch-data";

export type TopCategorySuggestion = { key: string; href: string; label: string };

/**
 * Top-level (root) categories for the zero-results "browse instead" links, sourced from
 * the same categories API as the category grid / mega menu so slugs and names are never
 * hard-coded. Returns `[]` (callers hide the block) when the API gave nothing usable.
 */
export function buildTopCategorySuggestions(
  categories: readonly CategoryRow[],
  locale: string,
  limit = 4,
): TopCategorySuggestion[] {
  return categories
    .filter((row) => row.parent_id === null && !row.prohibited && row.slug && row.name)
    .sort((left, right) => left.position - right.position)
    .slice(0, limit)
    .map((row) => ({
      key: row.slug,
      href: `/${locale}/c/${row.slug}`,
      label: row.name,
    }));
}
