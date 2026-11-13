/**
 * Courier dispatch v1 — pure board logic (no React, no fetch) so it is unit
 * tested without a DOM. The API (`/admin/dispatch/*`) is the authority for every
 * rule here; this module only shapes what the board offers so ops never see a
 * button the state machine would reject.
 */

export const DISPATCH_STATUSES = [
  "requested",
  "accepted",
  "picked_up",
  "delivered",
  "failed",
  "cancelled",
] as const;

export type DispatchStatus = (typeof DISPATCH_STATUSES)[number];

export const ACTIVE_DISPATCH_STATUSES: readonly DispatchStatus[] = [
  "requested",
  "accepted",
  "picked_up",
];

export type CourierZone = { zone_key: string; price_ngwee: number | null };

export type Courier = {
  id: string;
  name: string;
  contact_whatsapp_e164: string | null;
  contact_email: string | null;
  integration_kind: string;
  active: boolean;
  notes: string | null;
  zones: CourierZone[];
};

export type ReadyOrder = {
  order_id: string;
  order_reference: string;
  status: string;
  vendor_name: string;
  delivery_zone: string | null;
  cod: boolean;
  cod_amount_ngwee: number;
  subtotal_ngwee: number;
  delivery_fee_ngwee: number;
  item_count: number;
  created_at: string;
  last_failed_reason: string | null;
};

export type Dispatch = {
  id: string;
  order_id: string;
  order_reference: string;
  courier_partner_id: string;
  courier_name: string;
  status: DispatchStatus;
  allowed_next: DispatchStatus[];
  courier_reference: string | null;
  cod_amount_ngwee: number;
  quoted_price_ngwee: number | null;
  pod_photo_public_id: string | null;
  delivered_via: string | null;
  failure_reason: string | null;
  notify_count: number;
  last_notified_at: string | null;
  requested_at: string;
  accepted_at: string | null;
  picked_up_at: string | null;
  delivered_at: string | null;
  failed_at: string | null;
  cancelled_at: string | null;
  vendor_name: string;
  order_status: string;
  delivery_zone: string | null;
  handover_locked: boolean;
  /** Pay at the door (flag `pay_at_door`); null when not started or flag off. */
  door_payment_state?: DoorPaymentBoardState | null;
};

export type DoorPaymentBoardState =
  "arrived" | "pending" | "paid" | "cash" | "failed" | "exception";

/** Door-payment actions ops can take for the rider (COD parcel, rider picked up). */
export function doorPaymentActions(
  dispatch: Pick<Dispatch, "status" | "cod_amount_ngwee" | "door_payment_state">,
): Array<"arrived" | "request" | "poll" | "cash"> {
  if (dispatch.status !== "picked_up" || dispatch.cod_amount_ngwee <= 0) return [];
  const state = dispatch.door_payment_state ?? null;
  if (state === "paid" || state === "cash" || state === "exception") return [];
  if (state === "pending") return ["poll"];
  if (state === null) return ["arrived", "request", "cash"];
  return ["request", "cash"];
}

export type DeliveryZone = { zone_key: string; label: string; fee_ngwee: number };

export type Board = {
  flag_enabled: boolean;
  door_payment_enabled?: boolean;
  ready_orders: ReadyOrder[];
  dispatches: Dispatch[];
  couriers: Courier[];
  zones: DeliveryZone[];
};

/** Board columns: in-flight work first, closed work last. */
export function groupDispatches(dispatches: readonly Dispatch[]): {
  active: Dispatch[];
  closed: Dispatch[];
} {
  const active: Dispatch[] = [];
  const closed: Dispatch[] = [];
  for (const dispatch of dispatches) {
    (ACTIVE_DISPATCH_STATUSES.includes(dispatch.status) ? active : closed).push(dispatch);
  }
  const rank = (status: DispatchStatus) => ACTIVE_DISPATCH_STATUSES.indexOf(status);
  active.sort(
    (a, b) => rank(a.status) - rank(b.status) || a.requested_at.localeCompare(b.requested_at),
  );
  closed.sort((a, b) => b.requested_at.localeCompare(a.requested_at));
  return { active, closed };
}

