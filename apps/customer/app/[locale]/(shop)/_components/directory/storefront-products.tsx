"use client";

import { useMemo, useState } from "react";

import { ListingGrid, type CatalogListing } from "../plp/listing-grid";

import { CompareOtherShopsLink, type StorefrontCompare } from "./business-home/compare-other-shops";

export type StorefrontListing = CatalogListing & {
  categorySlug?: string | null;
  categoryName?: string | null;
  /** "Compare with other shops" — null when no other shop sells it. */
  compare?: StorefrontCompare | null;
};

type StorefrontProductsProps = {
  locale: string;
  listings: StorefrontListing[];
  gridLabels: Parameters<typeof ListingGrid>[0]["labels"];
  labels: { search: string; all: string; noMatches: string };
};

/**
 * Products tab on /v/[slug]: in-store search + category chips over the
 * vendor's listings (client-side — a storefront returns all active listings).
 */
export function StorefrontProducts({
  locale,
  listings,
  gridLabels,
  labels,
}: StorefrontProductsProps) {
  const [query, setQuery] = useState("");
  const [category, setCategory] = useState<string | null>(null);

  const categories = useMemo(() => {
    const seen = new Map<string, { name: string; count: number }>();
    for (const listing of listings) {
      if (listing.categorySlug && listing.categoryName) {
        const entry = seen.get(listing.categorySlug) ?? {
          name: listing.categoryName,
          count: 0,
        };
        entry.count += 1;
        seen.set(listing.categorySlug, entry);
      }
    }
    return [...seen.entries()].sort((a, b) => b[1].count - a[1].count);
  }, [listings]);

  const visible = useMemo(() => {
    const needle = query.trim().toLocaleLowerCase();
    return listings.filter(
      (listing) =>
        (!category || listing.categorySlug === category) &&
        (!needle || listing.title.toLocaleLowerCase().includes(needle)),
    );
  }, [category, listings, query]);

  const chip = (active: boolean) =>
    `inline-flex min-h-10 shrink-0 items-center rounded-pill border px-3.5 text-sm font-medium transition-colors focus-visible:outline-none focus-visible:shadow-focusRing ${
      active
        ? "border-primary bg-primary text-[var(--primary-btn-fg)]"
        : "border-border bg-surface text-text-2 hover:border-primary hover:text-primary"
    }`;

  return (
    <div className="flex flex-col gap-3" data-testid="storefront-products">
      <div className="flex flex-col gap-2 md:flex-row md:items-center">
        <label className="relative min-w-0 md:w-72 md:shrink-0">
          <span className="sr-only">{labels.search}</span>
          <svg
            aria-hidden
            viewBox="0 0 24 24"
            className="pointer-events-none absolute left-3.5 top-1/2 h-4 w-4 -translate-y-1/2 text-text-3"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
          >
            <circle cx="11" cy="11" r="7" />
            <path d="M20 20l-3-3" />
          </svg>
          <input
            type="search"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder={labels.search}
            className="min-h-11 w-full rounded-pill border border-border bg-surface pl-10 pr-4 text-sm text-text placeholder:text-text-3 focus:border-primary focus:outline-none"
          />
        </label>
        {categories.length > 1 ? (
          <div
            role="group"
            aria-label={labels.all}
            className="-mx-1 flex min-w-0 gap-1.5 overflow-x-auto px-1 [scrollbar-width:none]"
          >
            <button
              type="button"
              aria-pressed={category === null}
              onClick={() => setCategory(null)}
              className={chip(category === null)}
            >
              {labels.all}
            </button>
            {categories.map(([slug, entry]) => (
              <button
                key={slug}
                type="button"
                aria-pressed={category === slug}
                onClick={() => setCategory(category === slug ? null : slug)}
                className={chip(category === slug)}
              >
                {entry.name}
              </button>
            ))}
          </div>
        ) : null}
      </div>
      {visible.length === 0 ? (
        <p role="status" className="m-0 py-6 text-center text-sm text-text-2">
          {labels.noMatches}
        </p>
      ) : (
        <ListingGrid
          locale={locale}
          listings={visible}
          labels={gridLabels}
          renderFooter={(listing) => {
            const compare = (listing as StorefrontListing).compare;
            return compare ? <CompareOtherShopsLink compare={compare} /> : null;
          }}
        />
      )}
    </div>
  );
}
