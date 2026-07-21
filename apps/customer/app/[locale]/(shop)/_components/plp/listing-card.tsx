"use client";

import { Badge } from "@vergeo/ui/src/badge";
import { ProductCard } from "@vergeo/ui/src/product-card";
import Link from "next/link";
import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";

import { isDemoListingPublicId, shouldShowSampleListingBadge } from "../demo-listing";

import { useLocalWishlist } from "./use-local-wishlist";

import type { CatalogListing } from "./listing-grid";

/**
 * Dynamic import keeps `mini-cart-drawer` off the PLP/home *page* graph.
 * The shop layout already ships the cart store for nav badges; a static import
 * here would also list that ~6 KB gz chunk on every ListingCard route and fail
 * the bundle-guard regression gate (layout chunks are not counted on /page).
 */
async function quickAddListing(listingId: string, successMessage: string): Promise<void> {
  const { addCartItem, openMiniCart, setLastAddedMessage } =
    await import("../cart/mini-cart-drawer");
  await addCartItem(listingId, 1);
  setLastAddedMessage(successMessage);
  openMiniCart();
}

export type ListingCardLabels = {
  vendor: string;
  noReviews: string;
  reviewCount: string;
  quickAdd: string;
  quickAddError?: string;
  wishlist: string;
  wishlistRemove?: string;
  outOfStock: string;
  distance: string;
  /** Discount chip template, e.g. "−{percent}%". Renders only when a compare-at price is present. */
  discount?: string;
  sampleListing?: string;
  mediaEmpty?: string;
  /** Honest condition copy — only shown for known API values. */
  conditionNew?: string;
  conditionRefurbished?: string;
};

/** Map listing.condition to a label; unknown values render nothing (no invention). */
export function listingConditionLabel(
  condition: string,
  labels: Pick<ListingCardLabels, "conditionNew" | "conditionRefurbished">,
): string | undefined {
  if (condition === "new") {
    return labels.conditionNew;
  }
  if (condition === "refurbished") {
    return labels.conditionRefurbished;
  }
  return undefined;
}

type ListingCardProps = {
  locale: string;
  listing: CatalogListing;
  labels: ListingCardLabels;
  /** Prefetched by RSC `ListingGrid` via `CloudinaryImageStatic` (no client image island). */
  media?: ReactNode;
  showSampleBadge?: boolean;
  density?: "default" | "compact";
};

function formatDistance(meters: number | null): string | null {
  if (meters === null) {
    return null;
  }
  if (meters < 1000) {
    return `${Math.round(meters)} m`;
  }
  return `${(meters / 1000).toFixed(1)} km`;
}

export function ListingCard({
  locale,
  listing,
  labels,
  media,
  showSampleBadge = shouldShowSampleListingBadge(),
  density = "default",
}: ListingCardProps) {
  const { isWishlisted, toggleWishlist, enabled } = useLocalWishlist(listing.productSlug);
  const [wishlistStatusAnnouncement, setWishlistStatusAnnouncement] = useState("");
  const [quickAdding, setQuickAdding] = useState(false);
  const [quickAddAnnouncement, setQuickAddAnnouncement] = useState("");
  const wishlistMountedRef = useRef(false);
  const distance = formatDistance(listing.distanceM);
  const distanceLabel =
    distance !== null ? labels.distance.replace("{distance}", distance) : undefined;
  const isDemo = isDemoListingPublicId(listing.imagePublicId);
  const sampleLabel = labels.sampleListing;

  const badge = !listing.inStock ? (
    <Badge variant="sold_out" label={labels.outOfStock} />
  ) : isDemo && sampleLabel && showSampleBadge ? (
    <Badge variant="sample" label={sampleLabel} />
  ) : distanceLabel ? (
    <Badge variant="public" label={distanceLabel} />
  ) : undefined;

  const wishlistLabel =
    isWishlisted && labels.wishlistRemove ? labels.wishlistRemove : labels.wishlist;
  const conditionLabel = listingConditionLabel(listing.condition, labels);

  // Struck compare-at price only when in stock and genuinely cheaper now.
  const hasDiscount =
    listing.inStock &&
    typeof listing.oldNgwee === "number" &&
    listing.oldNgwee > listing.priceNgwee;
  const discountLabel =
    hasDiscount && labels.discount
      ? labels.discount.replace(
          "{percent}",
          String(Math.round(((listing.oldNgwee! - listing.priceNgwee) / listing.oldNgwee!) * 100)),
        )
      : undefined;

  useEffect(() => {
    if (!wishlistMountedRef.current) {
      wishlistMountedRef.current = true;
      return;
    }
    setWishlistStatusAnnouncement(wishlistLabel);
  }, [isWishlisted, wishlistLabel]);

  const onQuickAdd = useCallback(() => {
    if (!listing.inStock || quickAdding) {
      return;
    }
    setQuickAdding(true);
    setQuickAddAnnouncement("");
    void quickAddListing(listing.id, labels.quickAdd)
      .then(() => {
        setQuickAddAnnouncement(labels.quickAdd);
      })
      .catch(() => {
        setQuickAddAnnouncement(labels.quickAddError ?? labels.quickAdd);
      })
      .finally(() => {
        setQuickAdding(false);
      });
  }, [labels.quickAdd, labels.quickAddError, listing.id, listing.inStock, quickAdding]);

  const card = (
    <>
      <ProductCard
        title={listing.title}
        vendorLabel={labels.vendor.replace("{vendor}", listing.vendorName)}
        ngwee={listing.priceNgwee}
        oldNgwee={hasDiscount ? listing.oldNgwee : undefined}
        discountLabel={discountLabel}
        rating={listing.rating}
        reviewCount={listing.reviewCount}
        noReviewsLabel={labels.noReviews}
        reviewCountLabel={labels.reviewCount}
        quickAddLabel={labels.quickAdd}
        wishlistLabel={wishlistLabel}
        wishlistStatusAnnouncement={wishlistStatusAnnouncement}
        badge={badge}
        density={density}
        unavailable={!listing.inStock}
        mediaEmptyLabel={labels.mediaEmpty}
        meta={
          conditionLabel ? (
            <span data-testid="listing-card-condition">{conditionLabel}</span>
          ) : undefined
        }
        isWishlisted={isWishlisted}
        onWishlistToggle={enabled ? toggleWishlist : undefined}
        onQuickAdd={listing.inStock ? onQuickAdd : undefined}
        media={media}
      />
      {quickAddAnnouncement ? (
        <p className="sr-only" aria-live="polite" data-testid="listing-card-quick-add-status">
          {quickAddAnnouncement}
        </p>
      ) : null}
    </>
  );

  if (!listing.productSlug) {
    return (
      <div className="min-w-0" data-testid="listing-card-no-slug" aria-label={listing.title}>
        {card}
      </div>
    );
  }

  return (
    <div className="relative min-w-0" data-testid="listing-card">
      {card}
      <Link
        href={`/${locale}/p/${listing.productSlug}`}
        className="absolute inset-0 z-[1] rounded-lg focus-visible:outline-none focus-visible:shadow-focusRing"
        aria-label={listing.title}
        data-testid="listing-card-link"
      />
    </div>
  );
}
