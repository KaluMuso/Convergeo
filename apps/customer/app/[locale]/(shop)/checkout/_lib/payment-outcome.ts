/**
 * Customer-side payment outcome rules (CUST-08 / G4).
 *
 * Success UI is shown only when the API confirms the order path
 * (`order_confirmed`). Provider/payment status alone is never enough to claim
 * "paid" — without ledger confirmation the UI stays in a truthful pending or
 * held state.
 */

export type CardVerifyResult = {
  status: string;
  order_confirmed: boolean;
  held?: boolean;
  retry_checkout?: boolean;
};

export type CardViewState = "success" | "failed" | "held" | "pending";

/**
 * Map a card `/payments/card/{id}/verify` payload to a customer view state.
 * Never returns `success` unless `order_confirmed` is true.
 */
export function resolveCardVerifyViewState(result: CardVerifyResult): CardViewState {
  if (result.order_confirmed) {
    return "success";
  }
  if (result.held) {
    return "held";
  }
  if (result.retry_checkout) {
    return "failed";
  }
  // Provider may report success before order confirmation / ledger post —
  // keep the buyer in a confirming/pending state rather than a paid screen.
  if (result.status === "success" || result.status === "pending" || result.status === "initiated") {
    return "pending";
  }
  if (result.status === "failed" || result.status === "expired" || result.status === "cancelled") {
    return "failed";
  }
  return "pending";
}

export type MomoPollOutcome =
  "redirect_order" | "cod" | "waiting" | "failed" | "cancelled" | "confirming";

/**
 * MoMo poll outcomes. Payment `success` without a stronger confirmation surface
 * is treated as "confirming" (redirect to the order page — which shows real
 * escrow/payment state) rather than a standalone "paid" claim.
 */
export function resolveMomoPollOutcome(payload: { status: string; cod: boolean }): MomoPollOutcome {
  if (payload.cod) {
    return "cod";
  }
  if (payload.status === "success") {
    return "confirming";
  }
  if (payload.status === "cancelled") {
    return "cancelled";
  }
  if (payload.status === "failed" || payload.status === "expired") {
    return "failed";
  }
  if (
    payload.status === "initiated" ||
    payload.status === "ussd_pushed" ||
    payload.status === "pay_offline"
  ) {
    return "waiting";
  }
  return "waiting";
}
