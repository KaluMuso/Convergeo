/**
 * Build customer deep-links for global-search hits.
 *
 * Search indexes entities by UUID (`entity_id`). PDP / vendor / event routes
 * resolve by public slug. Prefer the API-enriched `slug` field; never put a
 * raw product/listing UUID into `/p/{…}` (that soft-404s).
 */

export type SearchResultHrefHit = {
  entity_kind: string;
  entity_id: string;
  title: string;
  /** Public route slug when the search API could resolve one. */
  slug?: string | null;
};

export function searchResultHref(locale: string, hit: SearchResultHrefHit): string {
  const slug = hit.slug?.trim() || null;
  const searchFallback = `/${locale}/search?q=${encodeURIComponent(hit.title)}`;

  switch (hit.entity_kind) {
    case "product": {
      if (!slug) {
        return searchFallback;
      }
      return `/${locale}/p/${encodeURIComponent(slug)}`;
    }
    case "listing": {
      if (!slug) {
        return searchFallback;
      }
      const params = new URLSearchParams({ listing: hit.entity_id });
      return `/${locale}/p/${encodeURIComponent(slug)}?${params.toString()}`;
    }
    case "service": {
      // Services use the UUID as the public slug (`/s/{id}`).
      const serviceSlug = slug ?? hit.entity_id;
      return `/${locale}/s/${encodeURIComponent(serviceSlug)}`;
    }
    case "event": {
      if (!slug) {
        return searchFallback;
      }
      return `/${locale}/e/${encodeURIComponent(slug)}`;
    }
    case "vendor": {
      if (!slug) {
        return searchFallback;
      }
      return `/${locale}/v/${encodeURIComponent(slug)}`;
    }
    default:
      return searchFallback;
  }
}
