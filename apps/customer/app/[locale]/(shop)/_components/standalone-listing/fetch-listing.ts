import { absoluteApiUrl } from "../../../../../lib/api-base-url";

import type { ListingCondition } from "../pdp/condition-badge";
import type { SaleUnit } from "../sale-quantity";

export const STANDALONE_LISTING_REVALIDATE_SECONDS = 60;

export type StandaloneListingImage = {
  cloudinary_public_id: string;
  position: number;
};

export type StandaloneListing = {
  id: string;
  title: string;
  product_class: "A" | "B" | "C" | "D" | "E";
  condition: ListingCondition;
  defect_notes: string | null;
  price_ngwee: number;
  compare_at_ngwee: number | null;
  sale_unit: SaleUnit;
  unit_step_milli: number;
  min_steps: number;
  fulfilment_mode: "stocked" | "made_to_order";
  lead_time_days: number | null;
  vendor_capacity_per_week: number | null;
  stock_mode: "tracked" | "always_available";
  stock_qty: number | null;
  in_stock: boolean;
  moq: number;
  wholesale: boolean;
  vendor: {
    id: string;
    name: string;
    slug: string | null;
  };
  location: {
    landmark: string | null;
    lat: number | null;
    lng: number | null;
  } | null;
  images: StandaloneListingImage[];
};

export type StandaloneListingFetchResult =
  { kind: "listing"; data: StandaloneListing } | { kind: "not_found" } | { kind: "unavailable" };

export function standaloneListingCacheTag(id: string): string {
  return `listing:${id}`;
}

/**
 * Loads an active standalone listing. The API deliberately returns 404 for
 * inactive, demo, or canonical-attached listings so this route cannot bypass
 * the normal product PDP or expose unpublished inventory.
 */
export async function fetchStandaloneListing(
  id: string,
  accessToken?: string | null,
): Promise<StandaloneListingFetchResult> {
  const url = absoluteApiUrl(`/catalog/listings/${encodeURIComponent(id)}`);
  if (!url) {
    return { kind: "unavailable" };
  }

  try {
    const response = await fetch(
      url,
      accessToken
        ? {
            headers: { Authorization: `Bearer ${accessToken}` },
            // Wholesale visibility is identity-dependent; never put it in a shared cache.
            cache: "no-store",
          }
        : {
            next: {
              revalidate: STANDALONE_LISTING_REVALIDATE_SECONDS,
              tags: [standaloneListingCacheTag(id), "catalog-listings"],
            },
          },
    );

    if (response.status === 404) {
      return { kind: "not_found" };
    }
    if (!response.ok) {
      return { kind: "unavailable" };
    }

    return { kind: "listing", data: (await response.json()) as StandaloneListing };
  } catch {
    return { kind: "unavailable" };
  }
}
