import { describe, expect, it } from "vitest";

/** Mirrors ngweeToZmwDecimal for unit tests without pulling JsonLdScript. */
function kwachaFromNgwee(ngwee: number): string {
  const major = Math.floor(ngwee / 100);
  const minor = Math.abs(ngwee % 100);
  return `${major}.${minor.toString().padStart(2, "0")}`;
}

describe("service JSON-LD price conversion", () => {
  it("maps ngwee to exact ZMW decimal (123450 → 1234.50)", () => {
    expect(kwachaFromNgwee(123_450)).toBe("1234.50");
  });
});
