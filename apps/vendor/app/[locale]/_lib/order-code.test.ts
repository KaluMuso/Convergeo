import { describe, expect, it } from "vitest";

import { formatOrderCode } from "./order-code";

describe("formatOrderCode", () => {
  it("returns the first eight characters in uppercase", () => {
    expect(formatOrderCode("a1b2c3d4-e5f6-7890-abcd-ef1234567890")).toBe("A1B2C3D4");
  });

  it("uppercases short prefixes", () => {
    expect(formatOrderCode("ord-xy12")).toBe("ORD-XY12");
  });
});
