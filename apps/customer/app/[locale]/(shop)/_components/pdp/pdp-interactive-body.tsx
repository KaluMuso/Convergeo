"use client";

import { formatK } from "@vergeo/i18n";
import dynamic from "next/dynamic";
import { useTranslations } from "next-intl";
import { lazy, Suspense, useCallback, useMemo, useRef, useState } from "react";

import { catalogLogisticsLabels } from "../plp/logistics-pills";

import { BuyBox, type BuyBoxLabels, type BuyBoxListing } from "./buy-box";
import { BuyerTrustPanel } from "./buyer-trust-panel";
import { shouldShowComparison } from "./comparison-visibility";
import { PdpGallery } from "./gallery";
import { buildOfferPriceContext } from "./offer-price-context";
import { PdpWishlistButton } from "./pdp-wishlist-button";
import { useListingPurchase } from "./use-listing-purchase";
import { VendorBlock } from "./vendor-block";

import type { ComparisonLabels, ComparisonListing } from "./comparison";
import type { ListingCondition } from "./condition-badge";
import type { PickupLocationPickerLabels } from "./pickup-location-picker";
import type { SaleUnit } from "../sale-quantity";
import type { ContactVendorLabels } from "./contact-vendor-button";
import type { PdpGalleryLabelStrings } from "./gallery-labels";
import type { RelatedRailsLabels } from "./related-product-rails";
import type { ReportListingLabels } from "./report-listing";
import type { RequestQuoteLabels } from "./request-quote-button";

// Server rendering retains the offer table; a single-seller PDP never loads its module.
const Comparison = dynamic(() => import("./comparison").then((module) => module.Comparison));

/** Lazy — keeps first-load JS on /p/[slug] within the bundle regression budget. */
const ContactVendorButton = dynamic(
  () => import("./contact-vendor-button").then((mod) => mod.ContactVendorButton),
  { ssr: false },
);

const RequestQuoteButton = dynamic(
  () => import("./request-quote-button").then((mod) => mod.RequestQuoteButton),
  { ssr: false },
);

const ReportListing = dynamic(() => import("./report-listing").then((mod) => mod.ReportListing), {
  ssr: false,
});

const RelatedProductRails = lazy(() =>
  import("./related-product-rails").then((module) => ({ default: module.RelatedProductRails })),
);

/** Lazy — measured-unit formatting + sticky chrome stay off the PDP first-load budget. */
const StickyMobileAtc = dynamic(
  () => import("./sticky-mobile-atc").then((mod) => mod.StickyMobileAtc),
  { ssr: false },
);

export type ProductListing = {
  id: string;
  title: string;
  priceNgwee: number;
  condition: ListingCondition;
  productClass: string;
  stockMode: "tracked" | "always_available";
  stockQty: number | null;
  moq: number;
  inStock: boolean;
  saleUnit?: SaleUnit;
  unitStepMilli?: number;
  minSteps?: number;
  leadTimeDays: number | null;
  vendorCapacityPerWeek: number | null;
  vendor: {
    slug: string;
    displayName: string;
    preferredBadge: boolean;
    ratingAvg: number | null;
    ratingCount: number;
    landmark: string | null;
  };
  images: Array<{ publicId: string; alt: string }>;
};

export type PdpInteractiveBodyProps = {
  relatedLabels?: RelatedRailsLabels;
  locale: string;
  productId: string;
  productSlug: string;
  productImages: Array<{ publicId: string; alt: string }>;
  listings: ProductListing[];
  comparisonListings: ComparisonListing[];
  initialListingId?: string;
  singleVendor: boolean;
  cloudName?: string;
  /** Serializable strings only — never pass functions across the RSC boundary. */
  galleryLabels: PdpGalleryLabelStrings;
  buyBoxLabels: BuyBoxLabels;
  pickupLabels: PickupLocationPickerLabels;
  comparisonLabels: ComparisonLabels;
  vendorLabels: {
    heading: string;
    preferredBadge: string;
    noReviews: string;
    viewStore: string;
  };
  trustLabels: {
    delivery: string;
    pickup: string;
    returns: string;
    escrow: string;
  };
  wishlistLabels: {
    add: string;
    remove: string;
    saved: string;
  };
  contactVendorLabels: ContactVendorLabels;
  /** When false, the Contact Vendor CTA is omitted (fail-closed — BLK-202). */
  contactVendorEnabled: boolean;
  requestQuoteLabels: RequestQuoteLabels;
  reportListingLabels: ReportListingLabels;
  comparePageLabel: string;
};

function selectListingById(
  listings: ProductListing[],
  listingId: string | undefined,
): ProductListing | null {
  if (listings.length === 0) {
    return null;
  }
  if (listingId) {
    const selected = listings.find((listing) => listing.id === listingId);
    if (selected) {
      return selected;
    }
  }
  return listings[0] ?? null;
}

