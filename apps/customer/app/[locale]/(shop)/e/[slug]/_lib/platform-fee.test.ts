import { describe, expect, it } from "vitest";

import { buyerPlatformFeeNgwee, parsePlatformFeeBps } from "./platform-fee";

describe("platform fee", () => {
  it("floors like the server for the API-provided bps", () => {
    expect(buyerPlatformFeeNgwee(10_000, 500)).toBe(500);
    expect(buyerPlatformFeeNgwee(12_345, 500)).toBe(617); // 617.25 -> 617
    expect(buyerPlatformFeeNgwee(12_345, 750)).toBe(925); // follows a changed rate
  });

  it("is zero for empty lines or a zero rate", () => {
    expect(buyerPlatformFeeNgwee(0, 500)).toBe(0);
    expect(buyerPlatformFeeNgwee(10_000, 0)).toBe(0);
  });

  it("rejects missing or invalid bps instead of guessing", () => {
    expect(parsePlatformFeeBps(undefined)).toBeNull();
    expect(parsePlatformFeeBps(5.5)).toBeNull();
    expect(parsePlatformFeeBps(-1)).toBeNull();
    expect(parsePlatformFeeBps(20_000)).toBeNull();
    expect(parsePlatformFeeBps(500)).toBe(500);
  });
});
