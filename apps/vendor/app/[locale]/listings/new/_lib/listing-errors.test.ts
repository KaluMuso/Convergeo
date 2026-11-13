import { ApiError } from "@vergeo/config";
import { describe, expect, it } from "vitest";

import { listingCreateErrorMessage } from "./listing-errors";

const messages = {
  standaloneRequired: "standalone",
  listingLimit: "limit reached, listings stay live",
  fallback: "failed",
};

describe("listingCreateErrorMessage", () => {
  it("shows the friendly limit message when the plan/KYC listing cap is reached", () => {
    const error = new ApiError("listing_cap_exceeded", "cap", {
      status: 403,
      details: { message_key: "vendor.plans.limitReached", upgrade_available: true },
    });
    expect(listingCreateErrorMessage(error, messages)).toBe(messages.listingLimit);
  });

  it("falls back when no limit copy is supplied", () => {
    const error = new ApiError("listing_cap_exceeded", "cap", { status: 403 });
    expect(listingCreateErrorMessage(error, { standaloneRequired: "s", fallback: "f" })).toBe("f");
  });
});
