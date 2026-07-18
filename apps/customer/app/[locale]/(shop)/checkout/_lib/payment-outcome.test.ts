import { describe, expect, it } from "vitest";

import { resolveCardVerifyViewState, resolveMomoPollOutcome } from "./payment-outcome";

describe("resolveCardVerifyViewState", () => {
  it("shows success only when order_confirmed is true", () => {
    expect(
      resolveCardVerifyViewState({
        status: "success",
        order_confirmed: true,
      }),
    ).toBe("success");
  });

  it("never treats provider success alone as paid", () => {
    expect(
      resolveCardVerifyViewState({
        status: "success",
        order_confirmed: false,
      }),
    ).toBe("pending");
  });

  it("surfaces held and retry_checkout distinctly", () => {
    expect(
      resolveCardVerifyViewState({
        status: "success",
        order_confirmed: false,
        held: true,
      }),
    ).toBe("held");
    expect(
      resolveCardVerifyViewState({
        status: "failed",
        order_confirmed: false,
        retry_checkout: true,
      }),
    ).toBe("failed");
  });

  it("maps failed statuses to failed without inventing success", () => {
    for (const status of ["failed", "expired", "cancelled"]) {
      expect(
        resolveCardVerifyViewState({
          status,
          order_confirmed: false,
        }),
      ).toBe("failed");
    }
  });
});

describe("resolveMomoPollOutcome", () => {
  it("keeps COD on the COD path and never claims MoMo success", () => {
    expect(resolveMomoPollOutcome({ status: "success", cod: true })).toBe("cod");
    expect(resolveMomoPollOutcome({ status: "cod", cod: true })).toBe("cod");
  });

  it("treats payment success as confirming, not a paid claim", () => {
    expect(resolveMomoPollOutcome({ status: "success", cod: false })).toBe("confirming");
  });

  it("keeps USSD rails in waiting and maps terminal failures", () => {
    expect(resolveMomoPollOutcome({ status: "ussd_pushed", cod: false })).toBe("waiting");
    expect(resolveMomoPollOutcome({ status: "failed", cod: false })).toBe("failed");
    expect(resolveMomoPollOutcome({ status: "cancelled", cod: false })).toBe("cancelled");
  });
});
