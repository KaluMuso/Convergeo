import { describe, expect, it } from "vitest";

import {
  DEFAULT_DISPATCH_COURIER,
  DISPATCH_COURIERS,
  isDispatchFormReady,
  requiresCourierOtherName,
} from "./dispatch-model";

describe("dispatch-model (D16 manual dispatch)", () => {
  it("defaults to other so Yango is not the implied integration", () => {
    expect(DEFAULT_DISPATCH_COURIER).toBe("other");
    expect(DISPATCH_COURIERS[0]).toBe("other");
  });

  it("requires a free-text courier name only for other", () => {
    expect(requiresCourierOtherName("other")).toBe(true);
    expect(requiresCourierOtherName("yango")).toBe(false);
    expect(requiresCourierOtherName("indrive")).toBe(false);
  });

  it("requires explicit manual confirmation before submit is ready", () => {
    expect(
      isDispatchFormReady({
        courier: "other",
        courierOther: "Local rider",
        trackingNote: "Plate ABC",
        confirmedManual: false,
      }),
    ).toBe(false);

    expect(
      isDispatchFormReady({
        courier: "other",
        courierOther: "Local rider",
        trackingNote: "Plate ABC",
        confirmedManual: true,
      }),
    ).toBe(true);

    expect(
      isDispatchFormReady({
        courier: "yango",
        courierOther: "",
        trackingNote: "Plate ABC",
        confirmedManual: true,
      }),
    ).toBe(true);

    expect(
      isDispatchFormReady({
        courier: "other",
        courierOther: "  ",
        trackingNote: "Plate ABC",
        confirmedManual: true,
      }),
    ).toBe(false);
  });
});
