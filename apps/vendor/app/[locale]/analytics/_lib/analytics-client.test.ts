import { describe, expect, it } from "vitest";

import { normalizeVendorAnalytics } from "./analytics-client";

const legacy = {
  window: 7,
  days: ["2026-10-02"],
  sales_ngwee_by_day: [12345],
  orders_by_day: [3],
  views_by_day: [1],
  top_listings: [],
  conversion_hint: { orders_total: 3, views_total: 1, conversion_pct: 300 },
};

describe("analytics API compatibility", () => {
  it("normalizes old API event counts without claiming conversion or capping the ratio", () => {
    const result = normalizeVendorAnalytics(legacy);
    expect(result.cart_activity_events_by_day).toEqual([1]);
    expect(result.order_activity_ratio).toEqual({
      orders_total: 3,
      cart_activity_events_total: 1,
      orders_per_100_cart_activity_events: 300,
    });
    expect(result.sales_ngwee_by_day).toEqual([12345]);
  });

  it("uses null for an absent denominator, including positive orders", () => {
    const result = normalizeVendorAnalytics({ ...legacy, views_by_day: [0] });
    expect(result.order_activity_ratio.orders_total).toBe(3);
    expect(result.order_activity_ratio.orders_per_100_cart_activity_events).toBeNull();
  });

  it("shows a real zero ratio when events exist but orders do not", () => {
    const result = normalizeVendorAnalytics({
      ...legacy,
      orders_by_day: [0],
      conversion_hint: { orders_total: 0, views_total: 1, conversion_pct: 0 },
    });
    expect(result.order_activity_ratio.orders_per_100_cart_activity_events).toBe(0);
  });

  it("prefers explicit new API fields over legacy aliases", () => {
    const ratio = {
      orders_total: 2,
      cart_activity_events_total: 3,
      orders_per_100_cart_activity_events: 66.7,
    };
    const result = normalizeVendorAnalytics({
      ...legacy,
      cart_activity_events_by_day: [3],
      order_activity_ratio: ratio,
    });
    expect(result.cart_activity_events_by_day).toEqual([3]);
    expect(result.order_activity_ratio).toEqual(ratio);
  });

  it("preserves the old server's rounding for a positive denominator", () => {
    const result = normalizeVendorAnalytics({
      ...legacy,
      orders_by_day: [1],
      views_by_day: [16],
      conversion_hint: {
        orders_total: 1,
        views_total: 16,
        conversion_pct: 6.2,
      },
    });
    expect(result.order_activity_ratio.orders_per_100_cart_activity_events).toBe(6.2);
  });
});
