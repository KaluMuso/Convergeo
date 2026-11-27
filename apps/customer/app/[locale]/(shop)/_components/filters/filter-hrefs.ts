/** Pure URL helpers for the filter boxes (URL is the single source of truth). */

export type FilterMode = "catalog" | "search";

export type PriceBandId = "under500" | "500to2000" | "2000to5000" | "over5000";

/** Bands in kwacha major units (URL convention); API conversion happens server-side of the page. */
export const PRICE_BANDS: ReadonlyArray<{
  id: PriceBandId;
  min?: string;
  max?: string;
  /** Matching key of the catalog `facets.price` buckets (ngwee bands). */
  facet: string;
}> = [
  { id: "under500", max: "500", facet: "under_50k" },
  { id: "500to2000", min: "500", max: "2000", facet: "50k_200k" },
  { id: "2000to5000", min: "2000", max: "5000", facet: "200k_500k" },
  { id: "over5000", min: "5000", facet: "over_500k" },
];

/** Params that never survive a filter change (progressive loading restarts at page 1). */
const RESET_PARAMS = ["page", "cursor"] as const;

export const NEAR_ME_RADIUS_KM = "5";

export function hrefWith(
  pathname: string,
  current: URLSearchParams,
  updates: Record<string, string | null | undefined>,
): string {
  const next = new URLSearchParams(current.toString());
  for (const key of RESET_PARAMS) next.delete(key);
  for (const [key, value] of Object.entries(updates)) {
    if (value === null || value === undefined || value === "") {
      next.delete(key);
    } else {
      next.set(key, value);
    }
  }
  const query = next.toString();
  return query ? `${pathname}?${query}` : pathname;
}

/** Toggle a boolean-style param ("1" on, absent off). */
export function toggleFlagHref(
  pathname: string,
  current: URLSearchParams,
  key: string,
  extra: Record<string, string | null> = {},
): string {
  const on = current.get(key) === "1";
  return hrefWith(pathname, current, { [key]: on ? null : "1", ...extra });
}

export function activePriceBand(current: URLSearchParams): PriceBandId | null {
  const min = current.get("min_price") ?? undefined;
  const max = current.get("max_price") ?? undefined;
  const found = PRICE_BANDS.find((band) => band.min === min && band.max === max);
  return found?.id ?? null;
}

export function priceBandHref(
  pathname: string,
  current: URLSearchParams,
  bandId: PriceBandId,
): string {
  const band = PRICE_BANDS.find((b) => b.id === bandId)!;
  if (activePriceBand(current) === bandId) {
    return hrefWith(pathname, current, { min_price: null, max_price: null });
  }
  return hrefWith(pathname, current, { min_price: band.min ?? null, max_price: band.max ?? null });
}

/** In-stock param differs per endpoint: catalog `availability=in_stock`, search `in_stock=1`. */
export function inStockKey(mode: FilterMode): { key: string; on: (p: URLSearchParams) => boolean } {
  return mode === "catalog"
    ? {
        key: "availability",
        on: (p) =>
          (p.get("availability") ?? "")
            .split(",")
            .map((v) => v.trim())
            .includes("in_stock"),
      }
    : { key: "in_stock", on: (p) => p.get("in_stock") === "1" };
}

export function inStockHref(mode: FilterMode, pathname: string, current: URLSearchParams): string {
  const { key, on } = inStockKey(mode);
  const enabled = on(current);
  return hrefWith(pathname, current, {
    [key]: enabled ? null : mode === "catalog" ? "in_stock" : "1",
  });
}

export function ratingHref(pathname: string, current: URLSearchParams, stars: "3" | "4"): string {
  return hrefWith(pathname, current, {
    min_rating: current.get("min_rating") === stars ? null : stars,
  });
}

export function nearMeActive(current: URLSearchParams): boolean {
  return current.has("radius_km") && current.has("lat") && current.has("lng");
}

export function nearMeOffHref(pathname: string, current: URLSearchParams): string {
  return hrefWith(pathname, current, { radius_km: null, lat: null, lng: null });
}

export function nearMeOnHref(
  pathname: string,
  current: URLSearchParams,
  coords: { lat: number; lng: number },
): string {
  return hrefWith(pathname, current, {
    lat: String(coords.lat),
    lng: String(coords.lng),
    radius_km: NEAR_ME_RADIUS_KM,
  });
}

export function categoryHref(
  pathname: string,
  current: URLSearchParams,
  path: string | null,
): string {
  return hrefWith(pathname, current, { category_path: path });
}

export function clearFiltersHref(
  pathname: string,
  current: URLSearchParams,
  keep: readonly string[],
): string {
  const next = new URLSearchParams();
  for (const key of keep) {
    const value = current.get(key);
    if (value) next.set(key, value);
  }
  const query = next.toString();
  return query ? `${pathname}?${query}` : pathname;
}
