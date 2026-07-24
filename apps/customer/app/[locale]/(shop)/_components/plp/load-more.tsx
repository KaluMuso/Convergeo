"use client";

import { useCallback, useMemo } from "react";

import {
  ProgressiveLoadControls,
  type ProgressiveLoadControlsLabels,
} from "../progressive-load/progressive-load-controls";
import { useProgressiveLoad } from "../progressive-load/use-progressive-load";

import { ListingGrid, type CatalogListing } from "./listing-grid";

type CatalogApiResponse = {
  items: Array<{
    id: string;
    title: string;
    product_slug: string | null;
    vendor_name: string;
    price_ngwee: number;
    compare_at_ngwee?: number | null;
    condition: string;
    in_stock: boolean;
    image_public_id: string | null;
    rating: number;
    review_count: number;
    distance_m: number | null;
    below_median?: boolean;
    delivery_available?: boolean;
    pickup_available?: boolean;
  }>;
  next_cursor: string | null;
};

function mapListing(item: CatalogApiResponse["items"][number]): CatalogListing {
  return {
    id: item.id,
    title: item.title,
    productSlug: item.product_slug,
    vendorName: item.vendor_name,
    priceNgwee: item.price_ngwee,
    oldNgwee: item.compare_at_ngwee ?? undefined,
    condition: item.condition,
    inStock: item.in_stock,
    imagePublicId: item.image_public_id,
    rating: item.rating,
    reviewCount: item.review_count,
    distanceM: item.distance_m,
    belowMedian: item.below_median ?? false,
    deliveryAvailable: item.delivery_available ?? false,
    pickupAvailable: item.pickup_available ?? false,
  };
}

export type PlpBrowseClientProps = {
  locale: string;
  initialListings: CatalogListing[];
  gridLabels: Parameters<typeof ListingGrid>[0]["labels"];
  apiBaseUrl: string;
  /** Catalog query string without requiring a cursor (filters/sort/category). */
  queryString: string;
  nextCursor: string | null;
  labels: ProgressiveLoadControlsLabels;
};

export function PlpBrowseClient({
  locale,
  initialListings,
  gridLabels,
  apiBaseUrl,
  queryString,
  nextCursor,
  labels,
}: PlpBrowseClientProps) {
  const resetKey = `${locale}|${queryString}|${nextCursor ?? ""}|${initialListings
    .map((item) => item.id)
    .join(",")}`;

  const fetchPage = useCallback(
    async (cursor: string, signal: AbortSignal) => {
      const params = new URLSearchParams(queryString);
      params.delete("cursor");
      params.set("cursor", cursor);
      const response = await fetch(`${apiBaseUrl}/catalog/listings?${params.toString()}`, {
        signal,
      });
      if (!response.ok) {
        throw new Error(`Catalog load failed (${response.status})`);
      }
      const body = (await response.json()) as CatalogApiResponse;
      return {
        items: body.items.map(mapListing),
        nextCursor: body.next_cursor,
      };
    },
    [apiBaseUrl, queryString],
  );

  const { items, status, hasMore, lastAppendedCount, loadMore, sentinelRef } =
    useProgressiveLoad<CatalogListing>({
      initialItems: initialListings,
      initialCursor: nextCursor,
      resetKey,
      fetchPage,
    });

  const controlLabels = useMemo(() => labels, [labels]);

  return (
    <>
      <ListingGrid locale={locale} listings={items} labels={gridLabels} density="compact" />
      <ProgressiveLoadControls
        status={status}
        hasMore={hasMore}
        lastAppendedCount={lastAppendedCount}
        labels={controlLabels}
        onLoadMore={loadMore}
        sentinelRef={sentinelRef}
        testIdPrefix="plp"
      />
    </>
  );
}
