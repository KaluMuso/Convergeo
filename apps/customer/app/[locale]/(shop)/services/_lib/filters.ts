/**
 * Services listing filters, URL-synced (`category`, `area`, `band`, `rating`, `avail`).
 * Price bands are integer ngwee ranges sent to the API as `price_min` / `price_max`.
 */
import { SERVICE_VERTICALS } from "../_components/service-verticals";

export const PRICE_BANDS = {
  under100: { min: null, max: 9_999 },
  mid: { min: 10_000, max: 50_000 },
  high: { min: 50_001, max: 200_000 },
  premium: { min: 200_001, max: null },
} as const;

export type PriceBand = keyof typeof PRICE_BANDS;
export const PRICE_BAND_KEYS = Object.keys(PRICE_BANDS) as PriceBand[];
export const RATING_OPTIONS = ["45", "4", "3"] as const;
export type RatingOption = (typeof RATING_OPTIONS)[number];

export type ServiceFilters = {
  category: string | null;
  area: string;
  band: PriceBand | null;
  rating: RatingOption | null;
  avail: boolean;
};

export type RawSearchParams = {
  category?: string;
  area?: string;
  band?: string;
  rating?: string;
  avail?: string;
  page?: string;
};

export const NO_FILTERS: ServiceFilters = {
  category: null,
  area: "",
  band: null,
  rating: null,
  avail: false,
};

export function parseFilters(raw: RawSearchParams): ServiceFilters {
  return {
    category: (SERVICE_VERTICALS as readonly string[]).includes(raw.category ?? "")
      ? (raw.category as string)
      : null,
    area: (raw.area ?? "").trim().slice(0, 120),
    band: PRICE_BAND_KEYS.includes(raw.band as PriceBand) ? (raw.band as PriceBand) : null,
    rating: (RATING_OPTIONS as readonly string[]).includes(raw.rating ?? "")
      ? (raw.rating as RatingOption)
      : null,
    avail: raw.avail === "1",
  };
}

export function ratingValue(option: RatingOption): number {
  return option === "45" ? 4.5 : Number(option);
}

/** Query string for the API (`/services?...`). */
export function toApiQuery(filters: ServiceFilters): string {
  const search = new URLSearchParams();
  if (filters.category) search.set("category", filters.category);
  if (filters.area) search.set("area", filters.area);
  if (filters.band) {
    const { min, max } = PRICE_BANDS[filters.band];
    if (min !== null) search.set("price_min", String(min));
    if (max !== null) search.set("price_max", String(max));
  }
  if (filters.rating) search.set("min_rating", String(ratingValue(filters.rating)));
  if (filters.avail) search.set("available", "true");
  return search.toString();
}

/** Query params for the public URL (what the page's own links and pager carry). */
export function toUrlParams(filters: ServiceFilters): Record<string, string | undefined> {
  return {
    category: filters.category ?? undefined,
    area: filters.area || undefined,
    band: filters.band ?? undefined,
    rating: filters.rating ?? undefined,
    avail: filters.avail ? "1" : undefined,
  };
}

export function hrefFor(locale: string, filters: ServiceFilters): string {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(toUrlParams(filters))) {
    if (value) params.set(key, value);
  }
  const query = params.toString();
  return `/${locale}/services${query ? `?${query}` : ""}`;
}

/** Toggling a value: selecting the active one clears it. */
export function withPatch(filters: ServiceFilters, patch: Partial<ServiceFilters>): ServiceFilters {
  return { ...filters, ...patch };
}

export function activeCount(filters: ServiceFilters): number {
  return (
    Number(filters.category !== null) +
    Number(filters.area !== "") +
    Number(filters.band !== null) +
    Number(filters.rating !== null) +
    Number(filters.avail)
  );
}

/** Distinct, trimmed service areas present in results (first segment), most common first. */
export function areaOptions(areas: (string | null)[], limit = 8): string[] {
  const counts = new Map<string, number>();
  for (const area of areas) {
    const name = area?.split(",")[0]?.trim();
    if (name) counts.set(name, (counts.get(name) ?? 0) + 1);
  }
  return [...counts.entries()]
    .sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))
    .slice(0, limit)
    .map(([name]) => name);
}
