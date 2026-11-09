import { describe, expect, it } from "vitest";

import {
  estimateDelivery,
  formatDeliveryEstimate,
  lusakaHour,
} from "./delivery-estimate";

const labels = {
  deliveryToday: "Delivery in Lusaka today",
  deliveryTomorrow: "Delivery in Lusaka tomorrow",
  deliveryDays: "Delivery in Lusaka in {min}–{max} days",
  pickupToday: "Pickup today",
  pickupTomorrow: "Pickup tomorrow",
  pickupDays: "Pickup in {min}–{max} days",
};
// 09:00 and 16:00 Lusaka (UTC+2).
const morning = new Date("2026-11-09T07:00:00Z");
const evening = new Date("2026-11-09T14:00:00Z");
const base = { deliveryAvailable: true, pickupAvailable: true, inStock: true };

describe("delivery estimate (Africa/Lusaka)", () => {
  it("reads the Lusaka clock", () => {
    expect(lusakaHour(morning)).toBe(9);
    expect(lusakaHour(evening)).toBe(16);
  });

  it("stocked delivery before cut-off lands tomorrow, after cut-off in 2–3 days", () => {
    expect(
      formatDeliveryEstimate(estimateDelivery(base, morning), labels),
    ).toBe("Delivery in Lusaka tomorrow");
    expect(
      formatDeliveryEstimate(estimateDelivery(base, evening), labels),
    ).toBe("Delivery in Lusaka in 2–3 days");
  });

  it("pickup-only stock is ready today before cut-off", () => {
    const est = estimateDelivery(
      { ...base, deliveryAvailable: false },
      morning,
    );
    expect(formatDeliveryEstimate(est, labels)).toBe("Pickup today");
  });

  it("made-to-order adds the lead time as a range", () => {
    const est = estimateDelivery(
      {
        ...base,
        deliveryAvailable: false,
        fulfilmentMode: "made_to_order",
        leadTimeDays: 2,
      },
      morning,
    );
    expect(formatDeliveryEstimate(est, labels)).toBe("Pickup in 2–3 days");
  });

  it("returns nothing for out-of-stock or no fulfilment", () => {
    expect(estimateDelivery({ ...base, inStock: false }, morning)).toBeNull();
    expect(
      estimateDelivery(
        { ...base, deliveryAvailable: false, pickupAvailable: false },
        morning,
      ),
    ).toBeNull();
  });
});
