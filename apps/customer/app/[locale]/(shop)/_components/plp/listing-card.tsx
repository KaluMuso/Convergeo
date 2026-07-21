"use client";

import { Badge } from "@vergeo/ui/src/badge";
import { CloudinaryImage } from "@vergeo/ui/src/media/cloudinary-image";
import { ProductCard } from "@vergeo/ui/src/product-card";
import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";

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
  sampleListing?: string;
  mediaEmpty?: string;
};

type ListingCardProps = {
  locale: string;
  listing: CatalogListing;
  labels: ListingCardLabels;
  priority?: boolean;
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
  priority = false,
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
        isWishlisted={isWishlisted}
        onWishlistToggle={enabled ? toggleWishlist : undefined}
        onQuickAdd={listing.inStock ? onQuickAdd : undefined}
        media={
          listing.imagePublicId ? (
            <CloudinaryImage
              publicId={listing.imagePublicId}
              alt={listing.title}
              width={360}
              ratio="4/3"
              priority={priority}
              sizes="(max-width: 360px) 50vw, (max-width: 720px) 33vw, 25vw"
              className="h-full w-full object-cover"
            />
          ) : undefined
        }
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
    <Link
      href={`/${locale}/p/${listing.productSlug}`}
      className="min-w-0 no-underline"
      data-testid="listing-card-link"
    >
      {card}
    </Link>
  );
}
