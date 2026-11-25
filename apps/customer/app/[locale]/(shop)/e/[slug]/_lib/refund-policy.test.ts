import { describe, expect, it } from "vitest";

import { refundPolicyMessageKey } from "./refund-policy";

describe("refundPolicyMessageKey", () => {
  it("maps known keys", () => {
    expect(refundPolicyMessageKey("no_refunds")).toBe("no_refunds");
  });

  it("falls back for unknown keys", () => {
    expect(refundPolicyMessageKey("custom_policy")).toBe("unknown");
  });

  it("falls back when empty", () => {
    expect(refundPolicyMessageKey(null)).toBe("unknown");
  });
});
