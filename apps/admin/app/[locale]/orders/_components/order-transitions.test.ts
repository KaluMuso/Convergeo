import { describe, expect, it } from "vitest";

import { allowedAdminActions, needsRefundPath, progressSteps } from "./order-transitions";

const base = { fulfilment: "delivery", cod: false, paid: true };
const events = (o: Parameters<typeof allowedAdminActions>[0]) =>
  allowedAdminActions(o).map((a) => a.event);

describe("allowedAdminActions", () => {
  it("offers only valid next events per status", () => {
    expect(events({ ...base, status: "placed" })).toEqual(["confirm", "reject", "cancel"]);
    expect(events({ ...base, status: "processing" })).toEqual(["ship", "cancel"]);
    expect(events({ ...base, status: "shipped" })).toEqual(["mark_delivered", "cancel"]);
    expect(events({ ...base, status: "delivered" })).toEqual(["confirm_received"]);
  });

  it("respects fulfilment", () => {
    expect(events({ ...base, fulfilment: "pickup", status: "processing" })).toEqual([
      "ready_for_pickup",
      "cancel",
    ]);
    expect(events({ ...base, fulfilment: "pickup", status: "ready" })).toEqual([
      "verify_pickup",
      "cancel",
    ]);
  });

  it("offers nothing from terminal states", () => {
    expect(events({ ...base, status: "completed" })).toEqual([]);
    expect(events({ ...base, status: "cancelled" })).toEqual([]);
    expect(events({ ...base, status: "mystery" })).toEqual([]);
  });

  it("blocks fulfilment on an unpaid prepaid order but keeps cancellation", () => {
    expect(events({ ...base, paid: false, status: "placed" })).toEqual(["reject", "cancel"]);
    expect(events({ ...base, paid: false, cod: true, status: "placed" })).toEqual([
      "confirm",
      "reject",
      "cancel",
    ]);
  });
});

describe("needsRefundPath", () => {
  it("is required only when cancelling paid prepaid orders", () => {
    expect(needsRefundPath({ ...base, status: "placed" }, "cancel")).toBe(true);
    expect(needsRefundPath({ ...base, cod: true, status: "placed" }, "cancel")).toBe(false);
    expect(needsRefundPath({ ...base, status: "placed" }, "confirm")).toBe(false);
  });
});

describe("progressSteps", () => {
  it("swaps shipped for ready on pickup", () => {
    expect(progressSteps("pickup")).toContain("ready");
    expect(progressSteps("delivery")).toContain("shipped");
  });
});
