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
