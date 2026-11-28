import { describe, expect, it } from "vitest";

import { EMPTY_DRAFT, canQuote, draftTotal, quoteBody, statusActions } from "./api";

const FILLED = {
  ...EMPTY_DRAFT,
  product: "7000",
  freight: "1,500",
  duty: "1200.50",
  clearing: "300",
};

describe("import request quote helpers", () => {
  it("totals the four lines plus other in integer ngwee", () => {
    expect(draftTotal(FILLED)).toBe(700000 + 150000 + 120050 + 30000);
    expect(draftTotal({ ...FILLED, other: "10" })).toBe(700000 + 150000 + 120050 + 30000 + 1000);
  });

  it("rejects a missing or invalid line", () => {
    expect(draftTotal({ ...FILLED, freight: "" })).toBeNull();
    expect(draftTotal({ ...FILLED, duty: "1.005" })).toBeNull();
    expect(quoteBody({ ...FILLED, clearing: "abc" })).toBeNull();
  });

  it("builds an ngwee-only body with optional fields", () => {
    expect(
      quoteBody({
        ...FILLED,
        partner: " P ",
        leadTime: "30",
        validUntil: "2026-12-31",
      }),
    ).toEqual({
      product_ngwee: 700000,
      freight_ngwee: 150000,
      duty_ngwee: 120050,
      clearing_ngwee: 30000,
      other_ngwee: 0,
      partner_label: "P",
      lead_time_days: 30,
      valid_until: "2026-12-31T23:59:59+02:00",
    });
    expect(quoteBody({ ...FILLED, leadTime: "0" })).toBeNull();
    expect(quoteBody({ ...FILLED, validUntil: "tomorrow" })).toBeNull();
  });

  it("mirrors the api state machine", () => {
    expect(statusActions("submitted")).toEqual(["in_review", "closed"]);
    expect(statusActions("closed")).toEqual([]);
    expect(statusActions("cancelled")).toEqual([]);
    expect(canQuote("closed")).toBe(false);
    expect(canQuote("quoted")).toBe(true);
  });
});