export function PdpInteractiveBody({
  locale,
  productId,
  productSlug,
  productImages,
  listings,
  comparisonListings,
  initialListingId,
  singleVendor,
  cloudName,
  galleryLabels,
  buyBoxLabels,
  pickupLabels,
  comparisonLabels,
  vendorLabels,
  trustLabels,
  wishlistLabels,
  contactVendorLabels,
  contactVendorEnabled,
  requestQuoteLabels,
  reportListingLabels,
  comparePageLabel,
  relatedLabels,
}: PdpInteractiveBodyProps) {
  const t = useTranslations("catalog");
  const logisticsPillLabels = useMemo(() => catalogLogisticsLabels(t), [t]);
  const buyBoxRef = useRef<HTMLElement | null>(null);
  const [stickyAtcVisible, setStickyAtcVisible] = useState(false);
  const [selectedListingId, setSelectedListingId] = useState<string | null>(
    () => selectListingById(listings, initialListingId)?.id ?? null,
  );

  const selectedListing = useMemo(
    () => selectListingById(listings, selectedListingId ?? undefined),
    [listings, selectedListingId],
  );

  const selectedComparison = useMemo(
    () => comparisonListings.find((listing) => listing.id === selectedListing?.id) ?? null,
    [comparisonListings, selectedListing?.id],
  );

  const galleryImages = useMemo(() => {
    if (selectedListing && selectedListing.images.length > 0) {
      return selectedListing.images;
    }
    return productImages;
  }, [productImages, selectedListing]);

  const buyBoxListing: BuyBoxListing | null = useMemo(() => {
    if (!selectedListing) {
      return null;
    }
    return {
      id: selectedListing.id,
      title: selectedListing.title,
      priceNgwee: selectedListing.priceNgwee,
      condition: selectedListing.condition,
      productClass: selectedListing.productClass,
      stockMode: selectedListing.stockMode,
      stockQty: selectedListing.stockQty,
      moq: selectedListing.moq,
      inStock: selectedListing.inStock,
      saleUnit: selectedListing.saleUnit,
      unitStepMilli: selectedListing.unitStepMilli,
      minSteps: selectedListing.minSteps,
      leadTimeDays: selectedListing.leadTimeDays,
      vendorCapacityPerWeek: selectedListing.vendorCapacityPerWeek,
    };
  }, [selectedListing]);

  const purchase = useListingPurchase(buyBoxListing, buyBoxLabels, locale);

  const priceContextLabel = useMemo(() => {
    if (!selectedListing) {
      return null;
    }
    const context = buildOfferPriceContext(
      selectedListing.priceNgwee,
      comparisonListings.map((listing) => listing.priceNgwee),
    );
    if (!context) {
      return null;
    }
    if (context.kind === "lowest") {
      return t("pdp.buyBox.lowestPrice");
    }
    return t("pdp.buyBox.moreThanLowest", { diff: formatK(context.diffNgwee) });
  }, [comparisonListings, selectedListing, t]);

  const sellerRatingLabel = useMemo(() => {
    if (!selectedListing) {
      return null;
    }
    if (selectedListing.vendor.ratingAvg !== null && selectedListing.vendor.ratingCount > 0) {
      return t("pdp.vendor.rating", {
        rating: selectedListing.vendor.ratingAvg,
        count: selectedListing.vendor.ratingCount,
      });
    }
    return vendorLabels.noReviews;
  }, [selectedListing, t, vendorLabels.noReviews]);

  const handleSelect = useCallback((listingId: string) => {
    setSelectedListingId(listingId);
  }, []);

  const handleStickyVisibleChange = useCallback((visible: boolean) => {
    setStickyAtcVisible(visible);
  }, []);

  const compareHref = shouldShowComparison(comparisonListings.length)
    ? `/${locale}/compare?product=${encodeURIComponent(productSlug)}`
    : null;

  return (
    /* Mobile (<1024px): gallery → buy-box → compare cards → vendor.
       lg+: two-column grid — gallery left, sticky buy-box right; comparison table + vendor full width. */
    <div
      className={[
        "flex flex-col gap-6 lg:grid lg:grid-cols-[minmax(0,1fr)_minmax(20rem,24rem)] lg:items-start lg:gap-8",
        stickyAtcVisible ? "pb-28 lg:pb-0" : "",
      ]
        .filter(Boolean)
        .join(" ")}
      data-testid="pdp-interactive-body"
    >
      <div className="min-w-0 lg:col-start-1 lg:row-start-1">
        <PdpGallery
          images={galleryImages}
          cloudName={cloudName}
          emptyLabel={galleryLabels.empty}
          previousLabel={galleryLabels.previous}
          nextLabel={galleryLabels.next}
          indicatorLabel={(current, total) => t("pdp.gallery.indicator", { current, total })}
        />
      </div>

      {buyBoxListing && selectedListing && purchase ? (
        <div className="flex flex-col gap-3 lg:sticky lg:top-20 lg:col-start-2 lg:row-start-1">
          <BuyBox
            listing={buyBoxListing}
            singleVendor={singleVendor}
            labels={buyBoxLabels}
            pickupLabels={pickupLabels}
            locale={locale}
            purchase={purchase}
            buyBoxRef={buyBoxRef}
            seller={{
              displayName: selectedListing.vendor.displayName,
              ratingLabel: sellerRatingLabel,
              preferred: selectedListing.vendor.preferredBadge,
            }}
            preferredBadgeLabel={vendorLabels.preferredBadge}
            priceContextLabel={priceContextLabel}
            compareHref={compareHref}
            compareLabel={comparePageLabel}
            wishlistSlot={
              <PdpWishlistButton
                productId={productId}
                productSlug={productSlug}
                addLabel={wishlistLabels.add}
                removeLabel={wishlistLabels.remove}
                savedAnnounceLabel={wishlistLabels.saved}
              />
            }
          />
          {selectedListing.productClass === "E" ? (
            <RequestQuoteButton
              locale={locale}
              listingId={selectedListing.id}
              vendorName={selectedListing.vendor.displayName}
              labels={requestQuoteLabels}
              className="w-full"
            />
          ) : null}
          <BuyerTrustPanel
            sellerStatusLabel={t(
              selectedListing.vendor.preferredBadge
                ? "pdp.trust.preferredSeller"
                : "pdp.trust.seller",
              { name: selectedListing.vendor.displayName },
            )}
            deliveryAvailable={selectedComparison?.deliveryAvailable ?? false}
            pickupAvailable={selectedComparison?.pickupAvailable ?? false}
            logisticsPillLabels={logisticsPillLabels}
            returnsLabel={trustLabels.returns}
            returnsHref={`/${locale}/legal/returns`}
            escrowLabel={trustLabels.escrow}
          />
        </div>
      ) : null}

      {shouldShowComparison(comparisonListings.length) ? (
        <div className="min-w-0 lg:col-span-2">
          <Comparison
            listings={comparisonListings}
            selectedListingId={selectedListingId}
            labels={comparisonLabels}
            logisticsPillLabels={logisticsPillLabels}
            onSelect={handleSelect}
          />
        </div>
      ) : null}

      {selectedListing ? (
        <div className="min-w-0 lg:col-span-2">
          <VendorBlock
            locale={locale}
            vendor={{
              slug: selectedListing.vendor.slug,
              displayName: selectedListing.vendor.displayName,
              preferredBadge: selectedListing.vendor.preferredBadge,
              ratingAvg: selectedListing.vendor.ratingAvg,
              ratingCount: selectedListing.vendor.ratingCount,
              landmark: selectedListing.vendor.landmark,
            }}
            heading={vendorLabels.heading}
            preferredBadgeLabel={vendorLabels.preferredBadge}
            noReviewsLabel={vendorLabels.noReviews}
            ratingLabel={
              selectedListing.vendor.ratingAvg !== null && selectedListing.vendor.ratingCount > 0
                ? t("pdp.vendor.rating", {
                    rating: selectedListing.vendor.ratingAvg,
                    count: selectedListing.vendor.ratingCount,
                  })
                : vendorLabels.noReviews
            }
            viewStoreLabel={vendorLabels.viewStore}
          />
          {contactVendorEnabled ? (
            <ContactVendorButton
              locale={locale}
              listingId={selectedListing.id}
              vendorName={selectedListing.vendor.displayName}
              labels={contactVendorLabels}
            />
          ) : null}
          <ReportListing listingId={selectedListing.id} labels={reportListingLabels} />
        </div>
      ) : null}

      {buyBoxListing && purchase ? (
        <StickyMobileAtc
          listing={buyBoxListing}
          labels={buyBoxLabels}
          purchase={purchase}
          observeRef={buyBoxRef}
          ariaLabel={t("pdp.stickyAtc.ariaLabel")}
          locale={locale}
          onVisibleChange={handleStickyVisibleChange}
        />
      ) : null}
      {relatedLabels ? (
        <div className="min-w-0 lg:col-span-2">
          <Suspense
            fallback={
              <p role="status" className="text-sm text-text-2">
                {relatedLabels.loading}
              </p>
            }
          >
            <RelatedProductRails
              locale={locale}
              slug={productSlug}
              listingId={selectedListing?.id ?? null}
              labels={relatedLabels}
              cloudName={cloudName}
            />
          </Suspense>
        </div>
      ) : null}
    </div>
  );
}
