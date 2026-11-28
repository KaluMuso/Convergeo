"use client";

import { formatK } from "@vergeo/i18n";
import { Badge } from "@vergeo/ui/src/badge";
import { CornerRibbon } from "@vergeo/ui/src/corner-ribbon";
import { useTranslations } from "next-intl";
import { useCallback, useEffect, useMemo, useState } from "react";

import { catalogDeliveryLabels } from "../plp/delivery-labels";
import { FulfillmentLogisticsPills, type LogisticsPillLabels } from "../plp/logistics-pills";

import { type BuyBoxLabels } from "./buy-box";
import { buildComparisonValueRow, mergeComparisonListings } from "./comparison-enrichment";
import { shouldShowComparison } from "./comparison-visibility";
import { ConditionBadge, type ListingCondition } from "./condition-badge";

import type { ComparisonValueChip } from "./comparison-enrichment";
import type { ProductListing } from "./pdp-interactive-body";

export { shouldShowComparison } from "./comparison-visibility";

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
  deliveryFeeNgwee?: number | null;
  deliveryFunding?: "customer" | "vendor" | "platform" | null;
  valueStockLabel?: string;
  valueEtaLabel?: string | null;
  valueChips?: ComparisonValueChip[];
};

export type ComparisonLabels = {
  heading: string;
  vendorCount: string;
  sortLabel: string;
  sortPrice: string;
  sortTotal: string;
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
  conditionUsed: string;
  usingFallbackLocation: string;
  /** Shown on the cheapest offer card/row when multi-seller. */
  lowestPriceBadge: string;
  deliveryFeeFree: string;
  deliveryFeePlus: string;
  chipCod: string;
  chipEscrow: string;
  readyIn: string;
};

type ComparisonSort = "price" | "distance" | "total";

export function comparisonTotalNgwee(listing: ComparisonListing): number | null {
  if (listing.deliveryFeeNgwee == null) {
    return listing.deliveryAvailable ? null : listing.priceNgwee;
  }
  return listing.priceNgwee + listing.deliveryFeeNgwee;
}

type GeoCoords = {
  lat: number;
  lng: number;
};

