import { ApiError } from "@vergeo/config";
import { describe, expect, it } from "vitest";

import { resolveQueueLoadFailure } from "./queue-load-failure";

describe("resolveQueueLoadFailure", () => {
  it("marks 401/403 as permission-denied", () => {
    expect(
      resolveQueueLoadFailure(new ApiError("unauthorized", "no", { status: 401 })),
    ).toEqual({ permissionDenied: true, messageKey: "permissionDenied" });
    expect(resolveQueueLoadFailure(new ApiError("forbidden", "no", { status: 403 }))).toEqual({
      permissionDenied: true,
      messageKey: "permissionDenied",
    });
  });

  it("marks retryable failures as generic error", () => {
    expect(resolveQueueLoadFailure(new ApiError("boom", "no", { status: 500 }))).toEqual({
      permissionDenied: false,
      messageKey: "error",
    });
    expect(resolveQueueLoadFailure(new Error("network"))).toEqual({
      permissionDenied: false,
      messageKey: "error",
    });
  });
});
