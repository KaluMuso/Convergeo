import { describe, expect, it } from "vitest";

import { ticketPurchaseErrorKey } from "./ticket-purchase-error";

describe("ticketPurchaseErrorKey", () => {
  it.each([
    ["tickets.oversell", "oversell"],
    ["tickets.free_use_rsvp", "freeUseRsvp"],
    ["tickets.paid_use_checkout", "paidUseCheckout"],
    ["tickets.attendee_names_required", "attendeeNamesRequired"],
    ["tickets.attendee_names_mismatch", "attendeeNamesMismatch"],
    ["promo_not_found", "promoInvalid"],
    ["promo_expired", "promoInvalid"],
    ["promo_exhausted", "promoInvalid"],
    ["promo_inactive", "promoInvalid"],
    ["promo_not_started", "promoInvalid"],
  ])("maps %s to the translated %s line", (code, key) => {
    expect(ticketPurchaseErrorKey(code)).toBe(key);
  });

  it.each(["organiser_gmv_cap_exceeded", "tickets.event_not_published", "validation_error", ""])(
    "never surfaces the API's English for %j",
    (code) => {
      expect(ticketPurchaseErrorKey(code)).toBe("generic");
    },
  );

  it("handles a response with no error envelope", () => {
    expect(ticketPurchaseErrorKey(null)).toBe("generic");
    expect(ticketPurchaseErrorKey(undefined)).toBe("generic");
  });
});