function conditionLabel(
  condition: ListingCondition,
  labels: Pick<ComparisonLabels, "conditionNew" | "conditionRefurbished" | "conditionUsed">,
): string {
  if (condition === "new") {
    return labels.conditionNew;
  }
  if (condition === "used") {
    return labels.conditionUsed;
  }
  return labels.conditionRefurbished;
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

export function formatDistanceMeters(
  meters: number,
  units?: {
    meters: (value: number) => string;
    kilometers: (value: number) => string;
  },
): string {
  if (units) {
    if (meters < 1000) {
      return units.meters(Math.round(meters));
    }
    return units.kilometers(Number((meters / 1000).toFixed(1)));
  }
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

function formatDeliveryFeeLabel(
  listing: ComparisonListing,
  labels: Pick<ComparisonLabels, "deliveryFeeFree" | "deliveryFeePlus">,
): string | null {
  if (!listing.deliveryAvailable) {
    return null;
  }
  if (listing.deliveryFeeNgwee == null) {
    return null;
  }
  if (listing.deliveryFeeNgwee === 0) {
    return labels.deliveryFeeFree;
  }
  return labels.deliveryFeePlus.replace("{fee}", formatK(listing.deliveryFeeNgwee));
}

function ComparisonValueExtras({
  listing,
  labels,
}: {
  listing: ComparisonListing;
  labels: ComparisonLabels;
}) {
  const deliveryFee = formatDeliveryFeeLabel(listing, labels);
  const chipLabel = (chip: ComparisonValueChip) =>
    chip === "cod" ? labels.chipCod : labels.chipEscrow;
  return (
    <div className="mt-2 flex flex-col gap-1.5 text-xs text-text-2">
      {listing.valueStockLabel ? (
        <p className="m-0 font-medium text-text">{listing.valueStockLabel}</p>
      ) : null}
      {listing.valueEtaLabel ? <p className="m-0">{listing.valueEtaLabel}</p> : null}
      {deliveryFee ? <p className="m-0">{deliveryFee}</p> : null}
      {listing.valueChips && listing.valueChips.length > 0 ? (
        <ul className="m-0 flex list-none flex-wrap gap-1.5 p-0">
          {listing.valueChips.map((chip) => (
            <li
              key={chip}
              className="rounded-full border border-border bg-bg px-2 py-0.5 text-micro font-medium text-text"
            >
              {chipLabel(chip)}
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
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

    if (sort === "total") {
      const leftTotal = comparisonTotalNgwee(left.listing);
      const rightTotal = comparisonTotalNgwee(right.listing);
      const leftKey = leftTotal ?? Number.POSITIVE_INFINITY;
      const rightKey = rightTotal ?? Number.POSITIVE_INFINITY;
      if (leftKey !== rightKey) {
        return leftKey - rightKey;
      }
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

type ComparisonEnrichment = {
  products: ProductListing[];
  codCapNgwee: number;
  codChipsEnabled: boolean;
  buyBoxLabels: BuyBoxLabels;
};

type ComparisonProps = {
  listings: ComparisonListing[];
  selectedListingId: string | null;
  labels: ComparisonLabels;
  logisticsPillLabels: Pick<LogisticsPillLabels, "delivery" | "pickup">;
  onSelect: (listingId: string) => void;
  enrichment?: ComparisonEnrichment;
};

export function Comparison({
  listings,
  selectedListingId,
  labels,
  logisticsPillLabels,
  onSelect,
  enrichment,
}: ComparisonProps) {
  const t = useTranslations("catalog");
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

  const resolvedListings = useMemo(() => {
    if (!enrichment) {
      return listings;
    }
    const productById = new Map(enrichment.products.map((product) => [product.id, product]));
    const deliveryEstimateLabels = catalogDeliveryLabels((key) => t.raw(key));
    const valueById = new Map(
      listings
        .map((row) => {
          const product = productById.get(row.id);
          if (!product) {
            return null;
          }
          return [
            row.id,
            buildComparisonValueRow(
              product,
              row,
              {
                buyBox: {
                  ...enrichment.buyBoxLabels,
                  lowStockLabel: (count) => t("pdp.buyBox.lowStock", { count }),
                },
                delivery: deliveryEstimateLabels,
                madeToOrderDays: (days) => t("pdp.value.madeToOrderDays", { days }),
              },
              {
                codCapNgwee: enrichment.codCapNgwee,
                codChipsEnabled: enrichment.codChipsEnabled,
              },
            ),
          ] as const;
        })
        .filter(
          (entry): entry is readonly [string, ReturnType<typeof buildComparisonValueRow>] =>
            entry !== null,
        ),
    );
    return mergeComparisonListings(listings, productById, valueById);
  }, [enrichment, listings, t]);

  const sortedListings = useMemo(
    () => sortComparisonListings(resolvedListings, sort, userCoords),
    [resolvedListings, sort, userCoords],
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

  const formatLocalizedDistance = useCallback(
    (meters: number) =>
      formatDistanceMeters(meters, {
        meters: (value) => t("comparison.distanceMeters", { value }),
        kilometers: (value) => t("comparison.distanceKilometers", { value }),
      }),
    [t],
  );

  if (!shouldShowComparison(listings.length)) {
    return null;
  }

  return (
    <section
      id="compare"
      data-testid="pdp-comparison"
      className="scroll-mt-20 rounded border border-border bg-surface"
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
            <option value="total">{labels.sortTotal}</option>
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
              ? labels.distance.replace("{distance}", formatLocalizedDistance(distanceM))
              : null;
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
                    label={conditionLabel(listing.condition, labels)}
                  />
                  {distanceLabel ? (
                    <span className="text-xs text-text-2">{distanceLabel}</span>
                  ) : null}
                  <FulfillmentLogisticsPills
                    deliveryAvailable={listing.deliveryAvailable}
                    pickupAvailable={listing.pickupAvailable}
                    labels={logisticsPillLabels}
                  />
                </div>
                <ComparisonValueExtras listing={listing} labels={labels} />
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
              <th className="px-4 py-2 font-medium">{labels.sortDistance}</th>
              <th className="px-4 py-2 font-medium">{labels.fulfillment}</th>
              <th className="sr-only">{labels.selectListing}</th>
            </tr>
          </thead>
          <tbody>
            {sortedListings.map((listing) => {
              const distanceM = distanceByListingId.get(listing.id);
              const distanceLabel =
                distanceM !== undefined
                  ? labels.distance.replace("{distance}", formatLocalizedDistance(distanceM))
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
                      label={conditionLabel(listing.condition, labels)}
                    />
                  </td>
                  <td className="px-4 py-3 align-top text-text-2">{distanceLabel}</td>
                  <td className="px-4 py-3 align-top">
                    <div className="flex flex-col gap-2">
                      <FulfillmentLogisticsPills
                        deliveryAvailable={listing.deliveryAvailable}
                        pickupAvailable={listing.pickupAvailable}
                        labels={logisticsPillLabels}
                      />
                      <ComparisonValueExtras listing={listing} labels={labels} />
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
