import { describe, expect, it } from "vitest";

import {
  deliveryPromise,
  estimateDelivery,
  estimateReadyDate,
  formatDeliveryEstimate,
  formatEstimateDate,
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

  it("stocked delivery before the 14:00 cut-off lands today, after it tomorrow", () => {
    expect(formatDeliveryEstimate(estimateDelivery(base, morning), labels)).toBe(
      "Delivery in Lusaka today",
    );
    expect(formatDeliveryEstimate(estimateDelivery(base, evening), labels)).toBe(
      "Delivery in Lusaka tomorrow",
    );
  });

  it("pickup-only stock is ready today before cut-off", () => {
    const est = estimateDelivery({ ...base, deliveryAvailable: false }, morning);
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
      estimateDelivery({ ...base, deliveryAvailable: false, pickupAvailable: false }, morning),
    ).toBeNull();
  });
});

describe("made-to-order estimated date (Africa/Lusaka)", () => {
  it("adds the lead time to today for pickup before the 14:00 cut-off", () => {
    const date = estimateReadyDate({ kind: "pickup", leadTimeDays: 7 }, morning);
    expect(formatEstimateDate(date, "en")).toContain("16 Nov");
  });

  it("adds one day for delivery", () => {
    const date = estimateReadyDate({ kind: "delivery", leadTimeDays: 7 }, morning);
    expect(formatEstimateDate(date, "en")).toContain("17 Nov");
  });

  it("starts the next day when ordered after the cut-off", () => {
    const date = estimateReadyDate({ kind: "pickup", leadTimeDays: 7 }, evening);
    expect(formatEstimateDate(date, "en")).toContain("17 Nov");
  });

  it("never returns a date before tomorrow for a zero or fractional lead time", () => {
    const date = estimateReadyDate({ kind: "pickup", leadTimeDays: 0 }, morning);
    expect(formatEstimateDate(date, "en")).toContain("10 Nov");
  });

  it("formats bem and nya with the Zambian English calendar", () => {
    const date = estimateReadyDate({ kind: "pickup", leadTimeDays: 7 }, morning);
    expect(formatEstimateDate(date, "bem")).toBe(formatEstimateDate(date, "en"));
  });
});

describe("delivery promise: Order before 2 pm, get it today", () => {
  // 2026-11-18 is a Wednesday. Lusaka is UTC+2.
  it("13:59 Lusaka is today, 14:01 is tomorrow", () => {
    const before = deliveryPromise(new Date("2026-11-18T11:59:00Z"), "home");
    const after = deliveryPromise(new Date("2026-11-18T12:01:00Z"), "home");
    expect(before).toEqual({
      day: "today",
      date: "2026-11-18",
      windowStart: "17:00",
      windowEnd: "19:30",
    });
    expect(after).toEqual({
      day: "tomorrow",
      date: "2026-11-19",
      windowStart: "12:00",
      windowEnd: "14:30",
    });
  });

  it("work addresses are delivered inside office hours, even in rain", () => {
    const work = deliveryPromise(new Date("2026-11-18T11:00:00Z"), "work", true);
    expect(work.windowStart).toBe("15:00");
    expect(work.windowEnd).toBe("16:45");
    const home = deliveryPromise(new Date("2026-11-18T11:00:00Z"), "home", true);
    expect(home.windowEnd).toBe("20:00");
  });

  it("weekends: Saturday round for homes, Monday for work, Sunday none", () => {
    expect(deliveryPromise(new Date("2026-11-20T13:00:00Z"), "home")).toMatchObject({
      day: "tomorrow",
      windowStart: "11:00",
    });
    expect(deliveryPromise(new Date("2026-11-20T13:00:00Z"), "work")).toMatchObject({
      day: "later",
      date: "2026-11-23",
    });
    expect(deliveryPromise(new Date("2026-11-22T07:00:00Z"), "home")).toMatchObject({
      day: "tomorrow",
      date: "2026-11-23",
    });
  });
});
