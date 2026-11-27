import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("./api-route-probe", () => ({
  // Never resolves: a hung API must not hold up the page.
  probeApiRoute: () => new Promise<boolean>(() => undefined),
}));
vi.mock("./route-capabilities", () => ({
  isClipsRouteAccessible: async () => true,
  isIntakeRouteAccessible: async () => true,
  isBundlesRouteAccessible: async () => true,
  isCouponsRouteAccessible: async () => true,
}));

import { NAV_CAPABILITIES_BUDGET_MS, resolveVendorNavCapabilities } from "./nav-capabilities";

afterEach(() => {
  vi.useRealTimers();
});

describe("resolveVendorNavCapabilities budget", () => {
  it("serves the core nav once the budget elapses instead of waiting on a hung probe", async () => {
    vi.useFakeTimers();
    const pending = resolveVendorNavCapabilities();
    await vi.advanceTimersByTimeAsync(NAV_CAPABILITIES_BUDGET_MS + 1);
    const caps = await pending;
    expect(caps.profile).toBe(true);
    expect(caps.extras).toBe(true);
    // Optional entries fail closed.
    expect(caps.rfq).toBe(false);
    expect(caps.clips).toBe(false);
  });
});
