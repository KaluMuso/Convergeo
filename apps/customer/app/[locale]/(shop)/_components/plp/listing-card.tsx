"use client";

import { formatK } from "@vergeo/i18n";
import { Badge } from "@vergeo/ui/src/badge";
import { ProductCard } from "@vergeo/ui/src/product-card";
import { emitToastKey } from "@vergeo/ui/src/toast";
import Link from "next/link";
import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";

import {
  estimateDelivery,
  formatDeliveryEstimate,
  type DeliveryEstimateLabels,
} from "../../../../../lib/delivery-estimate";
import { queueListingImpression } from "../../../../../lib/listing-view-telemetry";
import { isDemoListingPublicId, shouldShowSampleListingBadge } from "../demo-listing";
import { offerBadgeLabel, type OfferBadgeLabels } from "../offers/offer-badge";
import { formatMadeToOrderBadge, type MadeToOrderLabels } from "../sale-quantity";

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
async function quickAddListing(
  listingId: string,
  quantity: number,
  successMessage: string,
): Promise<void> {
  const { addCartItem, openMiniCart, setLastAddedMessage } =
    await import("../cart/mini-cart-drawer");
  await addCartItem(listingId, quantity);
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
  conditionUsed?: string;
  logistics?: LogisticsPillLabels;
  /** catalog.delivery.* — renders "Delivery in Lusaka tomorrow" style line. */
  delivery?: DeliveryEstimateLabels;
  /** catalog.madeToOrder.* — renders the "Made to order · ready within a week" badge. */
  madeToOrder?: MadeToOrderLabels;
  /** catalog.offers.badge.* — W8 offer pill ("Buy 2 get 1 free"). */
  offerBadge?: OfferBadgeLabels;
  /** common.value.listing.sellersFrom — `{count}` and `{price}` (pre-formatted). */
  sellersFrom?: string;
  /** common.value.listing.deliversToday — short pill when ETA is today in Lusaka. */
  deliversTodayPill?: string;
};

/** Map listing.condition to a label; unknown values render nothing (no invention). */
export function listingConditionLabel(
  condition: string,
  labels: Pick<ListingCardLabels, "conditionNew" | "conditionRefurbished" | "conditionUsed">,
): string | undefined {
  if (condition === "new") {
    return labels.conditionNew;
  }
  if (condition === "refurbished") {
    return labels.conditionRefurbished;
  }
  if (condition === "used") {
    return labels.conditionUsed;
  }
  return undefined;
}

