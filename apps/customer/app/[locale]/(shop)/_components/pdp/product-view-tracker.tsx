"use client";

import { track } from "@vergeo/analytics";
import { useEffect } from "react";

type Props = {
  productId: string;
  listingId?: string;
};

/**
 * Fires the anonymized `product_view` beacon once per PDP mount. Client-only and
 * renders nothing: the server log (`analytics_events`) is the source of truth;
 * the GA4 mirror fires only on consent. The beacon is batched and flushed on
 * tab-hide by the AnalyticsProvider, so this adds no per-view network cost.
 */
export function ProductViewTracker({ productId, listingId }: Props): null {
  useEffect(() => {
    track(
      "product_view",
      listingId ? { product_id: productId, listing_id: listingId } : { product_id: productId },
    );
  }, [productId, listingId]);
  return null;
}
