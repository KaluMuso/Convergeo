import { describe, expect, it } from "vitest";

import { progressPercent } from "./rewards-api";

describe("progressPercent", () => {
  it("floors toward the next threshold", () => {
    expect(progressPercent(460, 500)).toBe(92);
  });
  it("clamps to 0..100", () => {
    expect(progressPercent(-20, 500)).toBe(0);
    expect(progressPercent(900, 500)).toBe(100);
    expect(progressPercent(10, 0)).toBe(0);
  });
});