export function listingQuickAddQuantity(minSteps: number | null | undefined): number {
  return Number.isSafeInteger(minSteps) && (minSteps ?? 0) > 0 ? (minSteps as number) : 1;
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

export function listingCardHref(
  locale: string,
  listing: Pick<CatalogListing, "id" | "productSlug">,
): string {
  return listing.productSlug
    ? `/${locale}/p/${encodeURIComponent(listing.productSlug)}`
    : `/${locale}/l/${encodeURIComponent(listing.id)}`;
}

export function ListingCard({
  locale,
  listing,
  labels,
  media,
  showSampleBadge = shouldShowSampleListingBadge(),
  density = "compact",
}: ListingCardProps) {
  const { isWishlisted, toggleWishlist, enabled } = useLocalWishlist(listing.productSlug);
  const [wishlistStatusAnnouncement, setWishlistStatusAnnouncement] = useState("");
  const [quickAdding, setQuickAdding] = useState(false);
  const [quickAddAnnouncement, setQuickAddAnnouncement] = useState("");
  const cardRef = useRef<HTMLDivElement>(null);
  const wishlistMountedRef = useRef(false);
  const isDemo = isDemoListingPublicId(listing.imagePublicId);
  const sampleLabel = labels.sampleListing;
  const href = listingCardHref(locale, listing);
  const quickAddQuantity = listingQuickAddQuantity(listing.minSteps);
  const offerLabel =
    listing.offerBadge && labels.offerBadge
      ? offerBadgeLabel(listing.offerBadge, labels.offerBadge)
      : null;

  const badge = !listing.inStock ? (
    <Badge variant="sold_out" label={labels.outOfStock} />
  ) : isDemo && sampleLabel && showSampleBadge ? (
    <Badge variant="sample" label={sampleLabel} />
  ) : offerLabel ? (
    <Badge variant="promotion" label={offerLabel} />
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
    void quickAddListing(listing.id, quickAddQuantity, labels.quickAdd)
      .then(() => {
        setQuickAddAnnouncement(labels.quickAdd);
        emitToastKey("addedToCart", { type: "cart" });
      })
      .catch(() => {
        setQuickAddAnnouncement(labels.quickAddError ?? labels.quickAdd);
        emitToastKey("addToCartFailed", { type: "error" });
      })
      .finally(() => {
        setQuickAdding(false);
      });
  }, [
    labels.quickAdd,
    labels.quickAddError,
    listing.id,
    listing.inStock,
    quickAddQuantity,
    quickAdding,
  ]);

  // Lusaka-clock estimate from lead time; null when not in stock / no fulfilment.
  const deliveryEstimate = estimateDelivery({
    deliveryAvailable: listing.deliveryAvailable,
    pickupAvailable: listing.pickupAvailable,
    fulfilmentMode: listing.fulfilmentMode,
    leadTimeDays: listing.leadTimeDays,
    inStock: listing.inStock,
  });

  const deliveryLine = labels.delivery
    ? formatDeliveryEstimate(deliveryEstimate, labels.delivery)
    : null;

  const sellersFromLine =
    labels.sellersFrom &&
    typeof listing.productSellerCount === "number" &&
    listing.productSellerCount > 1 &&
    typeof listing.productLowestPriceNgwee === "number" &&
    Number.isInteger(listing.productLowestPriceNgwee)
      ? labels.sellersFrom
          .replace("{count}", String(listing.productSellerCount))
          .replace("{price}", formatK(listing.productLowestPriceNgwee))
      : null;

  const deliversTodayPill =
    labels.deliversTodayPill &&
    listing.deliveryAvailable &&
    deliveryEstimate?.kind === "delivery" &&
    deliveryEstimate.when === "today"
      ? labels.deliversTodayPill
      : null;

  const madeToOrderLine = labels.madeToOrder
    ? formatMadeToOrderBadge(listing.fulfilmentMode, listing.leadTimeDays, labels.madeToOrder)
    : null;

  // Dense cards already carry the delivery line; the pill row is for roomy layouts only.
  const showLogisticsPills = Boolean(labels.logistics) && density !== "compact";

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
        reviewCountLabel={labels.reviewCount.replace("{count}", String(listing.reviewCount))}
        quickAddLabel={labels.quickAdd}
        wishlistLabel={wishlistLabel}
        wishlistStatusAnnouncement={wishlistStatusAnnouncement}
        badge={badge}
        density={density}
        unavailable={!listing.inStock}
        mediaEmptyLabel={labels.mediaEmpty}
        meta={
          conditionLabel ||
          showLogisticsPills ||
          deliveryLine ||
          madeToOrderLine ||
          sellersFromLine ||
          deliversTodayPill ? (
            <div className="flex flex-col gap-0.5">
              {sellersFromLine ? (
                <span
                  className="text-xs font-medium text-text-2"
                  data-testid="listing-card-sellers-from"
                >
                  {sellersFromLine}
                </span>
              ) : null}
              {deliversTodayPill ? (
                <span data-testid="listing-card-delivers-today" className="w-fit">
                  <Badge variant="public" label={deliversTodayPill} />
                </span>
              ) : null}
              {madeToOrderLine ? (
                <span
                  className="font-semibold text-text-2"
                  data-testid="listing-card-made-to-order"
                >
                  {madeToOrderLine}
                </span>
              ) : null}
              {deliveryLine ? (
                <span
                  className="font-semibold text-success"
                  data-testid="listing-card-delivery"
                  suppressHydrationWarning
                >
                  {deliveryLine}
                </span>
              ) : null}
              {showLogisticsPills && labels.logistics ? (
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

  return (
    <div ref={cardRef} className="relative min-w-0" data-testid="listing-card">
      {card}
      <Link
        href={href}
        className="absolute inset-0 z-[1] rounded-lg focus-visible:outline-none focus-visible:shadow-focusRing"
        aria-label={listing.title}
        data-testid="listing-card-link"
      />
    </div>
  );
}
