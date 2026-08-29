import { getApiBaseUrl } from "../../../../../lib/api-base-url";

export type PickupLocation = {
  id: string;
  landmark: string;
  lat: number;
  lng: number;
};

export type PickupLocationsResult = {
  branchTracked: boolean;
  locations: PickupLocation[];
};

/**
 * Active branches carrying a branch-tracked listing (GET
 * /products/listings/{id}/pickup-locations) — the PDP's required-branch
 * selection reads this before Add to Cart can be enabled. Fails closed on
 * any error: an unreachable/erroring API never silently treats a listing as
 * "no branch needed" (`branchTracked: false` here is what gates whether the
 * picker even renders, so a false negative would let a real branch-tracked
 * add-to-cart through with no pickup_location_id).
 */
export async function fetchPickupLocations(listingId: string): Promise<PickupLocationsResult> {
  const response = await fetch(
    `${getApiBaseUrl().replace(/\/$/, "")}/products/listings/${encodeURIComponent(listingId)}/pickup-locations`,
    { credentials: "include" },
  );
  if (!response.ok) {
    throw new Error(`pickup-locations request failed (${response.status})`);
  }
  const payload = (await response.json()) as {
    branch_tracked: boolean;
    locations: Array<{ id: string; landmark: string; lat: number; lng: number }>;
  };
  return {
    branchTracked: payload.branch_tracked,
    locations: payload.locations.map((location) => ({
      id: location.id,
      landmark: location.landmark,
      lat: location.lat,
      lng: location.lng,
    })),
  };
}
