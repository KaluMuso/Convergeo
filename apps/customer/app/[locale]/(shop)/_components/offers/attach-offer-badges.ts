import { absoluteApiUrl } from "../../../../../lib/api-base-url";

import type { OfferBadge } from "./offer-badge";

const MAX_IDS = 60;

/**
 * W8: one server-side read of `/offers/badges` for a grid of listings.
 * Flag off, API down or no offers → listings unchanged (no badge, no error).
 */
export async function attachOfferBadges<
  T extends { id: string; offerBadge?: OfferBadge },
>(listings: T[]): Promise<T[]> {
  if (listings.length === 0) {
    return listings;
  }
  const ids = listings.slice(0, MAX_IDS).map((listing) => listing.id);
  const url = absoluteApiUrl(
    `/offers/badges?listing_ids=${ids.map(encodeURIComponent).join(",")}`,
  );
  if (!url) {
    return listings;
  }
  try {
    const response = await fetch(url, {
      next: { revalidate: 120, tags: ["offers"] },
    });
    if (!response.ok) {
      return listings;
    }
    const payload = (await response.json()) as {
      badges?: Record<string, OfferBadge>;
    };
    const badges = payload.badges ?? {};
    return listings.map((listing) =>
      badges[listing.id]
        ? { ...listing, offerBadge: badges[listing.id] }
        : listing,
    );
  } catch {
    return listings;
  }
}
