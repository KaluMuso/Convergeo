/** Facet row from directory/search APIs (value slug + optional human label). */
export type CategoryFacet = {
  value: string;
  label?: string | null;
};

/** Title-case slug fallback until the category tree resolver lands (T50). */
export function slugToCategoryLabel(slug: string): string {
  return slug
    .split(/[-/]+/)
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

export function resolveFacetCategoryLabel(
  slug: string,
  knownLabels: Record<string, string>,
): string {
  return knownLabels[slug] ?? slugToCategoryLabel(slug);
}

/**
 * Resolve a category slug to a display label using API facet labels, then i18n
 * maps, then title-case fallback (item 13 — no hand-maintained slug lists).
 */
export function categoryDisplayName(
  slug: string,
  labels: Record<string, string> = {},
  facetLabel?: string | null,
): string {
  if (facetLabel && facetLabel.trim()) {
    return facetLabel.trim();
  }
  return resolveFacetCategoryLabel(slug, labels);
}

/** Build a lookup map from facet payloads (directory/search). */
export function categoryLabelMapFromFacets(
  facets: CategoryFacet[],
  labels: Record<string, string> = {},
): Record<string, string> {
  const map = { ...labels };
  for (const facet of facets) {
    map[facet.value] = categoryDisplayName(facet.value, labels, facet.label);
  }
  return map;
}
