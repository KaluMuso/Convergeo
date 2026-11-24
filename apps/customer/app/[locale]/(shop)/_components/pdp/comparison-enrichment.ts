import {
  estimateDelivery,
  formatDeliveryEstimate,
  type DeliveryEstimateLabels,
} from "../../../../../lib/delivery-estimate";

import { getStockLabel, type BuyBoxListing } from "./buy-box";

import type { ComparisonListing, ComparisonLabels } from "./comparison";
import type { ProductListing } from "./pdp-interactive-body";

export type ComparisonValueChip = "cod" | "escrow";

export type ComparisonValueRow = {
  stockLabel: string;
  etaLabel: string | null;
  chips: ComparisonValueChip[];
};

export function listingToBuyBoxSnapshot(listing: ProductListing): BuyBoxListing {
  return {
    id: listing.id,
    title: listing.title,
    priceNgwee: listing.priceNgwee,
    condition: listing.condition,
    productClass: listing.productClass,
    stockMode: listing.stockMode,
    stockQty: listing.stockQty,
    lowStockThreshold: listing.lowStockThreshold,
    moq: listing.moq,
    inStock: listing.inStock,
    saleUnit: listing.saleUnit,
    unitStepMilli: listing.unitStepMilli,
    minSteps: listing.minSteps,
    leadTimeDays: listing.leadTimeDays,
    vendorCapacityPerWeek: listing.vendorCapacityPerWeek,
  };
}

export function buildComparisonValueRow(
  listing: ProductListing,
  comparison: ComparisonListing,
  labels: {
    buyBox: Parameters<typeof getStockLabel>[1] & {
      lowStockLabel: (count: number) => string;
    };
    delivery: DeliveryEstimateLabels;
    madeToOrderDays: (days: number) => string;
  },
  options: { codCapNgwee: number; codChipsEnabled: boolean },
): ComparisonValueRow {
  const { codCapNgwee, codChipsEnabled } = options;
  const buyBox = listingToBuyBoxSnapshot(listing);
  const stockLabel = getStockLabel(buyBox, labels.buyBox);
  const fulfilmentMode =
    listing.fulfilmentMode === "made_to_order" || listing.leadTimeDays
      ? "made_to_order"
      : "stocked";
  const etaEstimate = formatDeliveryEstimate(
    estimateDelivery({
      deliveryAvailable: comparison.deliveryAvailable,
      pickupAvailable: comparison.pickupAvailable,
      fulfilmentMode,
      leadTimeDays: listing.leadTimeDays,
      inStock: listing.inStock,
    }),
    labels.delivery,
  );
  const etaLabel =
    fulfilmentMode === "made_to_order" && listing.leadTimeDays
      ? labels.madeToOrderDays(listing.leadTimeDays)
      : etaEstimate;

  const chips: ComparisonValueChip[] = ["escrow"];
  const lineTotal = comparison.priceNgwee;
  if (codChipsEnabled && comparison.deliveryAvailable && lineTotal <= codCapNgwee) {
    chips.unshift("cod");
  }

  return { stockLabel, etaLabel, chips };
}

export function mergeComparisonListings(
  comparisonListings: ComparisonListing[],
  productById: Map<string, ProductListing>,
  valueById: Map<string, ComparisonValueRow>,
): ComparisonListing[] {
  return comparisonListings.map((row) => {
    const product = productById.get(row.id);
    const value = valueById.get(row.id);
    return {
      ...row,
      valueStockLabel: value?.stockLabel,
      valueEtaLabel: value?.etaLabel,
      valueChips: value?.chips,
      fulfilmentMode: product?.fulfilmentMode,
      inStock: product?.inStock,
      leadTimeDays: product?.leadTimeDays,
    };
  });
}
