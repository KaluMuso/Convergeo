import Link from "next/link";

import {
  buildAppliedFilterChips,
  type AppliedFilterChip,
  type PlpFilterState,
} from "./plp-filters";

export type AppliedFilterBarLabels = {
  ariaLabel: string;
  clearAll: string;
  removeChip: string;
  priceRange: string;
  minPriceOnly: string;
  maxPriceOnly: string;
  conditionNew: string;
  conditionRefurbished: string;
  inStock: string;
  outOfStock: string;
  rating4Plus: string;
  rating3Plus: string;
  nearMe: string;
  radiusKm: string;
};

type AppliedFilterBarProps = {
  pathname: string;
  /** Current URL search params (including sort). */
  searchParams: URLSearchParams;
  filterState: PlpFilterState;
  labels: AppliedFilterBarLabels;
};

function chipLabel(chip: AppliedFilterChip, labels: AppliedFilterBarLabels): string {
  switch (chip.kind) {
    case "price":
      if (chip.min && chip.max) {
        return labels.priceRange.replace("{min}", chip.min).replace("{max}", chip.max);
      }
      if (chip.min) {
        return labels.minPriceOnly.replace("{min}", chip.min);
      }
      return labels.maxPriceOnly.replace("{max}", chip.max ?? "");
    case "condition":
      return chip.value === "refurbished" ? labels.conditionRefurbished : labels.conditionNew;
    case "availability":
      return chip.value === "out_of_stock" ? labels.outOfStock : labels.inStock;
    case "rating":
      return chip.value === "3" ? labels.rating3Plus : labels.rating4Plus;
    case "location":
      return chip.radiusKm ? labels.radiusKm.replace("{km}", chip.radiusKm) : labels.nearMe;
    default:
      return "";
  }
}

function hrefWithoutChip(
  pathname: string,
  searchParams: URLSearchParams,
  chip: AppliedFilterChip,
): string {
  const next = new URLSearchParams(searchParams.toString());
  next.delete("cursor");

  switch (chip.kind) {
    case "price":
      next.delete("min_price");
      next.delete("max_price");
      break;
    case "condition": {
      const values = (next.get("condition") ?? "")
        .split(",")
        .map((part) => part.trim())
        .filter((part) => part && part !== chip.value);
      if (values.length > 0) {
        next.set("condition", values.join(","));
      } else {
        next.delete("condition");
      }
      break;
    }
    case "availability": {
      const values = (next.get("availability") ?? "")
        .split(",")
        .map((part) => part.trim())
        .filter((part) => part && part !== chip.value);
      if (values.length > 0) {
        next.set("availability", values.join(","));
      } else {
        next.delete("availability");
      }
      break;
    }
    case "rating":
      next.delete("min_rating");
      break;
    case "location":
      next.delete("lat");
      next.delete("lng");
      next.delete("radius_km");
      break;
  }

  const query = next.toString();
  return query ? `${pathname}?${query}` : pathname;
}

function clearAllHref(pathname: string, searchParams: URLSearchParams): string {
  const sort = searchParams.get("sort");
  if (!sort) {
    return pathname;
  }
  return `${pathname}?sort=${encodeURIComponent(sort)}`;
}

/**
 * Compact applied-filter chip row for the PLP (audit §4.3).
 * Server Component — each chip is a real link that removes one filter.
 */
export function AppliedFilterBar({
  pathname,
  searchParams,
  filterState,
  labels,
}: AppliedFilterBarProps) {
  const chips = buildAppliedFilterChips(filterState);
  if (chips.length === 0) {
    return null;
  }

  return (
    <div
      data-testid="plp-applied-filters"
      className="motion-fade flex flex-col gap-2 rounded border border-border bg-bg-2/60 px-3 py-2"
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="m-0 text-micro font-semibold uppercase tracking-wide text-text-3">
          {labels.ariaLabel}
        </p>
        <Link
          href={clearAllHref(pathname, searchParams)}
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
                href={hrefWithoutChip(pathname, searchParams, chip)}
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
