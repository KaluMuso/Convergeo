"use client";

import { formatK } from "@vergeo/i18n";
import { Badge } from "@vergeo/ui/src/badge";
import { CornerRibbon } from "@vergeo/ui/src/corner-ribbon";
import { useTranslations } from "next-intl";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { BuyBox, type BuyBoxLabels, type BuyBoxListing } from "./buy-box";
import { BuyerTrustPanel } from "./buyer-trust-panel";
import { ConditionBadge, type ListingCondition } from "./condition-badge";
import { PdpGallery } from "./gallery";
import { buildOfferPriceContext } from "./offer-price-context";
import { PdpWishlistButton } from "./pdp-wishlist-button";
import { StickyMobileAtc } from "./sticky-mobile-atc";
import { useListingPurchase } from "./use-listing-purchase";
import { VendorBlock } from "./vendor-block";

import type { PdpGalleryLabelStrings } from "./gallery-labels";

export const LUSAKA_CBD_LAT = -15.4167;
export const LUSAKA_CBD_LNG = 28.2833;

export type ComparisonListing = {
  id: string;
  priceNgwee: number;
  condition: ListingCondition;
  vendor: {
    id: string;
    slug: string;
    displayName: string;
    preferredBadge: boolean;
    ratingAvg: number | null;
    ratingCount: number;
    lat: number | null;
    lng: number | null;
    landmark: string | null;
  };
  deliveryAvailable: boolean;
  pickupAvailable: boolean;
};

export type ComparisonLabels = {
  heading: string;
  vendorCount: string;
  sortLabel: string;
  sortPrice: string;
  sortDistance: string;
  price: string;
  condition: string;
  distance: string;
  vendor: string;
  fulfillment: string;
  delivery: string;
  pickup: string;
  selectListing: string;
  selectedListing: string;
  preferredBadge: string;
  noReviews: string;
  rating: string;
  conditionNew: string;
  conditionRefurbished: string;
  usingFallbackLocation: string;
  /** Shown on the cheapest offer card/row when multi-seller. */
  lowestPriceBadge: string;
};

type ComparisonSort = "price" | "distance";

type GeoCoords = {
  lat: number;
  lng: number;
};

export type ProductListing = {
  id: string;
  title: string;
  priceNgwee: number;
  condition: ListingCondition;
  stockMode: "tracked" | "always_available";
  stockQty: number | null;
  moq: number;
  inStock: boolean;
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
  comparePageLabel: string;
};

export function shouldShowComparison(listingCount: number): boolean {
  return listingCount > 1;
}

export function haversineMeters(lat1: number, lng1: number, lat2: number, lng2: number): number {
  const earthRadiusM = 6_371_000;
  const phi1 = (lat1 * Math.PI) / 180;
  const phi2 = (lat2 * Math.PI) / 180;
  const dPhi = ((lat2 - lat1) * Math.PI) / 180;
  const dLambda = ((lng2 - lng1) * Math.PI) / 180;
  const a = Math.sin(dPhi / 2) ** 2 + Math.cos(phi1) * Math.cos(phi2) * Math.sin(dLambda / 2) ** 2;
  return earthRadiusM * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
}

export function formatDistanceMeters(meters: number): string {
  if (meters < 1000) {
    return `${Math.round(meters)} m`;
  }
  return `${(meters / 1000).toFixed(1)} km`;
}

export function resolveUserCoords(geo: GeoCoords | null, permissionDenied: boolean): GeoCoords {
  if (geo && !permissionDenied) {
    return geo;
  }
  return { lat: LUSAKA_CBD_LAT, lng: LUSAKA_CBD_LNG };
}

