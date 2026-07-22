import { Pill } from "@vergeo/ui/src/pill";
import { tokens } from "@vergeo/ui/tokens";

import type { CatalogListing } from "./listing-grid";

export type LogisticsPillLabels = {
  nearest: string;
  belowMedian: string;
  delivery: string;
  pickup: string;
};

export function catalogLogisticsLabels(t: (key: string) => string): LogisticsPillLabels {
  return {
    nearest: t("plp.card.pill.nearest"),
    belowMedian: t("plp.card.pill.belowMedian"),
    delivery: t("plp.card.pill.delivery"),
    pickup: t("plp.card.pill.pickup"),
  };
}

function formatDistance(meters: number): string {
  if (meters < 1000) {
    return `${Math.round(meters)} m`;
  }
  return `${(meters / 1000).toFixed(1)} km`;
}

export type LogisticsPillItem = {
  key: string;
  label: string;
  color: string;
};

/** Derive honest logistics pills from listing API fields — never invent tags. */
export function buildLogisticsPills(
  listing: CatalogListing,
  labels: LogisticsPillLabels,
): LogisticsPillItem[] {
  const pills: LogisticsPillItem[] = [];

  if (listing.distanceM !== null) {
    pills.push({
      key: "nearest",
      label: labels.nearest.replace("{distance}", formatDistance(listing.distanceM)),
      color: tokens.colors.primary,
    });
  }

  if (listing.belowMedian) {
    pills.push({
      key: "below-median",
      label: labels.belowMedian,
      color: tokens.colors.accent,
    });
  }

  if (listing.deliveryAvailable) {
    pills.push({
      key: "delivery",
      label: labels.delivery,
      color: tokens.colors.success,
    });
  }

  if (listing.pickupAvailable) {
    pills.push({
      key: "pickup",
      label: labels.pickup,
      color: tokens.colors.info,
    });
  }

  return pills;
}

type ListingLogisticsPillsProps = {
  listing: CatalogListing;
  labels: LogisticsPillLabels;
};

export function ListingLogisticsPills({ listing, labels }: ListingLogisticsPillsProps) {
  const pills = buildLogisticsPills(listing, labels);

  if (pills.length === 0) {
    return null;
  }

  return (
    <div className="flex flex-wrap gap-1.5" data-testid="listing-logistics-pills">
      {pills.map((pill) => (
        <Pill key={pill.key} label={pill.label} color={pill.color} />
      ))}
    </div>
  );
}
