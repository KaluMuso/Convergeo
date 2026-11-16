import { describe, expect, it } from "vitest";

import {
  isoToLocalInput,
  localInputToIso,
  MAX_PER_CUSTOMER_LIMIT,
  parsePerCustomerLimit,
  payloadForType,
  TYPE_ROLES,
} from "./offers-client";

const LISTING = "a1000000-0000-4000-8000-000000000001";

describe("payloadForType", () => {
  it("sends only the fields of the chosen type (the API rejects the rest)", () => {
    const payload = payloadForType({
      offer_type: "bundle",
      title: "  Kit  ",
      status: "draft",
      bundle_pricing: "addon_percent_off",
      addon_percent_off: 75,
      bundle_price_ngwee: 1234,
      buy_n: 3,
      pay_m: 2,
      gift_stock_total: 4,
      items: [
        { role: "anchor", item_kind: "product", ref_id: LISTING, qty: 1 },
        { role: "eligible", item_kind: "product", ref_id: LISTING, qty: 1 },
      ],
    });
    expect(payload.title).toBe("Kit");
    expect(payload.addon_percent_off).toBe(75);
    expect(payload).not.toHaveProperty("bundle_price_ngwee");
    expect(payload).not.toHaveProperty("buy_n");
    expect(payload).not.toHaveProperty("gift_stock_total");
    expect(payload.items.map((item) => item.role)).toEqual(["anchor"]);
  });

  it("fixed bundle price drops the percent", () => {
    const payload = payloadForType({
      offer_type: "bundle",
      title: "Trio",
      status: "active",
      bundle_pricing: "fixed_price",
      addon_percent_off: 20,
      bundle_price_ngwee: 50_000,
      items: [],
    });
    expect(payload.bundle_price_ngwee).toBe(50_000);
    expect(payload).not.toHaveProperty("addon_percent_off");
  });

  it("gift offers keep the gift stock and only product rewards", () => {
    expect(TYPE_ROLES.free_gift.find((spec) => spec.role === "reward")?.kinds).toEqual(["product"]);
    expect(TYPE_ROLES.bxgy.find((spec) => spec.role === "trigger")?.kinds).toEqual([
      "product",
      "service",
      "event",
    ]);
    const payload = payloadForType({
      offer_type: "free_gift",
      title: "Gift",
      status: "active",
      gift_stock_total: 10,
      buy_qty: 2,
      items: [],
    });
    expect(payload.gift_stock_total).toBe(10);
    expect(payload).not.toHaveProperty("buy_qty");
  });
});

describe("datetime-local round trip", () => {
  it("converts browser-local input to an ISO instant and back", () => {
    const iso = localInputToIso("2026-12-01T09:30");
    expect(iso).not.toBeNull();
    expect(isoToLocalInput(iso)).toBe("2026-12-01T09:30");
    expect(localInputToIso("")).toBeNull();
    expect(isoToLocalInput(null)).toBe("");
  });
});

describe("parsePerCustomerLimit", () => {
  it("treats blank as unlimited", () => {
    expect(parsePerCustomerLimit("")).toBeNull();
    expect(parsePerCustomerLimit("   ")).toBeNull();
  });

  it("accepts whole numbers from 1 to 1000", () => {
    expect(parsePerCustomerLimit("1")).toBe(1);
    expect(parsePerCustomerLimit(" 25 ")).toBe(25);
    expect(parsePerCustomerLimit(String(MAX_PER_CUSTOMER_LIMIT))).toBe(1000);
  });

  it("rejects zero, negatives, decimals, text and values above the cap", () => {
    for (const raw of ["0", "-1", "1.5", "abc", "1001", "1e3"]) {
      expect(parsePerCustomerLimit(raw)).toBe("invalid");
    }
  });

  it("is sent with the payload for every offer type", () => {
    const payload = payloadForType({
      offer_type: "buy_n_pay_m",
      title: "3 for 2",
      status: "active",
      buy_n: 3,
      pay_m: 2,
      per_customer_limit: 2,
      items: [],
    });
    expect(payload.per_customer_limit).toBe(2);
    expect(
      payloadForType({ offer_type: "free_gift", title: "x", status: "draft", items: [] })
        .per_customer_limit,
    ).toBeNull();
  });
});
