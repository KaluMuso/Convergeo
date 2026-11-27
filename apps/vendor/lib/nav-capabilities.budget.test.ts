import { afterEach, describe, expect, it, vi } from "vitest";

const probe = vi.hoisted(() => ({ hang: true }));
vi.mock("./api-route-probe", () => ({
  // Hangs by default: a slow API must not hold up the page.
  probeApiRoute: () => (probe.hang ? new Promise<boolean>(() => undefined) : Promise.resolve(true)),
}));
vi.mock("./route-capabilities", () => ({
  isClipsRouteAccessible: async () => true,
  isIntakeRouteAccessible: async () => true,
  isBundlesRouteAccessible: async () => true,
  isCouponsRouteAccessible: async () => true,
}));

import {
  NAV_CAPABILITIES_BUDGET_MS,
  resetLastResolvedCapabilities,
  resolveVendorNavCapabilities,
} from "./nav-capabilities";

afterEach(() => {
  vi.useRealTimers();
  probe.hang = true;
  resetLastResolvedCapabilities();
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

  it("reuses the last resolved nav when a later probe is slow, except per-vendor intake", async () => {
    probe.hang = false;
    const first = await resolveVendorNavCapabilities();
    expect(first.rfq).toBe(true);
    expect(first.intake).toBe(true);

    probe.hang = true;
    vi.useFakeTimers();
    const pending = resolveVendorNavCapabilities();
    await vi.advanceTimersByTimeAsync(NAV_CAPABILITIES_BUDGET_MS + 1);
    const slow = await pending;
    expect(slow.rfq).toBe(true);
    expect(slow.payouts).toBe(true);
    expect(slow.intake).toBe(false);
  });
});
