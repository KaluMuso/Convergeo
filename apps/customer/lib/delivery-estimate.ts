/**
 * Delivery / pickup estimate from listing lead time, computed on the Lusaka
 * clock (Africa/Lusaka, UTC+2, no DST). Output is relative ("tomorrow",
 * "in 2–3 days") so it never renders a hardcoded calendar date.
 *
 * Rules (Phase-1 manual dispatch):
 *  - stocked items dispatch same day when ordered before the 14:00 cut-off,
 *    else next day; delivery lands the day after dispatch;
 *  - made-to-order adds `lead_time_days` (range max = lead + 1);
 *  - pickup is ready on dispatch day (made-to-order: after lead time).
 */

export type DeliveryEstimateInput = {
  deliveryAvailable: boolean;
  pickupAvailable: boolean;
  fulfilmentMode?: string | null;
  leadTimeDays?: number | null;
  inStock: boolean;
};

export type DeliveryEstimate =
  | { kind: "delivery" | "pickup"; when: "today" | "tomorrow" }
  | { kind: "delivery" | "pickup"; when: "days"; min: number; max: number };

export type DeliveryEstimateLabels = {
  deliveryToday: string;
  deliveryTomorrow: string;
  /** ICU-free template with {min} and {max}. */
  deliveryDays: string;
  pickupToday: string;
  pickupTomorrow: string;
  pickupDays: string;
};

export const LUSAKA_CUTOFF_HOUR = 14;

/** Current hour (0–23) in Africa/Lusaka. */
export function lusakaHour(now: Date): number {
  const hour = new Intl.DateTimeFormat("en-GB", {
    timeZone: "Africa/Lusaka",
    hour: "2-digit",
    hourCycle: "h23",
  }).format(now);
  return Number.parseInt(hour, 10) % 24;
}

export function estimateDelivery(
  input: DeliveryEstimateInput,
  now: Date = new Date(),
): DeliveryEstimate | null {
  if (!input.inStock || (!input.deliveryAvailable && !input.pickupAvailable)) {
    return null;
  }
  const madeToOrder = input.fulfilmentMode === "made_to_order";
  const lead = madeToOrder ? Math.max(1, input.leadTimeDays ?? 1) : 0;
  const dispatchOffset = (lusakaHour(now) >= LUSAKA_CUTOFF_HOUR ? 1 : 0) + lead;
  const kind = input.deliveryAvailable ? "delivery" : "pickup";
  const first = kind === "delivery" ? dispatchOffset + 1 : dispatchOffset;
  if (madeToOrder) {
    return { kind, when: "days", min: first, max: first + 1 };
  }
  if (first === 0) return { kind, when: "today" };
  if (first === 1) return { kind, when: "tomorrow" };
  return { kind, when: "days", min: first, max: first + 1 };
}

export function formatDeliveryEstimate(
  estimate: DeliveryEstimate | null,
  labels: DeliveryEstimateLabels,
): string | null {
  if (!estimate) return null;
  const isDelivery = estimate.kind === "delivery";
  if (estimate.when === "days") {
    return (isDelivery ? labels.deliveryDays : labels.pickupDays)
      .replace("{min}", String(estimate.min))
      .replace("{max}", String(estimate.max));
  }
  if (estimate.when === "today") return isDelivery ? labels.deliveryToday : labels.pickupToday;
  return isDelivery ? labels.deliveryTomorrow : labels.pickupTomorrow;
}
