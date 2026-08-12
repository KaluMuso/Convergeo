"use client";

import { Badge } from "@vergeo/ui/src/badge";
import { ProductCard } from "@vergeo/ui/src/product-card";
import Link from "next/link";
import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";

import { queueListingImpression } from "../../../../../lib/listing-view-telemetry";
import { isDemoListingPublicId, shouldShowSampleListingBadge } from "../demo-listing";

import { ListingLogisticsPills, type LogisticsPillLabels } from "./logistics-pills";
import { useLocalWishlist } from "./use-local-wishlist";

import type { CatalogListing } from "./listing-grid";

const IMPRESSION_VISIBILITY_THRESHOLD = 0.5;
const IMPRESSION_MIN_VISIBLE_MS = 1_000;

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
  /** Discount chip template, e.g. "−{percent}%". Renders only when a compare-at price is present. */
  discount?: string;
  sampleListing?: string;
  mediaEmpty?: string;
  /** Honest condition copy — only shown for known API values. */
  conditionNew?: string;
  conditionRefurbished?: string;
  logistics?: LogisticsPillLabels;
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
  const cardRef = useRef<HTMLDivElement>(null);
  const wishlistMountedRef = useRef(false);
  const isDemo = isDemoListingPublicId(listing.imagePublicId);
  const sampleLabel = labels.sampleListing;

  const badge = !listing.inStock ? (
    <Badge variant="sold_out" label={labels.outOfStock} />
  ) : isDemo && sampleLabel && showSampleBadge ? (
    <Badge variant="sample" label={sampleLabel} />
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

  useEffect(() => {
    const cardElement = cardRef.current;
    if (!cardElement || typeof IntersectionObserver === "undefined") {
      return;
    }

    let eligibleTimer: ReturnType<typeof setTimeout> | null = null;
    const clearEligibilityTimer = (): void => {
      if (eligibleTimer !== null) {
        clearTimeout(eligibleTimer);
        eligibleTimer = null;
      }
    };

    const observer = new IntersectionObserver(
      (entries) => {
        const entry = entries.find((candidate) => candidate.target === cardElement);
        const isEligible =
          entry?.isIntersecting === true &&
          entry.intersectionRatio >= IMPRESSION_VISIBILITY_THRESHOLD;

        if (!isEligible) {
          clearEligibilityTimer();
          return;
        }
        if (eligibleTimer !== null) {
          return;
        }

        eligibleTimer = setTimeout(() => {
          eligibleTimer = null;
          queueListingImpression(listing.id);
          observer.disconnect();
        }, IMPRESSION_MIN_VISIBLE_MS);
      },
      { threshold: [0, IMPRESSION_VISIBILITY_THRESHOLD] },
    );

    observer.observe(cardElement);
    return () => {
      clearEligibilityTimer();
      observer.disconnect();
    };
  }, [listing.id]);

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
          conditionLabel || labels.logistics ? (
            <div className="flex flex-col gap-1.5">
              {labels.logistics ? (
                <ListingLogisticsPills listing={listing} labels={labels.logistics} />
              ) : null}
              {conditionLabel ? (
                <span data-testid="listing-card-condition">{conditionLabel}</span>
              ) : null}
            </div>
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
      <div
        ref={cardRef}
        className="min-w-0"
        data-testid="listing-card-no-slug"
        aria-label={listing.title}
      >
        {card}
      </div>
    );
  }

  return (
    <div ref={cardRef} className="relative min-w-0" data-testid="listing-card">
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
