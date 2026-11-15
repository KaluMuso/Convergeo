import { describe, expect, it } from "vitest";

import { parsePayoutsEnabled } from "./payout-posture";

describe("parsePayoutsEnabled", () => {
  it("fails closed", () => {
    expect(parsePayoutsEnabled(undefined)).toBe(false);
    expect(parsePayoutsEnabled("")).toBe(false);
    expect(parsePayoutsEnabled("false")).toBe(false);
    expect(parsePayoutsEnabled("0")).toBe(false);
  });
  it("accepts explicit truthy values", () => {
    expect(parsePayoutsEnabled("true")).toBe(true);
    expect(parsePayoutsEnabled(" ON ")).toBe(true);
  });
});
