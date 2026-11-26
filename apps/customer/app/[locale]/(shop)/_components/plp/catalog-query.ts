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
