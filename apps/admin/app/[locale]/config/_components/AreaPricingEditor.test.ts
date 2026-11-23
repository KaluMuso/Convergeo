import { describe, expect, it, vi } from "vitest";

vi.mock("@vergeo/ui/src/toast", () => ({ emitToastKey: vi.fn() }));
vi.mock("./api", () => ({ configApi: { request: vi.fn() } }));

import { isRoadKm, toWholeNumber } from "./AreaPricingEditor";

describe("area pricing editor input guards", () => {
  it("accepts only whole numbers for ngwee and basis points", () => {
    expect(toWholeNumber("1300")).toBe(1300);
    expect(toWholeNumber(" 400 ")).toBe(400);
    expect(toWholeNumber("400.5")).toBeNull();
    expect(toWholeNumber("-1")).toBeNull();
    expect(toWholeNumber("1e3")).toBeNull();
    expect(toWholeNumber("")).toBeNull();
  });

  it("keeps road km as a decimal string with at most two places", () => {
    expect(isRoadKm("3.15")).toBe(true);
    expect(isRoadKm("12")).toBe(true);
    expect(isRoadKm("3.155")).toBe(false);
    expect(isRoadKm("1000")).toBe(false);
    expect(isRoadKm("abc")).toBe(false);
  });
});
