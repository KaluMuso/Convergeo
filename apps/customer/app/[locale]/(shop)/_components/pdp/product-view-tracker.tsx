"use client";

import { track } from "@vergeo/analytics";
import { useEffect } from "react";

import { recordRecentlyViewed } from "./recently-viewed-storage";

type Props = {
  productId: string;
  listingId?: string;
  /** Optional local recently-viewed payload (serialisable). */
  recent?: {
    slug: string;
    name: string;
    imagePublicId: string | null;
    fromPriceNgwee: number | null;
  };
};

/**
 * Fires the anonymized `product_view` beacon once per PDP mount and records a
 * local recently-viewed entry when `recent` is provided.
 */
export function ProductViewTracker({ productId, listingId, recent }: Props): null {
  const recentSlug = recent?.slug;
  const recentName = recent?.name;
  const recentImage = recent?.imagePublicId ?? null;
  const recentPrice = recent?.fromPriceNgwee ?? null;

  useEffect(() => {
    track(
      "product_view",
      listingId ? { product_id: productId, listing_id: listingId } : { product_id: productId },
    );
    if (recentSlug && recentName) {
      recordRecentlyViewed({
        slug: recentSlug,
        name: recentName,
        imagePublicId: recentImage,
        fromPriceNgwee: recentPrice,
      });
    }
  }, [productId, listingId, recentSlug, recentName, recentImage, recentPrice]);

  return null;
}
