import { ApiError } from "@vergeo/config";
import { describe, expect, it } from "vitest";

import { branchErrorKey, tooCloseValues } from "./branch-errors";

describe("branchErrorKey", () => {
  it("maps known API message keys to vendor copy", () => {
    const error = new ApiError("conflict", "x", {
      status: 409,
      details: { message_key: "vendor.branches.errors.payoutTaken" },
    });
    expect(branchErrorKey(error)).toBe("branches.errors.payoutTaken");
  });

  it("never echoes an unknown key from the server", () => {
    const error = new ApiError("conflict", "x", {
      status: 409,
      details: { message_key: "vendor.branches.errors.<script>" },
    });
    expect(branchErrorKey(error)).toBe("branches.errors.generic");
  });

  it("falls back by status", () => {
    expect(branchErrorKey(new ApiError("rate", "x", { status: 429 }))).toBe(
      "branches.errors.rateLimited",
    );
    expect(branchErrorKey(new ApiError("v", "x", { status: 422 }))).toBe(
      "branches.errors.validation",
    );
    expect(branchErrorKey(new Error("boom"))).toBe("branches.errors.generic");
  });

  it("reads the too-close distances", () => {
    const error = new ApiError("v", "x", {
      status: 422,
      details: { message_key: "vendor.branches.errors.tooClose", min_m: 50, nearest_m: 12 },
    });
    expect(tooCloseValues(error)).toEqual({ min: 50, nearest: 12 });
    expect(tooCloseValues(new Error("x"))).toBeNull();
  });
});
