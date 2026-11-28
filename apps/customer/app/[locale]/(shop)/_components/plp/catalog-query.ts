import { kwachaMajorToNgweeString } from "../search/search-filters";

/** Build `/catalog/listings` query; price URL params are kwacha, API expects ngwee. */
export function buildCatalogQuery(
  categoryPath: string | undefined,
  searchParams: Record<string, string | string[] | undefined>,
): string {
  const params = new URLSearchParams();
  if (categoryPath) {
    params.set("category_path", categoryPath);
  }
  for (const [key, value] of Object.entries(searchParams)) {
    if (value === undefined || key === "slug") {
      continue;
    }
    const raw = Array.isArray(value) ? value[0] : value;
    if (!raw) {
      continue;
    }
    if (key === "min_price" || key === "max_price") {
      const ngwee = kwachaMajorToNgweeString(raw);
      if (ngwee !== undefined) {
        params.set(key, ngwee);
      }
      continue;
    }
    params.set(key, raw);
  }
  return params.toString();
}

/**
 * The user-facing URL params (price stays in kwacha, no injected `category_path`).
 * Filter UI state and chip/sort hrefs must derive from this, never from the
 * ngwee-converted API query, or every re-render multiplies prices by 100.
 */
export function buildDisplaySearchParams(
  searchParams: Record<string, string | string[] | undefined>,
): URLSearchParams {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(searchParams)) {
    if (value === undefined || key === "slug") {
      continue;
    }
    const raw = Array.isArray(value) ? value[0] : value;
    if (raw) {
      params.set(key, raw);
    }
  }
  return params;
}