export function sortComparisonListings(
  listings: ComparisonListing[],
  sort: ComparisonSort,
  userCoords: GeoCoords,
): ComparisonListing[] {
  const withDistance = listings.map((listing, index) => {
    const lat = listing.vendor.lat;
    const lng = listing.vendor.lng;
    const distanceM =
      lat !== null && lng !== null
        ? haversineMeters(userCoords.lat, userCoords.lng, lat, lng)
        : Number.POSITIVE_INFINITY;
    return { listing, index, distanceM };
  });

  const sorted = [...withDistance].sort((left, right) => {
    if (sort === "price") {
      if (left.listing.priceNgwee !== right.listing.priceNgwee) {
        return left.listing.priceNgwee - right.listing.priceNgwee;
      }
      return left.index - right.index;
    }

    if (left.distanceM !== right.distanceM) {
      return left.distanceM - right.distanceM;
    }
    if (left.listing.priceNgwee !== right.listing.priceNgwee) {
      return left.listing.priceNgwee - right.listing.priceNgwee;
    }
    return left.index - right.index;
  });

  return sorted.map((entry) => entry.listing);
}

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

type ComparisonProps = {
  listings: ComparisonListing[];
  selectedListingId: string | null;
  labels: ComparisonLabels;
  onSelect: (listingId: string) => void;
};

