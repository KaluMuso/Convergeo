export type PriceTier = { min_qty: number; price_ngwee: number };

export type ResolvablePrice = {
  price_ngwee: number;
  early_bird_price_ngwee: number | null;
  early_bird_until: string | null;
  tiers: PriceTier[];
};

/**
 * Client mirror of the server's `resolve_unit_price` (services/tickets/purchase.py):
 * the lowest applicable unit price given the base price, an active early-bird
 * window, and any qualifying group tier. This is presentation only — the server
 * remains the authority at checkout — so the shown total matches what the buyer
 * will actually pay.
 */
export function resolveUnitPriceNgwee(ticket: ResolvablePrice, qty: number, now: Date): number {
  const candidates = [ticket.price_ngwee];
  if (isEarlyBirdActive(ticket, now)) {
    candidates.push(ticket.early_bird_price_ngwee as number);
  }
  for (const tier of ticket.tiers) {
    if (qty >= tier.min_qty) {
      candidates.push(tier.price_ngwee);
    }
  }
  return Math.min(...candidates);
}

/** Whether an early-bird window is currently open (strictly before the cutoff). */
export function isEarlyBirdActive(ticket: ResolvablePrice, now: Date): boolean {
  if (ticket.early_bird_price_ngwee === null || ticket.early_bird_until === null) {
    return false;
  }
  const until = new Date(ticket.early_bird_until).getTime();
  return !Number.isNaN(until) && now.getTime() < until;
}

/** The best group tier that applies at `qty` (lowest price among those met), or null. */
export function bestActiveTier(ticket: ResolvablePrice, qty: number): PriceTier | null {
  let best: PriceTier | null = null;
  for (const tier of ticket.tiers) {
    if (qty >= tier.min_qty && (best === null || tier.price_ngwee < best.price_ngwee)) {
      best = tier;
    }
  }
  return best;
}

/**
 * The nearest group tier the buyer has not yet reached that would lower the
 * current resolved per-unit price — the basis for an "add N more to save" nudge.
 * Returns null when no higher tier improves on what they already pay (e.g. an
 * active early-bird already beats every remaining tier).
 */
export function nextTierUpsell(ticket: ResolvablePrice, qty: number, now: Date): PriceTier | null {
  const current = resolveUnitPriceNgwee(ticket, qty, now);
  let nearest: PriceTier | null = null;
  for (const tier of ticket.tiers) {
    if (tier.min_qty > qty && tier.price_ngwee < current) {
      if (nearest === null || tier.min_qty < nearest.min_qty) {
        nearest = tier;
      }
    }
  }
  return nearest;
}
