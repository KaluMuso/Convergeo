"use client";

import { Badge } from "@vergeo/ui/src/badge";
import { CloudinaryImage } from "@vergeo/ui/src/media/cloudinary-image";
import { ProductCard } from "@vergeo/ui/src/product-card";
import Link from "next/link";

import { isDemoListingPublicId, shouldShowSampleListingBadge } from "../demo-listing";

import { useLocalWishlist } from "./use-local-wishlist";

import type { CatalogListing } from "./listing-grid";

export type ListingCardLabels = {
  vendor: string;
  noReviews: string;
  reviewCount: string;
  quickAdd: string;
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

  const card = (
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
      badge={badge}
      density={density}
      unavailable={!listing.inStock}
      mediaEmptyLabel={labels.mediaEmpty}
      isWishlisted={isWishlisted}
      onWishlistToggle={enabled ? toggleWishlist : undefined}
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
