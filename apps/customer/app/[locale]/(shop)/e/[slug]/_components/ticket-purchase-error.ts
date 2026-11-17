/** Message keys under `events.ticketPurchase.errors` that every locale defines. */
export type TicketPurchaseErrorKey =
  | "generic"
  | "freeUseRsvp"
  | "paidUseCheckout"
  | "oversell"
  | "attendeeNamesRequired"
  | "attendeeNamesMismatch"
  | "promoInvalid"
  | "rsvpCap"
  | "rsvpInProgress"
  | "rateLimited"
  | "oneEvent";

const KEY_BY_CODE: Record<string, TicketPurchaseErrorKey> = {
  "tickets.oversell": "oversell",
  "tickets.free_use_rsvp": "freeUseRsvp",
  "tickets.paid_use_checkout": "paidUseCheckout",
  "tickets.attendee_names_required": "attendeeNamesRequired",
  "tickets.attendee_names_mismatch": "attendeeNamesMismatch",
  "tickets.rsvp_cap": "rsvpCap",
  "tickets.rsvp_in_progress": "rsvpInProgress",
  rate_limited: "rateLimited",
  promo_not_found: "promoInvalid",
  promo_inactive: "promoInvalid",
  promo_expired: "promoInvalid",
  promo_exhausted: "promoInvalid",
  promo_not_started: "promoInvalid",
  // Unified cart: tickets for one event date per checkout.
  "cart.tickets_one_event": "oneEvent",
};

/**
 * Translated message key for a failed RSVP / ticket checkout. The API's own
 * `message` is developer English, so an unmapped code falls back to the generic
 * translated line rather than being printed to the buyer.
 */
export function ticketPurchaseErrorKey(
  code: string | null | undefined,
): TicketPurchaseErrorKey {
  return (code && KEY_BY_CODE[code]) || "generic";
}
