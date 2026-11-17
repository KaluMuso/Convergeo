import { absoluteApiUrl } from "../../../../lib/api-base-url";

import type { CatalogListing } from "./plp/listing-grid";

/** Wire shape of `GET /deals` (flash deals). Existing endpoint, no backend change. */
export type DealItem = {
  deal_id: string;
  starts_at: string;
  ends_at: string;
  deal_price_ngwee: number;
  reference_price_ngwee: number;
  discount_percent: number;
  listing: {
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
    delivery_available?: boolean;
    pickup_available?: boolean;
  };
};

export type DealsResponse = { server_time: string; items: DealItem[] };

/** Empty-safe: any failure resolves to null so callers can hide the surface. */
export async function fetchDeals(limit: number, revalidate = 60): Promise<DealsResponse | null> {
  const url = absoluteApiUrl(`/deals?limit=${limit}`);
  if (!url) {
    return null;
  }
  try {
    const response = await fetch(url, { next: { revalidate, tags: ["deals"] } });
    if (!response.ok) {
      return null;
    }
    return (await response.json()) as DealsResponse;
  } catch {
    return null;
  }
}

/** Deal price is the live price; the reference price is the struck-through original. */
export function dealToListing(deal: DealItem): CatalogListing {
  return {
    id: deal.listing.id,
    title: deal.listing.title,
    productSlug: deal.listing.product_slug,
    vendorName: deal.listing.vendor_name,
    priceNgwee: deal.deal_price_ngwee,
    oldNgwee: deal.reference_price_ngwee,
    condition: deal.listing.condition,
    inStock: deal.listing.in_stock,
    imagePublicId: deal.listing.image_public_id,
    rating: deal.listing.rating,
    reviewCount: deal.listing.review_count,
    distanceM: deal.listing.distance_m,
    belowMedian: false,
    deliveryAvailable: deal.listing.delivery_available ?? false,
    pickupAvailable: deal.listing.pickup_available ?? false,
  };
}
