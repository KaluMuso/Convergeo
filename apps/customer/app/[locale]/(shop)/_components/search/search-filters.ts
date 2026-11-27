export type SearchFilterState = {
  minPrice?: string;
  maxPrice?: string;
  categoryPath?: string;
  /** Signal filter boxes (docs/plan/product-signals.md); all URL-synced booleans. */
  verified?: boolean;
  deals?: boolean;
  inStock?: boolean;
  madeInZambia?: boolean;
  minRating?: string;
  /** Near-me radius in km; needs `lat`/`lng` in the URL (the page forwards them). */
  radiusKm?: string;
};

export type SignalFilterKey =
  "verified" | "deals" | "inStock" | "madeInZambia" | "minRating" | "radiusKm";

/** state key -> URL param (also the API param for search). */
export const SIGNAL_FILTER_PARAMS: Record<SignalFilterKey, string> = {
  verified: "verified",
  deals: "deals",
  inStock: "in_stock",
  madeInZambia: "made_in_zambia",
  minRating: "min_rating",
  radiusKm: "radius_km",
};

export type SearchFilterChip =
  | { id: string; kind: "signal"; key: SignalFilterKey; value: string }
  | { id: string; kind: "price"; min?: string; max?: string }
  | { id: string; kind: "category"; path: string; label: string };

export function hasActiveSearchFilters(state: SearchFilterState): boolean {
  return buildSearchFilterChips(state).length > 0;
}

export function buildSearchFilterChips(
  state: SearchFilterState,
  categoryLabels: Record<string, string> = {},
): SearchFilterChip[] {
  const chips: SearchFilterChip[] = [];

  if (state.minPrice || state.maxPrice) {
    chips.push({
      id: "price",
      kind: "price",
      min: state.minPrice,
      max: state.maxPrice,
    });
  }

  for (const key of Object.keys(SIGNAL_FILTER_PARAMS) as SignalFilterKey[]) {
    const value = state[key];
    if (value) {
      chips.push({ id: `signal:${key}`, kind: "signal", key, value: String(value) });
    }
  }

  if (state.categoryPath) {
    chips.push({
      id: `category:${state.categoryPath}`,
      kind: "category",
      path: state.categoryPath,
      label: categoryLabels[state.categoryPath] ?? formatCategoryPathLabel(state.categoryPath),
    });
  }

  return chips;
}

export function formatCategoryPathLabel(path: string): string {
  const leaf = path.split("/").filter(Boolean).at(-1);
  if (!leaf) {
    return path;
  }
  return leaf
    .split("-")
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

export function decodeSearchFilters(params: URLSearchParams): SearchFilterState {
  return {
    minPrice: params.get("min_price") ?? undefined,
    maxPrice: params.get("max_price") ?? undefined,
    categoryPath: params.get("category_path") ?? undefined,
    verified: flag(params, "verified"),
    deals: flag(params, "deals"),
    inStock: flag(params, "in_stock"),
    madeInZambia: flag(params, "made_in_zambia"),
    minRating: params.get("min_rating") ?? undefined,
    radiusKm: params.get("radius_km") ?? undefined,
  };
}

function flag(params: URLSearchParams, key: string): boolean | undefined {
  return params.get(key) === "1" ? true : undefined;
}

function encodeSignalFilters(state: SearchFilterState, params: URLSearchParams): void {
  for (const key of Object.keys(SIGNAL_FILTER_PARAMS) as SignalFilterKey[]) {
    const value = state[key];
    if (value === true) {
      params.set(SIGNAL_FILTER_PARAMS[key], "1");
    } else if (typeof value === "string" && value) {
      params.set(SIGNAL_FILTER_PARAMS[key], value);
    }
  }
}

export function encodeSearchFilters(state: SearchFilterState): URLSearchParams {
  const params = new URLSearchParams();
  if (state.minPrice) {
    params.set("min_price", state.minPrice);
  }
  if (state.maxPrice) {
    params.set("max_price", state.maxPrice);
  }
  if (state.categoryPath) {
    params.set("category_path", state.categoryPath);
  }
  encodeSignalFilters(state, params);
  return params;
}

/** Kwacha major units (UI / URL) → ngwee string for API query params. */
export function kwachaMajorToNgweeString(kwacha: string): string | undefined {
  const major = Number(kwacha);
  if (!Number.isFinite(major)) {
    return undefined;
  }
  return String(Math.round(major * 100));
}

/** Append product filters to `/search` API query params (ngwee + category_path). */
export function appendSearchFiltersToApiParams(
  params: URLSearchParams,
  state: SearchFilterState,
): void {
  if (state.minPrice) {
    const ngwee = kwachaMajorToNgweeString(state.minPrice);
    if (ngwee !== undefined) {
      params.set("price_min_ngwee", ngwee);
    }
  }
  if (state.maxPrice) {
    const ngwee = kwachaMajorToNgweeString(state.maxPrice);
    if (ngwee !== undefined) {
      params.set("price_max_ngwee", ngwee);
    }
  }
  if (state.categoryPath) {
    params.set("category_path", state.categoryPath);
  }
  encodeSignalFilters(state, params);
}

export function hrefWithoutSearchFilterChip(
  pathname: string,
  searchParams: URLSearchParams,
  chip: SearchFilterChip,
): string {
  const next = new URLSearchParams(searchParams.toString());
  next.delete("page");

  switch (chip.kind) {
    case "signal":
      next.delete(SIGNAL_FILTER_PARAMS[chip.key]);
      if (chip.key === "radiusKm") {
        next.delete("lat");
        next.delete("lng");
      }
      break;
    case "price":
      next.delete("min_price");
      next.delete("max_price");
      break;
    case "category":
      next.delete("category_path");
      break;
  }

  const query = next.toString();
  return query ? `${pathname}?${query}` : pathname;
}

export function clearSearchFiltersHref(pathname: string, searchParams: URLSearchParams): string {
  const next = new URLSearchParams();
  const preserved = ["q", "kind"] as const;
  for (const key of preserved) {
    const value = searchParams.get(key);
    if (value) {
      next.set(key, value);
    }
  }
  const query = next.toString();
  return query ? `${pathname}?${query}` : pathname;
}
