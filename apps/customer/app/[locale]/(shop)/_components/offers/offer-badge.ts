/** W8 offers (flag `bundles`) — badge copy shared by cards, the PDP and the cart. */

export type OfferBadge = {
  offer_id: string;
  offer_type: "bxgy" | "bundle" | "buy_n_pay_m" | "free_gift" | string;
  buy_qty?: number | null;
  get_qty?: number | null;
  buy_n?: number | null;
  pay_m?: number | null;
  addon_percent_off?: number | null;
  bundle_pricing?: string | null;
};

/** Raw ICU-ish templates (read with `t.raw`) so they cross the RSC boundary as strings. */
export type OfferBadgeLabels = {
  bxgy: string;
  bundlePercent: string;
  bundleFixed: string;
  buyNPayM: string;
  freeGift: string;
};

function fill(template: string, values: Record<string, number>): string {
  return Object.entries(values).reduce(
    (text, [key, value]) => text.split(`{${key}}`).join(String(value)),
    template,
  );
}

/** Short badge text, e.g. "Buy 2 get 1 free", "-75% add-ons", "Free gift"; null if unknown. */
export function offerBadgeLabel(badge: OfferBadge, labels: OfferBadgeLabels): string | null {
  switch (badge.offer_type) {
    case "bxgy":
      return badge.buy_qty && badge.get_qty
        ? fill(labels.bxgy, { buy: badge.buy_qty, get: badge.get_qty })
        : null;
    case "bundle":
      return badge.bundle_pricing === "addon_percent_off" && badge.addon_percent_off
        ? fill(labels.bundlePercent, { percent: badge.addon_percent_off })
        : labels.bundleFixed;
    case "buy_n_pay_m":
      return badge.buy_n && badge.pay_m
        ? fill(labels.buyNPayM, { n: badge.buy_n, m: badge.pay_m })
        : null;
    case "free_gift":
      return labels.freeGift;
    default:
      return null;
  }
}

/** Serializable badge labels from a translator scoped to the `catalog` namespace. */
export function buildOfferBadgeLabels(raw: (key: string) => unknown): OfferBadgeLabels {
  return {
    bxgy: String(raw("offers.badge.bxgy")),
    bundlePercent: String(raw("offers.badge.bundlePercent")),
    bundleFixed: String(raw("offers.badge.bundleFixed")),
    buyNPayM: String(raw("offers.badge.buyNPayM")),
    freeGift: String(raw("offers.badge.freeGift")),
  };
}
