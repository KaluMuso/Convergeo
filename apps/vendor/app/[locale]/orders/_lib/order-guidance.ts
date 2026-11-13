/**
 * Plain-language "what happens next" for a vendor order.
 *
 * Mirrors the API order state machine (services/api/app/services/orders/state.py):
 *   delivery: placed → confirmed → processing → shipped → delivered → completed
 *   pickup:   placed → confirmed → processing → ready → delivered → completed
 * Any non-terminal status may go to cancelled. This module only decides which
 * explanation to show — the server stays the authority on available actions.
 */

export type OrderNextStepKey =
  | "confirm"
  | "pack"
  | "handToRider"
  | "readyForPickup"
  | "awaitCollection"
  | "awaitDelivery"
  | "awaitConfirmation"
  | "done"
  | "cancelled"
  | "unknown";

export type OrderGuidanceInput = {
  status: string;
  fulfilment: string;
};

/** Steps where the vendor has to do something now. */
export const VENDOR_ACTION_STEPS: ReadonlySet<OrderNextStepKey> = new Set([
  "confirm",
  "pack",
  "handToRider",
  "readyForPickup",
]);

export function orderNextStep({ status, fulfilment }: OrderGuidanceInput): OrderNextStepKey {
  const pickup = fulfilment === "pickup";
  switch (status) {
    case "placed":
      return "confirm";
    case "confirmed":
      return "pack";
    case "processing":
      return pickup ? "readyForPickup" : "handToRider";
    case "ready":
      return "awaitCollection";
    case "shipped":
      return "awaitDelivery";
    case "delivered":
      return "awaitConfirmation";
    case "completed":
      return "done";
    case "cancelled":
      return "cancelled";
    default:
      return "unknown";
  }
}

export function needsVendorAction(input: OrderGuidanceInput): boolean {
  return VENDOR_ACTION_STEPS.has(orderNextStep(input));
}

/** Delivery orders still to be handed to a rider are bound by the 14:00 cut-off. */
export function isBoundByDispatchCutoff(input: OrderGuidanceInput): boolean {
  if (input.fulfilment === "pickup") {
    return false;
  }
  const step = orderNextStep(input);
  return step === "confirm" || step === "pack" || step === "handToRider";
}

export type TimelineStepState = "done" | "current" | "upcoming";

export type TimelineEventInput = {
  to_status: string;
  note: string | null;
  created_at: string;
};

export type OrderTimelineStep = {
  status: string;
  state: TimelineStepState;
  at: string | null;
  note: string | null;
};

const DELIVERY_PATH = ["placed", "confirmed", "processing", "shipped", "delivered", "completed"];
const PICKUP_PATH = ["placed", "confirmed", "processing", "ready", "delivered", "completed"];

export function orderStatusPath(fulfilment: string): string[] {
  return fulfilment === "pickup" ? PICKUP_PATH : DELIVERY_PATH;
}

/**
 * Full lifecycle with done / current / upcoming markers so vendors see what is
 * still ahead, not only what already happened. A cancelled order shows the
 * steps it reached and then the cancellation as the current (final) step.
 */
export function orderTimelineSteps(
  order: OrderGuidanceInput & { timeline: TimelineEventInput[] },
): OrderTimelineStep[] {
  const latestByStatus = new Map<string, TimelineEventInput>();
  for (const event of order.timeline) {
    latestByStatus.set(event.to_status, event);
  }
  const path = orderStatusPath(order.fulfilment);

  if (order.status === "cancelled") {
    const reached = path.filter((status) => status === "placed" || latestByStatus.has(status));
    const steps: OrderTimelineStep[] = reached.map((status) => ({
      status,
      state: "done",
      at: latestByStatus.get(status)?.created_at ?? null,
      note: latestByStatus.get(status)?.note ?? null,
    }));
    const cancelEvent = latestByStatus.get("cancelled");
    steps.push({
      status: "cancelled",
      state: "current",
      at: cancelEvent?.created_at ?? null,
      note: cancelEvent?.note ?? null,
    });
    return steps;
  }

  const currentIndex = path.indexOf(order.status);
  return path.map((status, index) => {
    const event = latestByStatus.get(status);
    let state: TimelineStepState;
    if (currentIndex === -1) {
      state = event ? "done" : "upcoming";
    } else if (index < currentIndex) {
      state = "done";
    } else if (index === currentIndex) {
      state = status === "completed" ? "done" : "current";
    } else {
      state = "upcoming";
    }
    return { status, state, at: event?.created_at ?? null, note: event?.note ?? null };
  });
}
