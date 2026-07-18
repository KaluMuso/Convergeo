/**
 * D16: Lusaka delivery is manual admin dispatch — ops book Yango/inDrive/local
 * outside the platform and paste tracking. API courier enum is a label for the
 * note, not a courier integration CTA.
 */
export const DISPATCH_COURIERS = ["other", "yango", "indrive"] as const;

export type DispatchCourier = (typeof DISPATCH_COURIERS)[number];

/** Default to "other" so Yango is never presented as the implied integration. */
export const DEFAULT_DISPATCH_COURIER: DispatchCourier = "other";

export function requiresCourierOtherName(courier: DispatchCourier): boolean {
  return courier === "other";
}

export function isDispatchFormReady(input: {
  courier: DispatchCourier;
  courierOther: string;
  trackingNote: string;
  confirmedManual: boolean;
}): boolean {
  if (!input.confirmedManual) return false;
  if (!input.trackingNote.trim()) return false;
  if (requiresCourierOtherName(input.courier) && !input.courierOther.trim()) return false;
  return true;
}
