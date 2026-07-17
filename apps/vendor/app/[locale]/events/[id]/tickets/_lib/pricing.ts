// Pure client-side validation/mapping for the M10-P16 organiser pricing editor.
// Kept free of React/next-intl so the money rules are unit-testable. The server
// (M10-P15) is authoritative; these guards give fast inline feedback and mirror
// its rejections (discount must be below base, future cutoff, min_qty >= 2).

import { zmwDecimalToNgwee } from "./money";

import type { EarlyBirdInput, PriceTierRow } from "./tickets-client";

export type EarlyBirdDraft = { priceZmw: string; untilLocal: string };
export type TierDraft = { minQty: string; priceZmw: string };

export type EarlyBirdResolution =
  { ok: true; input: EarlyBirdInput } | { ok: false; errorKey: string };

export type TiersResolution = { ok: true; tiers: PriceTierRow[] } | { ok: false; errorKey: string };

function toNgweeOrNull(zmw: string): number | null {
  try {
    return zmwDecimalToNgwee(zmw.replace(/,/g, ""));
  } catch {
    return null;
  }
}

/** A `datetime-local` value ("YYYY-MM-DDTHH:mm", local time) -> UTC ISO, or null. */
export function localDateTimeToIso(local: string): string | null {
  const trimmed = local.trim();
  if (!trimmed) {
    return null;
  }
  const ms = Date.parse(trimmed);
  if (Number.isNaN(ms)) {
    return null;
  }
  return new Date(ms).toISOString();
}

/** An API ISO timestamp -> a `datetime-local` value in local time (empty if absent). */
export function isoToLocalDateTime(iso: string | null): string {
  if (!iso) {
    return "";
  }
  const ms = Date.parse(iso);
  if (Number.isNaN(ms)) {
    return "";
  }
  const d = new Date(ms);
  const pad = (n: number) => String(n).padStart(2, "0");
  return (
    `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}` +
    `T${pad(d.getHours())}:${pad(d.getMinutes())}`
  );
}

/**
 * Resolve the early-bird form: both blank = clear; both set = validate + configure;
 * one of the two = incomplete. Discount must be a positive amount below the base
 * price with a cutoff in the future.
 */
export function resolveEarlyBird(
  draft: EarlyBirdDraft,
  basePriceNgwee: number,
  now: Date,
): EarlyBirdResolution {
  const price = draft.priceZmw.trim();
  const until = draft.untilLocal.trim();
  if (!price && !until) {
    return { ok: true, input: { early_bird_price_ngwee: null, early_bird_until: null } };
  }
  if (!price || !until) {
    return { ok: false, errorKey: "errors.earlyBirdIncomplete" };
  }
  const ngwee = toNgweeOrNull(price);
  if (ngwee === null || ngwee <= 0) {
    return { ok: false, errorKey: "errors.priceInvalid" };
  }
  if (ngwee >= basePriceNgwee) {
    return { ok: false, errorKey: "errors.notDiscount" };
  }
  const iso = localDateTimeToIso(until);
  if (iso === null) {
    return { ok: false, errorKey: "errors.dateInvalid" };
  }
  if (Date.parse(iso) <= now.getTime()) {
    return { ok: false, errorKey: "errors.pastCutoff" };
  }
  return { ok: true, input: { early_bird_price_ngwee: ngwee, early_bird_until: iso } };
}

/**
 * Resolve the tier rows into the desired set. Fully-blank rows are dropped
 * (a removal); each remaining row needs min_qty >= 2 (unique) and a positive
 * price below the base. Returns the set sorted by min_qty.
 */
export function resolveTiers(rows: TierDraft[], basePriceNgwee: number): TiersResolution {
  const tiers: PriceTierRow[] = [];
  const seen = new Set<number>();
  for (const row of rows) {
    const minRaw = row.minQty.trim();
    const priceRaw = row.priceZmw.trim();
    if (!minRaw && !priceRaw) {
      continue;
    }
    const minQty = Number.parseInt(minRaw, 10);
    if (!Number.isInteger(minQty) || minQty < 2 || String(minQty) !== minRaw) {
      return { ok: false, errorKey: "errors.minQtyInvalid" };
    }
    if (seen.has(minQty)) {
      return { ok: false, errorKey: "errors.duplicateMinQty" };
    }
    const ngwee = toNgweeOrNull(priceRaw);
    if (ngwee === null || ngwee <= 0) {
      return { ok: false, errorKey: "errors.priceInvalid" };
    }
    if (ngwee >= basePriceNgwee) {
      return { ok: false, errorKey: "errors.tierNotDiscount" };
    }
    seen.add(minQty);
    tiers.push({ min_qty: minQty, price_ngwee: ngwee });
  }
  tiers.sort((a, b) => a.min_qty - b.min_qty);
  return { ok: true, tiers };
}

/** Map a server pricing rejection code to a `tickets.pricing.*` message key. */
export function pricingErrorKey(code: string | undefined): string {
  switch (code) {
    case "early_bird_not_a_discount":
      return "errors.notDiscount";
    case "early_bird_cutoff_in_past":
      return "errors.pastCutoff";
    case "invalid_early_bird_cutoff":
      return "errors.dateInvalid";
    case "tier_not_a_discount":
      return "errors.tierNotDiscount";
    case "pricing_not_allowed_on_free":
      return "errors.onFree";
    default:
      return "errors.saveFailed";
  }
}
