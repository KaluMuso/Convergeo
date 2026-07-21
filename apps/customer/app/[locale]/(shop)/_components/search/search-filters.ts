export type SearchFilterState = {
  minPrice?: string;
  maxPrice?: string;
  categoryPath?: string;
};

export type SearchFilterChip =
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
  };
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
  return params;
}

/** Append product filters to `/search` API query params (ngwee + category_path). */
export function appendSearchFiltersToApiParams(
  params: URLSearchParams,
  state: SearchFilterState,
): void {
  if (state.minPrice) {
    params.set("price_min_ngwee", state.minPrice);
  }
  if (state.maxPrice) {
    params.set("price_max_ngwee", state.maxPrice);
  }
  if (state.categoryPath) {
    params.set("category_path", state.categoryPath);
  }
}

export function hrefWithoutSearchFilterChip(
  pathname: string,
  searchParams: URLSearchParams,
  chip: SearchFilterChip,
): string {
  const next = new URLSearchParams(searchParams.toString());
  next.delete("page");

  switch (chip.kind) {
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
