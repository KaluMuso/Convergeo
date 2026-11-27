import { beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  flagRows: [] as Array<{ flag: string; enabled: boolean }>,
  flagError: null as unknown,
  flagQueries: 0,
  user: { id: "user-1" } as { id: string } | null,
  vendorId: "vendor-1" as string | null,
  allowlist: JSON.stringify(["vendor-1"]) as unknown,
}));

vi.mock("next/headers", () => ({ cookies: async () => ({}) }));
vi.mock("@vergeo/auth/server-client", () => ({
  createServerClient: () => ({
    auth: { getUser: async () => ({ data: { user: mocks.user } }) },
    from: (table: string) => {
      if (table === "feature_flags") {
        return {
          select: () => ({
            in: async () => {
              mocks.flagQueries += 1;
              return mocks.flagError
                ? { data: null, error: mocks.flagError }
                : { data: mocks.flagRows, error: null };
            },
          }),
        };
      }
      if (table === "vendors") {
        return {
          select: () => ({
            eq: () => ({
              maybeSingle: async () => ({ data: mocks.vendorId ? { id: mocks.vendorId } : null }),
            }),
          }),
        };
      }
      return {
        select: () => ({
          eq: () => ({ maybeSingle: async () => ({ data: { value: mocks.allowlist } }) }),
        }),
      };
    },
  }),
}));

import {
  FLAG_CACHE_TTL_MS,
  isBundlesRouteAccessible,
  isClipsRouteAccessible,
  isCouponsRouteAccessible,
  isIntakeRouteAccessible,
  resetCapabilityFlagCache,
} from "./route-capabilities";

beforeEach(() => {
  vi.useRealTimers();
  resetCapabilityFlagCache();
  mocks.flagQueries = 0;
  mocks.flagError = null;
  mocks.flagRows = [
    { flag: "clips", enabled: true },
    { flag: "bundles", enabled: false },
    { flag: "coupons", enabled: true },
    { flag: "waha_vendor_intake", enabled: true },
  ];
  mocks.user = { id: "user-1" };
  mocks.vendorId = "vendor-1";
  mocks.allowlist = JSON.stringify(["vendor-1"]);
});

describe("route capability flags", () => {
  it("answers all four flags from one batched query", async () => {
    const results = await Promise.all([
      isClipsRouteAccessible(),
      isBundlesRouteAccessible(),
      isCouponsRouteAccessible(),
      isIntakeRouteAccessible(),
    ]);
    expect(results).toEqual([true, false, true, true]);
    expect(mocks.flagQueries).toBe(1);
  });

  it("reuses the result across requests until the TTL elapses", async () => {
    vi.useFakeTimers();
    await isClipsRouteAccessible();
    await isCouponsRouteAccessible();
    expect(mocks.flagQueries).toBe(1);
    mocks.flagRows = [{ flag: "clips", enabled: false }];
    vi.advanceTimersByTime(FLAG_CACHE_TTL_MS + 1);
    expect(await isClipsRouteAccessible()).toBe(false);
    expect(mocks.flagQueries).toBe(2);
  });

  it("treats a missing flag row as off", async () => {
    mocks.flagRows = [];
    expect(await isClipsRouteAccessible()).toBe(false);
  });

  it("fails closed on a query error and does not cache the failure", async () => {
    mocks.flagError = new Error("boom");
    expect(await isClipsRouteAccessible()).toBe(false);
    mocks.flagError = null;
    expect(await isClipsRouteAccessible()).toBe(true);
    expect(mocks.flagQueries).toBe(2);
  });
});

describe("intake access", () => {
  it("stays per-vendor even though the flag is cached", async () => {
    expect(await isIntakeRouteAccessible()).toBe(true);
    mocks.vendorId = "vendor-2";
    expect(await isIntakeRouteAccessible()).toBe(false);
    expect(mocks.flagQueries).toBe(1);
  });

  it("is closed when the flag is off, the vendor is unknown or the allowlist is empty", async () => {
    mocks.flagRows = [{ flag: "waha_vendor_intake", enabled: false }];
    expect(await isIntakeRouteAccessible()).toBe(false);

    resetCapabilityFlagCache();
    mocks.flagRows = [{ flag: "waha_vendor_intake", enabled: true }];
    mocks.vendorId = null;
    expect(await isIntakeRouteAccessible()).toBe(false);

    mocks.vendorId = "vendor-1";
    mocks.allowlist = "[]";
    expect(await isIntakeRouteAccessible()).toBe(false);
  });
});
