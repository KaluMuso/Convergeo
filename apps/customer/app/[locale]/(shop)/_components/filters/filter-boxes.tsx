"use client";

import { FilterBox, FilterChip } from "@vergeo/ui/src/filter-box";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useCallback, useState, useTransition } from "react";

import { readNearCoords, rememberNearCoords } from "../../../../../lib/near-coords";

import {
  PRICE_BANDS,
  activePriceBand,
  categoryHref,
  clearFiltersHref,
  hrefWith,
  inStockHref,
  inStockKey,
  nearMeActive,
  nearMeOffHref,
  nearMeOnHref,
  priceBandHref,
  ratingHref,
  toggleFlagHref,
  type FilterMode,
  type PriceBandId,
} from "./filter-hrefs";

// Lusaka CBD: privacy-safe fallback when geolocation is denied (same as the search near-me toggle).
const LUSAKA = { lat: -15.42, lng: 28.28 };

export type FilterBoxesLabels = {
  heading: string;
  category: string;
  categoryAll: string;
  price: string;
  bands: Record<PriceBandId, string>;
  minPrice: string;
  maxPrice: string;
  setPrice: string;
  seller: string;
  verified: string;
  madeInZambia: string;
  nearby: string;
  nearMe: string;
  deals: string;
  dealsBox: string;
  availability: string;
  inStock: string;
  rating: string;
  rating4Plus: string;
  rating3Plus: string;
  condition?: string;
  conditionNew?: string;
  conditionRefurbished?: string;
  conditionUsed?: string;
  clear: string;
};

export type FilterCounts = {
  verified?: number;
  deals?: number;
  madeInZambia?: number;
  inStock?: number;
  rating4?: number;
  rating3?: number;
  priceBands?: Partial<Record<PriceBandId, number>>;
  condition?: Partial<Record<"new" | "refurbished" | "used", number>>;
};

export type FilterCategoryOption = { path: string; label: string; count?: number };

export type FilterBoxesProps = {
  mode: FilterMode;
  labels: FilterBoxesLabels;
  counts?: FilterCounts;
  categories?: FilterCategoryOption[];
  showPrice?: boolean;
  /** Made in Zambia needs approved claims; hidden until the caller knows some exist. */
  showMadeInZambia?: boolean;
  /** Params kept by "Clear" (query, sort, kind...). */
  keepParams?: readonly string[];
  className?: string;
  onNavigated?: () => void;
};

