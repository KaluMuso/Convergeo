// M10-P17: client-side mirror of the server's resolve_unit_price (M10-P12) so the
// event page shows the price the server will actually charge — base, active
// early-bird, and qualifying group tiers, lowest wins. Display only; the server
// stays authoritative at checkout.

export type DisplayTier = { min_qty: number; price_ngwee: number };

export type DisplayPricing = {
  price_ngwee: number;
  early_bird_price_ngwee: number | null;
  early_bird_until: string | null;
  tiers: DisplayTier[];
};

export function isEarlyBirdActive(pricing: DisplayPricing, now: Date): boolean {
  return (
    pricing.early_bird_price_ngwee !== null &&
    pricing.early_bird_until !== null &&
    now.getTime() < Date.parse(pricing.early_bird_until)
  );
}

/** Lowest applicable per-unit price (ngwee) for the given quantity. */
export function resolveUnitPriceNgwee(pricing: DisplayPricing, qty: number, now: Date): number {
  const candidates = [pricing.price_ngwee];
  if (isEarlyBirdActive(pricing, now) && pricing.early_bird_price_ngwee !== null) {
    candidates.push(pricing.early_bird_price_ngwee);
  }
  for (const tier of pricing.tiers) {
    if (qty >= tier.min_qty) {
      candidates.push(tier.price_ngwee);
    }
  }
  return Math.min(...candidates);
}

/** The smallest min_qty tier that is not yet reached at `qty` (for an upsell hint). */
export function nextTier(pricing: DisplayPricing, qty: number): DisplayTier | null {
  const upcoming = pricing.tiers
    .filter((tier) => tier.min_qty > qty)
    .sort((a, b) => a.min_qty - b.min_qty);
  return upcoming[0] ?? null;
}
