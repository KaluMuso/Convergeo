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
  // Logistics phase 1 (optional so older API payloads still parse).
  checkout_group_id?: string | null;
  group_key?: string | null;
  dropoff_landmark?: string | null;
  ready_at?: string | null;
  deliver_together?: boolean;
  pickup_label?: string | null;
  pickup_area?: string | null;
  multi_branch?: boolean;
  delivery_attempts?: number;
  // Area-pair pricing: coordinates for the Google Maps link-out (no API call).
  pickup_lat?: number | null;
  pickup_lng?: number | null;
  dropoff_area?: string | null;
  dropoff_lat?: number | null;
  dropoff_lng?: number | null;
  address_type?: "home" | "work";
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
  direction?: "delivery" | "return";
  attempt_no?: number;
  failure_code?: string | null;
  actual_cost_ngwee?: number | null;
  cod_collected_ngwee?: number | null;
  cod_collected_method?: string | null;
  remitted?: boolean;
};

export type DeliveryZone = { zone_key: string; label: string; fee_ngwee: number };

export type Board = {
  flag_enabled: boolean;
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
  | "accept"
  | "pickUp"
  | "fail"
  | "cancel"
  | "deliverWithPhoto"
  | "verifyHandover"
  | "complete"
  | "returned"
  | "recordCost";

export const FAILURE_CODES = [
  "customer_unavailable",
  "customer_refused",
  "wrong_address",
  "vendor_not_ready",
  "courier_no_show",
  "damaged",
  "other",
] as const;

export type FailureCode = (typeof FAILURE_CODES)[number];

const TARGET_TO_ACTION: Partial<Record<DispatchStatus, DispatchAction>> = {
  accepted: "accept",
  picked_up: "pickUp",
  failed: "fail",
  cancelled: "cancel",
};

/** Buttons for one dispatch, derived from the API's `allowed_next`. */
export function actionsFor(
  dispatch: Pick<Dispatch, "status" | "allowed_next"> & Partial<Pick<Dispatch, "direction">>,
): DispatchAction[] {
  const actions: DispatchAction[] = [];
  const isReturn = dispatch.direction === "return";
  for (const target of dispatch.allowed_next) {
    if (target === "delivered") {
      if (isReturn) continue; // a return closes only when the shop acknowledges it
      // One step: the customer's code (or a photo) AND the rider's cash.
      actions.push("complete", "verifyHandover", "deliverWithPhoto");
      continue;
    }
    const action = TARGET_TO_ACTION[target];
    if (action) actions.push(action);
  }
  if (isReturn && (dispatch.status === "accepted" || dispatch.status === "picked_up")) {
    actions.push("returned");
  }
  if (["picked_up", "delivered", "failed", "cancelled"].includes(dispatch.status)) {
    actions.push("recordCost");
  }
  return actions;
}

/** Ready orders grouped by checkout + address: one rider can take a multi-shop drop. */
export function groupReadyOrders(
  orders: readonly ReadyOrder[],
): { key: string; landmark: string | null; orders: ReadyOrder[] }[] {
  const groups = new Map<string, { key: string; landmark: string | null; orders: ReadyOrder[] }>();
  for (const order of orders) {
    const key = order.group_key ?? order.order_id;
    const group = groups.get(key) ?? { key, landmark: order.dropoff_landmark ?? null, orders: [] };
    group.orders.push(order);
    groups.set(key, group);
  }
  return [...groups.values()];
}

/** What the next job for a ready order is: first job, a second attempt, or a return. */
export function nextJobKind(
  order: Pick<ReadyOrder, "status" | "delivery_attempts">,
): "first" | "retry" | "returnOnly" {
  if (order.status !== "shipped") return "first";
  return (order.delivery_attempts ?? 0) >= 2 ? "returnOnly" : "retry";
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

export type PricingSwitches = {
  rain_mode: boolean;
  area_pricing_shadow: boolean;
  area_pricing_live: boolean;
};

function point(lat: number | null | undefined, lng: number | null | undefined): string | null {
  if (typeof lat !== "number" || typeof lng !== "number") return null;
  if (!Number.isFinite(lat) || !Number.isFinite(lng)) return null;
  return `${lat.toFixed(6)},${lng.toFixed(6)}`;
}

/**
 * Google Maps directions link for the dispatcher (opens Google Maps; Convergeo
 * makes no Maps API call, so it costs nothing). Shop -> customer, with the
 * customer's area name + "Lusaka" when the address has no pin. Null when there
 * is no usable destination.
 */
export function googleMapsDirectionsUrl(order: ReadyOrder): string | null {
  const origin = point(order.pickup_lat, order.pickup_lng);
  const destination =
    point(order.dropoff_lat, order.dropoff_lng) ??
    (order.dropoff_area ? `${order.dropoff_area}, Lusaka, Zambia` : null);
  if (!destination) return null;
  const params = new URLSearchParams({ api: "1", destination, travelmode: "driving" });
  if (origin) params.set("origin", origin);
  return `https://www.google.com/maps/dir/?${params.toString()}`;
}
