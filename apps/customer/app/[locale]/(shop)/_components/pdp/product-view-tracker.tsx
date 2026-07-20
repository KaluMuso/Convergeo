"use client";

import { track } from "@vergeo/analytics";
import { useEffect } from "react";

import { recordRecentlyViewed } from "../recently-viewed/use-recently-viewed";

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
 * local recently-viewed entry when `recent` is provided.
 */
export function ProductViewTracker({ productId, listingId, recent }: Props): null {
  const recentSlug = recent?.slug;
  const recentName = recent?.name;

  useEffect(() => {
    track(
      "product_view",
      listingId ? { product_id: productId, listing_id: listingId } : { product_id: productId },
    );
    if (recentSlug && recentName) {
      recordRecentlyViewed(recentSlug, recentName);
    }
  }, [productId, listingId, recentSlug, recentName]);

  return null;
}
