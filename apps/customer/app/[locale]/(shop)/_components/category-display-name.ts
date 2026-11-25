export function slugToCategoryLabel(slug: string): string {
  return slug
    .split(/[-/]+/)
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

export function resolveFacetCategoryLabel(slug: string, known: Record<string, string>): string {
  return known[slug] ?? slugToCategoryLabel(slug);
}
