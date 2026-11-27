"use client";

import { FilterBoxes, type FilterBoxesLabels } from "../filters/filter-boxes";

import type { SearchFilterState } from "./search-filters";

export type SearchCategoryOption = {
  path: string;
  label: string;
};

export type SearchFilterPanelLabels = FilterBoxesLabels & {
  /** "{label} ({count})" — kept for callers that still pass it. */
  facetCount?: string;
};

type SearchFilterPanelProps = {
  labels: SearchFilterPanelLabels;
  categories: SearchCategoryOption[];
  /** Kept for API compatibility; the URL is now the single source of truth. */
  initialState?: SearchFilterState;
  categoryCounts?: Record<string, number>;
  className?: string;
  onApplied?: () => void;
  /** Hide price boxes for non-commerce tabs (services/events). */
  showPriceFilters?: boolean;
};

/** Search filter boxes: chip/card groups, applied instantly and URL-synced. */
export function SearchFilterPanel({
  labels,
  categories,
  categoryCounts = {},
  className,
  onApplied,
  showPriceFilters = true,
}: SearchFilterPanelProps) {
  return (
    <aside
      className={["flex flex-col gap-3 lg:sticky lg:top-20 lg:self-start", className]
        .filter(Boolean)
        .join(" ")}
      aria-label={labels.heading}
      data-testid="search-filter-panel"
    >
      <h2 className="m-0 text-[var(--fs-h3)] font-semibold text-[var(--text)]">{labels.heading}</h2>
      <FilterBoxes
        mode="search"
        labels={labels}
        categories={categories.map((c) => ({
          path: c.path,
          label: c.label,
          count: categoryCounts[c.path],
        }))}
        showPrice={showPriceFilters}
        keepParams={["q", "kind"]}
        onNavigated={onApplied}
      />
    </aside>
  );
}
