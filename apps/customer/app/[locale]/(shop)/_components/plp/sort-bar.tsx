"use client";

import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useTransition } from "react";

/**
 * URL `sort` values. Legacy values stay valid (relevance/cheapest/nearest/newest);
 * `verified`, `bundle` and `best` come from the catalog API sort extension
 * (feat/home-feed-and-ads). "Best match" is the default and omits the param.
 */
export type CatalogSort =
  | "relevance"
  | "best"
  | "cheapest"
  | "price_asc"
  | "nearest"
  | "newest"
  | "verified"
  | "bundle";

type SortBarLabels = {
  label: string;
  relevance: string;
  cheapest: string;
  nearest: string;
  newest: string;
  best?: string;
  verified?: string;
  bundles?: string;
  cheapestChip?: string;
};

type SortBarProps = {
  labels: SortBarLabels;
  value: CatalogSort;
  hasLocation: boolean;
};

type Chip = { value: CatalogSort | null; label: string; disabled?: boolean };

/**
 * Quick sort chips (AliExpress/Shopee pattern): one horizontal, scrollable row
 * — Best match · Nearest · Cheapest · Verified · Bundles. One tap re-sorts.
 */
export function SortBar({ labels, value, hasLocation }: SortBarProps) {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const [isPending, startTransition] = useTransition();

  const chips: Chip[] = [
    { value: null, label: labels.best ?? labels.relevance },
    { value: "nearest", label: labels.nearest, disabled: !hasLocation },
    { value: "cheapest", label: labels.cheapestChip ?? labels.cheapest },
    ...(labels.verified
      ? [{ value: "verified" as const, label: labels.verified }]
      : []),
    ...(labels.bundles
      ? [{ value: "bundle" as const, label: labels.bundles }]
      : []),
    { value: "newest", label: labels.newest },
  ];

  const active: CatalogSort | null =
    value === "relevance" || value === "best"
      ? null
      : value === "price_asc"
        ? "cheapest"
        : value;

  const select = (next: CatalogSort | null) => {
    const params = new URLSearchParams(searchParams.toString());
    if (next === null) {
      params.delete("sort");
    } else {
      params.set("sort", next);
    }
    params.delete("cursor");
    const query = params.toString();
    startTransition(() => {
      router.push(query ? `${pathname}?${query}` : pathname, { scroll: false });
    });
  };

  return (
    <div
      role="group"
      aria-label={labels.label}
      aria-busy={isPending}
      data-testid="plp-sort-chips"
      className="-mx-1 flex min-w-0 items-center gap-1.5 overflow-x-auto px-1 py-0.5 [scrollbar-width:none]"
    >
      {chips.map((chip) => {
        const pressed = active === chip.value;
        return (
          <button
            key={chip.value ?? "best"}
            type="button"
            aria-pressed={pressed}
            disabled={chip.disabled || isPending}
            onClick={() => select(chip.value)}
            className={`inline-flex min-h-10 shrink-0 items-center rounded-pill border px-3.5 text-sm font-medium transition-colors focus-visible:outline-none focus-visible:shadow-focusRing disabled:cursor-not-allowed disabled:opacity-45 ${
              pressed
                ? "border-primary bg-primary text-[var(--primary-btn-fg)]"
                : "border-border bg-surface text-text-2 hover:border-primary hover:text-primary"
            }`}
          >
            {chip.label}
          </button>
        );
      })}
    </div>
  );
}
