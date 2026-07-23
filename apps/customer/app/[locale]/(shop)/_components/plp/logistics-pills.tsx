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

export type FulfillmentFlags = {
  deliveryAvailable: boolean;
  pickupAvailable: boolean;
};

/** Delivery/pickup pills only — for PDP comparison and trust panel. */
export function buildFulfillmentPills(
  flags: FulfillmentFlags,
  labels: Pick<LogisticsPillLabels, "delivery" | "pickup">,
): LogisticsPillItem[] {
  if (!flags.deliveryAvailable && !flags.pickupAvailable) {
    return [];
  }
  return buildLogisticsPills(
    {
      id: "",
      title: "",
      productSlug: "",
      vendorName: "",
      priceNgwee: 0,
      condition: "new",
      inStock: true,
      imagePublicId: null,
      rating: 0,
      reviewCount: 0,
      distanceM: null,
      belowMedian: false,
      deliveryAvailable: flags.deliveryAvailable,
      pickupAvailable: flags.pickupAvailable,
    },
    {
      nearest: "",
      belowMedian: "",
      delivery: labels.delivery,
      pickup: labels.pickup,
    },
  );
}

type FulfillmentLogisticsPillsProps = FulfillmentFlags & {
  labels: Pick<LogisticsPillLabels, "delivery" | "pickup">;
  className?: string;
  testId?: string;
};

export function FulfillmentLogisticsPills({
  deliveryAvailable,
  pickupAvailable,
  labels,
  className,
  testId = "fulfillment-logistics-pills",
}: FulfillmentLogisticsPillsProps) {
  const pills = buildFulfillmentPills({ deliveryAvailable, pickupAvailable }, labels);

  if (pills.length === 0) {
    return null;
  }

  return (
    <div className={className ?? "flex flex-wrap gap-1.5"} data-testid={testId}>
      {pills.map((pill) => (
        <Pill key={pill.key} label={pill.label} color={pill.color} />
      ))}
    </div>
  );
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
