"use client";

import { Button } from "@vergeo/ui/src/button";
import { useCallback, useState } from "react";

import { ListingGrid, type CatalogListing } from "./listing-grid";

type CatalogApiResponse = {
  items: Array<{
    id: string;
    title: string;
    product_slug: string | null;
    vendor_name: string;
    price_ngwee: number;
    condition: string;
    in_stock: boolean;
    image_public_id: string | null;
    rating: number;
    review_count: number;
    distance_m: number | null;
  }>;
  next_cursor: string | null;
};

type LoadMoreProps = {
  apiBaseUrl: string;
  queryString: string;
  nextCursor: string | null;
  label: string;
  loadingLabel: string;
  onAppend: (items: CatalogListing[]) => void;
};

function mapListing(item: CatalogApiResponse["items"][number]): CatalogListing {
  return {
    id: item.id,
    title: item.title,
    productSlug: item.product_slug,
    vendorName: item.vendor_name,
    priceNgwee: item.price_ngwee,
    condition: item.condition,
    inStock: item.in_stock,
    imagePublicId: item.image_public_id,
    rating: item.rating,
    reviewCount: item.review_count,
    distanceM: item.distance_m,
  };
}

export function PlpBrowseClient({
  locale,
  initialListings,
  gridLabels,
  apiBaseUrl,
  queryString,
  nextCursor,
  loadMoreLabel,
  loadingLabel,
}: {
  locale: string;
  initialListings: CatalogListing[];
  gridLabels: Parameters<typeof ListingGrid>[0]["labels"];
  apiBaseUrl: string;
  queryString: string;
  nextCursor: string | null;
  loadMoreLabel: string;
  loadingLabel: string;
}) {
  const [listings, setListings] = useState(initialListings);

  return (
    <>
      <ListingGrid locale={locale} listings={listings} labels={gridLabels} />
      <LoadMore
        apiBaseUrl={apiBaseUrl}
        queryString={queryString}
        nextCursor={nextCursor}
        label={loadMoreLabel}
        loadingLabel={loadingLabel}
        onAppend={(items) => setListings((current) => [...current, ...items])}
      />
    </>
  );
}

export function LoadMore({
  apiBaseUrl,
  queryString,
  nextCursor,
  label,
  loadingLabel,
  onAppend,
}: LoadMoreProps) {
  const [cursor, setCursor] = useState(nextCursor);
  const [loading, setLoading] = useState(false);

  const loadMore = useCallback(async () => {
    if (!cursor || loading) {
      return;
    }
    setLoading(true);
    try {
      const params = new URLSearchParams(queryString);
      params.set("cursor", cursor);
      const response = await fetch(`${apiBaseUrl}/catalog/listings?${params.toString()}`);
      if (!response.ok) {
        return;
      }
      const body = (await response.json()) as CatalogApiResponse;
      onAppend(body.items.map(mapListing));
      setCursor(body.next_cursor);
    } finally {
      setLoading(false);
    }
  }, [apiBaseUrl, cursor, loading, onAppend, queryString]);

  if (!cursor) {
    return null;
  }

  return (
    <div className="flex justify-center pt-4">
      <Button
        type="button"
        onClick={loadMore}
        disabled={loading}
        loading={loading}
        loadingLabel={loadingLabel}
      >
        {loading ? loadingLabel : label}
      </Button>
    </div>
  );
}
