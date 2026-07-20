/**
 * Honest multi-seller price framing for the buy box.
 * Never invents a “was” price — only compares live offer prices.
 *
 * Returns a structured result so ICU messages can be formatted with
 * `t("…", { diff })` on the client (avoid calling `t` without ICU values).
 */
export type OfferPriceContext = { kind: "lowest" } | { kind: "more"; diffNgwee: number };

export function buildOfferPriceContext(
  selectedPriceNgwee: number,
  offerPricesNgwee: number[],
): OfferPriceContext | null {
  if (offerPricesNgwee.length < 2) {
    return null;
  }

  const lowest = Math.min(...offerPricesNgwee);
  if (!Number.isFinite(lowest)) {
    return null;
  }

  if (selectedPriceNgwee <= lowest) {
    return { kind: "lowest" };
  }

  return { kind: "more", diffNgwee: selectedPriceNgwee - lowest };
}
