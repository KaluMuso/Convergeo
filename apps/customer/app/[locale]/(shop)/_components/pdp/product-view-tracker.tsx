"use client";

import { track } from "@vergeo/analytics";
import { useEffect } from "react";

import { recordListingPdpView } from "../../../../../lib/listing-view-telemetry";
import { recordRecentlyViewed } from "../recently-viewed/use-recently-viewed";

/** Fire-and-forget server record: load the engagement client on demand, outside first-load JS. */
function recordRecentlyViewedOnServer(productId: string): Promise<void> {
  return import("../../../../../lib/engagement-api")
    .then((mod) => mod.recordRecentlyViewedOnServer(productId))
    .catch(() => undefined);
}

type Props = {
  productId: string;
  listingId?: string;
  /** Optional local recently-viewed payload (serialisable). */
  recent?: {
    slug: string;
    name: string;
  };
};

/**
 * Fires the anonymized `product_view` beacon once per PDP mount and records a
 * local recently-viewed entry when `recent` is provided. Signed-in users also
 * sync to `/account/recently-viewed`.
 */
export function ProductViewTracker({ productId, listingId, recent }: Props): null {
  const recentSlug = recent?.slug;
  const recentName = recent?.name;

  useEffect(() => {
    track(
      "product_view",
      listingId ? { product_id: productId, listing_id: listingId } : { product_id: productId },
    );
    if (listingId) {
      recordListingPdpView(listingId);
    }
    if (recentSlug && recentName) {
      recordRecentlyViewed(recentSlug, recentName);
    }
    void recordRecentlyViewedOnServer(productId);
  }, [productId, listingId, recentSlug, recentName]);

  return null;
}
