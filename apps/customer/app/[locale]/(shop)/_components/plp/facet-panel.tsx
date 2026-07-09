"use client";

import { Button } from "@vergeo/ui/src/button";
import { Checkbox } from "@vergeo/ui/src/checkbox";
import { Input } from "@vergeo/ui/src/input";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useCallback, useMemo, useState, useTransition } from "react";

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

export type FacetCounts = {
  condition: { value: string; count: number }[];
  availability: { value: string; count: number }[];
  rating: { value: string; count: number }[];
};

type FacetPanelLabels = {
  heading: string;
  price: string;
  minPrice: string;
  maxPrice: string;
  condition: string;
  conditionNew: string;
  conditionRefurbished: string;
  availability: string;
  inStock: string;
  outOfStock: string;
  rating: string;
  rating4Plus: string;
  rating3Plus: string;
  location: string;
  radiusKm: string;
  apply: string;
  clear: string;
};

type FacetPanelProps = {
  labels: FacetPanelLabels;
  facets: FacetCounts;
  initialState: PlpFilterState;
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

function facetCount(buckets: { value: string; count: number }[], value: string): number {
  return buckets.find((bucket) => bucket.value === value)?.count ?? 0;
}

export function FacetPanel({ labels, facets, initialState }: FacetPanelProps) {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const [isPending, startTransition] = useTransition();
  const [state, setState] = useState<PlpFilterState>(initialState);

  const sortParam = searchParams.get("sort");
  const cursorParam = searchParams.get("cursor");

  const pushFilters = useCallback(
    (next: PlpFilterState) => {
      const params = encodePlpFilters(next);
      if (sortParam) {
        params.set("sort", sortParam);
      }
      const query = params.toString();
      startTransition(() => {
        router.push(query ? `${pathname}?${query}` : pathname, { scroll: false });
      });
    },
    [pathname, router, sortParam, startTransition],
  );

  const toggleValue = useCallback((key: "condition" | "availability", value: string) => {
    setState((current) => {
      const selected = new Set(current[key]);
      if (selected.has(value)) {
        selected.delete(value);
      } else {
        selected.add(value);
      }
      return { ...current, [key]: [...selected] };
    });
  }, []);

  const radiusLabel = useMemo(() => {
    const km = state.radiusKm ?? "10";
    return labels.radiusKm.replace("{km}", km);
  }, [labels.radiusKm, state.radiusKm]);

  return (
    <aside
      className="flex flex-col gap-4 rounded-[var(--r-lg)] border border-[var(--border)] bg-[var(--surface)] p-4"
      aria-label={labels.heading}
    >
      <h2 className="text-[var(--fs-h3)] font-semibold text-[var(--text)]">{labels.heading}</h2>

      <fieldset className="flex flex-col gap-2 border-0 p-0">
        <legend className="mb-1 text-sm font-medium text-[var(--text)]">{labels.price}</legend>
        <div className="grid grid-cols-2 gap-2">
          <Input
            type="number"
            inputMode="numeric"
            min={0}
            placeholder={labels.minPrice}
            value={state.minPrice ?? ""}
            onChange={(event) =>
              setState((current) => ({ ...current, minPrice: event.target.value || undefined }))
            }
            aria-label={labels.minPrice}
          />
          <Input
            type="number"
            inputMode="numeric"
            min={0}
            placeholder={labels.maxPrice}
            value={state.maxPrice ?? ""}
            onChange={(event) =>
              setState((current) => ({ ...current, maxPrice: event.target.value || undefined }))
            }
            aria-label={labels.maxPrice}
          />
        </div>
      </fieldset>

      <fieldset className="flex flex-col gap-2 border-0 p-0">
        <legend className="mb-1 text-sm font-medium text-[var(--text)]">{labels.condition}</legend>
        <Checkbox
          checked={state.condition.includes("new")}
          onChange={() => toggleValue("condition", "new")}
          label={`${labels.conditionNew} (${facetCount(facets.condition, "new")})`}
        />
        <Checkbox
          checked={state.condition.includes("refurbished")}
          onChange={() => toggleValue("condition", "refurbished")}
          label={`${labels.conditionRefurbished} (${facetCount(facets.condition, "refurbished")})`}
        />
      </fieldset>

      <fieldset className="flex flex-col gap-2 border-0 p-0">
        <legend className="mb-1 text-sm font-medium text-[var(--text)]">
          {labels.availability}
        </legend>
        <Checkbox
          checked={state.availability.includes("in_stock")}
          onChange={() => toggleValue("availability", "in_stock")}
          label={`${labels.inStock} (${facetCount(facets.availability, "in_stock")})`}
        />
        <Checkbox
          checked={state.availability.includes("out_of_stock")}
          onChange={() => toggleValue("availability", "out_of_stock")}
          label={`${labels.outOfStock} (${facetCount(facets.availability, "out_of_stock")})`}
        />
      </fieldset>

      <fieldset className="flex flex-col gap-2 border-0 p-0">
        <legend className="mb-1 text-sm font-medium text-[var(--text)]">{labels.rating}</legend>
        <Checkbox
          checked={state.minRating === "4"}
          onChange={() =>
            setState((current) => ({
              ...current,
              minRating: current.minRating === "4" ? undefined : "4",
            }))
          }
          label={`${labels.rating4Plus} (${facetCount(facets.rating, "4_plus")})`}
        />
        <Checkbox
          checked={state.minRating === "3"}
          onChange={() =>
            setState((current) => ({
              ...current,
              minRating: current.minRating === "3" ? undefined : "3",
            }))
          }
          label={`${labels.rating3Plus} (${facetCount(facets.rating, "3_plus")})`}
        />
      </fieldset>

      <fieldset className="flex flex-col gap-2 border-0 p-0">
        <legend className="mb-1 text-sm font-medium text-[var(--text)]">{labels.location}</legend>
        <Input
          type="number"
          inputMode="decimal"
          min={1}
          max={500}
          placeholder={radiusLabel}
          value={state.radiusKm ?? ""}
          onChange={(event) =>
            setState((current) => ({ ...current, radiusKm: event.target.value || undefined }))
          }
          aria-label={radiusLabel}
        />
      </fieldset>

      <div className="flex flex-col gap-2">
        <Button
          type="button"
          disabled={isPending}
          loading={isPending}
          loadingLabel={labels.apply}
          onClick={() => {
            if (state.radiusKm && (!state.lat || !state.lng) && navigator.geolocation) {
              navigator.geolocation.getCurrentPosition(
                (position) => {
                  const withLocation: PlpFilterState = {
                    ...state,
                    lat: String(position.coords.latitude),
                    lng: String(position.coords.longitude),
                  };
                  setState(withLocation);
                  pushFilters(withLocation);
                },
                () => pushFilters(state),
              );
              return;
            }
            pushFilters(state);
          }}
        >
          {labels.apply}
        </Button>
        <Button
          type="button"
          variant="secondary"
          disabled={isPending}
          loading={isPending}
          loadingLabel={labels.clear}
          onClick={() => {
            const cleared: PlpFilterState = {
              condition: [],
              availability: [],
            };
            setState(cleared);
            const params = new URLSearchParams();
            if (sortParam) {
              params.set("sort", sortParam);
            }
            if (cursorParam) {
              params.set("cursor", cursorParam);
            }
            const query = params.toString();
            startTransition(() => {
              router.push(query ? `${pathname}?${query}` : pathname, { scroll: false });
            });
          }}
        >
          {labels.clear}
        </Button>
      </div>
    </aside>
  );
}