export function Comparison({ listings, selectedListingId, labels, onSelect }: ComparisonProps) {
  const [sort, setSort] = useState<ComparisonSort>("price");
  const [geo, setGeo] = useState<GeoCoords | null>(null);
  const [permissionDenied, setPermissionDenied] = useState(false);

  useEffect(() => {
    if (!navigator.geolocation) {
      setPermissionDenied(true);
      return;
    }

    navigator.geolocation.getCurrentPosition(
      (position) => {
        setGeo({
          lat: position.coords.latitude,
          lng: position.coords.longitude,
        });
      },
      () => {
        setPermissionDenied(true);
      },
      { enableHighAccuracy: false, maximumAge: 60_000, timeout: 8_000 },
    );
  }, []);

  const userCoords = useMemo(
    () => resolveUserCoords(geo, permissionDenied),
    [geo, permissionDenied],
  );
  const usingFallbackLocation = geo === null || permissionDenied;

  const sortedListings = useMemo(
    () => sortComparisonListings(listings, sort, userCoords),
    [listings, sort, userCoords],
  );

  const lowestPriceNgwee = useMemo(() => {
    if (listings.length === 0) {
      return null;
    }
    return listings.reduce(
      (lowest, listing) => Math.min(lowest, listing.priceNgwee),
      listings[0]?.priceNgwee ?? Number.POSITIVE_INFINITY,
    );
  }, [listings]);

  const distanceByListingId = useMemo(() => {
    const distances = new Map<string, number>();
    for (const listing of listings) {
      const lat = listing.vendor.lat;
      const lng = listing.vendor.lng;
      if (lat === null || lng === null) {
        continue;
      }
      distances.set(listing.id, haversineMeters(userCoords.lat, userCoords.lng, lat, lng));
    }
    return distances;
  }, [listings, userCoords]);

  if (!shouldShowComparison(listings.length)) {
    return null;
  }

  return (
    <section
      data-testid="pdp-comparison"
      className="rounded border border-border bg-surface"
      style={{ borderRadius: "var(--r)" }}
    >
      <div className="flex flex-col gap-3 border-b border-border px-4 py-3">
        <div className="flex flex-col gap-1">
          <h2 className="font-display text-lg font-semibold text-text">{labels.heading}</h2>
          <p className="text-sm text-text-2">
            {labels.vendorCount.replace("{count}", String(listings.length))}
          </p>
          {usingFallbackLocation ? (
            <p className="text-xs text-text-2">{labels.usingFallbackLocation}</p>
          ) : null}
        </div>

        <div className="flex items-center gap-2">
          <label htmlFor="comparison-sort" className="text-sm text-text-2">
            {labels.sortLabel}
          </label>
          <select
            id="comparison-sort"
            data-testid="comparison-sort"
            value={sort}
            onChange={(event) => setSort(event.target.value as ComparisonSort)}
            className="min-h-11 flex-1 rounded border border-border bg-bg px-3 text-sm text-text"
            style={{ borderRadius: "var(--r)" }}
          >
            <option value="price">{labels.sortPrice}</option>
            <option value="distance">{labels.sortDistance}</option>
          </select>
        </div>
      </div>

      {/* Mobile: stacked seller cards (audit E10) */}
      <ul className="flex list-none flex-col gap-3 p-4 lg:hidden" data-testid="pdp-compare-cards">
        {sortedListings.map((listing) => {
          const distanceM = distanceByListingId.get(listing.id);
          const distanceLabel =
            distanceM !== undefined
              ? labels.distance.replace("{distance}", formatDistanceMeters(distanceM))
              : "—";
          const isSelected = listing.id === selectedListingId;
          const ratingLabel =
            listing.vendor.ratingAvg !== null && listing.vendor.ratingCount > 0
              ? labels.rating
                  .replace("{rating}", String(listing.vendor.ratingAvg))
                  .replace("{count}", String(listing.vendor.ratingCount))
              : labels.noReviews;

          return (
            <li key={listing.id}>
              <button
                type="button"
                data-testid={`comparison-card-${listing.id}`}
                aria-pressed={isSelected}
                aria-label={isSelected ? labels.selectedListing : labels.selectListing}
                onClick={() => onSelect(listing.id)}
                className={[
                  "w-full rounded border p-4 text-left transition-colors",
                  isSelected
                    ? "border-primary bg-primary/5 ring-2 ring-primary/20"
                    : "border-border bg-bg hover:bg-surface",
                ].join(" ")}
                style={{ borderRadius: "var(--r)" }}
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="font-medium text-text">{listing.vendor.displayName}</span>
                      {listing.vendor.preferredBadge ? (
                        <CornerRibbon trust="preferred" trustLabel={labels.preferredBadge} />
                      ) : null}
                      {lowestPriceNgwee !== null && listing.priceNgwee === lowestPriceNgwee ? (
                        <span data-testid={`comparison-lowest-${listing.id}`}>
                          <Badge variant="public" label={labels.lowestPriceBadge} />
                        </span>
                      ) : null}
                    </div>
                    <p className="mt-1 font-mono text-xl font-semibold text-[var(--price)]">
                      {formatK(listing.priceNgwee)}
                    </p>
                    <p className="mt-1 text-xs text-text-2">{ratingLabel}</p>
                  </div>
                  <span className="shrink-0 text-sm font-medium text-primary">
                    {isSelected ? labels.selectedListing : labels.selectListing}
                  </span>
                </div>
                <div className="mt-3 flex flex-wrap items-center gap-2">
                  <ConditionBadge
                    condition={listing.condition}
                    label={
                      listing.condition === "new"
                        ? labels.conditionNew
                        : labels.conditionRefurbished
                    }
                  />
                  <span className="text-xs text-text-2">{distanceLabel}</span>
                  {listing.deliveryAvailable ? (
                    <Badge variant="public" label={labels.delivery} />
                  ) : null}
                  {listing.pickupAvailable ? (
                    <Badge variant="public" label={labels.pickup} />
                  ) : null}
                </div>
              </button>
            </li>
          );
        })}
      </ul>

      {/* Desktop: comparison table */}
      <div className="hidden overflow-x-auto lg:block">
        <table className="min-w-full text-left text-sm">
          <thead className="bg-bg text-text-2">
            <tr>
              <th className="px-4 py-2 font-medium">{labels.vendor}</th>
              <th className="px-4 py-2 font-medium">{labels.price}</th>
              <th className="px-4 py-2 font-medium">{labels.condition}</th>
              <th className="px-4 py-2 font-medium">{labels.distance}</th>
              <th className="px-4 py-2 font-medium">{labels.fulfillment}</th>
              <th className="sr-only">{labels.selectListing}</th>
            </tr>
          </thead>
          <tbody>
            {sortedListings.map((listing) => {
              const distanceM = distanceByListingId.get(listing.id);
              const distanceLabel =
                distanceM !== undefined
                  ? labels.distance.replace("{distance}", formatDistanceMeters(distanceM))
                  : "—";
              const isSelected = listing.id === selectedListingId;
              const ratingLabel =
                listing.vendor.ratingAvg !== null && listing.vendor.ratingCount > 0
                  ? labels.rating
                      .replace("{rating}", String(listing.vendor.ratingAvg))
                      .replace("{count}", String(listing.vendor.ratingCount))
                  : labels.noReviews;

              return (
                <tr
                  key={listing.id}
                  data-testid={`comparison-row-${listing.id}`}
                  className={isSelected ? "bg-primary/5" : "border-t border-border"}
                >
                  <td className="px-4 py-3 align-top">
                    <div className="flex flex-col gap-1">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="font-medium text-text">{listing.vendor.displayName}</span>
                        {listing.vendor.preferredBadge ? (
                          <CornerRibbon trust="preferred" trustLabel={labels.preferredBadge} />
                        ) : null}
                      </div>
                      <span className="text-xs text-text-2">{ratingLabel}</span>
                    </div>
                  </td>
                  <td className="px-4 py-3 align-top font-medium text-[var(--price)]">
                    <div className="flex flex-col gap-1">
                      <span>{formatK(listing.priceNgwee)}</span>
                      {lowestPriceNgwee !== null && listing.priceNgwee === lowestPriceNgwee ? (
                        <Badge variant="public" label={labels.lowestPriceBadge} />
                      ) : null}
                    </div>
                  </td>
                  <td className="px-4 py-3 align-top">
                    <ConditionBadge
                      condition={listing.condition}
                      label={
                        listing.condition === "new"
                          ? labels.conditionNew
                          : labels.conditionRefurbished
                      }
                    />
                  </td>
                  <td className="px-4 py-3 align-top text-text-2">{distanceLabel}</td>
                  <td className="px-4 py-3 align-top">
                    <div className="flex flex-wrap gap-1">
                      {listing.deliveryAvailable ? (
                        <Badge variant="public" label={labels.delivery} />
                      ) : null}
                      {listing.pickupAvailable ? (
                        <Badge variant="public" label={labels.pickup} />
                      ) : null}
                    </div>
                  </td>
                  <td className="px-4 py-3 align-top">
                    <button
                      type="button"
                      data-testid={`comparison-select-${listing.id}`}
                      aria-pressed={isSelected}
                      aria-label={isSelected ? labels.selectedListing : labels.selectListing}
                      onClick={() => onSelect(listing.id)}
                      className="min-h-11 rounded border border-border px-3 text-sm font-medium text-primary hover:bg-primary/5"
                      style={{ borderRadius: "var(--r)" }}
                    >
                      {isSelected ? labels.selectedListing : labels.selectListing}
                    </button>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </section>
  );
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
  comparisonLabels,
  vendorLabels,
  trustLabels,
  wishlistLabels,
  comparePageLabel,
}: PdpInteractiveBodyProps) {
  const t = useTranslations("catalog");
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
      stockMode: selectedListing.stockMode,
      stockQty: selectedListing.stockQty,
      moq: selectedListing.moq,
      inStock: selectedListing.inStock,
    };
  }, [selectedListing]);

  const purchase = useListingPurchase(buyBoxListing, buyBoxLabels);

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
        stickyAtcVisible ? "pb-20 lg:pb-0" : "",
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
            purchase={purchase}
            buyBoxRef={buyBoxRef}
            seller={{
              displayName: selectedListing.vendor.displayName,
              ratingLabel: sellerRatingLabel,
              preferred: selectedListing.vendor.preferredBadge,
            }}
            priceContextLabel={priceContextLabel}
            compareHref={compareHref}
            compareLabel={comparePageLabel}
            wishlistSlot={
              <PdpWishlistButton
                productId={productId}
                addLabel={wishlistLabels.add}
                removeLabel={wishlistLabels.remove}
                savedAnnounceLabel={wishlistLabels.saved}
              />
            }
          />
          <BuyerTrustPanel
            sellerStatusLabel={t(
              selectedListing.vendor.preferredBadge
                ? "pdp.trust.preferredSeller"
                : "pdp.trust.seller",
              { name: selectedListing.vendor.displayName },
            )}
            deliveryLabel={selectedComparison?.deliveryAvailable ? trustLabels.delivery : null}
            pickupLabel={selectedComparison?.pickupAvailable ? trustLabels.pickup : null}
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
        </div>
      ) : null}

      {buyBoxListing && purchase ? (
        <StickyMobileAtc
          listing={buyBoxListing}
          labels={buyBoxLabels}
          purchase={purchase}
          observeRef={buyBoxRef}
          ariaLabel={t("pdp.stickyAtc.ariaLabel")}
          onVisibleChange={handleStickyVisibleChange}
        />
      ) : null}
    </div>
  );
}
