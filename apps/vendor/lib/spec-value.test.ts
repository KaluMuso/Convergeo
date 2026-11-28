import { describe, expect, it } from "vitest";

import { formatSpecValue } from "./spec-value";

describe("formatSpecValue", () => {
  it("keeps primitives readable", () => {
    expect(formatSpecValue("128GB")).toBe("128GB");
    expect(formatSpecValue(6.1)).toBe("6.1");
    expect(formatSpecValue(null)).toBe("");
    expect(formatSpecValue(undefined)).toBe("");
  });

  it("flattens arrays and objects instead of printing [object Object]", () => {
    expect(formatSpecValue(["red", "blue"])).toBe("red, blue");
    expect(formatSpecValue({ w: 10, h: [1, 2] })).toBe("w: 10, h: 1, 2");
    expect(formatSpecValue([{ a: 1 }])).not.toContain("[object Object]");
  });
});
