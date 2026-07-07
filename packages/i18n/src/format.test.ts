import { describe, expect, it } from "vitest";

import { formatK } from "./format";

describe("formatK", () => {
  it("formats zero", () => {
    expect(formatK(0)).toBe("K0.00");
  });

  it("formats positive ngwee with grouping", () => {
    expect(formatK(123456)).toBe("K1,234.56");
  });

  it("formats negative ngwee", () => {
    expect(formatK(-500)).toBe("-K5.00");
  });

  it("formats one kwacha", () => {
    expect(formatK(100)).toBe("K1.00");
  });

  it("formats large values without float drift", () => {
    expect(formatK(999999999)).toBe("K9,999,999.99");
  });
});
