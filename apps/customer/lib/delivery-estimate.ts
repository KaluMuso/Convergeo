/**
 * Delivery / pickup estimate from listing lead time, computed on the Lusaka
 * clock (Africa/Lusaka, UTC+2, no DST). Output is relative ("tomorrow",
 * "in 2–3 days") so it never renders a hardcoded calendar date.
 *
 * Rules (founder-approved promise, 2026-11-13: "Order before 2 pm, get it today"):
 *  - stocked items dispatch and land in Lusaka the same day when ordered
 *    before the 14:00 cut-off, else the next day;
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
  const first = dispatchOffset;
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

export type AddressType = "home" | "work";

export type DeliveryPromise = {
  day: "today" | "tomorrow" | "later";
  /** ISO date (YYYY-MM-DD) on the Lusaka calendar. */
  date: string;
  /** "HH:MM" on the Lusaka clock. */
  windowStart: string;
  windowEnd: string;
};

type LusakaParts = { date: string; weekday: number; minutes: number };

const WEEKDAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];

function lusakaParts(now: Date): LusakaParts {
  const parts = new Intl.DateTimeFormat("en-GB", {
    timeZone: "Africa/Lusaka",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    weekday: "short",
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
  }).formatToParts(now);
  const get = (type: string) => parts.find((part) => part.type === type)?.value ?? "";
  return {
    date: `${get("year")}-${get("month")}-${get("day")}`,
    weekday: WEEKDAYS.indexOf(get("weekday")),
    minutes: (Number.parseInt(get("hour"), 10) % 24) * 60 + Number.parseInt(get("minute"), 10),
  };
}

function addDays(isoDate: string, days: number): string {
  const [y, m, d] = isoDate.split("-").map((value) => Number.parseInt(value, 10));
  const next = new Date(Date.UTC(y ?? 1970, (m ?? 1) - 1, (d ?? 1) + days));
  return next.toISOString().slice(0, 10);
}

const hhmm = (minutes: number) =>
  `${String(Math.floor(minutes / 60)).padStart(2, "0")}:${String(minutes % 60).padStart(2, "0")}`;

const ROUND1: [number, number] = [12 * 60, 14 * 60 + 30];
const WORK_ROUND2: [number, number] = [15 * 60, 16 * 60 + 45];
const HOME_ROUND2: [number, number] = [17 * 60, 19 * 60 + 30];
const SATURDAY: [number, number] = [11 * 60, 14 * 60];
const WORK_LATEST = 16 * 60 + 45;

/**
 * Promised delivery day and window — mirrors the API's `delivery_promise`
 * (services/api/app/services/logistics/area_pricing.py). The API's answer
 * (fulfilment step `delivery_promise`) wins once it is known; this is the
 * before-submit preview. Weekdays: by 11:00 -> 12:00–14:30; by 14:00 ->
 * 15:00–16:45 (work) / 17:00–19:30 (home); later -> next working day.
 * Saturday: homes only, order by 10:00 -> 11:00–14:00. Sunday: none.
 */
export function deliveryPromise(
  now: Date,
  addressType: AddressType = "home",
  rain = false,
): DeliveryPromise {
  const { date: today, weekday, minutes } = lusakaParts(now);
  let date = today;
  let window: [number, number];
  if (weekday >= 1 && weekday <= 5 && minutes < 11 * 60) {
    window = ROUND1;
  } else if (weekday >= 1 && weekday <= 5 && minutes < LUSAKA_CUTOFF_HOUR * 60) {
    window = addressType === "work" ? WORK_ROUND2 : HOME_ROUND2;
  } else if (weekday === 6 && minutes < 10 * 60 && addressType === "home") {
    window = SATURDAY;
  } else {
    let offset = 1;
    let day = (weekday + 1) % 7;
    while (day === 0 || (day === 6 && addressType === "work")) {
      offset += 1;
      day = (day + 1) % 7;
    }
    date = addDays(today, offset);
    window = day === 6 ? SATURDAY : ROUND1;
  }
  let end = window[1] + (rain ? 30 : 0);
  if (addressType === "work") end = Math.min(end, WORK_LATEST);
  const gap = date === today ? 0 : date === addDays(today, 1) ? 1 : 2;
  return {
    day: gap === 0 ? "today" : gap === 1 ? "tomorrow" : "later",
    date,
    windowStart: hhmm(window[0]),
    windowEnd: hhmm(end),
  };
}
