import { ApiError } from "@vergeo/config";
import { describe, expect, it, vi } from "vitest";

import {
  decisionFailureReference,
  isTransientDecisionFailure,
  withDecisionRetry,
} from "./decision-retry";

describe("withDecisionRetry", () => {
  it("retries once after an expired-token 401 and refreshes first", async () => {
    const calls: string[] = [];
    const action = vi
      .fn<() => Promise<string>>()
      .mockImplementationOnce(async () => {
        calls.push("first");
        throw new ApiError("unauthorized", "expired", { status: 401 });
      })
      .mockImplementationOnce(async () => {
        calls.push("second");
        return "ok";
      });
    const beforeRetry = vi.fn(async () => {
      calls.push("refresh");
    });
    await expect(withDecisionRetry(action, { beforeRetry, delayMs: 0 })).resolves.toBe("ok");
    expect(calls).toEqual(["first", "refresh", "second"]);
  });

  it("retries a dropped connection once, then surfaces the second failure", async () => {
    const action = vi.fn(async () => {
      throw new ApiError("network_error", "down", { status: 0 });
    });
    await expect(withDecisionRetry(action, { delayMs: 0 })).rejects.toMatchObject({ status: 0 });
    expect(action).toHaveBeenCalledTimes(2);
  });

  it("does not retry a definitive refusal", async () => {
    const action = vi.fn(async () => {
      throw new ApiError("forbidden", "no", { status: 403 });
    });
    await expect(withDecisionRetry(action, { delayMs: 0 })).rejects.toMatchObject({ status: 403 });
    expect(action).toHaveBeenCalledTimes(1);
  });

  it("still retries when the token refresh itself fails", async () => {
    const action = vi
      .fn<() => Promise<string>>()
      .mockRejectedValueOnce(new ApiError("unauthorized", "x", { status: 401 }))
      .mockResolvedValueOnce("ok");
    await expect(
      withDecisionRetry(action, {
        delayMs: 0,
        beforeRetry: async () => {
          throw new Error("refresh failed");
        },
      }),
    ).resolves.toBe("ok");
  });
});

describe("failure helpers", () => {
  it("classifies transient statuses and non-API errors", () => {
    expect(isTransientDecisionFailure(new ApiError("x", "x", { status: 503 }))).toBe(true);
    expect(isTransientDecisionFailure(new ApiError("x", "x", { status: 422 }))).toBe(false);
    expect(isTransientDecisionFailure(new Error("boom"))).toBe(false);
  });

  it("reads the request id only when the API supplied one", () => {
    expect(decisionFailureReference(new ApiError("x", "x", { requestId: "req_1" }))).toBe("req_1");
    expect(decisionFailureReference(new ApiError("x", "x"))).toBeNull();
    expect(decisionFailureReference(new Error("x"))).toBeNull();
  });
});