/** Couriers ops may assign to an order: active, manual, and serving its zone. */
export function couriersForOrder(couriers: readonly Courier[], zoneKey: string | null): Courier[] {
  return couriers.filter((courier) => {
    if (!courier.active || courier.integration_kind !== "manual") return false;
    if (courier.zones.length === 0) return true;
    if (zoneKey === null) return true;
    return courier.zones.some((zone) => zone.zone_key === zoneKey);
  });
}

export function zonePriceNgwee(courier: Courier, zoneKey: string | null): number | null {
  if (!zoneKey) return null;
  return courier.zones.find((zone) => zone.zone_key === zoneKey)?.price_ngwee ?? null;
}

export type DispatchAction =
  "accept" | "pickUp" | "fail" | "cancel" | "deliverWithPhoto" | "verifyHandover";

const TARGET_TO_ACTION: Partial<Record<DispatchStatus, DispatchAction>> = {
  accepted: "accept",
  picked_up: "pickUp",
  failed: "fail",
  cancelled: "cancel",
};

/** Buttons for one dispatch, derived from the API's `allowed_next`. */
export function actionsFor(dispatch: Pick<Dispatch, "status" | "allowed_next">): DispatchAction[] {
  const actions: DispatchAction[] = [];
  for (const target of dispatch.allowed_next) {
    if (target === "delivered") {
      // Delivery is proven by the customer's code (preferred) or a POD photo.
      actions.push("verifyHandover", "deliverWithPhoto");
      continue;
    }
    const action = TARGET_TO_ACTION[target];
    if (action) actions.push(action);
  }
  return actions;
}

export function targetStatusFor(action: DispatchAction): DispatchStatus | null {
  switch (action) {
    case "accept":
      return "accepted";
    case "pickUp":
      return "picked_up";
    case "fail":
      return "failed";
    case "cancel":
      return "cancelled";
    case "deliverWithPhoto":
      return "delivered";
    default:
      return null;
  }
}

export function canNotify(dispatch: Pick<Dispatch, "status">): boolean {
  return dispatch.status === "requested" || dispatch.status === "accepted";
}

export function isHandoverCodeWellFormed(code: string): boolean {
  return /^[0-9]{6}$/.test(code.trim());
}

/** Cloudinary public_id (folder/id) — never a URL. Mirrors the API + DB check. */
export function isPodPublicIdWellFormed(value: string): boolean {
  const trimmed = value.trim();
  return /^[A-Za-z0-9_/.-]{1,255}$/.test(trimmed) && !trimmed.includes("://");
}

/** `wa.me` deep link for the manual "paste into WhatsApp" fallback. */
export function whatsAppShareUrl(phoneE164: string | null, text: string): string | null {
  const encoded = encodeURIComponent(text);
  if (!phoneE164) return `https://wa.me/?text=${encoded}`;
  const digits = phoneE164.replace(/[^0-9]/g, "");
  if (digits.length < 8 || digits.length > 15) return null;
  return `https://wa.me/${digits}?text=${encoded}`;
}

/** Minutes a `requested` dispatch has waited — drives the 45-minute stale badge. */
export function minutesWaiting(requestedAt: string, now: Date = new Date()): number {
  const started = Date.parse(requestedAt);
  if (Number.isNaN(started)) return 0;
  return Math.max(0, Math.floor((now.getTime() - started) / 60_000));
}

export const STALE_REQUESTED_MINUTES = 45;

export function isStale(dispatch: Pick<Dispatch, "status" | "requested_at">, now?: Date): boolean {
  return (
    dispatch.status === "requested" &&
    minutesWaiting(dispatch.requested_at, now) >= STALE_REQUESTED_MINUTES
  );
}

export type HandoverErrorKind = "invalid" | "locked" | "rateLimited" | "generic";

