import Link from "next/link";

import {
  buildSearchFilterChips,
  clearSearchFiltersHref,
  hrefWithoutSearchFilterChip,
  type SearchFilterChip,
  type SearchFilterState,
} from "./search-filters";

export type SearchAppliedFilterBarLabels = {
  ariaLabel: string;
  clearAll: string;
  removeChip: string;
  priceRange: string;
  minPriceOnly: string;
  maxPriceOnly: string;
};

type SearchAppliedFilterBarProps = {
  pathname: string;
  searchParams: URLSearchParams;
  filterState: SearchFilterState;
  categoryLabels: Record<string, string>;
  labels: SearchAppliedFilterBarLabels;
};

function chipLabel(chip: SearchFilterChip, labels: SearchAppliedFilterBarLabels): string {
  switch (chip.kind) {
    case "price":
      if (chip.min && chip.max) {
        return labels.priceRange.replace("{min}", chip.min).replace("{max}", chip.max);
      }
      if (chip.min) {
        return labels.minPriceOnly.replace("{min}", chip.min);
      }
      return labels.maxPriceOnly.replace("{max}", chip.max ?? "");
    case "category":
      return chip.label;
    default:
      return "";
  }
}

export function SearchAppliedFilterBar({
  pathname,
  searchParams,
  filterState,
  categoryLabels,
  labels,
}: SearchAppliedFilterBarProps) {
  const chips = buildSearchFilterChips(filterState, categoryLabels);
  if (chips.length === 0) {
    return null;
  }

  return (
    <div
      data-testid="search-applied-filters"
      className="motion-fade flex flex-col gap-2 rounded border border-border bg-bg-2/60 px-3 py-2"
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="m-0 text-micro font-semibold uppercase tracking-wide text-text-3">
          {labels.ariaLabel}
        </p>
        <Link
          href={clearSearchFiltersHref(pathname, searchParams)}
          className="inline-flex min-h-11 items-center text-sm font-medium text-primary hover:underline focus-visible:outline-none focus-visible:shadow-focusRing"
        >
          {labels.clearAll}
        </Link>
      </div>
      <ul className="m-0 flex list-none flex-wrap gap-2 p-0" aria-label={labels.ariaLabel}>
        {chips.map((chip) => {
          const label = chipLabel(chip, labels);
          const removeLabel = labels.removeChip.replace("{filter}", label);
          return (
            <li key={chip.id}>
              <Link
                href={hrefWithoutSearchFilterChip(pathname, searchParams, chip)}
                aria-label={removeLabel}
                className="inline-flex min-h-11 items-center gap-1.5 rounded border border-border bg-surface px-3 text-sm text-text-2 transition-colors hover:border-primary hover:text-primary focus-visible:outline-none focus-visible:shadow-focusRing"
              >
                <span>{label}</span>
                <svg
                  aria-hidden
                  viewBox="0 0 12 12"
                  className="h-3 w-3 shrink-0 text-text-3"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="1.75"
                >
                  <path d="M3 3l6 6M9 3L3 9" />
                </svg>
              </Link>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
