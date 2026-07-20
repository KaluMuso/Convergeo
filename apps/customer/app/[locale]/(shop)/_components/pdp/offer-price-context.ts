import { formatK } from "@vergeo/i18n";

/**
 * Honest multi-seller price framing for the buy box.
 * Never invents a “was” price — only compares live offer prices.
 */
export function buildOfferPriceContext(
  selectedPriceNgwee: number,
  offerPricesNgwee: number[],
  labels: {
    lowestPrice: string;
    moreThanLowest: string;
  },
): string | null {
  if (offerPricesNgwee.length < 2) {
    return null;
  }

  const lowest = Math.min(...offerPricesNgwee);
  if (!Number.isFinite(lowest)) {
    return null;
  }

  if (selectedPriceNgwee <= lowest) {
    return labels.lowestPrice;
  }

  const diff = selectedPriceNgwee - lowest;
  return labels.moreThanLowest.replace("{diff}", formatK(diff));
}
