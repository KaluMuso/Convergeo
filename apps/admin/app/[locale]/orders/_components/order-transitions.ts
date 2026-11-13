/**
 * Client mirror of the order state machine for the ADMIN actor
 * (services/api/app/services/orders/state.py TRANSITION_TABLE). The API stays
 * the authority and re-validates every call; this only decides which actions the
 * console OFFERS so an operator never sees a transition the backend would reject.
 */
import type { OrderEvent } from "./api";

export type Fulfilment = "delivery" | "pickup";

type Spec = { event: OrderEvent; to: string; fulfilment?: Fulfilment };

const ADMIN_TRANSITIONS: Record<string, Spec[]> = {
  placed: [
    { event: "confirm", to: "confirmed" },
    { event: "reject", to: "cancelled" },
    { event: "cancel", to: "cancelled" },
  ],
  confirmed: [
    { event: "start_processing", to: "processing" },
    { event: "reject", to: "cancelled" },
    { event: "cancel", to: "cancelled" },
  ],
  processing: [
    { event: "ready_for_pickup", to: "ready", fulfilment: "pickup" },
    { event: "ship", to: "shipped", fulfilment: "delivery" },
    { event: "cancel", to: "cancelled" },
  ],
  ready: [
    { event: "verify_pickup", to: "delivered" },
    { event: "cancel", to: "cancelled" },
  ],
  shipped: [
    { event: "mark_delivered", to: "delivered" },
    { event: "cancel", to: "cancelled" },
  ],
  delivered: [{ event: "confirm_received", to: "completed" }],
  completed: [],
  cancelled: [],
};

export const CANCELLATION_EVENTS: readonly OrderEvent[] = ["reject", "cancel"];

export type OrderGuardInput = {
  status: string;
  fulfilment: string;
  cod: boolean;
  /** At least one successful payment on the checkout group. */
  paid: boolean;
};

export type AllowedAction = { event: OrderEvent; to: string };

/**
 * Events an admin may apply now. A prepaid order with no successful payment can
 * only be cancelled/rejected (PREPAID_PAYMENT_REQUIRED_EVENTS in the API).
 */
export function allowedAdminActions(order: OrderGuardInput): AllowedAction[] {
  const specs = ADMIN_TRANSITIONS[order.status] ?? [];
  return specs
    .filter((spec) => !spec.fulfilment || spec.fulfilment === order.fulfilment)
    .filter((spec) => order.cod || order.paid || CANCELLATION_EVENTS.includes(spec.event))
    .map(({ event, to }) => ({ event, to }));
}

/** Cancelling a prepaid order with collected money needs the refund path acknowledged. */
export function needsRefundPath(order: OrderGuardInput, event: OrderEvent): boolean {
  return CANCELLATION_EVENTS.includes(event) && !order.cod && order.paid;
}

export function isPrepaidUnpaid(order: OrderGuardInput): boolean {
  return !order.cod && !order.paid;
}

/** Happy-path steps for the stepper, per fulfilment. */
export function progressSteps(fulfilment: string): string[] {
  return fulfilment === "pickup"
    ? ["placed", "confirmed", "processing", "ready", "delivered", "completed"]
    : ["placed", "confirmed", "processing", "shipped", "delivered", "completed"];
}

export function isDispatchEvent(event: OrderEvent): boolean {
  return event === "ship" || event === "mark_delivered";
}
