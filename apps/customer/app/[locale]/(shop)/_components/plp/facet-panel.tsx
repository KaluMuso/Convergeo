"use client";

import dynamic from "next/dynamic";

import type { PlpFilterState } from "./plp-filters";
import type { FilterBoxesLabels, FilterCounts } from "../filters/filter-boxes";
import type { PriceBandId } from "../filters/filter-hrefs";

/** Kept off the route's first-load JS (150 kB budget); server-rendered, hydrated on demand. */
const FilterBoxes = dynamic(() => import("../filters/filter-boxes").then((mod) => mod.FilterBoxes));

export type { PlpFilterState } from "./plp-filters";
export { decodePlpFilters, encodePlpFilters } from "./plp-filters";

type Bucket = { value: string; count: number };

export type FacetCounts = {
  condition: Bucket[];
  availability: Bucket[];
  rating: Bucket[];
  price?: Bucket[];
  /** `verified` / `deals` / `made_in_zambia` counts from the catalog API. */
  signals?: Bucket[];
};

export type FacetPanelLabels = FilterBoxesLabels;

type FacetPanelProps = {
  labels: FacetPanelLabels;
  facets: FacetCounts;
  /** Kept for API compatibility; the URL is now the single source of truth. */
  initialState?: PlpFilterState;
  className?: string;
  /** Called after a navigation (e.g. close the mobile drawer). */
  onApplied?: () => void;
};

function count(buckets: Bucket[] | undefined, value: string): number | undefined {
  return buckets?.find((bucket) => bucket.value === value)?.count;
}

const BAND_FACETS: Record<PriceBandId, string> = {
  under500: "under_50k",
  "500to2000": "50k_200k",
  "2000to5000": "200k_500k",
  over5000: "over_500k",
};

export function facetsToFilterCounts(facets: FacetCounts): FilterCounts {
  const priceBands: Partial<Record<PriceBandId, number>> = {};
  for (const [id, facet] of Object.entries(BAND_FACETS) as Array<[PriceBandId, string]>) {
    const value = count(facets.price, facet);
    if (value !== undefined) priceBands[id] = value;
  }
  return {
    verified: count(facets.signals, "verified"),
    deals: count(facets.signals, "deals"),
    madeInZambia: count(facets.signals, "made_in_zambia"),
    inStock: count(facets.availability, "in_stock"),
    rating4: count(facets.rating, "4_plus"),
    rating3: count(facets.rating, "3_plus"),
    priceBands,
    condition: {
      new: count(facets.condition, "new"),
      refurbished: count(facets.condition, "refurbished"),
      used: count(facets.condition, "used"),
    },
  };
}

/** Category-page filter boxes: chip/card groups, applied instantly and URL-synced. */
export function FacetPanel({ labels, facets, className, onApplied }: FacetPanelProps) {
  const madeInZambia = (count(facets.signals, "made_in_zambia") ?? 0) > 0;
  return (
    <aside
      className={["flex flex-col gap-3 lg:sticky lg:top-20 lg:self-start", className]
        .filter(Boolean)
        .join(" ")}
      aria-label={labels.heading}
      data-testid="plp-facet-panel"
    >
      <h2 className="m-0 text-[var(--fs-h3)] font-semibold text-[var(--text)]">{labels.heading}</h2>
      <FilterBoxes
        mode="catalog"
        labels={labels}
        counts={facetsToFilterCounts(facets)}
        showMadeInZambia={madeInZambia}
        keepParams={["sort"]}
        onNavigated={onApplied}
      />
    </aside>
  );
}