export function FilterBoxes({
  mode,
  labels,
  counts = {},
  categories = [],
  showPrice = true,
  showMadeInZambia = false,
  keepParams = ["q", "kind", "sort"],
  className,
  onNavigated,
}: FilterBoxesProps) {
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();
  const [, startTransition] = useTransition();
  const [min, setMin] = useState(params.get("min_price") ?? "");
  const [max, setMax] = useState(params.get("max_price") ?? "");

  const go = useCallback(
    (href: string) => {
      startTransition(() => {
        router.push(href, { scroll: false });
        onNavigated?.();
      });
    },
    [onNavigated, router],
  );

  const nearOn = nearMeActive(params);
  const toggleNearMe = useCallback(() => {
    if (nearOn) {
      go(nearMeOffHref(pathname, params));
      return;
    }
    // Prefer the area the shopper already chose; else a fresh GPS fix; else Lusaka.
    const remembered =
      typeof window !== "undefined" ? readNearCoords(window.location.search) : null;
    if (remembered) {
      go(nearMeOnHref(pathname, params, remembered));
      return;
    }
    const fallback = () => go(nearMeOnHref(pathname, params, LUSAKA));
    if (typeof navigator === "undefined" || !navigator.geolocation) {
      fallback();
      return;
    }
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        const coords = {
          lat: Math.round(pos.coords.latitude * 100) / 100,
          lng: Math.round(pos.coords.longitude * 100) / 100,
        };
        rememberNearCoords(coords.lat, coords.lng);
        go(nearMeOnHref(pathname, params, coords));
      },
      fallback,
      { enableHighAccuracy: false, timeout: 10_000, maximumAge: 300_000 },
    );
  }, [go, nearOn, params, pathname]);

  const band = activePriceBand(params);
  const stock = inStockKey(mode).on(params);
  const rating = params.get("min_rating");
  const selectedCategory = params.get("category_path");
  const conditions = (params.get("condition") ?? "").split(",").filter(Boolean);

  const nav = (href: string) => ({ href, onNavigate: go });

  return (
    <div
      className={["flex flex-col gap-3", className].filter(Boolean).join(" ")}
      data-testid="filter-boxes"
      aria-label={labels.heading}
      role="group"
    >
      {categories.length > 0 ? (
        <FilterBox title={labels.category}>
          <FilterChip
            label={labels.categoryAll}
            selected={!selectedCategory}
            {...nav(categoryHref(pathname, params, null))}
          />
          {categories.map((option) => (
            <FilterChip
              key={option.path}
              label={option.label}
              count={option.count}
              selected={selectedCategory === option.path}
              {...nav(categoryHref(pathname, params, option.path))}
            />
          ))}
        </FilterBox>
      ) : null}

      {showPrice ? (
        <FilterBox title={labels.price}>
          {PRICE_BANDS.map((b) => (
            <FilterChip
              key={b.id}
              label={labels.bands[b.id]}
              count={counts.priceBands?.[b.id]}
              selected={band === b.id}
              disabled={counts.priceBands?.[b.id] === 0}
              {...nav(priceBandHref(pathname, params, b.id))}
            />
          ))}
          <form
            className="flex w-full items-center gap-1.5"
            onSubmit={(event) => {
              event.preventDefault();
              go(hrefWith(pathname, params, { min_price: min || null, max_price: max || null }));
            }}
          >
            <input
              type="number"
              inputMode="numeric"
              min={0}
              value={min}
              placeholder={labels.minPrice}
              aria-label={labels.minPrice}
              onChange={(e) => setMin(e.target.value)}
              className="min-h-11 w-full min-w-0 rounded-md border border-border bg-surface px-2 text-sm text-text"
            />
            <input
              type="number"
              inputMode="numeric"
              min={0}
              value={max}
              placeholder={labels.maxPrice}
              aria-label={labels.maxPrice}
              onChange={(e) => setMax(e.target.value)}
              className="min-h-11 w-full min-w-0 rounded-md border border-border bg-surface px-2 text-sm text-text"
            />
            <button
              type="submit"
              className="min-h-11 shrink-0 rounded-pill border border-border bg-surface px-3 text-sm font-medium text-text"
            >
              {labels.setPrice}
            </button>
          </form>
        </FilterBox>
      ) : null}

      <FilterBox title={labels.seller}>
        <FilterChip
          label={labels.verified}
          count={counts.verified}
          selected={params.get("verified") === "1"}
          {...nav(toggleFlagHref(pathname, params, "verified"))}
        />
        {showMadeInZambia || params.get("made_in_zambia") === "1" ? (
          <FilterChip
            label={labels.madeInZambia}
            count={counts.madeInZambia}
            selected={params.get("made_in_zambia") === "1"}
            {...nav(toggleFlagHref(pathname, params, "made_in_zambia"))}
          />
        ) : null}
      </FilterBox>

      <FilterBox title={labels.nearby}>
        <FilterChip
          label={labels.nearMe}
          selected={nearOn}
          href={nearOn ? nearMeOffHref(pathname, params) : hrefWith(pathname, params, {})}
          onNavigate={() => toggleNearMe()}
        />
      </FilterBox>

      <FilterBox title={labels.dealsBox}>
        <FilterChip
          label={labels.deals}
          count={counts.deals}
          selected={params.get("deals") === "1"}
          {...nav(toggleFlagHref(pathname, params, "deals"))}
        />
      </FilterBox>

      <FilterBox title={labels.availability}>
        <FilterChip
          label={labels.inStock}
          count={counts.inStock}
          selected={stock}
          {...nav(inStockHref(mode, pathname, params))}
        />
      </FilterBox>

      <FilterBox title={labels.rating}>
        <FilterChip
          label={labels.rating4Plus}
          count={counts.rating4}
          selected={rating === "4"}
          {...nav(ratingHref(pathname, params, "4"))}
        />
        <FilterChip
          label={labels.rating3Plus}
          count={counts.rating3}
          selected={rating === "3"}
          {...nav(ratingHref(pathname, params, "3"))}
        />
      </FilterBox>

      {mode === "catalog" && labels.condition ? (
        <FilterBox title={labels.condition}>
          {(["new", "refurbished", "used"] as const).map((value) => {
            const label =
              value === "new"
                ? labels.conditionNew
                : value === "refurbished"
                  ? labels.conditionRefurbished
                  : labels.conditionUsed;
            const on = conditions.includes(value);
            const next = on ? conditions.filter((v) => v !== value) : [...conditions, value];
            return (
              <FilterChip
                key={value}
                label={label ?? value}
                count={counts.condition?.[value]}
                selected={on}
                {...nav(hrefWith(pathname, params, { condition: next.join(",") || null }))}
              />
            );
          })}
        </FilterBox>
      ) : null}

      <a
        href={clearFiltersHref(pathname, params, keepParams)}
        onClick={(event) => {
          event.preventDefault();
          go(clearFiltersHref(pathname, params, keepParams));
        }}
        className="inline-flex min-h-11 items-center justify-center rounded-pill border border-border bg-surface px-3 text-sm font-medium text-text"
        data-testid="filter-boxes-clear"
      >
        {labels.clear}
      </a>
    </div>
  );
}
