import { describe, expect, it } from "vitest";

import { advanceDebtsPath } from "./api";
import { kwachaToNgwee, REPAYMENT_REFERENCE_PATTERN } from "./money";

describe("kwachaToNgwee", () => {
  it("converts kwacha strings to integer ngwee", () => {
    expect(kwachaToNgwee("450")).toBe(45_000);
    expect(kwachaToNgwee("1,234.56")).toBe(123_456);
    expect(kwachaToNgwee("0.1")).toBe(10);
    expect(kwachaToNgwee("0.07")).toBe(7);
  });

  it("rejects zero, negatives, extra decimals and junk", () => {
    for (const bad of ["", "0", "0.00", "-5", "1.234", "abc", "1e3", "12.3.4"]) {
      expect(kwachaToNgwee(bad)).toBeNull();
    }
  });
});

describe("repayment reference", () => {
  it("matches the API charset", () => {
    expect(REPAYMENT_REFERENCE_PATTERN.test("MTN.Momo-0091")).toBe(true);
    expect(REPAYMENT_REFERENCE_PATTERN.test("x")).toBe(false);
    expect(REPAYMENT_REFERENCE_PATTERN.test("bank 1")).toBe(false);
  });
});

describe("advanceDebtsPath", () => {
  it("adds only the filters that are set", () => {
    expect(advanceDebtsPath({})).toBe("/admin/event-advance-debts");
    expect(advanceDebtsPath({ status: "open", vendorId: " abc " })).toBe(
      "/admin/event-advance-debts?status=open&vendor_id=abc",
    );
    expect(advanceDebtsPath({ status: "" })).toBe("/admin/event-advance-debts");
  });
});