export function classifyHandoverError(error: {
  code?: string;
  status?: number;
  details?: Record<string, unknown>;
}): { kind: HandoverErrorKind; attemptsRemaining: number | null; retryAfter: number | null } {
  const details = error.details ?? {};
  const remaining =
    typeof details.attempts_remaining === "number" ? details.attempts_remaining : null;
  const retryAfter = typeof details.retry_after === "number" ? details.retry_after : null;
  if (error.code === "dispatch_handover_invalid") {
    return { kind: "invalid", attemptsRemaining: remaining, retryAfter: null };
  }
  if (error.code === "dispatch_handover_locked") {
    return { kind: "locked", attemptsRemaining: 0, retryAfter };
  }
  if (error.code === "rate_limited" || error.status === 429) {
    return { kind: "rateLimited", attemptsRemaining: null, retryAfter };
  }
  return { kind: "generic", attemptsRemaining: null, retryAfter: null };
}

export type CourierFormState = {
  name: string;
  whatsapp: string;
  email: string;
  active: boolean;
  notes: string;
  /** zone_key -> price in KWACHA text as typed ("" = served, quote per job). */
  zones: Record<string, { enabled: boolean; priceKwacha: string }>;
};

/** "25" / "25.5" / "25.50" kwacha text -> integer ngwee, without float math. */
export function kwachaTextToNgwee(text: string): number | null {
  const trimmed = text.trim();
  if (!trimmed) return null;
  const match = /^(\d{1,7})(?:\.(\d{1,2}))?$/.exec(trimmed);
  if (!match) return Number.NaN;
  const major = Number.parseInt(match[1] ?? "0", 10);
  const minor = Number.parseInt((match[2] ?? "").padEnd(2, "0") || "0", 10);
  return major * 100 + minor;
}

export function ngweeToKwachaText(ngwee: number | null): string {
  if (ngwee === null) return "";
  const major = Math.trunc(ngwee / 100);
  const minor = Math.abs(ngwee % 100);
  return `${major}.${String(minor).padStart(2, "0")}`;
}

export type CourierPayload = {
  name: string;
  contact_whatsapp_e164: string | null;
  contact_email: string | null;
  integration_kind: "manual";
  active: boolean;
  notes: string | null;
  zones: CourierZone[];
};

export type CourierFormError = "name" | "contact" | "whatsapp" | "email" | "price";

export function buildCourierPayload(
  form: CourierFormState,
): { ok: true; payload: CourierPayload } | { ok: false; error: CourierFormError } {
  const name = form.name.trim();
  if (!name || name.length > 120) return { ok: false, error: "name" };
  const whatsapp = form.whatsapp.trim();
  const email = form.email.trim();
  if (!whatsapp && !email) return { ok: false, error: "contact" };
  if (whatsapp && !/^\+[1-9][0-9]{7,14}$/.test(whatsapp)) return { ok: false, error: "whatsapp" };
  if (email && !/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email)) return { ok: false, error: "email" };
  const zones: CourierZone[] = [];
  for (const [zoneKey, zone] of Object.entries(form.zones)) {
    if (!zone.enabled) continue;
    const price = kwachaTextToNgwee(zone.priceKwacha);
    if (price !== null && Number.isNaN(price)) return { ok: false, error: "price" };
    zones.push({ zone_key: zoneKey, price_ngwee: price });
  }
  zones.sort((a, b) => a.zone_key.localeCompare(b.zone_key));
  return {
    ok: true,
    payload: {
      name,
      contact_whatsapp_e164: whatsapp || null,
      contact_email: email || null,
      integration_kind: "manual",
      active: form.active,
      notes: form.notes.trim() || null,
      zones,
    },
  };
}

export function courierToForm(
  courier: Courier | null,
  zoneKeys: readonly string[],
): CourierFormState {
  const zones: CourierFormState["zones"] = {};
  for (const key of zoneKeys) {
    const existing = courier?.zones.find((zone) => zone.zone_key === key);
    zones[key] = {
      enabled: Boolean(existing),
      priceKwacha: ngweeToKwachaText(existing?.price_ngwee ?? null),
    };
  }
  return {
    name: courier?.name ?? "",
    whatsapp: courier?.contact_whatsapp_e164 ?? "",
    email: courier?.contact_email ?? "",
    active: courier?.active ?? true,
    notes: courier?.notes ?? "",
    zones,
  };
}
