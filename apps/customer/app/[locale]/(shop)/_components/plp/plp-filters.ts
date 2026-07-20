export type PlpFilterState = {
  minPrice?: string;
  maxPrice?: string;
  condition: string[];
  availability: string[];
  minRating?: string;
  radiusKm?: string;
  lat?: string;
  lng?: string;
};

export type AppliedFilterChip =
  | { id: string; kind: "price"; min?: string; max?: string }
  | { id: string; kind: "condition"; value: string }
  | { id: string; kind: "availability"; value: string }
  | { id: string; kind: "rating"; value: string }
  | { id: string; kind: "location"; radiusKm?: string };

export function hasActivePlpFilters(state: PlpFilterState): boolean {
  return buildAppliedFilterChips(state).length > 0;
}

/** Stable chip list for the applied-filter summary bar. */
export function buildAppliedFilterChips(state: PlpFilterState): AppliedFilterChip[] {
  const chips: AppliedFilterChip[] = [];

  if (state.minPrice || state.maxPrice) {
    chips.push({
      id: "price",
      kind: "price",
      min: state.minPrice,
      max: state.maxPrice,
    });
  }

  for (const value of state.condition) {
    chips.push({ id: `condition:${value}`, kind: "condition", value });
  }

  for (const value of state.availability) {
    chips.push({ id: `availability:${value}`, kind: "availability", value });
  }

  if (state.minRating) {
    chips.push({ id: `rating:${state.minRating}`, kind: "rating", value: state.minRating });
  }

  if (state.lat && state.lng) {
    chips.push({
      id: "location",
      kind: "location",
      radiusKm: state.radiusKm,
    });
  }

  return chips;
}

export function encodePlpFilters(state: PlpFilterState): URLSearchParams {
  const params = new URLSearchParams();
  if (state.minPrice) {
    params.set("min_price", state.minPrice);
  }
  if (state.maxPrice) {
    params.set("max_price", state.maxPrice);
  }
  if (state.condition.length > 0) {
    params.set("condition", state.condition.join(","));
  }
  if (state.availability.length > 0) {
    params.set("availability", state.availability.join(","));
  }
  if (state.minRating) {
    params.set("min_rating", state.minRating);
  }
  if (state.lat) {
    params.set("lat", state.lat);
  }
  if (state.lng) {
    params.set("lng", state.lng);
  }
  if (state.radiusKm) {
    params.set("radius_km", state.radiusKm);
  }
  return params;
}

export function decodePlpFilters(params: URLSearchParams): PlpFilterState {
  const split = (key: string) =>
    params
      .get(key)
      ?.split(",")
      .map((part) => part.trim())
      .filter(Boolean) ?? [];

  return {
    minPrice: params.get("min_price") ?? undefined,
    maxPrice: params.get("max_price") ?? undefined,
    condition: split("condition"),
    availability: split("availability"),
    minRating: params.get("min_rating") ?? undefined,
    lat: params.get("lat") ?? undefined,
    lng: params.get("lng") ?? undefined,
    radiusKm: params.get("radius_km") ?? undefined,
  };
}
